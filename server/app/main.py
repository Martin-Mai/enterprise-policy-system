"""
FastAPI 应用入口文件
负责创建应用实例、注册路由、初始化数据库表
"""
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


from app.core.database import engine, Base
from app.api import auth, admin

# 导入所有模型，确保 SQLAlchemy 能够识别并创建对应的表
import app.models.user  # noqa: F401

# 在应用启动时自动创建所有数据库表
Base.metadata.create_all(bind=engine)

# 创建 FastAPI 应用实例
app = FastAPI(
    title="企业知识库 - 用户认证与权限系统",
    description="提供用户注册、登录、JWT 认证和 RBAC 权限管理功能",
    version="1.0.0",
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


@app.get("/", tags=["健康检查"])
def root():
    """
    根路径健康检查接口
    用于确认服务是否正常运行
    """
    return {"message": "服务运行正常"}
