"""
数据库配置模块
提供 SQLAlchemy 同步引擎和会话管理
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 创建数据库引擎（同步模式，方便调试）
# pool_pre_ping=True 会在每次连接前检测连接是否有效，避免连接池中的死连接
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明式基类，所有 ORM 模型都继承自此类
Base = declarative_base()


def get_db():
    """
    获取数据库会话的依赖函数
    用于 FastAPI 的 Depends() 注入
    使用 try/finally 确保会话在使用后关闭
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
