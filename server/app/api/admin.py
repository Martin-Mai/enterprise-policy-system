"""
管理员接口路由
包含需要管理员权限才能访问的接口
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse
from app.api.deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["管理员"])


@router.get("/users", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    """
    获取所有用户列表（仅管理员可访问）
    - 通过 require_admin 依赖注入进行管理员权限校验
    - 返回所有用户的列表信息（不含密码）
    """
    users = db.query(User).all()
    return users
