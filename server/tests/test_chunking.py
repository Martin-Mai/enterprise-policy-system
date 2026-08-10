"""分块策略单元测试（flat / parent_child）"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.document_processor import split_text_segments
from app.services.search_service import _enrich_results


def _make_segment(
    text: str,
    page_no: int = 1,
    section_title: str = "第一章",
) -> dict:
    return {"text": text, "page_no": page_no, "section_title": section_title}


def _long_text(length: int, char: str = "制") -> str:
    return char * length


class _MockDbBm25Index:
    """模拟 BM25Index refresh 后的 child 元数据与 parent 缓存（等同 MySQL 回填源）"""

    def __init__(
        self,
        child_info_by_id: dict[str, dict],
        parent_cache: dict[tuple[int, int], str],
    ) -> None:
        self._child_info_by_id = child_info_by_id
        self._parent_cache = parent_cache

    def get_chunk_info(self, chunk_id: str):
        return self._child_info_by_id.get(chunk_id)

    def get_parent_text(self, doc_id: int, parent_chunk_index: int):
        return self._parent_cache.get((doc_id, parent_chunk_index))


class TestFlatChunking:
    def test_default_config_matches_500_50(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "CHUNK_SIZE", 500)
        monkeypatch.setattr(settings, "CHUNK_OVERLAP", 50)
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "flat")

        text = _long_text(1200)
        segments = [_make_segment(text)]

        expected = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
        ).split_text(text)
        expected = [piece.strip() for piece in expected if piece.strip()]

        chunks = split_text_segments(segments)
        assert [chunk["chunk_text"] for chunk in chunks] == expected

    def test_chunk_count_and_max_length(self, monkeypatch) -> None:
        chunk_size = 500
        monkeypatch.setattr(settings, "CHUNK_SIZE", chunk_size)
        monkeypatch.setattr(settings, "CHUNK_OVERLAP", 50)
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "flat")

        text = _long_text(1500)
        chunks = split_text_segments([_make_segment(text)])

        assert len(chunks) >= 2
        assert all(len(chunk["chunk_text"]) <= chunk_size for chunk in chunks)

    def test_inherits_segment_metadata(self) -> None:
        chunks = split_text_segments([
            _make_segment("短文本", page_no=3, section_title="第三条"),
        ])

        assert len(chunks) == 1
        assert chunks[0]["page_no"] == 3
        assert chunks[0]["section_title"] == "第三条"
        assert chunks[0]["chunk_index"] == 0
        assert "chunk_role" not in chunks[0]


class TestParentChildChunking:
    def test_single_segment_produces_parent_then_children(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "parent_child")
        monkeypatch.setattr(settings, "PARENT_CHUNK_SIZE", 1500)
        monkeypatch.setattr(settings, "CHILD_CHUNK_SIZE", 300)
        monkeypatch.setattr(settings, "CHILD_CHUNK_OVERLAP", 30)

        text = _long_text(2000)
        chunks = split_text_segments([_make_segment(text, page_no=2, section_title="第二章")])

        parents = [c for c in chunks if c["chunk_role"] == "parent"]
        children = [c for c in chunks if c["chunk_role"] == "child"]

        assert len(parents) == 2
        assert len(children) >= 5
        assert all(len(p["chunk_text"]) <= 1500 for p in parents)
        assert all(len(c["chunk_text"]) <= 300 for c in children)
        assert parents[0]["parent_chunk_index"] == 0
        assert parents[1]["parent_chunk_index"] == 1
        assert all(c["parent_chunk_index"] in (0, 1) for c in children)
        assert all(c["page_no"] == 2 for c in chunks)
        assert all(c["section_title"] == "第二章" for c in chunks)

        # 写入顺序：P0 → children → P1 → children
        first_parent_idx = next(i for i, c in enumerate(chunks) if c["chunk_role"] == "parent")
        assert chunks[first_parent_idx]["parent_chunk_index"] == 0
        assert chunks[first_parent_idx + 1]["chunk_role"] == "child"
        assert chunks[first_parent_idx + 1]["parent_chunk_index"] == 0

    def test_parent_chunk_index_increments_across_doc(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "parent_child")
        monkeypatch.setattr(settings, "PARENT_CHUNK_SIZE", 500)
        monkeypatch.setattr(settings, "CHILD_CHUNK_SIZE", 200)
        monkeypatch.setattr(settings, "CHILD_CHUNK_OVERLAP", 20)

        segments = [
            _make_segment(_long_text(400), page_no=1),
            _make_segment(_long_text(400), page_no=2),
        ]
        chunks = split_text_segments(segments)
        parent_indices = [
            c["parent_chunk_index"]
            for c in chunks
            if c["chunk_role"] == "parent"
        ]
        assert parent_indices == [0, 1]

    def test_child_count_gte_parent_and_all_children_have_parent_index(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "parent_child")
        monkeypatch.setattr(settings, "PARENT_CHUNK_SIZE", 1500)
        monkeypatch.setattr(settings, "CHILD_CHUNK_SIZE", 300)
        monkeypatch.setattr(settings, "CHILD_CHUNK_OVERLAP", 30)

        segments = [
            _make_segment(_long_text(800)),
            _make_segment(_long_text(2000)),
            _make_segment("短条款文本"),
        ]
        chunks = split_text_segments(segments)
        parents = [c for c in chunks if c["chunk_role"] == "parent"]
        children = [c for c in chunks if c["chunk_role"] == "child"]

        assert len(parents) >= 1
        assert len(children) >= len(parents)
        for child in children:
            assert "parent_chunk_index" in child
            assert isinstance(child["parent_chunk_index"], int)
            assert child["parent_chunk_index"] >= 0

    def test_enrich_child_hit_returns_parent_text_from_mock_db(
        self, monkeypatch
    ) -> None:
        """命中 child 时，enrich 通过 (doc_id, parent_chunk_index) 回填 parent 文本"""
        monkeypatch.setattr(settings, "CHUNK_STRATEGY", "parent_child")

        child_snippet = "满10年者可享受10天年假。"
        parent_full = child_snippet + "满20年者可享受15天年假。" + "补充说明。" * 50
        mock_index = _MockDbBm25Index(
            child_info_by_id={
                "101": {
                    "text": child_snippet,
                    "doc_id": 5,
                    "parent_chunk_index": 0,
                    "chunk_role": "child",
                    "file_name": "年假制度.pdf",
                    "page_no": 3,
                    "section_title": "第二章",
                },
            },
            parent_cache={(5, 0): parent_full},
        )
        fused = [{
            "chunk_id": "101",
            "final_rrf_score": 0.015,
            "text": child_snippet,
            "metadata": {
                "doc_id": 5,
                "parent_chunk_index": 0,
                "chunk_role": "child",
                "file_name": "年假制度.pdf",
                "page_no": 3,
                "section_title": "第二章",
            },
        }]

        enriched = _enrich_results(fused, mock_index)

        assert len(enriched) == 1
        assert enriched[0]["text"] == parent_full
        assert enriched[0]["child_text"] == child_snippet
        assert enriched[0]["chunk_role"] == "child"
        assert enriched[0]["parent_chunk_index"] == 0
        assert enriched[0]["file_name"] == "年假制度.pdf"

