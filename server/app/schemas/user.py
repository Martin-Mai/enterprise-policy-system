"""
用户数据模式模块
定义请求和响应的 Pydantic 模型
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    """用户注册请求模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名，3-50个字符")
    password: str = Field(..., min_length=6, max_length=128, description="密码，至少6个字符")


class UserLogin(BaseModel):
    """用户登录请求模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """登录成功后的令牌响应模型"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")


class UserResponse(BaseModel):
    """用户信息响应模型（不含密码）"""
    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    role: str = Field(..., description="用户角色")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True
