"""
FastAPI 应用入口文件
负责创建应用实例、注册路由、初始化数据库表
"""
import asyncio
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


from app.core.config import settings
from app.core.database import engine, Base
from app.core.migrations import run_schema_patches
from app.api import auth, admin, documents, chat, feedback, conversations
from app.services.ollama_warmup import get_warmup_status, warmup_ollama_models
from app.services.search_service import get_bm25_index

# 配置基础日志，便于后台文档处理任务输出调试信息
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# 导入所有模型，确保 SQLAlchemy 能够识别并创建对应的表
import app.models.user  # noqa: F401
import app.models.document  # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.message  # noqa: F401
import app.models.audit_log  # noqa: F401
import app.models.feedback  # noqa: F401

# 启动时自动创建 storage 与 chroma_data 目录
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_DATA_DIR.mkdir(parents=True, exist_ok=True)

# 补齐已有表的缺失列（如 documents.status），再 create_all 新表
run_schema_patches(engine)

# 在应用启动时自动创建所有数据库表
Base.metadata.create_all(bind=engine)

# 创建 FastAPI 应用实例
app = FastAPI(
    title="企业知识库 - 用户认证与权限系统",
    description="提供用户注册、登录、JWT 认证、RBAC 权限管理及文档向量化检索功能",
    version="1.1.0",
)

# 允许前端开发服务器跨域访问（含 SSE fetch 流式请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {exc}"},
    )

# 注册路由
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(feedback.router)


@app.on_event("startup")
async def startup_init() -> None:
    """应用启动：构建 BM25 索引，并后台异步预热 Ollama 模型"""
    get_bm25_index()
    asyncio.create_task(warmup_ollama_models())


@app.get("/", tags=["健康检查"])
def root():
    """
    根路径存活探针
    用于确认 HTTP 服务进程是否正常运行
    """
    return {"message": "服务运行正常"}


@app.get("/health/ready", tags=["健康检查"])
def health_ready():
    """
    就绪探针：BM25 已加载且 Ollama warmup 完成（或已跳过）时返回 200
    warmup 进行中或失败时返回 503，便于 Docker/K8s 区分「进程活着」与「推理就绪」
    """
    status = get_warmup_status()
    if status["ollama_ready"]:
        return {"status": "ready", **status}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", **status},
    )
