"""Tests for backend.utils.long_term_memory_reranker."""

import time
from types import SimpleNamespace

from backend.utils.long_term_memory_reranker import (
    RerankerConfig,
    rerank_store_memory_items,
)


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

    def test_episode_incident_gets_bonus(self):
        """episode_incident にスコアボーナスが適用される"""
        now = time.time()
        items = [
            _item(
                {
                    "type": "visitor_name",
                    "data": "田中",
                    "confidence": 0.8,
                    "timestamp": now - 3600,
                },
                score=0.5,
                key="name",
            ),
            _item(
                {
                    "type": "episode_incident",
                    "data": "もくもく会で来た",
                    "confidence": 0.75,
                    "timestamp": now - 3600,
                },
                score=0.5,
                key="episode",
            ),
        ]
        ranked = rerank_store_memory_items("もくもく会", items)
        assert ranked[0].key == "episode"

    def test_location_preference_gets_bonus(self):
        """location_preference にスコアボーナスが適用される"""
        now = time.time()
        items = [
            _item(
                {
                    "type": "location_preference",
                    "data": "窓際席",
                    "confidence": 0.7,
                    "timestamp": now - 3600,
                    "source": "promoter",
                },
                score=0.5,
                key="loc",
            ),
        ]
        ranked = rerank_store_memory_items("窓際", items)
        assert len(ranked) == 1
        assert ranked[0].key == "loc"


class TestRerankerConfig:
    """RerankerConfig 定数クラスのテスト"""

    def test_all_constants_defined(self):
        assert RerankerConfig.CONFIDENCE_WEIGHT == 0.25
        assert RerankerConfig.EXPLICIT_REMEMBER_BONUS == 0.2
        assert RerankerConfig.REPEAT_COUNT_CAP == 5
        assert RerankerConfig.REPEAT_COUNT_WEIGHT == 0.03
        assert RerankerConfig.CANDIDATE_COUNT_CAP == 5
        assert RerankerConfig.CANDIDATE_COUNT_WEIGHT == 0.02
        assert RerankerConfig.TOKEN_OVERLAP_CAP == 4
        assert RerankerConfig.TOKEN_OVERLAP_WEIGHT == 0.04
        assert RerankerConfig.FRESHNESS_PENALTY_UNDER_60S == 0.12
        assert RerankerConfig.FRESHNESS_PENALTY_UNDER_600S == 0.08
        assert RerankerConfig.FRESHNESS_PENALTY_UNDER_3600S == 0.03
        assert RerankerConfig.PROMOTER_SOURCE_BONUS == 0.05

    def test_new_type_bonuses(self):
        assert RerankerConfig.EPISODE_INCIDENT_BONUS == 0.10
        assert RerankerConfig.LOCATION_PREFERENCE_BONUS == 0.05
