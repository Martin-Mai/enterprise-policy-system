#!/usr/bin/env python3
"""
RAG 置信度阈值校准（P95 + 分布图）。

从 RAGAS 评测 CSV 读取 top1_rerank_score，按 tier / faithfulness / 拒答标签
计算 T_high / T_low 推荐值，并生成分布图与报告。

用法（仓库根目录或 eval/ 目录）：
    python eval/calibrate_thresholds.py --config eval/config.yaml --input eval/outputs/ragas_results.csv
    python eval/calibrate_thresholds.py --percentile 95 --holdout
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

EVAL_DIR = Path(__file__).resolve().parent

TIER_COLORS = {
    "high": "#2ecc71",
    "medium": "#f39c12",
    "low": "#e74c3c",
}

SMALL_SAMPLE_THRESHOLD = 20
HOLDOUT_TRAIN_RATIO = 0.8
HOLDOUT_SEED = 42


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


def resolve_input_path(arg: str, eval_dir: Path) -> Path:
    p = Path(arg)
    if p.is_absolute():
        path = p
    else:
        path = Path.cwd() / p
        if not path.exists():
            path = eval_dir / arg
    if not path.exists():
        raise FileNotFoundError(f"找不到输入 CSV: {path}")
    return path.resolve()


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in ("true", "1", "yes")


def load_config(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"tier", "faithfulness", "should_refuse", "refused", "top1_rerank_score"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV 缺少必要列: {sorted(missing)}")
    df = df.copy()
    df["should_refuse"] = df["should_refuse"].apply(parse_bool)
    df["refused"] = df["refused"].apply(parse_bool)
    df["top1_rerank_score"] = pd.to_numeric(df["top1_rerank_score"], errors="coerce")
    df["faithfulness"] = pd.to_numeric(df["faithfulness"], errors="coerce")
    return df


def percentile_value(scores: pd.Series, percentile: float) -> Optional[float]:
    valid = scores.dropna()
    if valid.empty:
        return None
    return float(np.percentile(valid.to_numpy(), percentile))


def split_holdout(
    scores: pd.Series, train_ratio: float = HOLDOUT_TRAIN_RATIO, seed: int = HOLDOUT_SEED
) -> Tuple[pd.Series, pd.Series]:
    n = len(scores)
    if n < 2:
        return scores, scores.iloc[0:0]
    rng = np.random.default_rng(seed)
    indices = rng.permutation(n)
    split_at = max(1, int(n * train_ratio))
    if split_at >= n:
        split_at = n - 1
    train_idx = indices[:split_at]
    test_idx = indices[split_at:]
    return scores.iloc[train_idx], scores.iloc[test_idx]


def compute_threshold_stats(
    scores: pd.Series, percentile: float
) -> Dict[str, Any]:
    valid = scores.dropna()
    n = len(valid)
    if n == 0:
        return {
            "count": 0,
            "threshold": None,
            "min": None,
            "max": None,
            "mean": None,
            "p95": None,
            "warnings": ["样本数为 0，无法计算阈值"],
        }

    threshold = percentile_value(valid, percentile)
    warnings: List[str] = []
    if n < SMALL_SAMPLE_THRESHOLD:
        warnings.append(
            f"校准样本仅 {n} 条（<{SMALL_SAMPLE_THRESHOLD}），P{percentile:.0f} 估计不稳定，"
            "建议扩大 RAGAS 评测集后再校准。"
        )

    return {
        "count": n,
        "threshold": threshold,
        "min": float(valid.min()),
        "max": float(valid.max()),
        "mean": float(valid.mean()),
        "p95": percentile_value(valid, 95),
        "warnings": warnings,
    }


def validate_holdout_high(
    train_scores: pd.Series, test_scores: pd.Series, percentile: float
) -> Dict[str, Any]:
    t_high = percentile_value(train_scores, percentile)
    if t_high is None or test_scores.empty:
        return {
            "train_count": len(train_scores),
            "test_count": len(test_scores),
            "T_high_train": t_high,
            "test_pass_rate": None,
            "note": "测试集为空或无法计算 T_high",
        }
    passed = (test_scores >= t_high).sum()
    return {
        "train_count": len(train_scores),
        "test_count": len(test_scores),
        "T_high_train": t_high,
        "test_pass_rate": float(passed / len(test_scores)),
        "test_pass_count": int(passed),
        "note": "测试集 high+faithful 样本 rerank_score >= T_high 的比例（越高越好）",
    }


def validate_holdout_low(
    train_scores: pd.Series, test_scores: pd.Series, percentile: float
) -> Dict[str, Any]:
    t_low = percentile_value(train_scores, percentile)
    if t_low is None or test_scores.empty:
        return {
            "train_count": len(train_scores),
            "test_count": len(test_scores),
            "T_low_train": t_low,
            "test_pass_rate": None,
            "note": "测试集为空或无法计算 T_low",
        }
    passed = (test_scores <= t_low).sum()
    return {
        "train_count": len(train_scores),
        "test_count": len(test_scores),
        "T_low_train": t_low,
        "test_pass_rate": float(passed / len(test_scores)),
        "test_pass_count": int(passed),
        "note": "测试集 low+refused 样本 rerank_score <= T_low 的比例（越高越好）",
    }


def tier_overlap_note(df: pd.DataFrame) -> str:
    high_min = df.loc[df["tier"] == "high", "top1_rerank_score"].min()
    low_max = df.loc[df["tier"] == "low", "top1_rerank_score"].max()
    if pd.isna(high_min) or pd.isna(low_max):
        return "无法评估 tier 间 rerank 分数重叠。"
    if low_max >= high_min:
        return (
            f"low tier 最高分 ({low_max:.3f}) 与 high tier 最低分 ({high_min:.3f}) 存在重叠；"
            "单靠 rerank 分数无法完全区分，门控须配合拒答模板与 should_refuse 逻辑。"
        )
    return (
        f"low tier 最高分 ({low_max:.3f}) 低于 high tier 最低分 ({high_min:.3f})，"
        "tier 间 rerank 分布有一定分离，但仍建议配合拒答模板。"
    )


def plot_score_distribution(
    df: pd.DataFrame,
    t_high: Optional[float],
    t_low: Optional[float],
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))

    all_scores = df["top1_rerank_score"].dropna()
    if not all_scores.empty:
        bins = np.linspace(all_scores.min(), all_scores.max(), 25)
    else:
        bins = 20

    for tier in ("high", "medium", "low"):
        tier_scores = df.loc[df["tier"] == tier, "top1_rerank_score"].dropna()
        if tier_scores.empty:
            continue
        ax.hist(
            tier_scores,
            bins=bins,
            alpha=0.55,
            label=f"{tier} (n={len(tier_scores)})",
            color=TIER_COLORS.get(tier, "#95a5a6"),
            edgecolor="white",
            linewidth=0.5,
        )

    if t_high is not None:
        ax.axvline(
            t_high,
            color="#27ae60",
            linestyle="--",
            linewidth=2,
            label=f"T_high = {t_high:.3f}",
        )
    if t_low is not None:
        ax.axvline(
            t_low,
            color="#c0392b",
            linestyle="--",
            linewidth=2,
            label=f"T_low = {t_low:.3f}",
        )

    ax.set_xlabel("top1_rerank_score (confidence)")
    ax.set_ylabel("Count")
    ax.set_title("Rerank Score Distribution by Tier")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _fmt(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def build_report_md(
    *,
    input_path: Path,
    config_path: Path,
    percentile: float,
    t_high_stats: Dict[str, Any],
    t_low_stats: Dict[str, Any],
    holdout_high: Optional[Dict[str, Any]],
    holdout_low: Optional[Dict[str, Any]],
    overlap_note: str,
    plot_path: Path,
    json_path: Path,
    all_warnings: List[str],
) -> str:
    t_high = t_high_stats["threshold"]
    t_low = t_low_stats["threshold"]
    lines = [
        "# 置信度阈值校准报告",
        "",
        f"- 生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- 输入: `{input_path}`",
        f"- 配置: `{config_path}`",
        f"- 置信度字段: `top1_rerank_score`",
        f"- 分位数: P{percentile:.0f}",
        "",
        "## 推荐阈值",
        "",
        "| 阈值 | 含义 | 推荐值 | 校准样本数 |",
        "|------|------|--------|------------|",
        f"| **T_high** | tier=high 且 faithfulness≥0.9 的 rerank_score P{percentile:.0f} | "
        f"{_fmt(t_high)} | {t_high_stats['count']} |",
        f"| **T_low** | tier=low 且 should_refuse 且 refused 的 rerank_score P{percentile:.0f}（拒答上界） | "
        f"{_fmt(t_low)} | {t_low_stats['count']} |",
        "",
        "## 方法论",
        "",
        "### 为何使用 P95 而非 max",
        "",
        "使用 P95 而非最大值，是为了避免个别极端样本（检索噪声、RAGAS 打分波动）"
        "把阈值推得过高或过低。P95 在覆盖绝大多数「高置信 faithful」或「应拒且已拒」"
        "样本的同时，保留约 5% 的缓冲，更适合作为线上门控的保守估计。",
        "",
        "### low tier rerank 重叠与门控",
        "",
        overlap_note,
        "",
        "因此 **T_low 仅作拒答上界参考**，线上须同时启用拒答模板（如 config 中 "
        "`refusal_phrase`）与 `should_refuse` 业务规则，不能单靠分数切断。",
        "",
        "## 校准子集统计",
        "",
        "### T_high 子集（tier=high, faithfulness≥0.9）",
        "",
        f"- 样本数: {t_high_stats['count']}",
        f"- min / mean / max: "
        f"{_fmt(t_high_stats['min'])} / {_fmt(t_high_stats['mean'])} / {_fmt(t_high_stats['max'])}",
        "",
        "### T_low 子集（tier=low, should_refuse=true, refused=true）",
        "",
        f"- 样本数: {t_low_stats['count']}",
        f"- min / mean / max: "
        f"{_fmt(t_low_stats['min'])} / {_fmt(t_low_stats['mean'])} / {_fmt(t_low_stats['max'])}",
        "",
    ]

    if holdout_high or holdout_low:
        lines.extend(["## Hold-out 验证（80/20, seed=42）", ""])
        if holdout_high:
            lines.extend(
                [
                    "### T_high",
                    "",
                    f"- 训练集: {holdout_high['train_count']} 条 → T_high_train = "
                    f"{_fmt(holdout_high['T_high_train'])}",
                    f"- 测试集: {holdout_high['test_count']} 条，通过率 = "
                    f"{holdout_high['test_pass_rate']:.1%}"
                    if holdout_high["test_pass_rate"] is not None
                    else "- 测试集: 0 条，通过率 = N/A",
                    f"- 说明: {holdout_high['note']}",
                    "",
                ]
            )
        if holdout_low:
            lines.extend(
                [
                    "### T_low",
                    "",
                    f"- 训练集: {holdout_low['train_count']} 条 → T_low_train = "
                    f"{_fmt(holdout_low['T_low_train'])}",
                    f"- 测试集: {holdout_low['test_count']} 条，通过率 = "
                    f"{holdout_low['test_pass_rate']:.1%}"
                    if holdout_low["test_pass_rate"] is not None
                    else "- 测试集: 0 条，通过率 = N/A",
                    f"- 说明: {holdout_low['note']}",
                    "",
                ]
            )

    if all_warnings:
        lines.extend(["## 警告", ""])
        for w in all_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.extend(
        [
            "## 小样本局限",
            "",
            f"- T_high 校准集仅 **{t_high_stats['count']}** 条（预期约 12 条），"
            "faithfulness 阈值 0.9 进一步缩小样本，P95 对单条样本敏感。",
            f"- T_low 校准集仅 **{t_low_stats['count']}** 条（预期约 5 条），"
            "hold-out 后测试集可能仅 1 条，验证指标仅供参考。",
            "- 建议第 5 批接入 chat.py 前，用更大评测集复校或在 A/B 中微调。",
            "",
            "## 输出文件",
            "",
            f"- 分布图: `{plot_path}`",
            f"- JSON: `{json_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def calibrate(
    df: pd.DataFrame,
    percentile: float,
    holdout: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[str]]:
    high_mask = (df["tier"] == "high") & (df["faithfulness"] >= 0.9)
    low_mask = (df["tier"] == "low") & df["should_refuse"] & df["refused"]

    high_scores = df.loc[high_mask, "top1_rerank_score"]
    low_scores = df.loc[low_mask, "top1_rerank_score"]

    t_high_stats = compute_threshold_stats(high_scores, percentile)
    t_low_stats = compute_threshold_stats(low_scores, percentile)

    all_warnings = list(t_high_stats.get("warnings", [])) + list(t_low_stats.get("warnings", []))

    holdout_high = None
    holdout_low = None
    if holdout:
        train_h, test_h = split_holdout(high_scores)
        train_l, test_l = split_holdout(low_scores)
        holdout_high = validate_holdout_high(train_h, test_h, percentile)
        holdout_low = validate_holdout_low(train_l, test_l, percentile)
        if holdout_high["test_count"] < 3:
            all_warnings.append(
                f"T_high hold-out 测试集仅 {holdout_high['test_count']} 条，验证结果不稳定。"
            )
        if holdout_low["test_count"] < 3:
            all_warnings.append(
                f"T_low hold-out 测试集仅 {holdout_low['test_count']} 条，验证结果不稳定。"
            )

    return t_high_stats, t_low_stats, holdout_high, holdout_low, all_warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 置信度阈值校准（P95 + 分布图）")
    parser.add_argument("--config", default="eval/config.yaml", help="eval/config.yaml 路径")
    parser.add_argument(
        "--input",
        default="eval/outputs/ragas_results.csv",
        help="RAGAS 结果 CSV",
    )
    parser.add_argument("--percentile", type=float, default=95.0, help="分位数（默认 95）")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录（默认 eval/outputs）",
    )
    parser.add_argument(
        "--holdout",
        action="store_true",
        default=True,
        help="启用 80/20 hold-out 验证（默认开启）",
    )
    parser.add_argument(
        "--no-holdout",
        action="store_true",
        help="跳过 hold-out 验证",
    )
    args = parser.parse_args()

    holdout = args.holdout and not args.no_holdout

    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    eval_dir = config_path.parent

    input_path = resolve_input_path(args.input, eval_dir)
    output_dir = Path(args.output_dir) if args.output_dir else eval_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_results(input_path)

    t_high_stats, t_low_stats, holdout_high, holdout_low, all_warnings = calibrate(
        df, args.percentile, holdout
    )

    plot_path = output_dir / "score_distribution.png"
    json_path = output_dir / "threshold_recommendation.json"
    md_path = output_dir / "calibration_report.md"

    plot_score_distribution(
        df,
        t_high_stats["threshold"],
        t_low_stats["threshold"],
        plot_path,
    )

    overlap_note = tier_overlap_note(df)

    result: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "config": str(config_path),
        "confidence_field": "top1_rerank_score",
        "score_field_from_config": config.get("confidence_score_field", "rerank_score"),
        "percentile": args.percentile,
        "T_high": t_high_stats["threshold"],
        "T_low": t_low_stats["threshold"],
        "samples": {
            "total_rows": len(df),
            "high_faithful_gte_0_9": t_high_stats["count"],
            "low_should_refuse_and_refused": t_low_stats["count"],
            "by_tier": df["tier"].value_counts().to_dict(),
        },
        "T_high_stats": {k: v for k, v in t_high_stats.items() if k != "warnings"},
        "T_low_stats": {k: v for k, v in t_low_stats.items() if k != "warnings"},
        "tier_overlap_note": overlap_note,
        "warnings": all_warnings,
        "outputs": {
            "plot": str(plot_path),
            "json": str(json_path),
            "report_md": str(md_path),
        },
    }
    if holdout:
        result["holdout"] = {
            "train_ratio": HOLDOUT_TRAIN_RATIO,
            "seed": HOLDOUT_SEED,
            "T_high": holdout_high,
            "T_low": holdout_low,
        }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    report_md = build_report_md(
        input_path=input_path,
        config_path=config_path,
        percentile=args.percentile,
        t_high_stats=t_high_stats,
        t_low_stats=t_low_stats,
        holdout_high=holdout_high,
        holdout_low=holdout_low,
        overlap_note=overlap_note,
        plot_path=plot_path,
        json_path=json_path,
        all_warnings=all_warnings,
    )
    md_path.write_text(report_md, encoding="utf-8")

    print(f"[ok] T_high = {t_high_stats['threshold']:.4f} (n={t_high_stats['count']})")
    print(f"[ok] T_low  = {t_low_stats['threshold']:.4f} (n={t_low_stats['count']})")
    if all_warnings:
        print("[warn]")
        for w in all_warnings:
            print(f"  - {w}")
    print(f"[ok] 分布图: {plot_path}")
    print(f"[ok] JSON:   {json_path}")
    print(f"[ok] 报告:   {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
