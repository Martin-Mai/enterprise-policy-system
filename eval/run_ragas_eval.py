#!/usr/bin/env python3
"""
RAGAS 评测执行脚本（阶段 2）。

对 ragas_cases.jsonl 每条：检索 → RAG 生成 → RAGAS 打分 → CSV 汇总。

用法（仓库根目录或 eval/ 目录）：
    python eval/run_ragas_eval.py --config eval/config.yaml
    python eval/run_ragas_eval.py --limit 5 --no-rerank
    python eval/run_ragas_eval.py --output eval/outputs/ragas_results.csv
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd
import yaml
from tqdm import tqdm

EVAL_DIR = Path(__file__).resolve().parent


def resolve_config_path(arg: str | None) -> Path:
    candidates: List[Path] = []
    if arg:
        p = Path(arg)
        candidates.append(p if p.is_absolute() else Path.cwd() / p)
        if not candidates[-1].exists():
            candidates.append(EVAL_DIR / arg)
    else:
        candidates.extend(
            [
                Path.cwd() / "eval" / "config.yaml",
                Path.cwd() / "config.yaml",
                EVAL_DIR / "config.yaml",
            ]
        )
    for path in candidates:
        if path.exists():
            return path.resolve()
    raise FileNotFoundError(f"找不到配置文件，已尝试: {[str(p) for p in candidates]}")


def resolve_eval_path(eval_dir: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        return path
    return (eval_dir / path).resolve()


def setup_server_imports(server_env_path: Path) -> None:
    server_dir = server_env_path.parent.resolve()
    server_str = str(server_dir)
    if server_str not in sys.path:
        sys.path.insert(0, server_str)
    from dotenv import load_dotenv

    if server_env_path.exists():
        load_dotenv(dotenv_path=server_env_path, override=True)


def reset_rerank_singleton() -> None:
    import app.services.rerank_service as rerank_module

    rerank_module._reranker = None
    rerank_module._reranker_load_attempted = False


def set_rerank_enabled(enabled: bool) -> None:
    from app.core.config import settings

    settings.RERANK_ENABLED = enabled
    reset_rerank_singleton()


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def call_ollama_generate(
    *,
    url: str,
    model: str,
    prompt: str,
    timeout: float,
    keep_alive: str = "30m",
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    return str(data.get("response", "")).strip()


def resolve_ollama_generate(cfg: Dict[str, Any]) -> Tuple[str, str, float, str]:
    from app.core.config import settings

    url = cfg.get("ollama_generate_url") or settings.OLLAMA_GENERATE_URL
    model = cfg.get("ollama_model") or settings.OLLAMA_CHAT_MODEL
    timeout = float(cfg.get("ollama_timeout", settings.OLLAMA_GENERATE_TIMEOUT))
    keep_alive = cfg.get("ollama_keep_alive") or settings.OLLAMA_KEEP_ALIVE
    return url, model, timeout, keep_alive


def load_eval_env(eval_dir: Path) -> None:
    from dotenv import load_dotenv

    env_file = eval_dir / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=False)


def detect_refused(answer: str, phrase: str) -> bool:
    return phrase in answer


def must_contain_hit(contexts: List[str], keywords: List[str]) -> Optional[bool]:
    if not keywords:
        return None
    context = "\n".join(contexts)
    return all(keyword in context for keyword in keywords)


def build_ragas_embeddings(judge_cfg: Dict[str, Any], cfg: Dict[str, Any]) -> Any:
    from langchain_community.embeddings import OllamaEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    embed_provider = str(
        judge_cfg.get("embedding_provider", "ollama")
    ).lower()
    if embed_provider != "ollama":
        raise ValueError(f"不支持的 embedding_provider: {embed_provider}")

    embed_base = judge_cfg.get("embedding_base_url", "http://localhost:11434")
    embed_model = judge_cfg.get("embedding_model", "nomic-embed-text")
    return LangchainEmbeddingsWrapper(
        OllamaEmbeddings(model=embed_model, base_url=embed_base)
    )


def build_ragas_judge(cfg: Dict[str, Any]) -> Tuple[Any, Any, Optional[str]]:
    """构建 RAGAS judge LLM / Embeddings；失败返回 (None, None, error_msg)。"""
    judge_cfg = cfg.get("ragas_judge") or {}
    provider = str(judge_cfg.get("provider", "dashscope")).lower()
    if provider in {"none", "off", "disabled"}:
        return None, None, "ragas_judge.provider=none，跳过 RAGAS 打分"

    try:
        embeddings = build_ragas_embeddings(judge_cfg, cfg)
        judge_timeout = float(judge_cfg.get("timeout", 120))

        if provider == "dashscope":
            from langchain_openai import ChatOpenAI
            from ragas.llms import LangchainLLMWrapper

            api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
            if not api_key:
                return (
                    None,
                    None,
                    "DASHSCOPE_API_KEY 未设置，请配置 eval/.env 或系统环境变量",
                )
            base_url = judge_cfg.get(
                "base_url",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            model = judge_cfg.get("model", "qwen-turbo")
            llm = LangchainLLMWrapper(
                ChatOpenAI(
                    model=model,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=0,
                    timeout=judge_timeout,
                )
            )
            return llm, embeddings, None

        if provider == "ollama":
            from langchain_community.llms import Ollama
            from ragas.llms import LangchainLLMWrapper

            base_url = judge_cfg.get("base_url", "http://localhost:11434")
            model = judge_cfg.get("model", cfg.get("ollama_model", "qwen2.5:7b"))
            llm = LangchainLLMWrapper(
                Ollama(
                    model=model,
                    base_url=base_url,
                    temperature=0.0,
                    timeout=int(judge_timeout),
                )
            )
            return llm, embeddings, None

        return None, None, f"不支持的 ragas_judge.provider: {provider}"
    except Exception as exc:
        return None, None, f"RAGAS judge 初始化失败: {exc}"


def run_ragas_scoring(
    rows: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    llm: Any,
    embeddings: Any,
) -> Optional[str]:
    """对无 error 的样本批量 RAGAS 打分，分数写回 rows。"""
    metrics_cfg = cfg.get("ragas_metrics") or {}
    eligible_indices = [
        i
        for i, row in enumerate(rows)
        if not row.get("error") and row.get("answer")
    ]
    if not eligible_indices:
        return "无可评分样本"

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, faithfulness

        from ragas.run_config import RunConfig

        metrics = []
        if metrics_cfg.get("faithfulness", True):
            metrics.append(faithfulness)
        if metrics_cfg.get("answer_relevancy", True):
            metrics.append(answer_relevancy)
        if not metrics:
            return "ragas_metrics 全部关闭"

        subset = [rows[i] for i in eligible_indices]
        dataset = Dataset.from_dict(
            {
                "question": [r["question"] for r in subset],
                "answer": [r["answer"] for r in subset],
                "contexts": [r["contexts"] for r in subset],
                "ground_truth": [r["ground_truth"] for r in subset],
            }
        )
        judge_cfg = cfg.get("ragas_judge") or {}
        run_timeout = int(judge_cfg.get("run_timeout", 600))
        max_workers = int(judge_cfg.get("max_workers", 1))
        run_config = RunConfig(timeout=run_timeout, max_workers=max_workers)

        metric_errors: List[str] = []
        for metric in metrics:
            metric_name = metric.name
            try:
                result = evaluate(
                    dataset,
                    metrics=[metric],
                    llm=llm,
                    embeddings=embeddings,
                    run_config=run_config,
                )
                scores_df = result.to_pandas()
                if metric_name not in scores_df.columns:
                    metric_errors.append(f"{metric_name}: 结果列缺失")
                    continue
                for local_idx, global_idx in enumerate(eligible_indices):
                    val = scores_df.iloc[local_idx][metric_name]
                    rows[global_idx][metric_name] = (
                        None if pd.isna(val) else float(val)
                    )
            except Exception as exc:
                metric_errors.append(f"{metric_name}: {exc}")

        if metric_errors:
            return "; ".join(metric_errors)
        return None
    except Exception as exc:
        return f"RAGAS evaluate 失败: {exc}"


async def process_one_case(
    case: Dict[str, Any],
    *,
    top_k: int,
    score_field: str,
    ollama_url: str,
    ollama_model: str,
    ollama_timeout: float,
    ollama_keep_alive: str,
    refusal_phrase: str,
) -> Dict[str, Any]:
    from app.core.config import settings
    from app.services.chat_service import build_rag_prompt
    from app.services.confidence_gate import (
        REFUSAL_MESSAGE,
        decide_gate,
        extract_top1_score,
    )
    from app.services.search_service import hybrid_search

    row: Dict[str, Any] = {
        "id": case.get("id", ""),
        "question": case.get("question", ""),
        "tier": case.get("tier", ""),
        "should_refuse": bool(case.get("should_refuse")),
        "ground_truth": case.get("ground_truth", ""),
        "expected_files": case.get("expected_files") or [],
        "must_contain_in_context": case.get("must_contain_in_context") or [],
        "source_doc": case.get("source_doc"),
        "faithfulness": None,
        "answer_relevancy": None,
        "gate_decision": None,
        "error": None,
    }

    try:
        question = row["question"]
        chunks = await hybrid_search(question, limit=top_k)

        confidence_score = extract_top1_score(chunks, score_field)
        if settings.CONFIDENCE_GATE_ENABLED:
            gate_decision = decide_gate(
                confidence_score,
                bool(chunks),
                settings.CONFIDENCE_HIGH_THRESHOLD,
                settings.CONFIDENCE_LOW_THRESHOLD,
            )
        else:
            gate_decision = "normal"

        if gate_decision == "refuse":
            answer = REFUSAL_MESSAGE
        else:
            prompt_mode = "cautious" if gate_decision == "cautious" else "normal"
            prompt = build_rag_prompt(question, "", chunks, mode=prompt_mode)
            answer = await asyncio.to_thread(
                call_ollama_generate,
                url=ollama_url,
                model=ollama_model,
                prompt=prompt,
                timeout=ollama_timeout,
                keep_alive=ollama_keep_alive,
            )

        contexts = [str(c.get("text", "")) for c in chunks]
        keywords = row["must_contain_in_context"]
        row.update(
            {
                "answer": answer,
                "contexts": contexts,
                "retrieved_files": [c.get("file_name", "") for c in chunks],
                "chunk_ids": [str(c.get("chunk_id", "")) for c in chunks],
                "top1_rerank_score": confidence_score,
                "top1_score_field": score_field,
                "retrieved_count": len(chunks),
                "gate_decision": gate_decision,
                "refused": detect_refused(answer, refusal_phrase),
                "must_contain_hit": must_contain_hit(contexts, keywords),
            }
        )
    except Exception as exc:
        row["error"] = str(exc)
        row.setdefault("answer", "")
        row.setdefault("contexts", [])
        row.setdefault("retrieved_files", [])
        row.setdefault("chunk_ids", [])
        row.setdefault("top1_rerank_score", None)
        row.setdefault("top1_score_field", score_field)
        row.setdefault("gate_decision", None)
        row.setdefault("refused", False)
        row.setdefault("must_contain_hit", None)

    row["refuse_correct"] = (
        row.get("refused") is True
        if row.get("should_refuse")
        else row.get("refused") is False
    )
    return row


def rows_to_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    export_rows: List[Dict[str, Any]] = []
    for row in rows:
        export = dict(row)
        for key in (
            "contexts",
            "retrieved_files",
            "chunk_ids",
            "expected_files",
            "must_contain_in_context",
        ):
            if key in export and not isinstance(export[key], str):
                export[key] = json.dumps(export[key], ensure_ascii=False)
        export_rows.append(export)
    df = pd.DataFrame(export_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _mean_metric(items: List[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [r[key] for r in items if r.get(key) is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _fill_rate(items: List[Dict[str, Any]], key: str) -> Optional[float]:
    if not items:
        return None
    filled = sum(1 for r in items if r.get(key) is not None)
    return round(filled / len(items), 4)


def _tier_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    tiers = ("high", "medium", "low")
    result: Dict[str, Dict[str, Optional[float]]] = {}
    for tier in tiers:
        subset = [r for r in rows if r.get("tier") == tier and not r.get("error")]
        result[tier] = {
            "count": len(subset),
            "faithfulness_mean": _mean_metric(subset, "faithfulness"),
            "answer_relevancy_mean": _mean_metric(subset, "answer_relevancy"),
            "faithfulness_fill_rate": _fill_rate(subset, "faithfulness"),
            "answer_relevancy_fill_rate": _fill_rate(subset, "answer_relevancy"),
        }
    return result


def compute_summary(
    rows: List[Dict[str, Any]],
    ragas_error: Optional[str],
    *,
    elapsed_seconds: float,
) -> Dict[str, Any]:
    scored = [r for r in rows if not r.get("error")]
    refuse_rows = [r for r in scored if r.get("should_refuse")]
    answerable = [r for r in scored if not r.get("should_refuse")]

    refuse_correct = sum(1 for r in refuse_rows if r.get("refused"))
    false_refusal = sum(1 for r in answerable if r.get("refused"))

    return {
        "total": len(rows),
        "errors": sum(1 for r in rows if r.get("error")),
        "scored_cases": len(scored),
        "faithfulness_mean": _mean_metric(answerable, "faithfulness"),
        "answer_relevancy_mean": _mean_metric(answerable, "answer_relevancy"),
        "faithfulness_fill_rate": _fill_rate(scored, "faithfulness"),
        "answer_relevancy_fill_rate": _fill_rate(scored, "answer_relevancy"),
        "refuse_accuracy": round(refuse_correct / len(refuse_rows), 4)
        if refuse_rows
        else None,
        "refuse_count": len(refuse_rows),
        "refuse_correct": refuse_correct,
        "false_refusal_on_answerable": false_refusal,
        "must_contain_hit_rate": _mean_metric(
            [r for r in answerable if r.get("must_contain_hit") is not None],
            "must_contain_hit",
        ),
        "tier_metrics": _tier_metrics(scored),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "ragas_scoring_error": ragas_error,
    }


def render_summary_md(
    summary: Dict[str, Any],
    *,
    run_dir: Path,
    config_path: Path,
    rerank_enabled: bool,
) -> str:
    lines = [
        "# RAGAS Eval Summary",
        "",
        f"- 运行目录: `{run_dir}`",
        f"- 配置: `{config_path}`",
        f"- Rerank: {'ON' if rerank_enabled else 'OFF'}",
        f"- 样本数: {summary['total']}（成功 {summary['scored_cases']}，"
        f"失败 {summary['errors']}）",
        f"- 耗时: {summary['elapsed_seconds']}s",
        "",
        "## Aggregate Metrics（可回答样本，不含 should_refuse）",
        "",
        f"- Faithfulness (mean): {summary['faithfulness_mean']}",
        f"- Answer Relevancy (mean): {summary['answer_relevancy_mean']}",
        f"- Faithfulness 非空率: {summary['faithfulness_fill_rate']}",
        f"- Answer Relevancy 非空率: {summary['answer_relevancy_fill_rate']}",
        "",
        "## 按 Tier 汇总",
        "",
        "| Tier | Count | Faithfulness | Answer Relevancy | F-fill | AR-fill |",
        "|------|-------|--------------|------------------|--------|---------|",
    ]
    for tier, metrics in summary.get("tier_metrics", {}).items():
        lines.append(
            f"| {tier} | {metrics['count']} | {metrics['faithfulness_mean']} | "
            f"{metrics['answer_relevancy_mean']} | {metrics['faithfulness_fill_rate']} | "
            f"{metrics['answer_relevancy_fill_rate']} |"
        )
    lines.extend(
        [
            "",
            "## 拒答评测（should_refuse 样本）",
            "",
            f"- refuse_accuracy: {summary['refuse_accuracy']} "
            f"({summary['refuse_correct']}/{summary['refuse_count']})",
            f"- 可回答样本误拒答数: {summary['false_refusal_on_answerable']}",
            f"- must_contain_hit_rate（可回答）: {summary['must_contain_hit_rate']}",
            "",
        ]
    )
    if summary.get("ragas_scoring_error"):
        lines.extend(
            [
                "## RAGAS 打分",
                "",
                f"- 状态: 失败或未执行 — {summary['ragas_scoring_error']}",
                "- contexts + answer 已保存，可后补 RAGAS 分数",
                "",
            ]
        )
    return "\n".join(lines)


def snapshot_config(config_path: Path, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, run_dir / "config.yaml")


async def async_main(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    config_path = resolve_config_path(args.config)
    eval_dir = config_path.parent
    load_eval_env(eval_dir)
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = resolve_eval_path(eval_dir, "outputs") / f"run_{timestamp}"

    snapshot_config(config_path, run_dir)

    setup_server_imports(resolve_eval_path(eval_dir, cfg["server_env_path"]))

    if args.no_rerank:
        rerank_enabled = False
    elif args.rerank_enabled:
        rerank_enabled = True
    else:
        rerank_enabled = bool(cfg.get("rerank_enabled", True))
    set_rerank_enabled(rerank_enabled)

    from app.services.search_service import get_bm25_index

    get_bm25_index().refresh_index()

    dataset_path = resolve_eval_path(eval_dir, cfg["ragas_dataset_path"])
    cases = read_jsonl(dataset_path)
    if args.limit is not None:
        cases = cases[: args.limit]

    top_k = int(cfg.get("search_top_k", 5))
    score_field = cfg.get("confidence_score_field", "rerank_score")
    refusal_phrase = cfg.get("refusal_phrase", "未找到相关信息")
    ollama_url, ollama_model, ollama_timeout, ollama_keep_alive = (
        resolve_ollama_generate(cfg)
    )

    rows: List[Dict[str, Any]] = []
    for case in tqdm(cases, desc="RAG 流水线", unit="case"):
        row = await process_one_case(
            case,
            top_k=top_k,
            score_field=score_field,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            ollama_timeout=ollama_timeout,
            ollama_keep_alive=ollama_keep_alive,
            refusal_phrase=refusal_phrase,
        )
        rows.append(row)

    llm, embeddings, judge_error = build_ragas_judge(cfg)
    ragas_error = judge_error
    if llm is not None and embeddings is not None:
        ragas_error = run_ragas_scoring(rows, cfg, llm, embeddings) or judge_error

    summary = compute_summary(
        rows,
        ragas_error,
        elapsed_seconds=time.perf_counter() - started,
    )

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (Path.cwd() / output_path).resolve()
    else:
        default_name = cfg.get("ragas_results_csv", "ragas_results.csv")
        output_path = resolve_eval_path(eval_dir, f"outputs/{default_name}")

    run_csv = run_dir / "ragas_results.csv"
    rows_to_csv(rows, run_csv)
    rows_to_csv(rows, output_path)

    summary_md = render_summary_md(
        summary,
        run_dir=run_dir,
        config_path=config_path,
        rerank_enabled=rerank_enabled,
    )
    (run_dir / "ragas_summary.md").write_text(summary_md, encoding="utf-8")

    print(f"\n结果 CSV:\n  {output_path}\n  {run_csv}")
    print(f"摘要: {run_dir / 'ragas_summary.md'}")
    print(
        f"Faithfulness={summary['faithfulness_mean']}, "
        f"AnswerRelevancy={summary['answer_relevancy_mean']}, "
        f"refuse_accuracy={summary['refuse_accuracy']}"
    )
    if ragas_error:
        print(f"[warn] RAGAS: {ragas_error}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="RAGAS 评测执行")
    parser.add_argument("--config", default=None, help="config.yaml 路径")
    parser.add_argument("--limit", type=int, default=None, help="仅跑前 N 条")
    parser.add_argument(
        "--rerank-enabled",
        action="store_true",
        help="强制开启 rerank",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="关闭 rerank",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV 输出路径（默认 eval/outputs/ragas_results.csv）",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
