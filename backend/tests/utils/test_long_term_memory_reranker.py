"""Tests for backend.utils.long_term_memory_reranker."""

import time
from types import SimpleNamespace

from backend.utils.long_term_memory_reranker import rerank_store_memory_items


def _item(value: dict, score: float | None = None, key: str = "k"):
    return SimpleNamespace(value=value, score=score, key=key)


class TestLongTermMemoryReranker:
    def test_explicit_memory_gets_priority(self):
        now = time.time()
        items = [
            _item(
                {
                    "type": "visitor_name",
                    "data": "田中",
                    "confidence": 0.9,
                    "timestamp": now - 3600,
                },
                score=0.7,
                key="a",
            ),
            _item(
                {
                    "type": "explicit_remember",
                    "data": "火曜に来る",
                    "confidence": 1.0,
                    "timestamp": now - 60,
                },
                score=0.7,
                key="b",
            ),
        ]
        ranked = rerank_store_memory_items("覚えている？火曜", items)
        assert ranked[0].key == "b"

    def test_very_fresh_non_explicit_can_be_dampened(self):
        now = time.time()
        items = [
            _item(
                {
                    "type": "visitor_affiliation",
                    "data": "Acme",
                    "confidence": 0.8,
                    "timestamp": now - 10,
                },
                score=0.8,
                key="new",
            ),
            _item(
                {
                    "type": "visitor_affiliation",
                    "data": "Acme",
                    "confidence": 0.8,
                    "timestamp": now - 7200,
                    "source": "promoter",
                    "promotion": {"candidate_count": 2, "repeat_count_sum": 2},
                },
                score=0.8,
                key="stable",
            ),
        ]
        ranked = rerank_store_memory_items("Acme", items)
        assert ranked[0].key == "stable"
