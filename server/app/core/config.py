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

    # 文档上传存储目录（相对于 server 根目录）
    STORAGE_DIR: Path = SERVER_DIR / "storage"

    # ChromaDB 向量数据库持久化目录
    CHROMA_DATA_DIR: Path = SERVER_DIR / "chroma_data"

    # ChromaDB 集合名称
    CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "enterprise_docs")

    # Ollama 向量化服务地址
    OLLAMA_EMBEDDING_URL: str = os.getenv(
        "OLLAMA_EMBEDDING_URL",
        "http://localhost:11434/api/embeddings",
    )

    # Ollama 向量化模型名称
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    # Ollama 文本生成接口地址
    OLLAMA_GENERATE_URL: str = os.getenv(
        "OLLAMA_GENERATE_URL",
        "http://localhost:11434/api/generate",
    )

    # Ollama 对话生成模型名称
    OLLAMA_CHAT_MODEL: str = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")

    # Ollama 流式生成超时（秒）
    OLLAMA_GENERATE_TIMEOUT: float = float(os.getenv("OLLAMA_GENERATE_TIMEOUT", "300"))

    # Ollama 向量化请求超时（秒）
    OLLAMA_EMBEDDING_TIMEOUT: float = float(os.getenv("OLLAMA_EMBEDDING_TIMEOUT", "180"))

    # Ollama 模型内存驻留时长（如 30m、-1 表示永久）
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

    # 是否在应用启动后后台预热 Ollama 模型
    OLLAMA_WARMUP_ENABLED: bool = os.getenv("OLLAMA_WARMUP_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # 文档上传大小限制（字节），默认 10MB
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))

    # 文本分块策略：flat（单层）/ parent_child（父子块）
    CHUNK_STRATEGY: str = os.getenv("CHUNK_STRATEGY", "flat")

    # flat 模式分块参数
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

    # parent_child 模式参数
    PARENT_CHUNK_SIZE: int = int(os.getenv("PARENT_CHUNK_SIZE", "1500"))
    CHILD_CHUNK_SIZE: int = int(os.getenv("CHILD_CHUNK_SIZE", "300"))
    CHILD_CHUNK_OVERLAP: int = int(os.getenv("CHILD_CHUNK_OVERLAP", "30"))

    # 检索侧 BM25 索引文本长度上限（默认 800；parent_child 下应 >= CHILD_CHUNK_SIZE）
    SEARCH_MAX_CHUNK_LENGTH: int = int(os.getenv("SEARCH_MAX_CHUNK_LENGTH", "800"))

    # 混合检索粗排每路召回上限
    SEARCH_COARSE_RECALL_LIMIT: int = int(os.getenv("SEARCH_COARSE_RECALL_LIMIT", "30"))

    # Cross-Encoder 精排（transformers 本地加载，非 Ollama）
    RERANK_ENABLED: bool = os.getenv("RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    # auto：有 CUDA 则用 GPU；cuda / cpu 可强制指定
    RERANK_DEVICE: str = os.getenv("RERANK_DEVICE", "auto")
    RERANK_MAX_CHARS: int = int(os.getenv("RERANK_MAX_CHARS", "512"))
    RERANK_MAX_LENGTH: int = int(os.getenv("RERANK_MAX_LENGTH", "512"))

    # RAG 置信度门控（第 4 批 calibrate_thresholds.py 校准，见 eval/outputs/threshold_recommendation.json）
    CONFIDENCE_GATE_ENABLED: bool = os.getenv(
        "CONFIDENCE_GATE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    CONFIDENCE_HIGH_THRESHOLD: float = float(
        os.getenv("CONFIDENCE_HIGH_THRESHOLD", "6.3734")
    )
    CONFIDENCE_LOW_THRESHOLD: float = float(
        os.getenv("CONFIDENCE_LOW_THRESHOLD", "-3.6671")
    )
    CONFIDENCE_SCORE_FIELD: str = os.getenv("CONFIDENCE_SCORE_FIELD", "rerank_score")


# 全局配置单例
settings = Settings()
