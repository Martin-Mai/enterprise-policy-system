"""
应用配置模块
从 server 文件夹下的 .env 文件中读取环境变量，提供全局配置对象
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 获取 server 文件夹的绝对路径
SERVER_DIR = Path(__file__).resolve().parent.parent.parent
# 加载 server 文件夹下的 .env 文件
load_dotenv(dotenv_path=SERVER_DIR / ".env")


class Settings:
    """应用全局配置类"""

    # 数据库连接字符串，格式：mysql+pymysql://用户名:密码@主机:端口/数据库名
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:root@127.0.0.1:3306/enterprise_kb"
    )

    # JWT 签名密钥，生产环境请使用随机强密码
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

    # JWT 签名算法
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")

    # JWT 令牌过期时间（天）
    ACCESS_TOKEN_EXPIRE_DAYS: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", "7"))


# 全局配置单例
settings = Settings()
