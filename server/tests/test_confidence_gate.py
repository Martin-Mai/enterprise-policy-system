"""置信度门控单元测试"""

from app.services.confidence_gate import (
    REFUSAL_MESSAGE,
    decide_gate,
    extract_top1_score,
)

T_HIGH = 6.3734
T_LOW = -3.6671


class TestDecideGate:
    def test_score_below_t_low_refuse(self) -> None:
        assert decide_gate(-5.0, True, T_HIGH, T_LOW) == "refuse"

    def test_score_at_t_low_cautious(self) -> None:
        assert decide_gate(T_LOW, True, T_HIGH, T_LOW) == "cautious"

    def test_score_mid_range_cautious(self) -> None:
        assert decide_gate(0.0, True, T_HIGH, T_LOW) == "cautious"

    def test_score_just_below_t_high_cautious(self) -> None:
        assert decide_gate(6.0, True, T_HIGH, T_LOW) == "cautious"

    def test_score_at_t_high_normal(self) -> None:
        assert decide_gate(T_HIGH, True, T_HIGH, T_LOW) == "normal"

    def test_score_above_t_high_normal(self) -> None:
        assert decide_gate(7.0, True, T_HIGH, T_LOW) == "normal"

    def test_empty_chunks_refuse(self) -> None:
        assert decide_gate(7.0, False, T_HIGH, T_LOW) == "refuse"

    def test_empty_chunks_ignores_score(self) -> None:
        assert decide_gate(-10.0, False, T_HIGH, T_LOW) == "refuse"

    def test_none_score_with_chunks_cautious(self) -> None:
        assert decide_gate(None, True, T_HIGH, T_LOW) == "cautious"

    def test_t_high_does_not_trigger_refuse(self) -> None:
        """score < T_high 但 >= T_low 应走 cautious，不能拒答"""
        assert decide_gate(1.0, True, T_HIGH, T_LOW) == "cautious"
        assert decide_gate(T_HIGH - 0.01, True, T_HIGH, T_LOW) == "cautious"


class TestExtractTop1Score:
    def test_prefers_configured_score_field(self) -> None:
        chunks = [{"rerank_score": 1.0, "final_rrf_score": 0.01}]
        assert extract_top1_score(chunks, "rerank_score") == 1.0

    def test_fallback_to_final_rrf_when_rerank_missing(self) -> None:
        chunks = [{"final_rrf_score": 0.012345}]
        assert extract_top1_score(chunks, "rerank_score") == 0.012345

    def test_fallback_when_configured_field_missing(self) -> None:
        chunks = [{"rerank_score": 3.5, "final_rrf_score": 0.02}]
        assert extract_top1_score(chunks, "unknown_field") == 3.5

    def test_empty_chunks_returns_none(self) -> None:
        assert extract_top1_score([], "rerank_score") is None

    def test_uses_top1_only(self) -> None:
        chunks = [
            {"rerank_score": 5.0},
            {"rerank_score": 9.0},
        ]
        assert extract_top1_score(chunks, "rerank_score") == 5.0

    def test_invalid_score_skips_to_next_field(self) -> None:
        chunks = [{"rerank_score": "bad", "final_rrf_score": 0.5}]
        assert extract_top1_score(chunks, "rerank_score") == 0.5


class TestRefusalMessage:
    def test_refusal_message_constant(self) -> None:
        assert REFUSAL_MESSAGE == "未找到相关信息"
