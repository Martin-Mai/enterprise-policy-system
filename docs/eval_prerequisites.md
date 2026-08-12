# 评测前置环境检查报告

> 检查时间：2026-08-11  
> 项目路径：`c:\2026_Project\enterprise-policy-system`  
> 说明：仅环境检查，不含 eval 脚本实现。

---

## Checklist

| # | 检查项 | 状态 | 备注 |
|---|--------|------|------|
| 1 | `test_datasets/` 9 PDF + 2 MD 齐全 | ✅ 通过 | 11 份测试文档均在 |
| 2 | Server 核心模块可 import | ✅ 通过 | `hybrid_search` / `rerank_service` / `build_rag_prompt` / `stream_ollama_generate` |
| 3 | `server/.env` 存在 | ✅ 通过 | 已加载 |
| 4 | Ollama embedding（`nomic-embed-text`）可用 | ✅ 通过 | API 200，向量维度 768 |
| 5 | Ollama 生成（`qwen2.5:7b`）可用 | ✅ 通过 | `/api/generate` 200 |
| 6 | MySQL 11 份测试文档已入库 | ✅ 通过 | 11 篇 active，共 75 分块 |
| 7 | ChromaDB 向量已写入 | ✅ 通过 | `enterprise_docs` count = 75 |
| 8 | BM25 索引已构建 | ✅ 通过 | 69 条可检索块（6 条因长度过滤跳过，属正常） |
| 9 | Cross-Encoder rerank 运行态 | ✅ 通过（`.venv`） | `server/.venv` 内 `torch 2.13.0+cpu` + `transformers 5.15.0`，`get_reranker()` 正常（CPU） |

**结论：11 份测试文档已全部上传并完成索引，可进入评测阶段。**  
**注意：请始终使用 `server/.venv` 下的 Python**；全局 `python` 无 `torch`，会导致 rerank 误报失败。

---

## 1. 测试数据集

路径：`test_datasets/`

### PDF（9）

| 文件名 | 大小 |
|--------|------|
| `01_financial_audit_2026.pdf` | 84 KB |
| `02_hr_handbook_dense.pdf` | 94 KB |
| `03_edge_cases_symbols.pdf` | 52 KB |
| `04-product-servo-motor.pdf` | 4.5 KB |
| `05-financial-budget-q3.pdf` | 4.8 KB |
| `06-hr-attendance-normal.pdf` | 4.6 KB |
| `07-contract-project-alpha.pdf` | 7.1 KB |
| `08-project-summary-delta.pdf` | 4.3 KB |
| `09-ops-emergency-dense.pdf` | 5.2 KB |

### Markdown（2）

| 文件名 | 大小 |
|--------|------|
| `01_standard_policy.md` | 6.3 KB |
| `02_boundary_cases.md` | 4.8 KB |

目录内另有 `generate_test_pdfs.py`（生成脚本）及预览图，不计入 11 份测试文档。

---

## 2. Server Import 检查

在 `server/` 目录执行（**必须用 `.venv` 解释器**）：

```powershell
cd c:\2026_Project\enterprise-policy-system\server
.\.venv\Scripts\python.exe -c "from app.services.search_service import hybrid_search; from app.services.rerank_service import rerank_candidates; from app.services.chat_service import build_rag_prompt; from app.services.llm import stream_ollama_generate; print('IMPORT_OK')"
```

结果：`IMPORT_OK`

| 符号 | 模块路径 |
|------|----------|
| `hybrid_search` | `app.services.search_service` |
| `rerank_candidates` | `app.services.rerank_service` |
| `build_rag_prompt` | `app.services.chat_service` |
| `stream_ollama_generate` | `app.services.llm` |

`hybrid_search('财务审计', limit=3)` 实测返回 3 条结果。

---

## 3. `.env` / Ollama

| 项 | 值 / 状态 |
|----|-----------|
| `server/.env` | 存在 |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:7b` |
| Ollama 服务 | 运行中（`localhost:11434`） |
| 本地已拉取模型 | `qwen2.5:7b`、`nomic-embed-text:latest` 等 |

验证命令：

```powershell
ollama list
python -c "import httpx; r=httpx.post('http://localhost:11434/api/embeddings', json={'model':'nomic-embed-text','prompt':'ping'}, timeout=30); print(r.status_code, len(r.json()['embedding']))"
python -c "import httpx; r=httpx.post('http://localhost:11434/api/generate', json={'model':'qwen2.5:7b','prompt':'Say OK','stream':False}, timeout=120); print(r.status_code, r.json()['response'][:30])"
```

---

## 4. 入库与索引状态

### MySQL（documents + document_chunks）

| doc_id | file_name | status | chunks |
|--------|-----------|--------|--------|
| 1 | `01_financial_audit_2026.pdf` | active | 6 |
| 3 | `02_hr_handbook_dense.pdf` | active | 14 |
| 4 | `03_edge_cases_symbols.pdf` | active | 5 |
| 8 | `01_standard_policy.md` | active | 21 |
| 9 | `04-product-servo-motor.pdf` | active | 2 |
| 10 | `05-financial-budget-q3.pdf` | active | 2 |
| 11 | `06-hr-attendance-normal.pdf` | active | 2 |
| 12 | `07-contract-project-alpha.pdf` | active | 4 |
| 13 | `08-project-summary-delta.pdf` | active | 1 |
| 14 | `09-ops-emergency-dense.pdf` | active | 4 |
| 15 | `02_boundary_cases.md` | active | 14 |

- 期望 11 份：全部命中，`missing_expected=[]`
- 总分块：75；全部 `status=active`，无零分块文档

### ChromaDB

- 集合：`enterprise_docs`
- 向量数：**75**（与 MySQL 分块数一致）

### BM25

- 可检索块：**69**（MySQL 75 块中 6 块因过短/过长被过滤，见 `search_service.BM25Index.refresh_index`）

---

## 5. 若需重新上传 / 重建索引

当前环境**已入库**，以下命令供重置或新环境使用。

### 方式 A：脚本批量 reindex（文档已在库、仅重建索引）

```powershell
cd c:\2026_Project\enterprise-policy-system\server
python -m scripts.reindex_all_documents
# 单篇：python -m scripts.reindex_all_documents --doc-id 1
```

### 方式 B：API 上传（新环境从零入库）

1. 启动后端（默认 `http://localhost:8000`）
2. 登录获取 JWT：

```powershell
$resp = Invoke-RestMethod -Method POST -Uri "http://localhost:8000/api/auth/login" `
  -ContentType "application/json" `
  -Body '{"username":"<用户名>","password":"<密码>"}'
$token = $resp.access_token
```

3. 批量上传 `test_datasets` 下 11 个文件：

```powershell
$files = @(
  "01_financial_audit_2026.pdf","01_standard_policy.md","02_boundary_cases.md",
  "02_hr_handbook_dense.pdf","03_edge_cases_symbols.pdf","04-product-servo-motor.pdf",
  "05-financial-budget-q3.pdf","06-hr-attendance-normal.pdf","07-contract-project-alpha.pdf",
  "08-project-summary-delta.pdf","09-ops-emergency-dense.pdf"
)
$base = "c:\2026_Project\enterprise-policy-system\test_datasets"
foreach ($f in $files) {
  curl.exe -X POST "http://localhost:8000/api/documents/upload" `
    -H "Authorization: Bearer $token" `
    -F "file=@$base\$f"
}
```

4. 等待各文档 `status` 变为 `active` 后，可选执行全量 reindex（方式 A）。

### 方式 C：Admin API 单篇 reindex

```powershell
curl.exe -X POST "http://localhost:8000/api/admin/documents/reindex/{doc_id}" `
  -H "Authorization: Bearer $token"
```

---

## 6. 虚拟环境与 Rerank

| 解释器 | 路径 | `torch` | `transformers` | rerank |
|--------|------|---------|----------------|--------|
| **项目 .venv（推荐）** | `server/.venv/Scripts/python.exe` | ✅ 2.13.0+cpu | ✅ 5.15.0 | ✅ CPU 正常 |
| 全局 `python` | `Python311` 等 | ❌ 未安装 | ❌ 未安装 | ❌ `ModuleNotFoundError: torch` |

`requirements.txt` 已声明 `torch>=2.0.0`、`transformers>=4.40.0`，安装/补依赖应在 venv 内执行：

```powershell
cd c:\2026_Project\enterprise-policy-system\server
.\.venv\Scripts\pip.exe install -r requirements.txt
# 或单独补装：.\.venv\Scripts\pip.exe install torch transformers
```

启动后端、跑脚本、做评测时，统一用：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
.\.venv\Scripts\python.exe -m scripts.reindex_all_documents
```

## 7. 已知问题（非阻塞）

1. **ChromaDB telemetry 警告**：`capture() takes 1 positional argument but 3 were given`，不影响读写。
2. **Rerank 当前为 CPU 版 PyTorch**：`2.13.0+cpu`；若需 GPU 精排，在 venv 内按 `requirements.txt` 注释安装 CUDA 版 torch。
