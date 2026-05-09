"""Enhanced RAG scoring/helper method tests."""

import pytest
from unittest.mock import patch, Mock
from backend.tools.enhanced_rag import (
    EnhancedRAGSearch,
    RPC_SIMILARITY_THRESHOLDS,
    DEFAULT_RPC_SIMILARITY_THRESHOLD,
)


@pytest.fixture
def rag():
    with patch("backend.tools.enhanced_rag.create_client") as mock_create:
        mock_create.return_value = Mock()
        return EnhancedRAGSearch()


class TestDetectEntity:
    """6 tests for _detect_entity()"""

    def test_entity_from_metadata(self, rag):
        result = {"content": "", "title": "", "metadata": {"entity": "engineer-cafe"}}
        assert rag._detect_entity(result) == "engineer-cafe"

    def test_engineer_cafe_from_content(self, rag):
        result = {"content": "engineer cafe is great", "title": "", "metadata": {}}
        assert rag._detect_entity(result) == "engineer-cafe"

    def test_engineer_cafe_from_japanese(self, rag):
        result = {"content": "エンジニアカフェは素晴らしい", "title": "", "metadata": {}}
        assert rag._detect_entity(result) == "engineer-cafe"

    def test_saino_from_content(self, rag):
        result = {"content": "saino cafe has great food", "title": "", "metadata": {}}
        assert rag._detect_entity(result) == "saino"

    def test_saino_preferred_when_content_mentions_engineer_cafe_location(self, rag):
        result = {
            "content": "cafe&bar saino（サイノカフェ）はエンジニアカフェ1階に併設されています。",
            "title": "cafe&bar saino 営業情報",
            "metadata": {},
        }
        assert rag._detect_entity(result) == "saino"

    def test_meeting_room_from_content(self, rag):
        result = {"content": "会議室は3階にあります", "title": "", "metadata": {}}
        assert rag._detect_entity(result) == "meeting-room"

    def test_general_fallback(self, rag):
        result = {"content": "some random content", "title": "random", "metadata": {}}
        assert rag._detect_entity(result) == "general"


class TestCalculateCategoryBonus:
    """4 tests for _calculate_category_bonus()"""

    def test_matching_category(self, rag):
        result = {"category": "hours", "metadata": {}}
        assert rag._calculate_category_bonus(result, "hours") == 0.2

    def test_non_matching_category(self, rag):
        result = {"category": "general", "metadata": {}}
        assert rag._calculate_category_bonus(result, "hours") == 0.0

    def test_category_from_metadata_fallback(self, rag):
        result = {"category": "", "metadata": {"category": "pricing"}}
        assert rag._calculate_category_bonus(result, "pricing") == 0.2

    def test_empty_category(self, rag):
        result = {"category": "", "metadata": {}}
        assert rag._calculate_category_bonus(result, "hours") == 0.0


class TestCalculateEntityBonus:
    """3 tests for _calculate_entity_bonus()"""

    def test_engineer_cafe_in_query(self, rag):
        assert (
            rag._calculate_entity_bonus("engineer-cafe", "エンジニアカフェの料金", "pricing") == 0.3
        )

    def test_entity_priority_bonus(self, rag):
        bonus = rag._calculate_entity_bonus("engineer-cafe", "料金はいくら", "pricing")
        assert bonus > 0  # engineer-cafe is first in pricing priority

    def test_no_entity_bonus(self, rag):
        bonus = rag._calculate_entity_bonus("general", "天気はどう", "general")
        assert bonus == 0.0

    def test_saino_entity_bonus_uses_explicit_saino_terms(self, rag):
        bonus = rag._calculate_entity_bonus("saino", "What are Saino cafe hours?", "hours")
        assert bonus == 0.35


class TestScoreResults:
    """2 tests for _score_results()"""

    def test_results_sorted_by_priority(self, rag):
        results = [
            {
                "content": "low",
                "title": "low",
                "similarity": 0.5,
                "category": "",
                "metadata": {},
            },
            {
                "content": "engineer cafe info",
                "title": "high",
                "similarity": 0.9,
                "category": "hours",
                "metadata": {"entity": "engineer-cafe"},
            },
        ]
        scored = rag._score_results(results, "engineer cafe hours", "hours", "ja")
        assert scored[0]["title"] == "high"
        assert scored[0]["priority_score"] > scored[1]["priority_score"]

    def test_preserves_original_similarity(self, rag):
        results = [
            {
                "content": "test",
                "title": "test",
                "similarity": 0.7,
                "category": "",
                "metadata": {},
            }
        ]
        scored = rag._score_results(results, "test", "general", "ja")
        assert scored[0]["original_similarity"] == 0.7


class TestBuildContextFromResults:
    """3 tests for _build_context_from_results()"""

    def test_empty_results(self, rag):
        assert rag._build_context_from_results([], "hours", "ja") == ""

    def test_entity_grouping(self, rag):
        results = [
            {"entity": "engineer-cafe", "content": "EC content"},
            {"entity": "saino", "content": "Saino content"},
        ]
        context = rag._build_context_from_results(results, "pricing", "ja")
        assert "エンジニアカフェ" in context
        assert "sainoカフェ" in context

    def test_japanese_headers(self, rag):
        results = [{"entity": "meeting-room", "content": "会議室情報"}]
        context = rag._build_context_from_results(results, "facility-info", "ja")
        assert "会議室" in context


class TestGetEntityPriority:
    """2 tests for _get_entity_priority()"""

    def test_pricing_priority_order(self, rag):
        priority = rag._get_entity_priority("pricing")
        assert priority[0] == "engineer-cafe"
        assert "saino" in priority

    def test_unknown_category_default(self, rag):
        priority = rag._get_entity_priority("unknown_cat")
        assert priority[0] == "engineer-cafe"


class TestGeneratePracticalAdvice:
    """2 tests for _generate_practical_advice()"""

    def test_hours_advice_ja(self, rag):
        results = [{"content": "test"}]
        advice = rag._generate_practical_advice(results, "営業時間", "hours", "ja")
        assert advice is not None
        assert "営業時間" in advice

    def test_no_advice_for_unknown_category(self, rag):
        results = [{"content": "test"}]
        advice = rag._generate_practical_advice(results, "test", "general", "ja")
        assert advice is None


class TestGetRpcThreshold:
    """Tests for the new _get_rpc_threshold method"""

    def test_hours_threshold(self, rag):
        assert rag._get_rpc_threshold("hours") == 0.25

    def test_event_threshold(self, rag):
        assert rag._get_rpc_threshold("event") == 0.35

    def test_unknown_returns_default(self, rag):
        assert rag._get_rpc_threshold("unknown") == DEFAULT_RPC_SIMILARITY_THRESHOLD

    def test_all_categories_have_thresholds(self, rag):
        for cat in RPC_SIMILARITY_THRESHOLDS:
            assert rag._get_rpc_threshold(cat) == RPC_SIMILARITY_THRESHOLDS[cat]
