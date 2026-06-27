FROM python:3.11-slim

# 安装编译工具、cairo 依赖（pycairo 必需）
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    cmake \
    pkg-config \
    libgl1 \
    libglib2.0-0 \
    libstdc++6 \
    libgomp1 \
    libfreetype6 \
    libharfbuzz0b \
    libjpeg62-turbo \
    libopenjp2-7 \
    libtiff6 \
    libcairo2-dev \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /app

COPY server/requirements.txt .

RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn

COPY server/ .

RUN mkdir -p /app/storage /app/chroma_data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "300", "app.main:app"]