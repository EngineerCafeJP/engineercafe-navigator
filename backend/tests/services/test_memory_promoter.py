"""Tests for backend.services.memory_promoter."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.memory_promoter import (
    MemoryPromoter,
    get_memory_promoter,
    reset_memory_promoter,
)


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
                "content": "火曜に来る",
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

    def test_visitor_name_high_confidence_single_mention_promoted(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "visitor_name",
                "candidate_count": 1,
                "repeat_count_sum": 1,
                "confidence_max": 0.9,
                "confidence_avg": 0.9,
            }
        )
        assert decision.promote is True
        assert decision.reason == "visitor_name_high_confidence"

    def test_explicit_keyword_in_evidence_promoted(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "visitor_name",
                "content": "田中花子",
                "candidate_count": 1,
                "repeat_count_sum": 1,
                "confidence_max": 0.85,
                "confidence_avg": 0.85,
                "evidence_queries": ["私の名前は田中花子です。覚えてください。"],
            }
        )
        assert decision.promote is True
        assert decision.reason == "explicit_remember"


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


class TestNFKCNormalization:
    """NFKC正規化のテスト"""

    def test_fullwidth_halfwidth_unified(self):
        """全角・半角が同じagg_keyに統一される"""
        items = [
            _item("k1", {"candidate_type": "visitor_name", "content": "ＡＢＣ", "confidence": 0.9}),
            _item("k2", {"candidate_type": "visitor_name", "content": "ABC", "confidence": 0.9}),
        ]
        grouped = MemoryPromoter.aggregate_candidates(items)
        assert len(grouped) == 1
        aggregate = next(iter(grouped.values()))
        assert aggregate["candidate_count"] == 2

    def test_nfkc_in_aggregate_key(self):
        """_aggregate_keyがNFKC正規化を適用する"""
        key1 = MemoryPromoter._aggregate_key("test", "Ａ Ｂ Ｃ")
        key2 = MemoryPromoter._aggregate_key("test", "A B C")
        assert key1 == key2

    def test_facility_aliases_in_aggregate_key(self):
        """ASR揺れを同じ施設記憶として重複排除する"""
        key1 = MemoryPromoter._aggregate_key("facility_interest", "エンジンやカベの営業時間")
        key2 = MemoryPromoter._aggregate_key("facility_interest", "エンジニアカフェの営業時間")
        assert key1 == key2

    def test_multilingual_facility_aliases_in_aggregate_key(self):
        """#516: Engineer Cafe と エンジニアカフェを同じ施設記憶として集約する"""
        key1 = MemoryPromoter._aggregate_key("facility_interest", "Engineer Cafeの営業時間")
        key2 = MemoryPromoter._aggregate_key("facility_interest", "エンジニアカフェの営業時間")
        assert key1 == key2

    def test_aggregate_candidates_merges_multilingual_facility_aliases(self):
        """#516: 多言語facility aliasの候補を1件に集約する"""
        items = [
            _item(
                "k1",
                {
                    "candidate_type": "facility_interest",
                    "content": "Engineer Cafeの営業時間",
                    "confidence": 0.9,
                },
            ),
            _item(
                "k2",
                {
                    "candidate_type": "facility_interest",
                    "content": "エンジニアカフェの営業時間",
                    "confidence": 0.8,
                },
            ),
        ]

        grouped = MemoryPromoter.aggregate_candidates(items)

        assert len(grouped) == 1
        aggregate = next(iter(grouped.values()))
        assert aggregate["candidate_count"] == 2


class TestNewTypePromotionRules:
    """新メモリタイプ昇格ルールのテスト"""

    def test_episode_incident_promotes_above_threshold(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "episode_incident",
                "candidate_count": 2,
                "repeat_count_sum": 2,
                "confidence_max": 0.75,
            }
        )
        assert decision.promote is True

    def test_episode_incident_rejected_below_threshold(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "episode_incident",
                "candidate_count": 2,
                "repeat_count_sum": 2,
                "confidence_max": 0.65,
            }
        )
        assert decision.promote is False
        assert decision.reason == "confidence_below_threshold"

    def test_location_preference_promotes_above_threshold(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "location_preference",
                "candidate_count": 2,
                "repeat_count_sum": 2,
                "confidence_max": 0.70,
            }
        )
        assert decision.promote is True

    def test_location_preference_rejected_below_threshold(self):
        decision = MemoryPromoter.should_promote(
            {
                "candidate_type": "location_preference",
                "candidate_count": 2,
                "repeat_count_sum": 2,
                "confidence_max": 0.60,
            }
        )
        assert decision.promote is False


class TestSingleton:
    """get_memory_promoter() シングルトンテスト"""

    def test_returns_same_instance(self):
        reset_memory_promoter()
        a = get_memory_promoter()
        b = get_memory_promoter()
        assert a is b

    def test_reset_clears_instance(self):
        reset_memory_promoter()
        a = get_memory_promoter()
        reset_memory_promoter()
        b = get_memory_promoter()
        assert a is not b


# --- Regression tests for #522 (fast-path actionable gate) -----------------
# `_has_actionable_content` is shared between MemoryPromoter.promote_for_user
# and _is_fast_path_memory in backend/workflows/main_workflow.py so that
# empty / filler / single-character content — including the English "please"
# extracted from remember-requests — never reaches LTM.
@pytest.mark.parametrize(
    "content, expected",
    [
        ("please", False),
        ("ください", False),
        ("お願いします", False),
        ("a", False),  # len == 1
        ("", False),
        ("太郎", True),
        ("田中太郎", True),
        ("I love engineer cafe", True),
    ],
)
def test_has_actionable_content_rejects_filler_strings(content, expected):
    aggregate = {"content": content}
    assert MemoryPromoter._has_actionable_content(aggregate) is expected
