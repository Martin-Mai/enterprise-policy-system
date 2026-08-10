"""
Cross-Encoder 精排服务
使用 HuggingFace transformers 本地加载 BGE reranker，对粗排候选重新打分。
加载失败或推理异常时降级为 RRF 排序，不抛出未捕获异常。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

_reranker: Optional[Tuple[Any, Any, str]] = None
_reranker_load_attempted: bool = False


def resolve_rerank_device() -> str:
    """根据配置与 torch CUDA 可用性选择推理设备。"""
    import torch

    requested = settings.RERANK_DEVICE.strip().lower()
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if torch.cuda.is_available():
            return "cuda"
        logger.warning("[Rerank] RERANK_DEVICE=cuda 但 CUDA 不可用，降级 cpu")
        return "cpu"
    if requested not in ("auto", ""):
        logger.warning("[Rerank] 未知 RERANK_DEVICE=%r，使用 auto", settings.RERANK_DEVICE)
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_reranker() -> Optional[Tuple[Any, Any, str]]:
    """懒加载单例：(AutoTokenizer, AutoModelForSequenceClassification, device) 或 None。"""
    global _reranker, _reranker_load_attempted

    if not settings.RERANK_ENABLED:
        return None

    if _reranker is not None:
        return _reranker

    if _reranker_load_attempted:
        return None

    _reranker_load_attempted = True

    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        device = resolve_rerank_device()
        dtype = torch.float16 if device == "cuda" else torch.float32

        tokenizer = AutoTokenizer.from_pretrained(settings.RERANK_MODEL)
        model = AutoModelForSequenceClassification.from_pretrained(
            settings.RERANK_MODEL,
            dtype=dtype,
        )
        model.eval()
        model.to(device)

        _reranker = (tokenizer, model, device)
        logger.info(
            "[Rerank] 模型加载完成: %s | device=%s | dtype=%s",
            settings.RERANK_MODEL,
            device,
            dtype,
        )
        return _reranker
    except Exception:
        logger.exception("[Rerank] 模型加载失败: %s", settings.RERANK_MODEL)
        return None


def _fallback_rrf_select(candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """按 final_rrf_score 降序取 top_k，与 _select_for_llm 行为一致。"""
    sorted_candidates = sorted(
        candidates,
        key=lambda item: item.get("final_rrf_score", 0.0),
        reverse=True,
    )
    return sorted_candidates[:top_k]


def _score_batch(
    tokenizer: Any,
    model: Any,
    device: str,
    query: str,
    doc_texts: List[str],
) -> List[float]:
    import torch

    pairs = [[query, doc] for doc in doc_texts]
    inputs = tokenizer(
        pairs,
        padding=True,
        truncation=True,
        max_length=settings.RERANK_MAX_LENGTH,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs, return_dict=True).logits.view(-1).float()
    return logits.tolist()


def rerank_candidates(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    """
    对粗排候选做 Cross-Encoder 精排，返回 top_k 条。
    candidates 中 text 字段应为 child chunk 正文（enrich 前传入）。
    """
    if not candidates:
        return []

    if len(candidates) <= top_k:
        for item in candidates:
            item["rerank_score"] = item.get("final_rrf_score", 0.0)
        return candidates

    reranker = get_reranker()
    if reranker is None:
        return _fallback_rrf_select(candidates, top_k)

    tokenizer, model, device = reranker

    try:
        doc_texts = [
            str(item.get("text", ""))[: settings.RERANK_MAX_CHARS]
            for item in candidates
        ]
        scores = _score_batch(tokenizer, model, device, query, doc_texts)

        scored: List[Dict[str, Any]] = []
        for item, score in zip(candidates, scores):
            row = dict(item)
            row["rerank_score"] = float(score)
            scored.append(row)

        scored.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        selected = scored[:top_k]

        top1_score = selected[0].get("rerank_score", 0.0) if selected else 0.0
        logger.info(
            "[Rerank] candidates=%d top_k=%d top1_score=%.4f | device=%s",
            len(candidates),
            top_k,
            top1_score,
            device,
        )
        return selected
    except Exception:
        logger.exception("[Rerank] 推理异常，降级 RRF 排序")
        return _fallback_rrf_select(candidates, top_k)
