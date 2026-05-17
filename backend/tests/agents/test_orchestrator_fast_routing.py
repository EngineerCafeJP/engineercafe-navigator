"""
Test fast routing logic for orchestrator_agent
"""

import pytest
from backend.agents.orchestrator_agent import OrchestratorAgent
from backend.utils.intent_classifier import filler_intent_for_query


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

    def test_llm_agent_class_name_is_normalized_to_graph_node(self, orchestrator):
        decision = orchestrator._parse_llm_response("""
            {
              "next_agent": "BusinessInfoAgent",
              "reasoning": "営業時間の質問",
              "category": "business-hours",
              "request_type": "hours"
            }
            """)

        assert decision["next_agent"] == "business_info"
        assert decision["raw_next_agent"] == "BusinessInfoAgent"
        assert decision["agent_resolution_source"] == "request_type"

    def test_llm_specific_category_overrides_stale_default_agent(self, orchestrator):
        decision = orchestrator._parse_llm_response("""
            {
              "next_agent": "GeneralKnowledgeAgent",
              "reasoning": "料金カテゴリだがagentが古い既定値",
              "category": "pricing",
              "request_type": "price"
            }
            """)

        assert decision["next_agent"] == "business_info"
        assert decision["agent_resolution_source"] == "request_type"

    def test_llm_request_type_overrides_wrong_facility_category(self, orchestrator):
        decision = orchestrator._parse_llm_response("""
            {
              "next_agent": "FacilityAgent",
              "reasoning": "施設全般カテゴリだが営業時間の質問",
              "category": "facility-info",
              "request_type": "hours"
            }
            """)

        assert decision["next_agent"] == "business_info"
        assert decision["raw_next_agent"] == "FacilityAgent"
        assert decision["agent_resolution_source"] == "request_type"

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

    def test_pet_bottle_query_stays_food_drink(self, orchestrator):
        """ペットボトル should not trigger the pet policy fast path."""
        result = orchestrator._try_fast_routing("ペットボトルの飲み物は持ち込めますか？")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["request_type"] == "food_drink"
        assert result["reasoning"] == "Food/drink policy keyword detected"

    def test_food_drink_verb_variations(self, orchestrator):
        """Test various food/drink verb patterns"""
        test_queries = [
            "コーヒーは飲めますか",
            "ランチは食べられますか",
            "注文できますか",
            "コーヒーを飲みたい",
            "ちょっと休憩したい",
            "I want coffee",
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

    @pytest.mark.parametrize(
        ("previous_type", "query", "expected_agent", "expected_type"),
        [
            ("basement", "明日のイベントは？", "event", "event"),
            ("wifi", "営業時間は？", "business_info", "hours"),
            ("facility", "今週のイベントを教えて", "event", "event"),
            ("slide", "明日のイベントは？", "event", "event"),
            ("reception", "Pythonって何ですか？", None, None),
            ("event", "スライドを見せて", "slide", "slide"),
        ],
    )
    def test_current_query_fast_intent_is_independent_of_stale_request_type(
        self,
        orchestrator,
        previous_type,
        query,
        expected_agent,
        expected_type,
    ):
        del previous_type
        result = orchestrator._try_fast_routing(query)
        if expected_agent is None:
            assert result is None
        else:
            assert result is not None
            assert result["agent"] == expected_agent
            assert result["request_type"] == expected_type

    @pytest.mark.parametrize(
        "query",
        [
            "私の希望席と利用目的を確認してください。",
            "この会話で伝えた希望席と利用目的を教えてください。",
            "前に話した好きな席を覚えていますか。",
        ],
    )
    def test_reception_practical_fact_recall_routes_to_memory(self, orchestrator, query):
        assert orchestrator._is_memory_related_question(query) is True

    @pytest.mark.parametrize(
        "query",
        [
            "窓側の席がいいです。コワーキングスペースを使いたいです。",
            "利用目的はコワーキングです。",
            "エンジニアカフェの目的を教えてください。",
        ],
    )
    def test_reception_practical_fact_statements_do_not_route_to_memory(
        self,
        orchestrator,
        query,
    ):
        assert orchestrator._is_memory_related_question(query) is False

    def test_filler_intent_reuses_fast_classifier(self):
        assert filler_intent_for_query("WiFiのパスワードは？") == "wifi"
        assert filler_intent_for_query("明日のイベントは？") == "event"
        assert filler_intent_for_query("スライドを見せて") == "slide"
        assert filler_intent_for_query("Tell me about membership") == "business_info"

    @pytest.mark.parametrize(
        "query",
        [
            "How do I become a member?",
            "Tell me about membership",
            "What is the membership like?",
            "Do I need to register to use Engineer Cafe?",
        ],
    )
    def test_abstract_english_membership_routes_to_business_info(self, orchestrator, query):
        """#567: abstract EN membership queries should not fall through to general fallback."""
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["category"] == "reception"
        assert result["request_type"] == "reception"

    # --- Phase 1A: 新規キーワードパターンテスト ---

    def test_business_hours_extended_keywords(self, orchestrator):
        """新規営業時間キーワード: 休館日、定休日、開館、閉館"""
        test_cases = [
            ("休館日はいつですか？", "hours"),
            ("定休日はありますか？", "hours"),
            ("開館時間を教えてください", "hours"),
            ("閉館は何時ですか？", "hours"),
            ("今日の最終受付は何時ですか。", "hours"),
            ("受付時間を教えてください。", "hours"),
            ("土日祝日も利用できますか。", "hours"),
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

    def test_bare_cafe_hours_routes_to_saino(self, orchestrator):
        """Bare カフェ hours should use the Saino-first policy."""
        result = orchestrator._try_fast_routing("カフェの営業時間は？")

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["category"] == "saino-cafe"
        assert result["request_type"] == "hours"

    @pytest.mark.parametrize(
        "query,agent,request_type",
        [
            ("カフェでイベントはできますか？", "event", "event"),
            ("コワーキングスペースの営業時間は？", "business_info", "hours"),
            ("カフェで施設利用の営業時間を教えて", "business_info", "hours"),
        ],
    )
    def test_cafe_facility_context_prefers_engineer_cafe(
        self, orchestrator, query, agent, request_type
    ):
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == agent
        assert result["request_type"] == request_type

    @pytest.mark.parametrize(
        "query",
        [
            "サイノカフェの営業時間は？",
            "cafe&bar sainoの営業時間は？",
            "併設のカフェの営業時間は？",
        ],
    )
    def test_explicit_saino_hours_routes_to_business_info(self, orchestrator, query):
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["category"] == "saino-cafe"
        assert result["request_type"] == "hours"

    def test_saino_menu_routes_to_facility_food_drink(self, orchestrator):
        """Saino menu questions stay on facility food/drink canonical answers."""
        result = orchestrator._try_fast_routing("サイノカフェのメニューを教えて")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["category"] == "facility-info"
        assert result["request_type"] == "food_drink"

    def test_business_hours_english_extended(self, orchestrator):
        """英語: closed, holiday キーワード"""
        test_cases = [
            ("Are there any holidays?", "hours"),
            ("What is the last reception time today?", "hours"),
        ]
        for query, expected_type in test_cases:
            result = orchestrator._try_fast_routing(query)
            assert result is not None, f"Query '{query}' should match fast-path"
            assert (
                result["agent"] == "business_info"
            ), f"Query '{query}' should route to business_info"

    def test_bare_english_cafe_hours_routes_to_saino(self, orchestrator):
        """Bare English cafe hours should use the Saino-first policy."""
        result = orchestrator._try_fast_routing("Is the cafe closed on weekends?")

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["category"] == "saino-cafe"
        assert result["request_type"] == "hours"

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

    def test_english_available_spaces_routes_to_facility(self, orchestrator):
        result = orchestrator._try_fast_routing("What spaces are available at Engineer Cafe?")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["category"] == "facility-info"
        assert result["request_type"] == "facility"

    def test_namespace_does_not_route_to_facility_space_keyword(self, orchestrator):
        result = orchestrator._try_fast_routing("What is namespace in Python?")

        assert result is None

    def test_gt_019_consultation_not_assistant_profile(self, orchestrator):
        result = orchestrator._try_fast_routing("コミュニティマネージャーに相談できることは？")

        assert result is not None
        assert result["request_type"] != "assistant_profile"
        assert result["category"] == "consultation"
        assert result["request_type"] == "consultation"

    def test_korean_smoking_routes_to_facility(self, orchestrator):
        result = orchestrator._try_fast_routing("실내에서 흡연할 수 있나요?")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["category"] == "facility-info"
        assert result["request_type"] == "smoking"

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

    def test_greeting_ohayou_gozaimasu(self, orchestrator):
        """おはようございます が greeting にルーティングされること"""
        result = orchestrator._try_fast_routing("おはようございます")
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

    def test_printer_copier_in_building_routes_to_facility_equipment(self, orchestrator):
        """gt-094: 'in the building' must not preempt printer/copier intent."""
        result = orchestrator._try_fast_routing("Is there a printer or copier in the building?")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["request_type"] == "facility"

    def test_no_false_positive_compound_greeting(self, orchestrator):
        """'hello, what are the business hours?' should NOT match greeting (too long)"""
        result = orchestrator._try_fast_routing("hello, what are the business hours?")
        assert (
            result is None or result["category"] != "greeting"
        ), "Compound query with greeting should not be routed to greeting"

    def test_assistant_profile_name_question_routes_without_llm(self, orchestrator):
        result = orchestrator._try_fast_routing("あなたの名前は？")

        assert result is not None
        assert result["agent"] == "general_knowledge"
        assert result["category"] == "assistant_profile"
        assert result["request_type"] == "assistant_profile"

    def test_daily_conversation_routes_to_general_fast_path(self, orchestrator):
        result = orchestrator._try_fast_routing("少し雑談して")

        assert result is not None
        assert result["agent"] == "general_knowledge"
        assert result["category"] == "daily_conversation"
        assert result["request_type"] == "daily_conversation"

    @pytest.mark.parametrize(
        "query",
        [
            "軽く話して",
            "ちょっと話して",
            "退屈なので相手して",
            "お疲れ様です",
        ],
    )
    def test_log_observed_small_talk_markers_route_to_daily_conversation(self, orchestrator, query):
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == "general_knowledge"
        assert result["request_type"] == "daily_conversation"

    @pytest.mark.parametrize(
        ("query", "agent", "request_type"),
        [
            ("元気ですか？営業時間も教えてください。", "business_info", "hours"),
            ("ありがとう、Wi-Fiの接続方法も知りたいです。", "facility", "wifi"),
            ("少し雑談してから今日のイベントを教えてください。", "event", "event"),
        ],
    )
    def test_daily_conversation_marker_does_not_preempt_specific_intent(
        self, orchestrator, query, agent, request_type
    ):
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == agent
        assert result["request_type"] == request_type

    def test_current_weather_routes_to_current_info(self, orchestrator):
        result = orchestrator._try_fast_routing("今日の福岡の天気は？")

        assert result is not None
        assert result["agent"] == "general_knowledge"
        assert result["category"] == "current_info"
        assert result["request_type"] == "current_info"

    def test_visitor_name_memory_write_not_assistant_profile(self, orchestrator):
        result = orchestrator._try_fast_routing("私の名前は田中です。覚えて")

        assert result is None or result["request_type"] != "assistant_profile"

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

    def test_quality_gate_q_recv_ja_002_reception_not_current_info(self, orchestrator):
        """Q-RECV-JA-002: 再受付 + 今日 は current_info に吸われず business_info reception へ。"""
        result = orchestrator._try_fast_routing(
            "以前登録した来館者ですが、今日は再受付だけで大丈夫ですか。"
        )
        assert result is not None
        assert result["agent"] == "business_info"
        assert result["request_type"] == "reception"
        assert result["category"] == "reception"

    @pytest.mark.parametrize(
        "query",
        [
            "受付手続きはこれで完了ですか。",
            "受け付けで何を伝えれば入館できますか？",
        ],
    )
    def test_log_observed_reception_questions_route_to_business_info(self, orchestrator, query):
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["request_type"] == "reception"

    def test_quality_gate_q_farewell_ja_001_farewell_not_daily(self, orchestrator):
        """Q-FAREWELL-JA-001: 感謝 + また来ます は daily ではなく farewell へ。"""
        result = orchestrator._try_fast_routing("今日はありがとうございました。また来ます。")
        assert result is not None
        assert result["agent"] == "farewell"
        assert result["request_type"] == "farewell"
        assert result["category"] == "farewell"

    @pytest.mark.parametrize(
        ("query", "request_type"),
        [
            ("一時外出のルールは？", "temporary_exit"),
            ("ペットを連れて入れますか？", "pets"),
        ],
    )
    def test_alpha_c_ragas_live_source_cases_route_to_facility(
        self, orchestrator, query, request_type
    ):
        """gt-038/gt-057 should not fall through to broad business_info fallback."""
        result = orchestrator._try_fast_routing(query)
        assert result is not None
        assert result["agent"] == "facility"
        assert result["category"] == "facility-info"
        assert result["request_type"] == request_type

    def test_alpha_ko_food_policy_routes_to_facility(self, orchestrator):
        """gt-113: Korean outside-food query must use facility knowledge, not fallback."""
        result = orchestrator._try_fast_routing("외부 음식을 가져와도 되나요?")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["category"] == "facility-info"
        assert result["request_type"] == "food_drink"

    def test_alpha_en_contact_routes_to_business_info(self, orchestrator):
        """gt-009b/gt-096: English contact questions should hit canonical contact answer."""
        result = orchestrator._try_fast_routing("How can I contact Engineer Cafe?")

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["category"] == "contact"
        assert result["request_type"] == "contact"

    def test_emergency_kaji_overrides_farewell(self, orchestrator):
        """P1 guard: 火事なので帰ります must not route to farewell."""
        result = orchestrator._try_fast_routing("火事なので帰ります")
        assert result is not None
        assert result["agent"] != "farewell", f"emergency kaji query leaked to farewell: {result}"

    def test_emergency_jishin_overrides_farewell(self, orchestrator):
        """P1 guard: 地震なので帰ります must not route to farewell."""
        result = orchestrator._try_fast_routing("地震なので帰ります")
        assert result is not None
        assert result["agent"] != "farewell", f"emergency jishin query leaked to farewell: {result}"

    def test_emergency_english_overrides_farewell(self, orchestrator):
        """P1 guard: 'emergency, I am leaving' must not route to farewell."""
        result = orchestrator._try_fast_routing("emergency, I am leaving")
        assert result is not None
        assert (
            result["agent"] != "farewell"
        ), f"english emergency query leaked to farewell: {result}"

    def test_p2_mata_kuru_with_reception_not_farewell(self, orchestrator):
        """P2 anchor: 'また来るときに受付は必要ですか' must not route to farewell."""
        result = orchestrator._try_fast_routing("また来るときに受付は必要ですか")
        # Must not be routed to farewell. Either fallthrough (None) or reception/business_info.
        if result is not None:
            assert result["agent"] != "farewell", f"reception query leaked to farewell: {result}"

    def test_alpha_c127_returning_visit_routes_to_reception(self, orchestrator):
        """gt-082: 'また来ました' is an arrival signal, not farewell."""
        result = orchestrator._try_fast_routing("また来ました")

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["request_type"] == "reception"

    def test_alpha_c127_nearby_lunch_routes_to_facility(self, orchestrator):
        """gt-046: nearby lunch should use facility nearby canonical answer."""
        result = orchestrator._try_fast_routing("周辺でランチを食べられる場所は？")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["request_type"] == "nearby"

    def test_log_observed_engineer_cafe_overview_does_not_route_to_nearby(self, orchestrator):
        result = orchestrator._try_fast_routing("エンジニアカフェって何ですか？")

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["category"] == "general"
        assert result["request_type"] == "general"

    def test_log_observed_english_memory_preference_is_not_member_reception(self, orchestrator):
        result = orchestrator._try_fast_routing("Please remember that I prefer English answers.")

        assert result is None or result["request_type"] != "reception"

    @pytest.mark.parametrize(
        ("query", "agent", "request_type"),
        [
            ("エンジニアカフェで飲みは可能ですか？", "facility", "food_drink"),
            ("MAKER'sスペースではどんな機材が使えますか？", "facility", "facility"),
            ("와이파이 비밀번호가 뭐예요?", "facility", "wifi"),
            ("工程师咖啡的营业时间是什么？", "business_info", "hours"),
            ("엔지니어 카페의 운영 시간은 어떻게 되나요?", "business_info", "hours"),
        ],
    )
    def test_log_observed_multilingual_and_facility_queries_fast_route(
        self, orchestrator, query, agent, request_type
    ):
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == agent
        assert result["request_type"] == request_type

    @pytest.mark.parametrize(
        ("query", "agent", "request_type"),
        [
            ("レーザー加工機で使える素材は？", "facility", "facility"),
            ("プロジェクターを借りることはできますか？", "facility", "facility"),
            ("ウォーターサーバーはありますか？", "facility", "facility"),
            ("雨の日にエンジニアカフェへ行く最短ルートは？", "facility", "access"),
            ("充電器を借りることはできますか？", "facility", "facility"),
            ("メインホールを貸切利用できますか？", "facility", "exclusive_rental"),
            ("営利目的の勧誘はできますか？", "facility", "children_noise"),
            ("エンジニアカフェの公式SNSアカウントは？", "business_info", "contact"),
            ("英語対応はしていますか？", "business_info", "contact"),
            ("英語対応はしていますか", "business_info", "contact"),
            ("コミュニティマネージャーに相談できることは？", "business_info", "consultation"),
            ("エンジニアフレンドリーシティ福岡とは？", "business_info", "community"),
        ],
    )
    def test_alpha_c127_low_quality_queries_fast_route(
        self, orchestrator, query, agent, request_type
    ):
        """Low-scoring C-127 cases should reach deterministic canonical agents."""
        result = orchestrator._try_fast_routing(query)

        assert result is not None
        assert result["agent"] == agent
        assert result["request_type"] == request_type

    def test_english_see_your_floor_map_not_farewell(self, orchestrator):
        result = orchestrator._try_fast_routing("Can I see your floor map?")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["request_type"] == "floor_layout"

    def test_english_see_your_hours_not_farewell(self, orchestrator):
        result = orchestrator._try_fast_routing("Can I see your opening hours?")

        assert result is not None
        assert result["agent"] == "business_info"
        assert result["request_type"] == "hours"

    def test_hajimete_does_not_preempt_floor_map(self, orchestrator):
        result = orchestrator._try_fast_routing("初めて来ました。フロアマップを見せてください。")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["request_type"] == "floor_layout"

    def test_hajimete_does_not_preempt_parking(self, orchestrator):
        result = orchestrator._try_fast_routing("初めて来ました。駐車場はありますか？")

        assert result is not None
        assert result["agent"] == "facility"
        assert result["request_type"] == "parking"


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
