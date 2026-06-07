"""
安全模块
提供密码哈希、JWT 令牌生成与解析功能
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# 密码哈希上下文，使用 bcrypt 算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _preprocess_password(password: str) -> str:
    """
    对密码进行预处理，确保符合 bcrypt 的长度限制（最大 72 字节）。
    如果密码长度超过 72 字节，先进行 SHA256 哈希再返回（哈希结果为 64 字节的十六进制字符串）。
    否则返回原始密码。
    """
    if len(password.encode()) > 72:
        return hashlib.sha256(password.encode()).hexdigest()
    return password


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希处理（自动处理超长密码）"""
    password = _preprocess_password(password)
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希值是否匹配（自动处理超长密码）"""
    plain_password = _preprocess_password(plain_password)
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    生成 JWT 访问令牌
    :param data: 要编码到令牌中的数据字典，通常包含 {"sub": username}
    :param expires_delta: 自定义过期时间增量，默认使用配置中的 ACCESS_TOKEN_EXPIRE_DAYS
    :return: 编码后的 JWT 字符串
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    解析 JWT 令牌
    :param token: JWT 字符串
    :return: 解析后的 payload 字典，解析失败则返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None