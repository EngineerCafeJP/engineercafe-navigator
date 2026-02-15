"""
Test fast routing logic for orchestrator_agent
"""

import pytest
from backend.agents.orchestrator_agent import OrchestratorAgent


class TestOrchestratorFastRouting:
    """Test fast-path routing logic"""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance"""
        return OrchestratorAgent()

    def test_rt_011_food_drink_verb(self, orchestrator):
        """Test rt-011: 飲食動詞 fast-path"""
        result = orchestrator._try_fast_routing("カフェでコーヒーは飲めますか？")

        assert result is not None, "rt-011 should match fast-path"
        assert result["agent"] == "facility", "rt-011 should route to facility"
        assert result["request_type"] == "food_drink", "rt-011 should be food_drink type"
        assert result["category"] == "facility-info", "rt-011 should be facility-info category"

    def test_rt_014_meeting_room_with_floor(self, orchestrator):
        """Test rt-014: 会議室+階情報 fast-path"""
        result = orchestrator._try_fast_routing("2階の会議室を借りたいのですが")

        assert result is not None, "rt-014 should match fast-path"
        assert result["agent"] == "facility", "rt-014 should route to facility"
        assert result["request_type"] == "meeting_room", "rt-014 should be meeting_room type"
        assert result["category"] == "facility-info", "rt-014 should be facility-info category"

    def test_existing_food_drink_keywords(self, orchestrator):
        """Test existing food_drink keywords still work"""
        # Test a query with explicit food/drink keywords
        result = orchestrator._try_fast_routing("飲食物の持ち込みは可能ですか？")

        # This query contains "持ち込み" and "飲食" which are in FOOD_DRINK_KEYWORDS
        assert result is not None, "Existing food_drink should match fast-path"
        assert result["agent"] == "facility", "Should route to facility"
        assert result["request_type"] == "food_drink", "Should be food_drink type"
        assert result["reasoning"] == "Food/drink policy keyword detected"

    def test_food_drink_verb_variations(self, orchestrator):
        """Test various food/drink verb patterns"""
        test_queries = [
            "コーヒーは飲めますか",
            "ランチは食べられますか",
            "注文できますか",
        ]

        for query in test_queries:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert result["agent"] == "facility", f"Query '{query}' should route to facility"
            assert (
                result["request_type"] == "food_drink"
            ), f"Query '{query}' should be food_drink type"

    def test_meeting_room_floor_variations(self, orchestrator):
        """Test various meeting room + floor patterns"""
        test_queries = [
            "3階の会議室を使いたい",
            "二階の会議室はありますか",
        ]

        for query in test_queries:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert result["agent"] == "facility", f"Query '{query}' should route to facility"
            assert (
                result["request_type"] == "meeting_room"
            ), f"Query '{query}' should be meeting_room type"

    def test_basement_takes_precedence_over_meeting_room(self, orchestrator):
        """Test that basement keywords take precedence over meeting_room+floor"""
        result = orchestrator._try_fast_routing("地下の会議室を予約したい")

        # "地下" is in BASEMENT_KEYWORDS and FLOOR_KEYWORDS
        # Since basement check comes before meeting_room+floor check,
        # it should match basement
        assert result is not None
        assert result["agent"] == "facility"
        assert result["request_type"] == "basement"

    def test_meeting_room_without_floor_not_fast_routed(self, orchestrator):
        """Test that meeting room without floor info doesn't use the new fast-path"""
        result = orchestrator._try_fast_routing("会議室を借りたいのですが")

        # This should NOT match the meeting_room+floor fast-path
        # It might match other paths or return None
        if result is not None and result["request_type"] == "meeting_room":
            # If it matches, it should be via a different path
            assert result["reasoning"] != "Meeting room with floor info detected"
