"""
用户数据模型模块
定义 users 表的 ORM 映射
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime

from app.core.database import Base


class User(Base):
    """
    用户表 ORM 模型
    对应数据库中的 users 表
    """
    __tablename__ = "users"

    # 主键，自增整数
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 用户名，唯一且不可为空
    username = Column(String(50), unique=True, index=True, nullable=False, comment="用户名")

    # 密码哈希值，存储 bcrypt 加密后的结果
    password_hash = Column(String(255), nullable=False, comment="密码哈希")

    # 用户角色，默认值为 'user'，可选值：'admin' 或 'user'
    role = Column(String(20), nullable=False, default="user", comment="用户角色：admin/user")

    # 创建时间，默认为当前时间
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
