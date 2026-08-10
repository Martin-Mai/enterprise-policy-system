"""检索 enrich 与 RAG prompt 单元测试"""

from app.core.config import settings
from app.services.chat_service import _truncate_for_prompt, build_rag_prompt, parse_citations
from app.services.search_service import BM25Index, _enrich_results


class _StubBM25Index:
    def __init__(
        self,
        chunk_info: dict | None = None,
        parent_text: str | None = None,
    ) -> None:
        self._chunk_info = chunk_info
        self._parent_text = parent_text

    def get_chunk_info(self, chunk_id: str):
        return self._chunk_info

    def get_parent_text(self, doc_id: int, parent_chunk_index: int):
        return self._parent_text


class TestEnrichResults:
    def test_flat_mode_output_unchanged(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "flat")

        fused = [{
            "chunk_id": "42",
            "final_rrf_score": 0.012345,
            "text": "flat chunk text content here",
            "metadata": {"file_name": "制度.pdf", "page_no": 3, "section_title": "第二章"},
        }]
        index = _StubBM25Index(chunk_info={
            "text": "flat chunk text content here",
            "doc_id": 1,
            "file_name": "制度.pdf",
            "page_no": 3,
            "section_title": "第二章",
        })

        enriched = _enrich_results(fused, index)

        assert enriched == [{
            "chunk_id": "42",
            "text": "flat chunk text content here",
            "final_rrf_score": 0.012345,
            "file_name": "制度.pdf",
            "page_no": 3,
            "section_title": "第二章",
        }]
        assert "child_text" not in enriched[0]

    def test_parent_child_resolves_parent_text(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "parent_child")

        fused = [{
            "chunk_id": "99",
            "final_rrf_score": 0.02,
            "text": "child snippet",
            "metadata": {
                "doc_id": 1,
                "parent_chunk_index": 0,
                "chunk_role": "child",
            },
        }]
        index = _StubBM25Index(
            chunk_info={
                "text": "child snippet",
                "doc_id": 1,
                "parent_chunk_index": 0,
                "chunk_role": "child",
                "file_name": "制度.pdf",
                "page_no": 2,
                "section_title": "第一章",
            },
            parent_text="parent full context with more details",
        )

        enriched = _enrich_results(fused, index)

        assert enriched[0]["text"] == "parent full context with more details"
        assert enriched[0]["child_text"] == "child snippet"
        assert enriched[0]["chunk_role"] == "child"
        assert enriched[0]["parent_chunk_index"] == 0


class TestChatPromptAndCitations:
    def test_truncate_long_parent_text(self) -> None:
        long_text = "制" * 2500
        truncated = _truncate_for_prompt(long_text)
        assert len(truncated) == 2000 + len("…（节选）")
        assert truncated.endswith("…（节选）")

    def test_build_rag_prompt_uses_truncated_text(self) -> None:
        chunks = [{
            "file_name": "制度.pdf",
            "page_no": 1,
            "text": "制" * 2500,
        }]
        prompt = build_rag_prompt("问题？", "", chunks)
        assert "…（节选）" in prompt
        assert "制" * 2500 not in prompt

    def test_parse_citations_prefers_child_text(self) -> None:
        chunks = [{
            "chunk_id": "1",
            "file_name": "制度.pdf",
            "page_no": 1,
            "section_title": "第一章",
            "text": "parent " + "P" * 300,
            "child_text": "child " + "C" * 50,
        }]
        citations = parse_citations("答案引用[1]", chunks)
        assert citations[0]["text_preview"].startswith("child ")

    def test_parse_citations_falls_back_to_text(self) -> None:
        chunks = [{
            "chunk_id": "1",
            "file_name": "制度.pdf",
            "page_no": 1,
            "section_title": "第一章",
            "text": "flat chunk preview text",
        }]
        citations = parse_citations("答案[1]", chunks)
        assert citations[0]["text_preview"] == "flat chunk preview text"[:200]
