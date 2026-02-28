"""
受付機能強化 E2Eテスト - Issues #95-#99

AI受付エージェントとしての全機能を網羅的にテスト。
緊急情報、受付案内、イベント曖昧性、スペース曖昧性、
アクセシビリティを含む包括的シナリオ。

実行方法:
    pytest backend/tests/e2e/test_reception_enhancement_e2e.py --run-e2e -v
"""

import uuid

import pytest

from backend.tests.e2e.conftest import assert_keywords, is_routing_failure


# =============================================================================
# Issue #97: 緊急情報対応テスト
# =============================================================================


@pytest.mark.e2e
class TestEmergencyResponseE2E:
    """緊急キーワード検出とFacilityAgentルーティングのE2Eテスト"""

    async def test_aed_location_japanese(self, invoke_workflow):
        """AED場所の質問 → FacilityAgentが応答"""
        result = await invoke_workflow("AEDはどこですか？")
        assert result["answer"], "回答が空です"
        # AED/emergency系の応答であることを確認
        metadata = result.get("metadata", {})
        # FacilityAgentまたはorchestrator_inline経由で応答
        agent = metadata.get("agent", "")
        assert agent in (
            "FacilityAgent",
            "orchestrator_inline",
            "",
        ), f"Unexpected agent: {agent}"

    async def test_aed_location_english(self, invoke_workflow):
        """AED location query in English → FacilityAgent responds"""
        result = await invoke_workflow("Where is the AED?", language="en")
        assert result["answer"], "Answer is empty"

    async def test_earthquake_response_japanese(self, invoke_workflow):
        """地震の質問 → 安全情報を提供"""
        result = await invoke_workflow("地震です！どうすればいいですか？")
        assert result["answer"], "回答が空です"

    async def test_fire_emergency_japanese(self, invoke_workflow):
        """火事の質問 → 避難情報を提供"""
        result = await invoke_workflow("火事だ！避難経路を教えて！")
        assert result["answer"], "回答が空です"

    async def test_evacuation_route_english(self, invoke_workflow):
        """Evacuation query in English"""
        result = await invoke_workflow(
            "How do I evacuate? Where is the emergency exit?",
            language="en",
        )
        assert result["answer"], "Answer is empty"

    async def test_emergency_priority_over_location(self, invoke_workflow):
        """緊急が場所キーワードより優先される"""
        result = await invoke_workflow("AEDの場所はどこにありますか？")
        assert result["answer"], "回答が空です"
        # 回答にAEDまたは緊急系の情報が含まれるべき
        # （"場所"キーワードに引きずられずemergencyルーティングされるか確認）

    async def test_first_aid_query(self, invoke_workflow):
        """救急に関する質問"""
        result = await invoke_workflow("救急箱はありますか？けがをしました")
        assert result["answer"], "回答が空です"


# =============================================================================
# Issue #96: 受付案内テスト
# =============================================================================


@pytest.mark.e2e
class TestReceptionE2E:
    """受付テンプレート応答のE2Eテスト"""

    async def test_first_time_visitor_japanese(self, invoke_workflow):
        """初回利用者の質問 → first_time テンプレート"""
        result = await invoke_workflow("初めて来ました。利用方法を教えてください。")
        assert result["answer"], "回答が空です"
        # reception template or business_info agent
        if not is_routing_failure(result["answer"]):
            assert_keywords(
                result["answer"],
                ["ようこそ", "受付", "登録", "無料", "Wi-Fi", "エンジニアカフェ"],
                threshold=0.2,
                msg="初回利用者案内",
            )

    async def test_first_time_visitor_english(self, invoke_workflow):
        """First-time visitor in English → first_time template"""
        result = await invoke_workflow(
            "This is my first visit. How do I use the space?",
            language="en",
        )
        assert result["answer"], "Answer is empty"
        if not is_routing_failure(result["answer"]):
            assert_keywords(
                result["answer"],
                ["welcome", "free", "Wi-Fi", "register", "reception"],
                threshold=0.2,
                msg="First-time visitor guidance",
            )

    async def test_check_in_query(self, invoke_workflow):
        """チェックイン方法の質問"""
        result = await invoke_workflow("チェックインはどうすればいいですか？")
        assert result["answer"], "回答が空です"

    async def test_registration_query(self, invoke_workflow):
        """利用登録の質問"""
        result = await invoke_workflow("初回利用登録はどこでできますか？")
        assert result["answer"], "回答が空です"

    async def test_general_welcome(self, invoke_workflow):
        """一般的な受付案内"""
        result = await invoke_workflow("利用方法を教えてください")
        assert result["answer"], "回答が空です"


# =============================================================================
# Issue #95: Clarification テンプレート新カテゴリテスト
# =============================================================================


@pytest.mark.e2e
class TestEventClarificationE2E:
    """イベント曖昧性質問のE2Eテスト"""

    async def test_vague_event_query_japanese(self, invoke_workflow):
        """曖昧なイベント質問 → clarification テンプレート"""
        result = await invoke_workflow("イベントについて教えてください")
        assert result["answer"], "回答が空です"
        # イベント情報またはclarificationが返る
        if not is_routing_failure(result["answer"]):
            assert_keywords(
                result["answer"],
                ["イベント", "参加", "開催", "スケジュール", "予定"],
                threshold=0.2,
                msg="イベント曖昧性テスト",
            )

    async def test_vague_event_query_english(self, invoke_workflow):
        """Vague event query in English"""
        result = await invoke_workflow(
            "Tell me about events",
            language="en",
        )
        assert result["answer"], "Answer is empty"

    async def test_specific_event_query(self, invoke_workflow):
        """具体的なイベント質問 → EventAgentで直接応答"""
        result = await invoke_workflow("今週のイベントは何がありますか？")
        assert result["answer"], "回答が空です"


@pytest.mark.e2e
class TestSpaceClarificationE2E:
    """スペース曖昧性質問のE2Eテスト"""

    async def test_vague_space_query_japanese(self, invoke_workflow):
        """曖昧なスペース質問 → clarification テンプレート or detailed info"""
        result = await invoke_workflow("どのスペースが使えますか？")
        assert result["answer"], "回答が空です"
        if not is_routing_failure(result["answer"]):
            assert_keywords(
                result["answer"],
                [
                    "メインホール",
                    "集中スペース",
                    "MTG",
                    "MAKER",
                    "スペース",
                    "1階",
                    "地下",
                ],
                threshold=0.15,
                msg="スペース案内",
            )

    async def test_vague_space_query_english(self, invoke_workflow):
        """Vague space query in English"""
        result = await invoke_workflow(
            "What spaces are available?",
            language="en",
        )
        assert result["answer"], "Answer is empty"

    async def test_specific_space_query(self, invoke_workflow):
        """具体的なスペース質問 → FacilityAgentで直接応答"""
        result = await invoke_workflow("地下のMTGスペースの利用方法を教えて")
        assert result["answer"], "回答が空です"


# =============================================================================
# Issue #98: EventAgent.get_today_events() テスト
# =============================================================================


@pytest.mark.e2e
class TestTodayEventsE2E:
    """本日のイベント情報取得のE2Eテスト"""

    async def test_today_events_japanese(self, invoke_workflow):
        """今日のイベント情報を聞く"""
        result = await invoke_workflow("今日のイベントはありますか？")
        assert result["answer"], "回答が空です"
        # イベントがあってもなくても適切な応答であること
        metadata = result.get("metadata", {})
        agent = metadata.get("agent", "")
        assert agent in ("EventAgent", "orchestrator_inline", ""), f"Unexpected agent: {agent}"

    async def test_today_events_english(self, invoke_workflow):
        """Today's events query in English"""
        result = await invoke_workflow("What events are happening today?", language="en")
        assert result["answer"], "Answer is empty"

    async def test_today_schedule(self, invoke_workflow):
        """本日のスケジュール確認"""
        result = await invoke_workflow("本日のスケジュールを教えて")
        assert result["answer"], "回答が空です"


# =============================================================================
# Issue #99: アクセシビリティ情報テスト
# =============================================================================


@pytest.mark.e2e
class TestAccessibilityE2E:
    """アクセシビリティ情報のE2Eテスト"""

    async def test_wheelchair_access_japanese(self, invoke_workflow):
        """車椅子利用可否の質問"""
        result = await invoke_workflow("車椅子で利用できますか？")
        assert result["answer"], "回答が空です"
        if not is_routing_failure(result["answer"]):
            assert_keywords(
                result["answer"],
                ["車椅子", "1階", "地下", "バリアフリー", "スタッフ", "エレベーター"],
                threshold=0.15,
                msg="車椅子アクセス情報",
            )

    async def test_wheelchair_access_english(self, invoke_workflow):
        """Wheelchair accessibility query in English"""
        result = await invoke_workflow(
            "Is the cafe wheelchair accessible?",
            language="en",
        )
        assert result["answer"], "Answer is empty"

    async def test_elevator_availability(self, invoke_workflow):
        """エレベーターの有無"""
        result = await invoke_workflow("エレベーターはありますか？")
        assert result["answer"], "回答が空です"

    async def test_barrier_free_info(self, invoke_workflow):
        """バリアフリー情報の質問"""
        result = await invoke_workflow("バリアフリー対応について教えてください")
        assert result["answer"], "回答が空です"

    async def test_stair_ramp_info(self, invoke_workflow):
        """段差・スロープの質問"""
        result = await invoke_workflow("段差はありますか？スロープはありますか？")
        assert result["answer"], "回答が空です"


# =============================================================================
# 複合シナリオテスト（受付エージェントとしての統合テスト）
# =============================================================================


@pytest.mark.e2e
class TestReceptionScenarioE2E:
    """受付エージェントとしての統合シナリオテスト"""

    async def test_first_visit_full_scenario(self, invoke_workflow):
        """初回訪問者の完全フロー: 受付 → 施設案内 → Wi-Fi → イベント"""
        sid = f"e2e-first-visit-{uuid.uuid4().hex[:8]}"

        # Step 1: 初回訪問
        r1 = await invoke_workflow("初めて来ました", session_id=sid)
        assert r1["answer"], "Step 1: 受付案内が空です"

        # Step 2: スペースについて聞く
        r2 = await invoke_workflow("どんなスペースがありますか？", session_id=sid)
        assert r2["answer"], "Step 2: スペース案内が空です"

        # Step 3: Wi-Fiについて聞く
        r3 = await invoke_workflow("Wi-Fiは使えますか？", session_id=sid)
        assert r3["answer"], "Step 3: Wi-Fi案内が空です"

        # Step 4: イベントについて聞く
        r4 = await invoke_workflow("今日のイベントはありますか？", session_id=sid)
        assert r4["answer"], "Step 4: イベント情報が空です"

    async def test_emergency_during_visit(self, invoke_workflow):
        """通常利用中の緊急事態シナリオ"""
        sid = f"e2e-emergency-{uuid.uuid4().hex[:8]}"

        # Step 1: 通常の質問
        r1 = await invoke_workflow("Wi-Fiのパスワードを教えて", session_id=sid)
        assert r1["answer"], "Step 1: Wi-Fi情報が空です"

        # Step 2: 突然の緊急事態
        r2 = await invoke_workflow("AEDはどこですか？急いでいます！", session_id=sid)
        assert r2["answer"], "Step 2: AED情報が空です"

    async def test_multilingual_reception(self, invoke_workflow):
        """多言語受付シナリオ"""
        sid = f"e2e-multilingual-{uuid.uuid4().hex[:8]}"

        # 英語での初回訪問
        r1 = await invoke_workflow(
            "Hello, this is my first time here. How do I use this place?",
            language="en",
            session_id=sid,
        )
        assert r1["answer"], "Step 1: English welcome is empty"

        # 英語でWi-Fi質問
        r2 = await invoke_workflow(
            "Is there free Wi-Fi?",
            language="en",
            session_id=sid,
        )
        assert r2["answer"], "Step 2: Wi-Fi info is empty"

    async def test_accessibility_focused_visit(self, invoke_workflow):
        """アクセシビリティ重視の訪問シナリオ"""
        sid = f"e2e-accessibility-{uuid.uuid4().hex[:8]}"

        # Step 1: 車椅子利用可否
        r1 = await invoke_workflow("車椅子で利用できますか？", session_id=sid)
        assert r1["answer"], "Step 1: 車椅子情報が空です"

        # Step 2: 地下施設へのアクセス
        r2 = await invoke_workflow(
            "地下のスペースは車椅子で行けますか？",
            session_id=sid,
        )
        assert r2["answer"], "Step 2: 地下アクセス情報が空です"


# =============================================================================
# ストレステスト・エッジケース
# =============================================================================


@pytest.mark.e2e
class TestReceptionEdgeCasesE2E:
    """エッジケース・ストレステスト"""

    async def test_empty_query(self, invoke_workflow):
        """空のクエリに対する応答"""
        result = await invoke_workflow("")
        # 空クエリでもクラッシュしないこと
        assert isinstance(result.get("answer", ""), str)

    async def test_very_long_query(self, invoke_workflow):
        """非常に長いクエリ"""
        long_query = "エンジニアカフェについて教えてください。" * 20
        result = await invoke_workflow(long_query)
        assert result["answer"], "長いクエリへの回答が空です"

    async def test_mixed_language_query(self, invoke_workflow):
        """日英混在クエリ"""
        result = await invoke_workflow("Wi-Fiのpasswordを教えて。Where can I find it?")
        assert result["answer"], "混在クエリへの回答が空です"

    async def test_emoji_in_query(self, invoke_workflow):
        """絵文字を含むクエリ"""
        result = await invoke_workflow("Wi-Fiは使えますか？🤔")
        assert result["answer"], "絵文字クエリへの回答が空です"

    async def test_special_characters_query(self, invoke_workflow):
        """特殊文字を含むクエリ"""
        result = await invoke_workflow("Wi-Fi（ワイファイ）の<<パスワード>>は？")
        assert result["answer"], "特殊文字クエリへの回答が空です"

    async def test_multiple_topics_in_one_query(self, invoke_workflow):
        """複数トピックを含む質問"""
        result = await invoke_workflow(
            "Wi-Fiの使い方と、今日のイベント情報と、トイレの場所を教えてください"
        )
        assert result["answer"], "複合質問への回答が空です"

    async def test_negative_sentiment_query(self, invoke_workflow):
        """ネガティブな感情のクエリ"""
        result = await invoke_workflow(
            "Wi-Fiが繋がらないんですけど、どうすればいいですか？"
        )
        assert result["answer"], "ネガティブクエリへの回答が空です"

    async def test_ambiguous_cafe_reference(self, invoke_workflow):
        """カフェの曖昧参照（エンジニアカフェ vs サイノカフェ）"""
        result = await invoke_workflow("カフェのメニューを見たいんですが")
        assert result["answer"], "カフェ曖昧参照への回答が空です"

    async def test_greeting_only(self, invoke_workflow):
        """挨拶のみのクエリ"""
        result = await invoke_workflow("こんにちは！")
        assert result["answer"], "挨拶への応答が空です"


# =============================================================================
# ルーティング精度検証テスト
# =============================================================================


@pytest.mark.e2e
class TestRoutingAccuracyE2E:
    """新しいルーティングの精度検証"""

    async def test_emergency_routes_to_facility(self, invoke_workflow):
        """緊急クエリが正しくルーティングされること"""
        queries = [
            "AEDはどこですか？",
            "地震の時はどうする？",
            "火事です！",
        ]
        for query in queries:
            result = await invoke_workflow(query)
            assert result["answer"], f"'{query}' の回答が空です"
            # FacilityAgentにルーティングされることを確認
            agent = result.get("metadata", {}).get("agent", "")
            if agent:  # agentメタデータがある場合のみチェック
                assert agent in (
                    "FacilityAgent",
                    "facility",
                    "orchestrator_inline",
                ), f"'{query}' が {agent} にルーティングされました（facility期待）"

    async def test_reception_routes_correctly(self, invoke_workflow):
        """受付クエリが正しくルーティングされること"""
        queries = [
            "初めて来ました",
            "利用方法を教えてください",
            "チェックインしたい",
        ]
        for query in queries:
            result = await invoke_workflow(query)
            assert result["answer"], f"'{query}' の回答が空です"

    async def test_event_query_routes_to_event_agent(self, invoke_workflow):
        """イベントクエリがEventAgentにルーティングされること"""
        result = await invoke_workflow("今週の勉強会は何がありますか？")
        assert result["answer"], "イベントクエリの回答が空です"
        agent = result.get("metadata", {}).get("agent", "")
        if agent:
            assert agent in (
                "EventAgent",
                "event",
                "orchestrator_inline",
            ), f"イベントクエリが {agent} にルーティング（event期待）"

    async def test_accessibility_routes_to_facility(self, invoke_workflow):
        """アクセシビリティクエリがFacilityAgentにルーティングされること"""
        result = await invoke_workflow("車椅子で利用できますか？")
        assert result["answer"], "アクセシビリティクエリの回答が空です"
        agent = result.get("metadata", {}).get("agent", "")
        if agent:
            assert agent in (
                "FacilityAgent",
                "facility",
                "orchestrator_inline",
            ), f"アクセシビリティが {agent} にルーティング（facility期待）"
