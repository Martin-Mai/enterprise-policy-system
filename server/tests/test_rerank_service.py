"""Cross-Encoder rerank_service 单元测试（mock transformers，不下载真实模型）"""

from __future__ import annotations

import sys
from functools import wraps
from typing import Any, Callable, List, TypeVar
from unittest.mock import MagicMock, patch

import pytest

import app.services.rerank_service as rerank_module
from app.core.config import settings
from app.services.rerank_service import get_reranker, rerank_candidates, resolve_rerank_device


def _make_candidates(count: int) -> List[dict[str, Any]]:
    return [
        {
            "chunk_id": str(i),
            "text": f"child chunk text {i}",
            "final_rrf_score": round(0.01 * (count - i), 6),
        }
        for i in range(count)
    ]


@pytest.fixture(autouse=True)
def _reset_reranker_state() -> None:
    rerank_module._reranker = None
    rerank_module._reranker_load_attempted = False


class _MockLogits:
    def __init__(self, scores: List[float]) -> None:
        self._scores = scores

    def view(self, *_args: Any) -> "_MockLogits":
        return self

    def float(self) -> "_MockLogits":
        return self

    def tolist(self) -> List[float]:
        return self._scores


class _MockModelOutput:
    def __init__(self, scores: List[float]) -> None:
        self.logits = _MockLogits(scores)


class _MockModel:
    def __init__(self, scores: List[float] | None = None, *, raise_on_forward: bool = False) -> None:
        self._scores = scores or []
        self._raise_on_forward = raise_on_forward

    def eval(self) -> "_MockModel":
        return self

    def to(self, _device: str) -> "_MockModel":
        return self

    def __call__(self, **_kwargs: Any) -> _MockModelOutput:
        if self._raise_on_forward:
            raise RuntimeError("mock inference failure")
        return _MockModelOutput(self._scores)


class _MockTensor:
    def to(self, _device: str) -> "_MockTensor":
        return self


class _MockTokenizer:
    def __call__(self, pairs: List[List[str]], **_kwargs: Any) -> dict[str, Any]:
        return {"input_ids": _MockTensor()}


F = TypeVar("F", bound=Callable[..., Any])


def _patch_transformers(scores: List[float] | None = None, *, raise_on_forward: bool = False) -> Callable[[F], F]:
    mock_model = _MockModel(scores, raise_on_forward=raise_on_forward)
    mock_tokenizer = _MockTokenizer()
    fake_transformers = MagicMock()
    fake_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
    fake_transformers.AutoModelForSequenceClassification.from_pretrained.return_value = mock_model

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with patch.dict(sys.modules, {"transformers": fake_transformers}):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def _install_fake_torch(monkeypatch: pytest.MonkeyPatch, *, cuda_available: bool) -> None:
    fake_cuda = MagicMock()
    fake_cuda.is_available.return_value = cuda_available
    fake_torch = MagicMock()
    fake_torch.cuda = fake_cuda
    fake_torch.float16 = "float16"
    fake_torch.float32 = "float32"
    monkeypatch.setitem(sys.modules, "torch", fake_torch)


class TestRerankCandidates:
    def test_empty_candidates(self) -> None:
        assert rerank_candidates("query", [], top_k=5) == []

    def test_candidates_lte_top_k_no_crash(self) -> None:
        candidates = _make_candidates(3)
        result = rerank_candidates("query", candidates, top_k=5)

        assert len(result) == 3
        for item in result:
            assert item["rerank_score"] == item["final_rrf_score"]

    def test_disabled_falls_back_to_rrf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "RERANK_ENABLED", False)
        candidates = _make_candidates(6)

        result = rerank_candidates("query", candidates, top_k=3)

        assert len(result) == 3
        assert [item["chunk_id"] for item in result] == ["0", "1", "2"]
        assert "rerank_score" not in result[0]

    def test_get_reranker_none_falls_back_to_rrf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "RERANK_ENABLED", True)
        monkeypatch.setattr(rerank_module, "get_reranker", lambda: None)
        candidates = _make_candidates(6)

        result = rerank_candidates("query", candidates, top_k=2)

        assert len(result) == 2
        assert [item["chunk_id"] for item in result] == ["0", "1"]

    def test_inference_exception_falls_back_to_rrf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "RERANK_ENABLED", True)
        mock_model = _MockModel(raise_on_forward=True)
        mock_tokenizer = _MockTokenizer()
        monkeypatch.setattr(rerank_module, "get_reranker", lambda: (mock_tokenizer, mock_model, "cpu"))
        candidates = _make_candidates(5)

        result = rerank_candidates("query", candidates, top_k=2)

        assert len(result) == 2
        assert [item["chunk_id"] for item in result] == ["0", "1"]

    def test_mock_logits_write_rerank_score_and_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "RERANK_ENABLED", True)
        candidates = _make_candidates(4)
        # RRF 顺序 0>1>2>3，mock logits 让 chunk 2 排第一
        mock_scores = [0.2, 0.5, 0.9, 0.1]
        mock_model = _MockModel(mock_scores)
        mock_tokenizer = _MockTokenizer()
        monkeypatch.setattr(rerank_module, "get_reranker", lambda: (mock_tokenizer, mock_model, "cpu"))
        monkeypatch.setattr(
            rerank_module,
            "_score_batch",
            lambda _tokenizer, _model, _device, _query, doc_texts: mock_scores[: len(doc_texts)],
        )

        result = rerank_candidates("query", candidates, top_k=2)

        assert len(result) == 2
        assert result[0]["chunk_id"] == "2"
        assert result[0]["rerank_score"] == pytest.approx(0.9)
        assert result[1]["chunk_id"] == "1"
        assert result[1]["rerank_score"] == pytest.approx(0.5)


class TestGetReranker:
    def test_disabled_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "RERANK_ENABLED", False)
        assert get_reranker() is None

    @_patch_transformers()
    def test_load_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_torch(monkeypatch, cuda_available=False)
        monkeypatch.setattr(settings, "RERANK_ENABLED", True)
        monkeypatch.setattr(settings, "RERANK_MODEL", "mock/bge-reranker")
        monkeypatch.setattr(settings, "RERANK_DEVICE", "cpu")

        pair = get_reranker()

        assert pair is not None
        tokenizer, model, device = pair
        assert device == "cpu"
        assert get_reranker() is pair


class TestResolveRerankDevice:
    def test_force_cpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_torch(monkeypatch, cuda_available=True)
        monkeypatch.setattr(settings, "RERANK_DEVICE", "cpu")
        assert resolve_rerank_device() == "cpu"

    def test_auto_uses_cuda_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_torch(monkeypatch, cuda_available=True)
        monkeypatch.setattr(settings, "RERANK_DEVICE", "auto")
        assert resolve_rerank_device() == "cuda"

    def test_auto_falls_back_cpu_when_cuda_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_torch(monkeypatch, cuda_available=False)
        monkeypatch.setattr(settings, "RERANK_DEVICE", "auto")
        assert resolve_rerank_device() == "cpu"

    def test_force_cuda_when_unavailable_falls_back_cpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_torch(monkeypatch, cuda_available=False)
        monkeypatch.setattr(settings, "RERANK_DEVICE", "cuda")
        assert resolve_rerank_device() == "cpu"
