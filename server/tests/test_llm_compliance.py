"""数值合规安全垫单元测试（天数额度 / 幻觉扣减）"""

from typing import Any, Dict, List

from app.services.llm import (
    _correction_baseline_for,
    validate_unauthorized_deduction,
)


def _chunks(text: str) -> List[Dict[str, Any]]:
    return [{"text": text}]


class TestCorrectionBaselineFor:
    def test_picks_nearest_higher_tier(self) -> None:
        assert _correction_baseline_for(7.0, [5.0, 10.0, 15.0]) == 10.0

    def test_falls_back_to_max_when_no_higher_tier(self) -> None:
        assert _correction_baseline_for(20.0, [5.0, 10.0, 15.0]) == 15.0


class TestValidateUnauthorizedDeduction:
    QUERY = "我工龄12年，今年从未休过年假，请问能休几天？"

    def test_tiered_policy_correct_answer_not_intercepted(self) -> None:
        chunk_text = (
            "满1年者可享受5天年假。"
            "满10年者可享受10天年假。"
            "满20年者可享受15天年假。"
        )
        answer = "您本年度尚未休过年假，因此可全额享受制度规定的10天年假。"

        intercepted, suffix = validate_unauthorized_deduction(
            self.QUERY,
            _chunks(chunk_text),
            answer,
        )

        assert intercepted is False
        assert suffix == ""

    def test_single_tier_hallucinated_deduction_intercepted(self) -> None:
        chunk_text = "员工工龄满10年者，每年可享受10天法定年假。"
        answer = "您目前剩余5天年假。"

        intercepted, suffix = validate_unauthorized_deduction(
            self.QUERY,
            _chunks(chunk_text),
            answer,
        )

        assert intercepted is True
        assert "10" in suffix
        assert "无需扣减" in suffix

    def test_multi_tier_phantom_day_uses_nearest_tier_not_max(self) -> None:
        chunk_text = (
            "满1年者可享受5天年假。"
            "满10年者可享受10天年假。"
            "满20年者可享受15天年假。"
        )
        answer = "根据制度，您目前可休7天年假。"

        intercepted, suffix = validate_unauthorized_deduction(
            self.QUERY,
            _chunks(chunk_text),
            answer,
        )

        assert intercepted is True
        assert "10" in suffix
        assert "15" not in suffix

    def test_valid_lower_tier_in_baselines_not_intercepted(self) -> None:
        chunk_text = (
            "满1年者可享受5天年假。"
            "满10年者可享受10天年假。"
        )
        answer = "您可享有5天年假。"

        intercepted, suffix = validate_unauthorized_deduction(
            "工龄3年，从未休年假",
            _chunks(chunk_text),
            answer,
        )

        assert intercepted is False
        assert suffix == ""

    def test_skipped_when_deduction_evidence_in_chunks(self) -> None:
        chunk_text = "每年10天年假，已休3天，剩余7天。"
        answer = "您剩余7天年假。"

        intercepted, suffix = validate_unauthorized_deduction(
            self.QUERY,
            _chunks(chunk_text),
            answer,
        )

        assert intercepted is False
        assert suffix == ""
