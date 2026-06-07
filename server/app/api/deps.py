"""
认证依赖注入模块
提供获取当前用户和管理员权限校验的依赖函数
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

# OAuth2 密码模式，指定令牌获取 URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    获取当前登录用户的依赖函数
    - 从请求头 Authorization: Bearer <token> 中提取令牌
    - 解析 JWT 令牌获取用户名
    - 从数据库查询用户信息
    - 令牌无效或用户不存在时抛出 401 异常
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 解析 JWT 令牌
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    # 从数据库查询用户
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    管理员权限校验依赖函数
    - 依赖 get_current_user 获取当前用户
    - 检查用户角色是否为 'admin'
    - 非管理员抛出 403 禁止访问异常
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user
