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

    # --- Phase 1A: 新規キーワードパターンテスト ---

    def test_business_hours_extended_keywords(self, orchestrator):
        """新規営業時間キーワード: 休館日、定休日、開館、閉館"""
        test_cases = [
            ("休館日はいつですか？", "hours"),
            ("定休日はありますか？", "hours"),
            ("開館時間を教えてください", "hours"),
            ("閉館は何時ですか？", "hours"),
            ("お休みの日はありますか？", "hours"),
        ]
        for query, expected_type in test_cases:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert (
                result["agent"] == "business_info"
            ), f"Query '{query}' should route to business_info"
            assert (
                result["request_type"] == expected_type
            ), f"Query '{query}' should be {expected_type} type"

    def test_business_hours_english_extended(self, orchestrator):
        """英語: closed, holiday キーワード"""
        test_cases = [
            ("Is the cafe closed on weekends?", "hours"),
            ("Are there any holidays?", "hours"),
        ]
        for query, expected_type in test_cases:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert (
                result["agent"] == "business_info"
            ), f"Query '{query}' should route to business_info"

    def test_pricing_extended_keywords(self, orchestrator):
        """新規料金キーワード: free, フリー, タダ, 利用料"""
        test_cases = [
            ("利用料はかかりますか？", "price"),
            ("フリーですか？", "price"),
            ("タダで使えますか？", "price"),
        ]
        for query, expected_type in test_cases:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert (
                result["agent"] == "business_info"
            ), f"Query '{query}' should route to business_info"
            assert (
                result["request_type"] == expected_type
            ), f"Query '{query}' should be {expected_type} type"

    def test_reception_keywords(self, orchestrator):
        """初回利用/利用方法キーワード"""
        test_cases = [
            "初回利用の手続きは？",
            "利用方法を教えてください",
            "I'm a first-time visitor. What should I do?",
        ]
        for query in test_cases:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert (
                result["agent"] == "business_info"
            ), f"Query '{query}' should route to business_info"
            assert (
                result["request_type"] == "reception"
            ), f"Query '{query}' should be reception type"

    def test_floor_layout_keywords(self, orchestrator):
        """フロアマップ/館内案内キーワード"""
        test_cases = [
            "フロアマップを見せてください",
            "館内案内はありますか？",
            "フロア構成を教えてください",
        ]
        for query in test_cases:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert result["agent"] == "facility", f"Query '{query}' should route to facility"
            assert (
                result["request_type"] == "floor_layout"
            ), f"Query '{query}' should be floor_layout type"

    def test_english_pricing_free(self, orchestrator):
        """英語: free キーワードが pricing にルーティング"""
        result = orchestrator._try_fast_routing("Is it free to use?")
        assert result is not None
        assert result["agent"] == "business_info"
        assert result["request_type"] == "price"

    def test_english_floor_map(self, orchestrator):
        """英語: floor map/plan キーワード"""
        test_cases = [
            "Can I see the floor map?",
            "Do you have a floor plan?",
        ]
        for query in test_cases:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert result["agent"] == "facility", f"Query '{query}' should route to facility"

    def test_greeting_konnichiwa(self, orchestrator):
        """こんにちは が greeting にルーティングされること"""
        result = orchestrator._try_fast_routing("こんにちは")
        assert result is not None
        assert result["category"] == "greeting"
        assert result["request_type"] == "greeting"

    def test_greeting_hello(self, orchestrator):
        """hello が greeting にルーティングされること"""
        result = orchestrator._try_fast_routing("hello")
        assert result is not None
        assert result["category"] == "greeting"
        assert result["request_type"] == "greeting"

    def test_greeting_good_morning(self, orchestrator):
        """good morning が greeting にルーティングされること"""
        result = orchestrator._try_fast_routing("good morning")
        assert result is not None
        assert result["category"] == "greeting"
        assert result["request_type"] == "greeting"

    def test_greeting_ohayou(self, orchestrator):
        """おはよう が greeting にルーティングされること"""
        result = orchestrator._try_fast_routing("おはよう")
        assert result is not None
        assert result["category"] == "greeting"
        assert result["request_type"] == "greeting"

    def test_greeting_konbanwa(self, orchestrator):
        """こんばんは が greeting にルーティングされること"""
        result = orchestrator._try_fast_routing("こんばんは")
        assert result is not None
        assert result["category"] == "greeting"
        assert result["request_type"] == "greeting"

    def test_greeting_uppercase_hello(self, orchestrator):
        """HELLO (uppercase) should match greeting"""
        result = orchestrator._try_fast_routing("HELLO")
        assert result is not None
        assert result["category"] == "greeting"
        assert result["request_type"] == "greeting"

    def test_greeting_with_punctuation(self, orchestrator):
        """Hello! with punctuation should match greeting"""
        result = orchestrator._try_fast_routing("Hello!")
        assert result is not None
        assert result["category"] == "greeting"
        assert result["request_type"] == "greeting"

    def test_no_false_positive_history(self, orchestrator):
        """'history' should NOT match greeting (no 'hi'/'hey' substring match)"""
        result = orchestrator._try_fast_routing("What is the history of this building?")
        assert (
            result is None or result["category"] != "greeting"
        ), "Query containing 'history' should not be routed to greeting"

    def test_no_false_positive_compound_greeting(self, orchestrator):
        """'hello, what are the business hours?' should NOT match greeting (too long)"""
        result = orchestrator._try_fast_routing("hello, what are the business hours?")
        assert (
            result is None or result["category"] != "greeting"
        ), "Compound query with greeting should not be routed to greeting"

    def test_no_false_positive_short_question_after_greeting_ja(self, orchestrator):
        """こんにちは + 質問は greeting にルーティングされないこと"""
        result = orchestrator._try_fast_routing("こんにちは 営業時間は？")
        assert result is None or result["category"] != "greeting"

    def test_no_false_positive_hello_wifi(self, orchestrator):
        """hello + wifi は greeting にルーティングされないこと"""
        result = orchestrator._try_fast_routing("hello wifi?")
        assert result is None or result["category"] != "greeting"

    def test_pure_greeting_with_exclamation(self, orchestrator):
        """こんにちは！ は greeting にルーティングされること"""
        result = orchestrator._try_fast_routing("こんにちは！")
        assert result is not None
        assert result["category"] == "greeting"

    def test_greeting_chinese_nihao(self, orchestrator):
        """你好 should match greeting fast-path"""
        result = orchestrator._try_fast_routing("你好")
        assert result is not None
        assert result["category"] == "greeting"

    def test_greeting_chinese_zaoshanghao(self, orchestrator):
        """早上好 should match greeting fast-path"""
        result = orchestrator._try_fast_routing("早上好")
        assert result is not None
        assert result["category"] == "greeting"

    def test_greeting_korean_annyeonghaseyo(self, orchestrator):
        """안녕하세요 should match greeting fast-path"""
        result = orchestrator._try_fast_routing("안녕하세요")
        assert result is not None
        assert result["category"] == "greeting"

    def test_greeting_korean_annyeong(self, orchestrator):
        """안녕 should match greeting fast-path"""
        result = orchestrator._try_fast_routing("안녕")
        assert result is not None
        assert result["category"] == "greeting"

    def test_general_explanation_does_not_match_slide(self, orchestrator):
        """一般的な説明依頼は slide fast-path に吸わせない"""
        result = orchestrator._try_fast_routing("Docker を使うメリットを短く説明してください。")
        assert result is None or result["agent"] != "slide"

    def test_explicit_slide_explanation_still_matches_slide(self, orchestrator):
        """スライド明示の説明依頼は slide fast-path のまま"""
        result = orchestrator._try_fast_routing("このスライドを説明してください。")
        assert result is not None
        assert result["agent"] == "slide"
        assert result["request_type"] == "slide"


def test_zh_greeting_template_content():
    """Chinese greeting templates should exist for all time periods"""
    from backend.config.routing_constants import TIME_GREETING_TEMPLATES

    for period in TIME_GREETING_TEMPLATES:
        assert "zh" in TIME_GREETING_TEMPLATES[period], f"Missing zh for {period}"
        assert len(TIME_GREETING_TEMPLATES[period]["zh"]) > 0


def test_ko_greeting_template_content():
    """Korean greeting templates should exist for all time periods"""
    from backend.config.routing_constants import TIME_GREETING_TEMPLATES

    for period in TIME_GREETING_TEMPLATES:
        assert "ko" in TIME_GREETING_TEMPLATES[period], f"Missing ko for {period}"
        assert len(TIME_GREETING_TEMPLATES[period]["ko"]) > 0
