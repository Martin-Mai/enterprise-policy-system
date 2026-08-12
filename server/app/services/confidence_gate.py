"""
RAG 置信度门控模块
基于 top1 rerank/RRF 分数划分 normal / cautious / refuse 三档决策
"""

from typing import Any, Dict, List, Literal, Optional

GateDecision = Literal["normal", "cautious", "refuse"]

REFUSAL_MESSAGE = "未找到相关信息"


def extract_top1_score(
    chunks: List[Dict[str, Any]],
    score_field: str = "rerank_score",
) -> Optional[float]:
    """
    从检索 Top-1 分块提取置信度分数。

    优先使用 score_field；缺失时依次 fallback rerank_score、final_rrf_score。
    """
    if not chunks:
        return None

    top = chunks[0]
    candidates = [score_field, "rerank_score", "final_rrf_score"]
    seen: set[str] = set()
    for key in candidates:
        if key in seen:
            continue
        seen.add(key)
        if key not in top or top[key] is None:
            continue
        try:
            return float(top[key])
        except (TypeError, ValueError):
            continue
    return None


def decide_gate(
    score: Optional[float],
    has_chunks: bool,
    t_high: float,
    t_low: float,
) -> GateDecision:
    """
    根据分数与检索结果决定门控档位。

    - retrieved_chunks 为空，或 score < T_low → refuse
    - T_low <= score < T_high → cautious
    - score >= T_high → normal

    T_high 仅区分 normal/cautious，score >= T_low 但 < T_high 不会拒答。
    """
    if not has_chunks:
        return "refuse"
    if score is None:
        return "cautious"
    if score < t_low:
        return "refuse"
    if score >= t_high:
        return "normal"
    return "cautious"
