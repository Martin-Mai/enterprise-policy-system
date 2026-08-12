# RAGAS 评测安装与 Judge 配置



## 依赖安装



在 `server/.venv` 中：



```bash

pip install -r eval/requirements-eval.txt

```



本项目 **固定 `ragas==0.1.21`**。`ragas>=0.4` 在当前 venv 会因 VertexAI 导入失败。



## API Key（DashScope judge）



```bash

cp eval/.env.example eval/.env

# 编辑 eval/.env，填入 DASHSCOPE_API_KEY（勿提交 git）

```



或在运行前设置系统环境变量 `DASHSCOPE_API_KEY`。



## Judge 配置（eval/config.yaml，默认 dashscope）



```yaml

ragas_judge:

  provider: dashscope          # dashscope | ollama | none

  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1

  model: qwen-plus            # RAGAS 评判 LLM；qwen-turbo 对中文 Faithfulness 常 NaN

  embedding_provider: ollama   # Answer Relevancy 仍用本地 embedding

  embedding_model: nomic-embed-text

  embedding_base_url: http://localhost:11434

```



| provider | 行为 |

|----------|------|

| **dashscope**（推荐） | 百炼 `qwen-turbo` 作 judge；需 `DASHSCOPE_API_KEY` |

| `ollama` | 本地 judge（易 `Failed to parse output`，分数常为空） |

| `none` | 跳过 RAGAS 打分，仅保存 contexts + answer |



**分工**：RAG **答案生成**始终用本地 Ollama `qwen2.5:7b`（与线上一致）；RAGAS **打分**默认用 DashScope `qwen-plus`（经实测 `qwen-turbo` 对中文 Faithfulness 易返回 NaN）。



## 运行命令



### 调试（smoke test）



```bash

# 激活 server/.venv 后

python eval/run_ragas_eval.py --config eval/config.yaml --limit 1 --rerank-enabled

```



验收：该条 `faithfulness`、`answer_relevancy` 为非空数值；`top1_rerank_score` 在 -10~+10 量级。



### 正式全量（交付用）



```bash

python eval/run_ragas_eval.py --config eval/config.yaml --rerank-enabled

```



**禁止**在正式跑批中使用 `--limit` 或 `--no-rerank`。



## 输出



- `eval/outputs/ragas_results.csv`

- `eval/outputs/run_<timestamp>/config.yaml`（配置快照）

- `eval/outputs/run_<timestamp>/ragas_results.csv`

- `eval/outputs/run_<timestamp>/ragas_summary.md`



## 拒答 KPI



低置信 tier 以 `should_refuse` + 答案是否含「未找到相关信息」计算 `refuse_accuracy`。**不以 Answer Relevancy ≤ 0.3 作为唯一拒答标准。**



## Fallback



若 judge 失败，CSV 仍含 `contexts` / `answer` / `refused`，RAGAS 分数字段可后补。本地 Ollama judge 详见历史说明；正式评测请用 `dashscope`。

