# 文本分块策略说明

企业制度 RAG 知识库支持两种分块策略，通过环境变量 `CHUNK_STRATEGY` 切换。**切换策略或调整分块参数后，必须对存量文档执行 reindex**，否则 MySQL / ChromaDB / BM25 索引将与当前配置不一致。

## flat vs parent_child

| 对比项 | `flat`（默认） | `parent_child` |
|--------|----------------|----------------|
| 结构 | 单层 chunk | Parent（段落级）+ Child（检索级） |
| 预切 | PDF 按页 / MD 按 `#` 标题 | 同左 |
| 二次切分 | `CHUNK_SIZE` / `CHUNK_OVERLAP` | Parent：`PARENT_CHUNK_SIZE`；Child：`CHILD_CHUNK_SIZE` / `CHILD_CHUNK_OVERLAP` |
| 向量化 | 全部 chunk 写入 ChromaDB | **仅 Child** 向量化 |
| 检索 | 直接返回 chunk 文本 | 命中 Child，**回填 Parent 文本**给 LLM |
| 适用场景 | 文档较短、结构简单、快速上线 | 制度条文较长、需要更完整上下文、减少断句割裂 |

### 数据流（parent_child）

```
上传 → parse → Parent 切分 → Child 切分
     → MySQL：Parent + Child 均入库
     → ChromaDB：仅 Child
     → 检索：BM25 + 向量均基于 Child
     → Prompt：Parent 文本（超 2000 字截断）+ citation preview 用 Child
```

## 环境变量

在 `server/.env`（本地开发）或 Docker 根目录 `.env`（Compose 部署）中配置：

```env
# 分块策略：flat | parent_child
CHUNK_STRATEGY=flat

# flat 模式
CHUNK_SIZE=500
CHUNK_OVERLAP=50

# parent_child 模式
PARENT_CHUNK_SIZE=1500
CHILD_CHUNK_SIZE=300
CHILD_CHUNK_OVERLAP=30

# 检索侧 BM25 索引长度上限（应 >= CHILD_CHUNK_SIZE）
SEARCH_MAX_CHUNK_LENGTH=800
```

### 切换策略示例

从 flat 改为 parent_child：

```env
# 1. 修改 .env
CHUNK_STRATEGY=parent_child

# 2. 重启后端服务（使配置生效）

# 3. 重建全部 active 文档索引（见下方命令）
```

从 parent_child 改回 flat 时，同样修改 `CHUNK_STRATEGY=flat` 后执行 reindex。

## 重建索引（reindex）

### 命令行脚本（推荐）

在 **`server/` 目录**下执行，需已配置 `.env`、MySQL 可连、Ollama 嵌入服务可用：

```bash
# 重建全部 status=active 的文档
python -m scripts.reindex_all_documents

# 仅重建单篇文档
python -m scripts.reindex_all_documents --doc-id 3
```

脚本行为：

1. 遍历 `status=active` 的文档（或指定 `--doc-id`）
2. 对每篇：`purge` 旧 chunks → 重新 parse + split + embed
3. 结束后统一刷新 BM25 内存索引
4. 打印进度；失败 doc_id 列表；若有失败则以 exit code 1 退出

### Admin API（单文档，异步）

已有端点（需管理员 JWT）：

```http
POST /api/admin/documents/reindex/{doc_id}
```

提交后台任务，逻辑与上传后 `process_document_background` 相同，适合管理后台单篇重跑。

用户侧 reprocess（需登录且为上传者或 admin）：

```http
POST /api/documents/{doc_id}/reprocess
```

### 注意事项

- reindex **不会**修改 upload 流程；新上传文档仍按当前 `CHUNK_STRATEGY` 自动处理
- reindex 前请确认磁盘上 `documents.file_path` 源文件仍存在
- `status=deleting` 或 `processing` 的文档不会被全量脚本处理
- parent_child 模式下 Parent 不进 Chroma；若只改检索逻辑未 reindex，可能出现检索与库内 metadata 不一致

## 相关代码

| 模块 | 职责 |
|------|------|
| `server/app/services/document_processor.py` | parse、split、embed、入库 |
| `server/app/services/search_service.py` | 混合检索、Parent 回填 |
| `server/app/services/chat_service.py` | RAG Prompt、citation |
| `server/scripts/reindex_all_documents.py` | 批量/单文档重建索引 |

## 如何运行 retrieval eval

在仓库根目录（需已激活 `server/.venv` 并安装 `eval/requirements-eval.txt`）：

```bash
pip install -r eval/requirements-eval.txt
python eval/run_retrieval_eval.py              # 全量 62 条，对比 rerank on/off
python eval/run_retrieval_eval.py --limit 5    # 快速调试
```

Golden Query 共 62 条（baseline 22 + hard 32 + 拒答 8）。报告含 **Strict / Effective Recall**、多文档 Strict、拒答误检索率、rerank 翻转样本。主看 **Effective Recall**（单文档 any-recall，多文档 strict-recall）。

## 如何生成 RAGAS 评测用例（generate_cases）

```bash
pip install -r eval/requirements-eval.txt
python eval/generate_cases.py --config eval/config.yaml   # drafts + ragas_cases
python eval/generate_cases.py --draft-only                # 仅 LLM 草稿与过滤
python eval/generate_cases.py --finalize                  # 仅合并为 ragas_cases.jsonl
```

输出：`eval/datasets/drafts_100.jsonl`、`filtered_80.jsonl`、`ragas_cases.jsonl`（50 条，20/20/10 tier）。

## 如何运行 RAGAS 评测（run_ragas_eval.py）

```bash
python eval/run_ragas_eval.py --config eval/config.yaml --limit 5
python eval/run_ragas_eval.py --output eval/outputs/ragas_results.csv
```

Judge 与依赖说明见 `eval/RAGAS_SETUP.md`。`DASHSCOPE_API_KEY` 可写在 `eval/.env` 或 `server/.env`。

**调试**：`python eval/run_ragas_eval.py --limit 1 --rerank-enabled`

**正式全量**（勿用 `--limit` / `--no-rerank`）：

```bash
python eval/run_ragas_eval.py --config eval/config.yaml --rerank-enabled
```
