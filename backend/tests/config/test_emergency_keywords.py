"""
緊急キーワードテスト - Issue #97
"""

import pytest

from backend.config.routing_constants import (
    EMERGENCY_KEYWORDS,
    CATEGORY_TO_AGENT_MAP,
    extract_request_type,
)


class TestEmergencyKeywords:
    """緊急キーワード定義のテスト"""

    def test_emergency_keywords_exist(self):
        """EMERGENCY_KEYWORDSが定義されていること"""
        assert len(EMERGENCY_KEYWORDS) > 0

    def test_emergency_keywords_contain_japanese(self):
        """日本語キーワードが含まれること"""
        ja_keywords = ["緊急", "地震", "火事", "避難", "AED"]
        for kw in ja_keywords:
            assert kw in EMERGENCY_KEYWORDS, f"{kw} not in EMERGENCY_KEYWORDS"

    def test_emergency_keywords_contain_english(self):
        """英語キーワードが含まれること"""
        en_keywords = ["emergency", "earthquake", "fire", "evacuate"]
        for kw in en_keywords:
            assert kw in EMERGENCY_KEYWORDS, f"{kw} not in EMERGENCY_KEYWORDS"

    def test_emergency_maps_to_facility_agent(self):
        """emergencyカテゴリがfacilityエージェントにマッピングされること"""
        assert CATEGORY_TO_AGENT_MAP["emergency"] == "facility"


class TestEmergencyRouting:
    """extract_request_typeでの緊急キーワードルーティングテスト"""

    @pytest.mark.parametrize(
        "query",
        [
            "AEDはどこですか？",
            "地震です！",
            "火事だ！",
            "避難経路を教えて",
            "緊急です",
        ],
    )
    def test_japanese_emergency_queries(self, query):
        """日本語の緊急クエリがemergencyにルーティングされること"""
        assert extract_request_type(query) == "emergency"

    @pytest.mark.parametrize(
        "query",
        [
            "Where is the AED?",
            "Emergency!",
            "There is a fire!",
            "How do I evacuate?",
        ],
    )
    def test_english_emergency_queries(self, query):
        """英語の緊急クエリがemergencyにルーティングされること"""
        assert extract_request_type(query) == "emergency"

    def test_emergency_detected_before_reception(self):
        """emergencyがreceptionより優先されること"""
        # "初めて" is a reception keyword, but "緊急" should take priority
        result = extract_request_type("緊急で初めて来ました")
        assert result == "emergency"

    def test_non_emergency_query_not_affected(self):
        """非緊急クエリが影響を受けないこと"""
        assert extract_request_type("Wi-Fiはありますか？") == "wifi"
        assert extract_request_type("営業時間は？") == "hours"
