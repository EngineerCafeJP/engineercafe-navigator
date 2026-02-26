"""Tests for backend.services.memory_promoter."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.memory_promoter import MemoryPromoter


def _item(key: str, value: dict, score: float | None = None):
    return SimpleNamespace(key=key, value=value, score=score)


class TestMemoryPromoterAggregation:
    def test_aggregate_candidates_merges_same_type_and_content(self):
        items = [
            _item("k1", {"candidate_type": "visitor_name", "content": "田中", "confidence": 0.9}),
            _item("k2", {"candidate_type": "visitor_name", "content": "田中", "confidence": 0.8}),
        ]
        grouped = MemoryPromoter.aggregate_candidates(items)
        assert len(grouped) == 1
        aggregate = next(iter(grouped.values()))
        assert aggregate["candidate_count"] == 2
        assert aggregate["confidence_max"] == 0.9
        assert aggregate["confidence_avg"] == pytest.approx(0.85)

    def test_should_promote_explicit_remember(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "explicit_remember",
                "candidate_count": 1,
                "repeat_count_sum": 1,
                "confidence_max": 1.0,
                "confidence_avg": 1.0,
            }
        )
        assert decision.promote is True
        assert decision.reason == "explicit_remember"

    def test_should_not_promote_single_non_explicit(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "visitor_affiliation",
                "candidate_count": 1,
                "repeat_count_sum": 1,
                "confidence_max": 0.95,
                "confidence_avg": 0.95,
            }
        )
        assert decision.promote is False
        assert decision.reason == "insufficient_repetition"


class TestMemoryPromoterService:
    @pytest.mark.asyncio
    async def test_promote_for_user_promotes_repeated_candidate(self):
        promoter = MemoryPromoter()
        store = AsyncMock()

        candidate_items = [
            _item("c1", {"candidate_type": "visitor_name", "content": "田中", "confidence": 0.9}),
            _item("c2", {"candidate_type": "visitor_name", "content": "田中", "confidence": 0.92}),
        ]
        store.asearch = AsyncMock(side_effect=[candidate_items, []])  # candidates, existing
        store.aput = AsyncMock()

        stats = await promoter.promote_for_user(store, "u1")

        assert stats["promoted"] == 1
        store.aput.assert_called_once()
        ns, key, payload = store.aput.await_args.args
        assert ns == ("visitor_memories", "u1")
        assert isinstance(key, str)
        assert payload["type"] == "visitor_name"
        assert payload["data"] == "田中"
        assert payload["source"] == "promoter"
        assert payload["promotion"]["candidate_count"] == 2

    @pytest.mark.asyncio
    async def test_promote_for_user_skips_duplicate_existing(self):
        promoter = MemoryPromoter()
        store = AsyncMock()

        candidate_items = [
            _item(
                "c1",
                {
                    "candidate_type": "explicit_remember",
                    "content": "火曜に来る",
                    "confidence": 1.0,
                },
            )
        ]
        existing_items = [_item("e1", {"type": "explicit_remember", "data": "火曜に来る"})]
        store.asearch = AsyncMock(side_effect=[candidate_items, existing_items])
        store.aput = AsyncMock()

        stats = await promoter.promote_for_user(store, "u2")

        assert stats["promoted"] == 0
        assert stats["duplicates_skipped"] == 1
        store.aput.assert_not_called()
