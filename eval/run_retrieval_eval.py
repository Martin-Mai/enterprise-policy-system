#!/usr/bin/env python3
"""
Golden Query 检索评测脚本。

从 eval/config.yaml 读取配置，调用 server 侧 hybrid_search，
输出 Recall@K、MRR、must_contain 命中率，并对比 rerank 开/关。

用法（仓库根目录或 eval/ 目录均可）：
    python eval/run_retrieval_eval.py
    python eval/run_retrieval_eval.py --limit 5
    python eval/run_retrieval_eval.py --no-rerank --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from tqdm import tqdm

EVAL_DIR = Path(__file__).resolve().parent

BASELINE_ID_RE = re.compile(r"^gq0(?:0[1-9]|1[0-9]|2[0-2])$")
HARD_ID_RE = re.compile(r"^gq0(?:2[6-9]|[3-5][0-9]|6[0-2])$")


def resolve_config_path(arg: str | None) -> Path:
    """解析 config 路径：支持 repo 根或 eval/ 作为 cwd。"""
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


def setup_server_imports(server_env_path: Path) -> Path:
    """将 server 加入 sys.path 并加载 .env。"""
    server_dir = server_env_path.parent.resolve()
    if not server_dir.is_dir():
        raise FileNotFoundError(f"server 目录不存在: {server_dir}")
    server_str = str(server_dir)
    if server_str not in sys.path:
        sys.path.insert(0, server_str)

    from dotenv import load_dotenv

    if server_env_path.exists():
        load_dotenv(dotenv_path=server_env_path, override=True)
    else:
        print(f"[warn] server .env 不存在: {server_env_path}，将使用默认配置")

    return server_dir


def reset_rerank_singleton() -> None:
    import app.services.rerank_service as rerank_module

    rerank_module._reranker = None
    rerank_module._reranker_load_attempted = False


def set_rerank_enabled(enabled: bool) -> None:
    from app.core.config import settings

    settings.RERANK_ENABLED = enabled
    reset_rerank_singleton()


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("golden_queries.json 应为数组")
    return data


def query_group(item: Dict[str, Any]) -> str:
    explicit = item.get("query_group")
    if explicit in ("baseline", "hard"):
        return explicit
    qid = str(item.get("id", ""))
    if BASELINE_ID_RE.match(qid):
        return "baseline"
    if HARD_ID_RE.match(qid):
        return "hard"
    if item.get("should_refuse"):
        return "refusal"
    return "other"


def recall_at_k(
    results: List[Dict[str, Any]], expected_files: List[str], k: int
) -> bool:
    if not expected_files:
        return False
    top_files = {r.get("file_name", "") for r in results[:k]}
    return any(name in top_files for name in expected_files)


def strict_recall_at_k(
    results: List[Dict[str, Any]], expected_files: List[str], k: int
) -> bool:
    """多文档题要求所有 expected_files 均出现在 Top-K。"""
    if not expected_files:
        return False
    top_files = {r.get("file_name", "") for r in results[:k]}
    return all(name in top_files for name in expected_files)


def reciprocal_rank(
    results: List[Dict[str, Any]], expected_files: List[str]
) -> float:
    if not expected_files:
        return 0.0
    expected = set(expected_files)
    for rank, item in enumerate(results, start=1):
        if item.get("file_name", "") in expected:
            return 1.0 / rank
    return 0.0


def must_contain_hit(
    results: List[Dict[str, Any]], keywords: List[str], k: int
) -> Tuple[bool, List[str]]:
    if not keywords:
        return False, []
    context = "\n".join(str(r.get("text", "")) for r in results[:k])
    missing = [kw for kw in keywords if kw not in context]
    return len(missing) == 0, missing


def failure_type(row: Dict[str, Any]) -> str:
    if row.get("should_refuse"):
        return "refusal"
    recall_ok = bool(row.get("effective_recall"))
    must_ok = bool(row.get("must_contain_hit"))
    keywords = row.get("must_contain_in_context") or []
    if recall_ok and (must_ok or not keywords):
        return "both_ok"
    if not recall_ok:
        return "wrong_file"
    return "wrong_chunk"


def effective_recall(row: Dict[str, Any]) -> bool:
    """单文档用 any-recall；多文档用 strict-recall。"""
    expected = row.get("expected_files") or []
    if len(expected) > 1:
        return bool(row.get("strict_recall_at_k"))
    return bool(row.get("recall_at_k"))


def is_scored_failure(row: Dict[str, Any]) -> bool:
    if row.get("should_refuse"):
        return False
    keywords = row.get("must_contain_in_context") or []
    if not effective_recall(row):
        return True
    return bool(keywords) and not row.get("must_contain_hit")


def aggregate_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [r for r in rows if not r.get("should_refuse")]
    if not scored:
        return {
            "query_count": 0,
            "recall_at_k": 0.0,
            "strict_recall_at_k": 0.0,
            "mrr": 0.0,
            "must_contain_hit_rate": 0.0,
        }

    recall_hits = sum(1 for r in scored if r["recall_at_k"])
    strict_hits = sum(1 for r in scored if r["strict_recall_at_k"])
    effective_hits = sum(1 for r in scored if effective_recall(r))
    mrr_sum = sum(r["mrr"] for r in scored)
    must_rows = [r for r in scored if r.get("must_contain_in_context")]
    must_hits = sum(1 for r in must_rows if r["must_contain_hit"])
    multi_file = [r for r in scored if len(r.get("expected_files") or []) > 1]
    multi_strict_hits = sum(1 for r in multi_file if r["strict_recall_at_k"])

    return {
        "query_count": len(scored),
        "recall_at_k": round(recall_hits / len(scored), 4),
        "strict_recall_at_k": round(strict_hits / len(scored), 4),
        "effective_recall_at_k": round(effective_hits / len(scored), 4),
        "multi_file_strict_recall_at_k": round(
            multi_strict_hits / len(multi_file) if multi_file else 0.0, 4
        ),
        "multi_file_query_count": len(multi_file),
        "mrr": round(mrr_sum / len(scored), 4),
        "must_contain_hit_rate": round(
            must_hits / len(must_rows) if must_rows else 0.0, 4
        ),
        "refusal_query_count": sum(1 for r in rows if r.get("should_refuse")),
    }


def refusal_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    refusal_rows = [r for r in rows if r.get("should_refuse")]
    if not refusal_rows:
        return {
            "query_count": 0,
            "false_retrieval_rate": 0.0,
            "retrieved_any_count": 0,
        }
    retrieved_any = sum(1 for r in refusal_rows if r.get("retrieved_count", 0) > 0)
    return {
        "query_count": len(refusal_rows),
        "false_retrieval_rate": round(retrieved_any / len(refusal_rows), 4),
        "retrieved_any_count": retrieved_any,
    }


def breakdown_by_key(
    rows: List[Dict[str, Any]], key_fn
) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = key_fn(row)
        groups.setdefault(key, []).append(row)
    return {name: aggregate_metrics(group_rows) for name, group_rows in groups.items()}


async def evaluate_one(
    query_item: Dict[str, Any],
    top_k: int,
    score_field: str,
) -> Dict[str, Any]:
    from app.services.search_service import hybrid_search

    question = query_item["question"]
    expected_files = query_item.get("expected_files") or []
    keywords = query_item.get("must_contain_in_context") or []
    should_refuse = bool(query_item.get("should_refuse"))

    results = await hybrid_search(question, limit=top_k)

    hit, missing = must_contain_hit(results, keywords, top_k)
    row: Dict[str, Any] = {
        "id": query_item["id"],
        "question": question,
        "tier": query_item.get("tier"),
        "query_group": query_group(query_item),
        "should_refuse": should_refuse,
        "expected_files": expected_files,
        "must_contain_in_context": keywords,
        "recall_at_k": recall_at_k(results, expected_files, top_k),
        "strict_recall_at_k": strict_recall_at_k(results, expected_files, top_k),
        "mrr": reciprocal_rank(results, expected_files),
        "must_contain_hit": hit,
        "must_contain_missing": missing,
        "retrieved_count": len(results),
        "retrieved_files": [r.get("file_name", "") for r in results[:top_k]],
        "top_scores": [
            {
                "file_name": r.get("file_name", ""),
                "rerank_score": r.get("rerank_score"),
                "final_rrf_score": r.get("final_rrf_score"),
                score_field: r.get(score_field),
            }
            for r in results[:top_k]
        ],
    }
    row["effective_recall"] = effective_recall(row)
    row["failure_type"] = failure_type(row)
    return row


async def run_mode(
    queries: List[Dict[str, Any]],
    *,
    rerank_enabled: bool,
    top_k: int,
    score_field: str,
    mode_label: str,
) -> Dict[str, Any]:
    set_rerank_enabled(rerank_enabled)

    from app.services.search_service import get_bm25_index

    get_bm25_index().refresh_index()

    per_query: List[Dict[str, Any]] = []
    iterator = tqdm(queries, desc=f"检索评测 [{mode_label}]", unit="query")
    for item in iterator:
        row = await evaluate_one(item, top_k, score_field)
        per_query.append(row)

    return {
        "rerank_enabled": rerank_enabled,
        "aggregate": aggregate_metrics(per_query),
        "refusal": refusal_metrics(per_query),
        "tier_breakdown": breakdown_by_key(
            per_query, lambda r: str(r.get("tier") or "unknown")
        ),
        "group_breakdown": breakdown_by_key(
            per_query, lambda r: str(r.get("query_group") or "other")
        ),
        "per_query": per_query,
    }


def build_comparison(
    rerank_on: Dict[str, Any], rerank_off: Dict[str, Any]
) -> Dict[str, Any]:
    on_agg = rerank_on["aggregate"]
    off_agg = rerank_off["aggregate"]
    return {
        "recall_at_k_delta": round(
            on_agg["recall_at_k"] - off_agg["recall_at_k"], 4
        ),
        "strict_recall_at_k_delta": round(
            on_agg["strict_recall_at_k"] - off_agg["strict_recall_at_k"], 4
        ),
        "effective_recall_at_k_delta": round(
            on_agg["effective_recall_at_k"] - off_agg["effective_recall_at_k"], 4
        ),
        "mrr_delta": round(on_agg["mrr"] - off_agg["mrr"], 4),
        "must_contain_hit_rate_delta": round(
            on_agg["must_contain_hit_rate"] - off_agg["must_contain_hit_rate"], 4
        ),
        "refusal_false_retrieval_delta": round(
            rerank_on.get("refusal", {}).get("false_retrieval_rate", 0.0)
            - rerank_off.get("refusal", {}).get("false_retrieval_rate", 0.0),
            4,
        ),
    }


def build_rerank_flips(
    rerank_on: Dict[str, Any], rerank_off: Dict[str, Any]
) -> List[Dict[str, Any]]:
    off_by_id = {r["id"]: r for r in rerank_off.get("per_query", [])}
    flips: List[Dict[str, Any]] = []
    for on_row in rerank_on.get("per_query", []):
        if on_row.get("should_refuse"):
            continue
        off_row = off_by_id.get(on_row["id"])
        if not off_row:
            continue
        off_failed = is_scored_failure(off_row)
        on_failed = is_scored_failure(on_row)
        if off_failed and not on_failed:
            flips.append(
                {
                    "id": on_row["id"],
                    "tier": on_row.get("tier"),
                    "query_group": on_row.get("query_group"),
                    "question": on_row.get("question"),
                    "off_failure_type": off_row.get("failure_type"),
                    "on_failure_type": on_row.get("failure_type"),
                    "off_retrieved_files": off_row.get("retrieved_files"),
                    "on_retrieved_files": on_row.get("retrieved_files"),
                }
            )
    return flips


def _render_metrics_table(
    lines: List[str], title: str, breakdown: Dict[str, Dict[str, Any]]
) -> None:
    if not breakdown:
        return
    lines.extend(["", f"## {title}", ""])
    lines.append(
        "| Group | Recall@K | Strict | Effective | MRR | Must-Contain | Queries |"
    )
    lines.append(
        "|-------|----------|--------|-----------|-----|--------------|---------|"
    )
    for name in sorted(breakdown.keys()):
        agg = breakdown[name]
        if agg.get("query_count", 0) == 0 and name in ("refusal", "low"):
            continue
        lines.append(
            f"| {name} | {agg['recall_at_k']:.4f} | "
            f"{agg['strict_recall_at_k']:.4f} | "
            f"{agg['effective_recall_at_k']:.4f} | {agg['mrr']:.4f} | "
            f"{agg['must_contain_hit_rate']:.4f} | {agg['query_count']} |"
        )


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Retrieval Eval Report",
        "",
        f"- 生成时间: {report['generated_at']}",
        f"- 数据集: `{report['dataset_path']}`",
        f"- Top-K: {report['search_top_k']}",
        f"- 置信分字段: `{report['confidence_score_field']}`",
        f"- 总题数: {report['total_queries']}（可评分 {report['scored_queries']}，"
        f"拒答 {report['refusal_queries']}）",
        "",
        "## Aggregate Metrics",
        "",
        "| Mode | Recall@K | Strict Recall | Effective Recall | MRR | Must-Contain | Queries |",
        "|------|----------|---------------|------------------|-----|--------------|---------|",
    ]

    for key, label in [("rerank_on", "Rerank ON"), ("rerank_off", "Rerank OFF")]:
        if key not in report["modes"]:
            continue
        agg = report["modes"][key]["aggregate"]
        lines.append(
            f"| {label} | {agg['recall_at_k']:.4f} | "
            f"{agg['strict_recall_at_k']:.4f} | {agg['effective_recall_at_k']:.4f} | "
            f"{agg['mrr']:.4f} | {agg['must_contain_hit_rate']:.4f} | "
            f"{agg['query_count']} |"
        )

    on_mode = report["modes"].get("rerank_on") or report["modes"].get("rerank_off")
    if on_mode and on_mode.get("aggregate", {}).get("multi_file_query_count", 0) > 0:
        mf = on_mode["aggregate"]
        lines.extend(
            [
                "",
                f"- 多文档题 Strict Recall@K: **{mf['multi_file_strict_recall_at_k']:.4f}** "
                f"（{mf['multi_file_query_count']} 题）",
            ]
        )

    for key, label in [("rerank_on", "Rerank ON"), ("rerank_off", "Rerank OFF")]:
        mode = report["modes"].get(key)
        if not mode:
            continue
        ref = mode.get("refusal", {})
        if ref.get("query_count", 0) > 0:
            lines.append(
                f"- {label} 拒答误检索率: **{ref['false_retrieval_rate']:.4f}** "
                f"（{ref['retrieved_any_count']}/{ref['query_count']} 仍返回结果）"
            )

    if "comparison" in report:
        cmp_ = report["comparison"]
        lines.extend(
            [
                "",
                "## Rerank ON vs OFF (delta)",
                "",
                f"- Recall@K: {cmp_['recall_at_k_delta']:+.4f}",
                f"- Strict Recall@K: {cmp_['strict_recall_at_k_delta']:+.4f}",
                f"- Effective Recall@K: {cmp_['effective_recall_at_k_delta']:+.4f}",
                f"- MRR: {cmp_['mrr_delta']:+.4f}",
                f"- Must-Contain: {cmp_['must_contain_hit_rate_delta']:+.4f}",
                f"- Refusal false retrieval: {cmp_['refusal_false_retrieval_delta']:+.4f}",
            ]
        )

    on_mode = report["modes"].get("rerank_on")
    if on_mode:
        _render_metrics_table(
            lines, "Tier Breakdown (Rerank ON)", on_mode.get("tier_breakdown", {})
        )
        _render_metrics_table(
            lines,
            "Query Group Breakdown (Rerank ON)",
            on_mode.get("group_breakdown", {}),
        )

    flips = report.get("rerank_flips", [])
    lines.extend(["", "## Rerank Flips (OFF fail → ON pass)", ""])
    if not flips:
        lines.append("_无翻转样本_")
    else:
        for flip in flips:
            lines.append(
                f"- **{flip['id']}** ({flip.get('query_group')}/{flip.get('tier')}): "
                f"off={flip.get('off_failure_type')} → on={flip.get('on_failure_type')}"
            )

    lines.extend(["", "## Per-Query Failures (Rerank ON)", ""])
    on_rows = report["modes"].get("rerank_on", {}).get("per_query", [])
    failures = [r for r in on_rows if is_scored_failure(r)]
    if not failures:
        lines.append("_无失败样本_")
    else:
        for row in failures:
            lines.append(
                f"- **{row['id']}** ({row.get('query_group')}/{row['tier']}): "
                f"type={row.get('failure_type')}, "
                f"recall={row['recall_at_k']}, strict={row['strict_recall_at_k']}, "
                f"effective={row.get('effective_recall')}, "
                f"must_contain={row['must_contain_hit']}, "
                f"files={row['retrieved_files']}"
            )

    return "\n".join(lines) + "\n"


async def async_main(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    eval_dir = config_path.parent

    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    dataset_path = resolve_eval_path(eval_dir, cfg["dataset_path"])
    output_dir = resolve_eval_path(eval_dir, cfg["output_dir"])
    server_env_path = resolve_eval_path(eval_dir, cfg["server_env_path"])
    output_dir.mkdir(parents=True, exist_ok=True)

    top_k = int(cfg.get("search_top_k", 5))
    score_field = cfg.get("confidence_score_field", "rerank_score")
    report_json_name = cfg.get("report_json", "retrieval_report.json")
    report_md_name = cfg.get("report_md", "retrieval_report.md")

    setup_server_imports(server_env_path)

    queries = load_dataset(dataset_path)
    if args.limit is not None:
        queries = queries[: args.limit]

    scored = [q for q in queries if not q.get("should_refuse")]
    refusal = [q for q in queries if q.get("should_refuse")]

    modes: Dict[str, Any] = {}

    if args.no_rerank:
        modes["rerank_off"] = await run_mode(
            queries,
            rerank_enabled=False,
            top_k=top_k,
            score_field=score_field,
            mode_label="rerank OFF",
        )
    else:
        default_rerank = bool(cfg.get("rerank_enabled", True))
        modes["rerank_on"] = await run_mode(
            queries,
            rerank_enabled=default_rerank,
            top_k=top_k,
            score_field=score_field,
            mode_label="rerank ON",
        )
        modes["rerank_off"] = await run_mode(
            queries,
            rerank_enabled=False,
            top_k=top_k,
            score_field=score_field,
            mode_label="rerank OFF",
        )

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "dataset_path": str(dataset_path),
        "search_top_k": top_k,
        "confidence_score_field": score_field,
        "total_queries": len(queries),
        "scored_queries": len(scored),
        "refusal_queries": len(refusal),
        "modes": modes,
    }

    if "rerank_on" in modes and "rerank_off" in modes:
        report["comparison"] = build_comparison(modes["rerank_on"], modes["rerank_off"])
        report["rerank_flips"] = build_rerank_flips(
            modes["rerank_on"], modes["rerank_off"]
        )

    json_path = output_dir / report_json_name
    md_path = output_dir / report_md_name

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"\n报告已写入:\n  {json_path}\n  {md_path}")

    primary = modes.get("rerank_on") or modes["rerank_off"]
    agg = primary["aggregate"]
    print(
        f"Primary aggregate — Recall@K={agg['recall_at_k']:.4f}, "
        f"Strict={agg['strict_recall_at_k']:.4f}, "
        f"Effective={agg['effective_recall_at_k']:.4f}, "
        f"MRR={agg['mrr']:.4f}, Must-Contain={agg['must_contain_hit_rate']:.4f}"
    )
    ref = primary.get("refusal", {})
    if ref.get("query_count", 0) > 0:
        print(
            f"Refusal false retrieval — {ref['false_retrieval_rate']:.4f} "
            f"({ref['retrieved_any_count']}/{ref['query_count']})"
        )
    if report.get("rerank_flips"):
        flip_ids = [f["id"] for f in report["rerank_flips"]]
        print(f"Rerank flips ({len(flip_ids)}): {', '.join(flip_ids)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden Query 检索评测")
    parser.add_argument(
        "--config",
        default=None,
        help="config.yaml 路径（默认自动探测 eval/config.yaml）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅评测前 N 条（快速调试）",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="仅运行 rerank 关闭模式（跳过 rerank on 对比）",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
