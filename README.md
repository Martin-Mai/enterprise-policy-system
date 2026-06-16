# Enterprise Policy System — 企业受控知识库系统

企业内部 HR/行政制度文档的本地化 RAG 问答系统，支持引用溯源、全链路审计与 RBAC 权限管控。数据与模型均可部署在内网环境，满足企业对合规、可追溯与权限隔离的要求。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11、FastAPI、SQLAlchemy、LangChain Text Splitters |
| 检索 | ChromaDB（语义向量）、rank-bm25 + jieba（关键词） |
| 大模型 | Ollama（`qwen2.5:7b` 对话 + `nomic-embed-text` 向量化） |
| 数据库 | MySQL 8.0 |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia |
| 部署 | Docker Compose、Nginx、Gunicorn + Uvicorn |

## 核心功能

- **文档入库流水线**：支持 PDF / Markdown 上传；按页或按标题切分，配合固定长度递归分块；元数据与分块双写 MySQL + ChromaDB；文档变更后热刷新 BM25 内存索引。
- **混合检索**：ChromaDB 语义召回与 BM25 关键词召回并行，经加权 RRF（Reciprocal Rank Fusion）融合，提升制度条款类问题的命中率。
- **RAG 流式问答**：通过 SSE 对接 Ollama 流式生成；强约束 Prompt 要求模型基于检索上下文作答；引用编号 `[n]` 逆向映射至原文档页码与章节。
- **合规与审计**：数值幻觉防护协议、全链路审计日志落库（检索、生成、引用解析等关键步骤均可追溯）。
- **权限与管理后台**：JWT 认证 + RBAC（`admin` / `user`）；文档管理、审计日志查询、运营仪表盘、用户反馈处理。
- **容器化部署**：Docker Compose 一键编排 MySQL、后端与前端；Ollama 运行于宿主机，容器经 `host.docker.internal` 调用。

## 功能预览

### 1. Login

![Login](product-display-img/Login.jpg)

### 2. Chatting

![Chatting](product-display-img/Chatting.jpg)

### 3. Dashboard

![Dashboard](product-display-img/Dashboard.jpg)

### 4. Document Management

![Document Management](product-display-img/Document-Management.jpg)

### 5. Audit Logs

![Audit Logs](product-display-img/Audit-Logs.jpg)

### 6. Feedback Centre

![Feedback Centre](product-display-img/Feedback-Centre.jpg)

## 架构亮点

```
┌─────────────┐     SSE / REST      ┌──────────────┐
│  Vue3 前端   │ ◄─────────────────► │  FastAPI 后端 │
│  (Nginx)    │                     │              │
└─────────────┘                     └──────┬───────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
        ┌──────────┐               ┌─────────────┐              ┌─────────────┐
        │  MySQL   │               │  ChromaDB   │              │   Ollama    │
        │ 元数据/   │               │  向量索引    │              │  宿主机 LLM  │
        │ 分块/BM25│               │             │              │  + Embedding │
        └──────────┘               └─────────────┘              └─────────────┘
```

- **双存储一致性**：MySQL 保存文档、分块与审计记录；ChromaDB 保存向量；分块 ID 在两侧对齐，便于删除、重建与引用回溯。
- **启动即建索引**：应用启动时从 MySQL 全量加载分块，构建 BM25 内存索引，与向量检索互补。
- **Nginx SSE 透传**：生产环境前端经 Nginx 反向代理 `/api`，关闭缓冲并延长超时，保障流式 token 实时推送。
- **角色隔离**：普通用户仅可使用问答与文档检索；管理员可访问 `/admin` 下的仪表盘、文档、审计与反馈模块。

## 项目结构

```
enterprise-policy-system/
├── client/                    # Vue 3 前端源码
│   ├── src/
│   │   ├── api/               # Axios 接口封装
│   │   ├── components/        # 聊天、引用、输入等组件
│   │   ├── views/             # 登录、问答、管理后台页面
│   │   ├── stores/            # Pinia 状态（auth、chat）
│   │   └── router/            # 路由与 RBAC 守卫
│   └── package.json
├── server/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/               # REST / SSE 路由
│   │   ├── core/              # 配置、数据库、安全、迁移
│   │   ├── models/            # SQLAlchemy ORM 模型
│   │   ├── schemas/           # Pydantic 请求/响应模型
│   │   └── services/          # 文档处理、检索、LLM、聊天业务
│   ├── migrations/            # SQL 增量迁移脚本
│   ├── scripts/               # 运维脚本（如 Chroma ID 迁移）
│   ├── storage/               # 上传文档存储（运行时生成）
│   └── requirements.txt
├── backend/                   # 后端 Docker 构建文件
├── frontend/                  # 前端 Docker 构建与 Nginx 配置
├── chroma_data/               # ChromaDB 持久化（运行时生成）
├── docker-compose.yml         # 一键编排 MySQL + backend + frontend
├── .env.example               # Docker 部署环境变量模板
└── LICENSE                    # MIT License
```

## 快速开始

### 前置条件

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（含 Docker Compose）
- [Ollama](https://ollama.com/) 已安装并运行在**宿主机**（默认端口 `11434`）

拉取所需模型：

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### Docker 一键启动

在项目根目录执行：

```powershell
# 1. 复制并编辑环境变量
copy .env.example .env
# 修改 MYSQL_PASSWORD、JWT_SECRET、SECRET_KEY 等为强密码

# 2. 构建并启动全部服务
docker compose up -d --build

# 3. 查看运行状态
docker compose ps
```

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:8080 | Vue 应用（Nginx 托管） |
| 后端 API | http://localhost:8000 | FastAPI，Swagger 文档见 `/docs` |
| MySQL | localhost:3307 | 容器内 3306，映射至宿主机 3307 |

停止并移除容器：

```bash
docker compose down
```

> **注意**：Ollama 不在 Docker 内运行。后端容器通过 `host.docker.internal:11434` 访问 Windows/macOS 宿主机上的 Ollama；请勿将 Ollama 地址改为 `localhost`（在容器内无效）。

### 本地开发（可选）

**后端**（`server/` 目录）：

```bash
cd server
copy .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**前端**（`client/` 目录）：

```bash
cd client
npm install
npm run dev
```

开发环境前端默认连接 `http://localhost:8000`（见 `client/.env.development`），Vite 开发服务器端口为 `5173`。

### 环境变量

**根目录 `.env`（Docker Compose 部署）**

| 变量 | 说明 | 示例 |
|------|------|------|
| `MYSQL_PASSWORD` | MySQL root 密码 | 强密码 |
| `DATABASE_URL` | 容器内数据库连接串 | `mysql+pymysql://root:密码@mysql:3306/enterprise_kb` |
| `JWT_SECRET` | JWT 签名密钥（注入后端 `SECRET_KEY`） | 随机强字符串 |
| `SECRET_KEY` | 与 `JWT_SECRET` 保持一致 | 随机强字符串 |
| `CHROMA_PERSIST_DIRECTORY` | ChromaDB 持久化路径（容器内） | `/app/chroma_data` |
| `OLLAMA_EMBEDDING_URL` | Ollama Embedding API | `http://host.docker.internal:11434/api/embeddings` |
| `OLLAMA_GENERATE_URL` | Ollama Generate API | `http://host.docker.internal:11434/api/generate` |
| `OLLAMA_EMBEDDING_MODEL` | 向量化模型 | `nomic-embed-text` |
| `OLLAMA_CHAT_MODEL` | 对话模型 | `qwen2.5:7b` |
| `OLLAMA_GENERATE_TIMEOUT` | 流式生成超时（秒） | `300` |

**`server/.env`（本地后端开发）**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 本地 MySQL 连接串 | `mysql+pymysql://root:root@127.0.0.1:3306/enterprise_kb` |
| `SECRET_KEY` | JWT 签名密钥 | 需自行修改 |
| `ALGORITHM` | JWT 算法 | `HS256` |
| `ACCESS_TOKEN_EXPIRE_DAYS` | Token 有效期（天） | `7` |
| `CHROMA_COLLECTION_NAME` | ChromaDB 集合名 | `enterprise_docs` |
| `MAX_UPLOAD_SIZE` | 上传大小上限（字节） | `10485760`（10MB） |

持久化目录（Docker 卷挂载）：

- `./chroma_data` — 向量库数据
- `./server/storage` — 上传的原始文档

## API 概览

完整交互式文档：启动后端后访问 [http://localhost:8000/docs](http://localhost:8000/docs)。

| 模块 | 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|------|
| 健康检查 | GET | `/` | 服务状态 | 公开 |
| 认证 | POST | `/api/auth/register` | 用户注册 | 公开 |
| 认证 | POST | `/api/auth/login` | 登录获取 JWT | 公开 |
| 认证 | GET | `/api/auth/me` | 当前用户信息 | 登录 |
| 文档 | POST | `/api/documents/upload` | 上传 PDF/Markdown | 登录 |
| 文档 | GET | `/api/documents` | 文档列表 | 登录 |
| 文档 | GET | `/api/documents/search` | 混合检索 | 登录 |
| 文档 | POST | `/api/documents/{doc_id}/reprocess` | 重新处理文档 | 登录 |
| 文档 | DELETE | `/api/documents/{doc_id}` | 删除文档 | 登录 |
| 问答 | POST | `/api/chat/stream` | RAG 流式问答（SSE） | 登录 |
| 会话 | GET | `/api/conversations` | 会话列表 | 登录 |
| 会话 | GET | `/api/conversations/{session_id}/messages` | 会话消息 | 登录 |
| 会话 | DELETE | `/api/conversations/{session_id}` | 删除会话 | 登录 |
| 反馈 | POST | `/api/feedback` | 提交消息反馈 | 登录 |
| 反馈 | DELETE | `/api/feedback/{message_id}` | 撤销反馈 | 登录 |
| 管理 | GET | `/api/admin/stats` | 运营统计 | admin |
| 管理 | GET | `/api/admin/hot-documents` | 热门文档 | admin |
| 管理 | GET | `/api/admin/documents` | 文档管理列表 | admin |
| 管理 | DELETE | `/api/admin/documents/{doc_id}` | 删除文档 | admin |
| 管理 | POST | `/api/admin/documents/reindex/{doc_id}` | 重建索引 | admin |
| 管理 | GET | `/api/admin/audit-logs` | 审计日志列表 | admin |
| 管理 | GET | `/api/admin/audit-logs/{log_id}` | 审计详情 | admin |
| 管理 | DELETE | `/api/admin/audit-logs` | 清空审计日志 | admin |
| 管理 | GET | `/api/admin/feedbacks` | 反馈列表 | admin |
| 管理 | PATCH | `/api/admin/feedbacks/{id}/resolve` | 标记反馈已处理 | admin |
| 管理 | GET | `/api/admin/users` | 用户列表 | admin |

除公开接口外，请求头需携带：`Authorization: Bearer <access_token>`。

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
---
# Enterprise Policy System — Enterprise Controlled Knowledge Base

A localized RAG Q&A system for internal HR and administrative policy documents. It supports citation tracing, full-chain audit logging, and RBAC-based access control. Both data and models can run entirely within your intranet to meet compliance, traceability, and permission isolation requirements.

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy, LangChain Text Splitters |
| Retrieval | ChromaDB (semantic vectors), rank-bm25 + jieba (keyword search) |
| LLM | Ollama (`qwen2.5:7b` for chat, `nomic-embed-text` for embeddings) |
| Database | MySQL 8.0 |
| Frontend | Vue 3, TypeScript, Vite, Element Plus, Pinia |
| Deployment | Docker Compose, Nginx, Gunicorn + Uvicorn |

## Core Features

- **Document ingestion pipeline**: Upload PDF/Markdown; split by page or heading with fixed-length recursive chunking; dual-write metadata and chunks to MySQL + ChromaDB; hot-reload BM25 in-memory index on document changes.
- **Hybrid retrieval**: Parallel ChromaDB semantic recall and BM25 keyword recall, fused via weighted RRF (Reciprocal Rank Fusion) for better hit rates on policy-style queries.
- **RAG streaming Q&A**: SSE integration with Ollama streaming generation; strict prompts require answers grounded in retrieved context; citation markers `[n]` reverse-map to source page and section.
- **Compliance & audit**: Numerical hallucination guardrails; full-chain audit logs persisted (retrieval, generation, citation parsing, and other critical steps are traceable).
- **RBAC & admin console**: JWT auth with `admin` / `user` roles; document management, audit log viewer, operations dashboard, and user feedback handling.
- **Containerized deployment**: One-command Docker Compose for MySQL, backend, and frontend; Ollama runs on the host and is reached via `host.docker.internal`.

## Feature Preview

### 1. Login

![Login](product-display-img/Login.jpg)

### 2. Chatting

![Chatting](product-display-img/Chatting.jpg)

### 3. Dashboard

![Dashboard](product-display-img/Dashboard.jpg)

### 4. Document Management

![Document Management](product-display-img/Document-Management.jpg)

### 5. Audit Logs

![Audit Logs](product-display-img/Audit-Logs.jpg)

### 6. Feedback Centre

![Feedback Centre](product-display-img/Feedback-Centre.jpg)

## Architecture Highlights

```
┌─────────────┐     SSE / REST      ┌──────────────┐
│  Vue3 UI    │ ◄─────────────────► │  FastAPI     │
│  (Nginx)    │                     │  Backend     │
└─────────────┘                     └──────┬───────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
        ┌──────────┐               ┌─────────────┐              ┌─────────────┐
        │  MySQL   │               │  ChromaDB   │              │   Ollama    │
        │ metadata │               │  vectors    │              │  host LLM   │
        │ chunks/  │               │             │              │  + embed    │
        │ BM25     │               │             │              │             │
        └──────────┘               └─────────────┘              └─────────────┘
```

- **Dual-store consistency**: MySQL holds documents, chunks, and audit records; ChromaDB holds vectors; aligned chunk IDs enable delete, reindex, and citation lookup.
- **Index at startup**: BM25 in-memory index is built from all MySQL chunks on application startup, complementing vector search.
- **Nginx SSE passthrough**: Production frontend proxies `/api` through Nginx with buffering disabled and extended timeouts for real-time token streaming.
- **Role isolation**: Regular users access chat and document search only; admins access dashboard, documents, audit logs, and feedback under `/admin`.

## Project Structure

```
enterprise-policy-system/
├── client/                    # Vue 3 frontend source
│   ├── src/
│   │   ├── api/               # Axios API clients
│   │   ├── components/        # Chat, citations, input components
│   │   ├── views/             # Login, chat, admin pages
│   │   ├── stores/            # Pinia stores (auth, chat)
│   │   └── router/            # Routes and RBAC guards
│   └── package.json
├── server/                    # FastAPI backend
│   ├── app/
│   │   ├── api/               # REST / SSE routes
│   │   ├── core/              # Config, DB, security, migrations
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic request/response models
│   │   └── services/          # Ingestion, search, LLM, chat logic
│   ├── migrations/            # SQL migration scripts
│   ├── scripts/               # Ops scripts (e.g. Chroma ID migration)
│   ├── storage/               # Uploaded documents (runtime)
│   └── requirements.txt
├── backend/                   # Backend Docker build
├── frontend/                  # Frontend Docker build & Nginx config
├── chroma_data/               # ChromaDB persistence (runtime)
├── docker-compose.yml         # MySQL + backend + frontend orchestration
├── .env.example               # Docker env template
└── LICENSE                    # MIT License
```

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker Compose)
- [Ollama](https://ollama.com/) installed and running on the **host** (default port `11434`)

Pull required models:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### One-Click Docker Launch

From the project root:

```powershell
# 1. Copy and edit environment variables
copy .env.example .env
# Set MYSQL_PASSWORD, JWT_SECRET, SECRET_KEY to strong secrets

# 2. Build and start all services
docker compose up -d --build

# 3. Check status
docker compose ps
```

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:8080 | Vue app (Nginx) |
| Backend API | http://localhost:8000 | FastAPI; Swagger at `/docs` |
| MySQL | localhost:3307 | Container port 3306 mapped to host 3307 |

Stop and remove containers:

```bash
docker compose down
```

> **Note**: Ollama is **not** run inside Docker. The backend container reaches Ollama on the Windows/macOS host via `host.docker.internal:11434`. Do not use `localhost` for Ollama URLs inside containers.

### Local Development (Optional)

**Backend** (`server/`):

```bash
cd server
copy .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend** (`client/`):

```bash
cd client
npm install
npm run dev
```

Dev frontend targets `http://localhost:8000` (see `client/.env.development`); Vite dev server runs on port `5173`.

### Environment Variables

**Root `.env` (Docker Compose)**

| Variable | Description | Example |
|----------|-------------|---------|
| `MYSQL_PASSWORD` | MySQL root password | Strong secret |
| `DATABASE_URL` | DB URL inside Docker network | `mysql+pymysql://root:pass@mysql:3306/enterprise_kb` |
| `JWT_SECRET` | JWT signing key (injected as backend `SECRET_KEY`) | Random strong string |
| `SECRET_KEY` | Same as `JWT_SECRET` | Random strong string |
| `CHROMA_PERSIST_DIRECTORY` | ChromaDB persist path (in container) | `/app/chroma_data` |
| `OLLAMA_EMBEDDING_URL` | Ollama Embedding API | `http://host.docker.internal:11434/api/embeddings` |
| `OLLAMA_GENERATE_URL` | Ollama Generate API | `http://host.docker.internal:11434/api/generate` |
| `OLLAMA_EMBEDDING_MODEL` | Embedding model | `nomic-embed-text` |
| `OLLAMA_CHAT_MODEL` | Chat model | `qwen2.5:7b` |
| `OLLAMA_GENERATE_TIMEOUT` | Streaming timeout (seconds) | `300` |

**`server/.env` (local backend dev)**

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Local MySQL connection string | `mysql+pymysql://root:root@127.0.0.1:3306/enterprise_kb` |
| `SECRET_KEY` | JWT signing key | Change in production |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_DAYS` | Token TTL (days) | `7` |
| `CHROMA_COLLECTION_NAME` | ChromaDB collection name | `enterprise_docs` |
| `MAX_UPLOAD_SIZE` | Max upload size (bytes) | `10485760` (10MB) |

Persisted directories (Docker volume mounts):

- `./chroma_data` — vector store data
- `./server/storage` — uploaded source documents

## API Overview

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs) after starting the backend.

| Module | Method | Path | Description | Access |
|--------|--------|------|-------------|--------|
| Health | GET | `/` | Service status | Public |
| Auth | POST | `/api/auth/register` | Register user | Public |
| Auth | POST | `/api/auth/login` | Login, get JWT | Public |
| Auth | GET | `/api/auth/me` | Current user | Authenticated |
| Documents | POST | `/api/documents/upload` | Upload PDF/Markdown | Authenticated |
| Documents | GET | `/api/documents` | List documents | Authenticated |
| Documents | GET | `/api/documents/search` | Hybrid search | Authenticated |
| Documents | POST | `/api/documents/{doc_id}/reprocess` | Reprocess document | Authenticated |
| Documents | DELETE | `/api/documents/{doc_id}` | Delete document | Authenticated |
| Chat | POST | `/api/chat/stream` | RAG streaming Q&A (SSE) | Authenticated |
| Conversations | GET | `/api/conversations` | List sessions | Authenticated |
| Conversations | GET | `/api/conversations/{session_id}/messages` | Session messages | Authenticated |
| Conversations | DELETE | `/api/conversations/{session_id}` | Delete session | Authenticated |
| Feedback | POST | `/api/feedback` | Submit message feedback | Authenticated |
| Feedback | DELETE | `/api/feedback/{message_id}` | Revoke feedback | Authenticated |
| Admin | GET | `/api/admin/stats` | Operations stats | admin |
| Admin | GET | `/api/admin/hot-documents` | Hot documents | admin |
| Admin | GET | `/api/admin/documents` | Document admin list | admin |
| Admin | DELETE | `/api/admin/documents/{doc_id}` | Delete document | admin |
| Admin | POST | `/api/admin/documents/reindex/{doc_id}` | Rebuild index | admin |
| Admin | GET | `/api/admin/audit-logs` | Audit log list | admin |
| Admin | GET | `/api/admin/audit-logs/{log_id}` | Audit detail | admin |
| Admin | DELETE | `/api/admin/audit-logs` | Clear audit logs | admin |
| Admin | GET | `/api/admin/feedbacks` | Feedback list | admin |
| Admin | PATCH | `/api/admin/feedbacks/{id}/resolve` | Mark feedback resolved | admin |
| Admin | GET | `/api/admin/users` | User list | admin |

Protected endpoints require header: `Authorization: Bearer <access_token>`.

## License

This project is licensed under the [MIT License](LICENSE).
