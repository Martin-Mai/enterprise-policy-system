"""
FastAPI 应用入口文件
负责创建应用实例、注册路由、初始化数据库表
"""
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


from app.core.config import settings
from app.core.database import engine, Base
from app.api import auth, admin, documents
from app.services.search_service import get_bm25_index

# 配置基础日志，便于后台文档处理任务输出调试信息
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# 导入所有模型，确保 SQLAlchemy 能够识别并创建对应的表
import app.models.user  # noqa: F401
import app.models.document  # noqa: F401

# 启动时自动创建 storage 与 chroma_data 目录
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_DATA_DIR.mkdir(parents=True, exist_ok=True)

# 在应用启动时自动创建所有数据库表
Base.metadata.create_all(bind=engine)

# 创建 FastAPI 应用实例
app = FastAPI(
    title="企业知识库 - 用户认证与权限系统",
    description="提供用户注册、登录、JWT 认证、RBAC 权限管理及文档向量化检索功能",
    version="1.1.0",
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


@app.on_event("startup")
def startup_build_bm25_index() -> None:
    """应用启动时全量加载 MySQL 分块，构建 BM25 内存索引"""
    get_bm25_index()


@app.get("/", tags=["健康检查"])
def root():
    """
    根路径健康检查接口
    用于确认服务是否正常运行
    """
    return {"message": "服务运行正常"}
