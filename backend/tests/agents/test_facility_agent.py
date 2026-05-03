"""
FacilityAgent テストスイート
施設情報エージェントのテスト
"""

import pytest
from unittest.mock import AsyncMock, patch
from backend.agents.facility_agent import FacilityAgent


class TestFacilityAgent:
    """FacilityAgentのテストクラス"""

    # ==========================================================================
    # 初期化テスト
    # ==========================================================================

    def test_initialization_default(self):
        """デフォルト設定での初期化テスト"""
        agent = FacilityAgent()
        assert agent is not None
        assert hasattr(agent, "enhanced_rag")
        assert hasattr(agent, "llm_provider")

    # ==========================================================================
    # 基本機能テスト - Wi-Fi
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_wifi_query_japanese(self):
        """Wi-Fi関連のクエリテスト（日本語）"""
        agent = FacilityAgent()

        # モックの設定
        with (
            patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
            patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
        ):

            mock_rag.return_value = {
                "success": True,
                "data": {
                    "context": "Wi-Fiは無料で利用できます。接続方法はスタッフにお尋ねください。",
                    "results": [],
                    "totalResults": 1,
                },
            }

            mock_llm.return_value = (
                "[relaxed]Wi-Fiは無料で利用可能です。接続方法はスタッフにお尋ねください。"
            )

            result = await agent.answer_facility_query(
                query="Wi-Fiはありますか？",
                request_type="wifi",
                language="ja",
                session_id="test_session",
            )

            # アサーション
            assert result["answer"] is not None
            assert "wifi" in result["answer"].lower() or "wi-fi" in result["answer"].lower()
            assert result["emotion"] in ["relaxed", "informative", "helpful"]
            assert result["metadata"]["agent"] == "FacilityAgent"
            assert result["metadata"]["request_type"] == "wifi"

    # ==========================================================================
    # 基本機能テスト - 設備
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_facility_query_japanese(self):
        """設備関連のクエリテスト（日本語）"""
        agent = FacilityAgent()

        with (
            patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
            patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
        ):

            mock_rag.return_value = {
                "success": True,
                "data": {
                    "context": "各席に電源コンセントがあります。プリンターは1階受付にあります。",
                    "results": [],
                    "totalResults": 1,
                },
            }

            mock_llm.return_value = "[relaxed]各席に電源コンセントがあります。"

            result = await agent.answer_facility_query(
                query="電源は使えますか？",
                request_type="facility",
                language="ja",
                session_id="test_session",
            )

            assert result["answer"] is not None
            assert result["emotion"] in ["relaxed", "informative", "helpful"]
            assert result["metadata"]["agent"] == "FacilityAgent"
            assert result["metadata"]["request_type"] == "facility"

    # ==========================================================================
    # 基本機能テスト - 地下施設
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_basement_query_japanese(self):
        """地下施設関連のクエリテスト（日本語）"""
        agent = FacilityAgent()

        with (
            patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
            patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
        ):

            mock_rag.return_value = {
                "success": True,
                "data": {
                    "context": (
                        "地下にはMTGスペース、集中スペース、"
                        "アンダースペース、"
                        "Makersスペースがあります。"
                    ),
                    "results": [],
                    "totalResults": 1,
                },
            }

            mock_llm.return_value = (
                "[relaxed]地下にはMTGスペース、集中スペース、"
                "アンダースペース、Makersスペースがあります。"
            )

            result = await agent.answer_facility_query(
                query="地下の会議室について教えて",
                request_type="basement",
                language="ja",
                session_id="test_session",
            )

            assert result["answer"] is not None
            assert result["emotion"] in ["relaxed", "guiding", "helpful"]
            assert result["metadata"]["agent"] == "FacilityAgent"
            assert result["metadata"]["request_type"] == "basement"

    # ==========================================================================
    # クエリ拡張テスト
    # ==========================================================================

    def test_enhance_query_wifi(self):
        """Wi-Fiクエリ拡張テスト"""
        agent = FacilityAgent()
        query = "Wi-Fiはありますか？"
        enhanced = agent._enhance_query(query, "wifi", "ja")

        assert "Wi-Fi" in enhanced or "無料Wi-Fi" in enhanced
        assert "インターネット" in enhanced or "接続" in enhanced

    def test_enhance_query_facility(self):
        """設備クエリ拡張テスト"""
        agent = FacilityAgent()
        query = "電源は？"
        enhanced = agent._enhance_query(query, "facility", "ja")

        assert "設備" in enhanced or "電源" in enhanced
        assert "コンセント" in enhanced or "プリンター" in enhanced

    def test_enhance_query_basement(self):
        """地下施設クエリ拡張テスト"""
        agent = FacilityAgent()
        query = "地下の施設について"
        enhanced = agent._enhance_query(query, "basement", "ja")

        assert "地下" in enhanced or "B1" in enhanced
        assert "MTGスペース" in enhanced or "集中スペース" in enhanced

    def test_alpha_c127_nearby_lunch_canonical(self):
        """gt-046: 周辺ランチは飲食持ち込みポリシーに倒さない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("周辺でランチを食べられる場所は？", "nearby", "ja")

        assert response is not None
        assert "天神地下街" in response["answer"]
        assert "西中洲" in response["answer"]
        assert "アクロス福岡" in response["answer"]
        assert "持ち込み" not in response["answer"]

    def test_alpha_c127_airport_route_canonical(self):
        """gt-064/gt-060: 空港アクセスは所要時間と運賃を含める"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "How do I get to Engineer Cafe from Fukuoka Airport?", "access", "en"
        )

        assert response is not None
        assert "11 minutes" in response["answer"]
        assert "260 yen" in response["answer"]
        assert "Exit 16" in response["answer"]

    def test_alpha_c127_available_spaces_canonical(self):
        """gt-065/gt-084: 利用可能スペース一覧を固定する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "What spaces are available at Engineer Cafe?", "facility", "en"
        )

        assert response is not None
        assert "1F Main Hall" in response["answer"]
        assert "Focus Space" in response["answer"]
        assert "MAKER's Space" in response["answer"]
        assert "paid meeting rooms" in response["answer"]

    def test_alpha_c127_multipurpose_toilet_canonical(self):
        """gt-077: 多目的トイレは通常トイレ案内に倒さない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("多目的トイレはありますか？", "toilet", "ja")

        assert response is not None
        assert "多目的トイレはありません" in response["answer"]
        assert "080-6742-7231" in response["answer"]

    def test_alpha_c127_children_policy_canonical(self):
        """gt-034: 子連れ利用は年齢制限・安全・専用設備なしを含める"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "子供を連れて利用できますか？", "children_noise", "ja"
        )

        assert response is not None
        assert "年齢制限" in response["answer"]
        assert "保護者同伴" in response["answer"]
        assert "授乳室" in response["answer"]
        assert "おむつ交換台" in response["answer"]

    def test_alpha_c127_laser_materials_canonical(self):
        """gt-044: レーザー素材は可否と禁止素材を固定する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("レーザー加工機で使える素材は？", "facility", "ja")

        assert response is not None
        assert "アクリル" in response["answer"]
        assert "PVC" in response["answer"]
        assert "ポリカーボネート" in response["answer"]
        assert "発泡スチロール" in response["answer"]

    def test_alpha_c127_projector_loan_canonical(self):
        """gt-052: AV機器貸出は主要機材とCM相談を含める"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "プロジェクターを借りることはできますか？", "facility", "ja"
        )

        assert response is not None
        assert "プロジェクター" in response["answer"]
        assert "スクリーン" in response["answer"]
        assert "マイク" in response["answer"]
        assert "コミュニティマネージャー" in response["answer"]

    def test_alpha_c127_conduct_policy_canonical(self):
        """gt-054: 勧誘禁止は仮眠禁止も含める"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "営利目的の勧誘はできますか？", "children_noise", "ja"
        )

        assert response is not None
        assert "勧誘" in response["answer"]
        assert "名刺交換" in response["answer"]
        assert "セールス" in response["answer"]
        assert "仮眠" in response["answer"]

    def test_alpha_c127_water_server_canonical(self):
        """gt-058: 水回りはサーバーなしと購入先を含める"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "ウォーターサーバーはありますか？", "facility", "ja"
        )

        assert response is not None
        assert "ウォーターサーバー" in response["answer"]
        assert "自動販売機" in response["answer"]
        assert "ふた付き" in response["answer"]
        assert "近隣コンビニ" in response["answer"]

    def test_alpha_c127_bicycle_parking_english_canonical(self):
        """gt-071: 英語の駐輪場案内を短く固定する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "Is there bicycle parking near Engineer Cafe?", "bicycle", "en"
        )

        assert response is not None
        assert "no dedicated bicycle parking" in response["answer"].lower()
        assert "public bicycle parking" in response["answer"].lower()

    # ==========================================================================
    # 地下施設フィルタリングテスト
    # ==========================================================================

    def test_filter_basement_context_specific_space(self):
        """特定の地下施設名を含むコンテキストフィルタリング"""
        agent = FacilityAgent()
        context = """
        地下にはMTGスペースがあります。予約不要です。
        集中スペースは静かな作業環境です。
        アンダースペースはイベント用です。要予約。
        """
        query = "MTGスペースについて"
        filtered = agent._filter_basement_context(context, query, "ja")

        assert "MTGスペース" in filtered
        # 特定の施設名のみに絞られる
        assert "MTGスペース" in filtered

    def test_filter_basement_context_general(self):
        """一般的な地下施設クエリの場合、全情報を返す"""
        agent = FacilityAgent()
        context = """
        地下にはMTGスペース、集中スペース、アンダースペース、Makersスペースがあります。
        """
        query = "地下の施設について"
        filtered = agent._filter_basement_context(context, query, "ja")

        # 一般的なクエリの場合は全情報を返す
        assert "地下" in filtered or "MTGスペース" in filtered

    # ==========================================================================
    # 感情タグ決定テスト
    # ==========================================================================

    def test_determine_emotion_from_text(self):
        """レスポンステキストから感情タグを抽出"""
        agent = FacilityAgent()

        assert agent._determine_emotion("wifi", "[happy]Wi-Fiは無料です") == "happy"
        assert agent._determine_emotion("wifi", "[sad]Wi-Fiは利用できません") == "sad"
        assert agent._determine_emotion("wifi", "[relaxed]Wi-Fiがあります") == "relaxed"

    def test_wifi_canonical_response_korean_public_guest_credentials(self):
        """通常のWi-Fi質問には公開ゲストSSIDとパスワードを案内する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("와이파이 비밀번호가 뭐예요?", "wifi", "ko")

        assert response is not None
        assert "engnecf-guest-2.4GHz" in response["answer"]
        assert "engnecf-guest-5GHz" in response["answer"]
        assert "akarenga-112years" in response["answer"]
        assert "테라스" in response["answer"]

    def test_3d_printer_filament_price_canonical_precedes_general_printer(self):
        """3Dプリンターのフィラメント料金は一般プリンター回答に倒さない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "3Dプリンターのフィラメント料金を教えてください",
            "facility",
            "ja",
        )

        assert response is not None
        assert "2円/g" in response["answer"]
        assert "福岡市在住の学生は無料" in response["answer"]
        assert "紙の印刷" not in response["answer"]

    def test_lost_found_canonical_response(self):
        """忘れ物は受付・電話番号案内に固定する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("忘れ物をしたのですが", "lost_found", "ja")

        assert response is not None
        assert "1階のエンジニアカフェ受付" in response["answer"]
        assert "080-6742-7231" in response["answer"]

    def test_chinese_food_policy_canonical(self):
        """中国語の持ち込み食物質問を food policy として扱う"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("可以自己带食物进去吗？", "food_drink", "zh")

        assert response is not None
        assert "外带食物原则上不允许" in response["answer"]
        assert "cafe&bar saino" in response["answer"]

    def test_saino_food_menu_canonical_precedes_food_policy(self):
        """gt-016: サイノカフェのメニューを一般持ち込みポリシーに倒さない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "サイノカフェのフードメニューを教えてください",
            "food_drink",
            "ja",
        )

        assert response is not None
        assert "てりたまハンバーグサンド" in response["answer"]
        assert "ツナチーズメルトサンド" in response["answer"]
        assert "ドリンクセット" in response["answer"]
        assert "持ち込み" not in response["answer"]

    def test_saino_alcohol_canonical_precedes_food_policy(self):
        """gt-018: サイノカフェのアルコール質問を一般飲食ポリシーに倒さない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "サイノカフェでアルコールは飲めますか？",
            "food_drink",
            "ja",
        )

        assert response is not None
        assert "18:00〜20:00" in response["answer"]
        assert "ハイネケン500円" in response["answer"]
        assert "カクテル各700円" in response["answer"]
        assert "持ち込み" not in response["answer"]

    def test_saino_coffee_price_canonical(self):
        """gt-017: サイノカフェのコーヒー価格を具体価格で固定する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "サイノカフェのコーヒーの値段は？",
            "food_drink",
            "ja",
        )

        assert response is not None
        assert "ブレンドコーヒー380円" in response["answer"]
        assert "カフェラテ570円" in response["answer"]
        assert "カフェモカ700円" in response["answer"]

    def test_access_canonical_response_english(self):
        """アクセス案内は施設名と最寄り駅を含める"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("Where is Engineer Cafe located?", "access", "en")

        assert response is not None
        assert "Red Brick Culture Hall" in response["answer"]
        assert "Tenjin Station" in response["answer"]

    def test_power_outlet_query_does_not_route_to_access(self):
        """whereを含む電源質問は所在地ではなく電源案内にする"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "Where can I find power outlets?", "facility", "en"
        )

        assert response is not None
        assert "Power outlets" in response["answer"]
        assert "reception staff" in response["answer"]
        assert "Tenjin Station" not in response["answer"]

    def test_access_canonical_response_japanese_includes_parking_context(self):
        """アクセス案内は徒歩導線と駐車場注意を含める"""
        agent = FacilityAgent()
        response = agent._get_canonical_response(
            "エンジニアカフェへのアクセス方法は？", "access", "ja"
        )

        assert response is not None
        assert "天神駅" in response["answer"]
        assert "徒歩約5分" in response["answer"]
        assert "天神4丁目" in response["answer"]
        assert "専用駐車場はない" in response["answer"]

    def test_generic_wifi_query_does_not_expose_credentials(self):
        """一般的なWi-Fi可否質問では認証情報回答へ固定しない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("Wi-Fiはありますか？", "wifi", "ja")

        assert response is None

    def test_wifi_password_canonical_response_does_not_expose_literal_secret(self):
        """実地では受付カード・スタッフ確認へ誘導し、固定パスワードを出さない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("Wi-Fiのパスワードは何ですか？", "wifi", "ja")

        assert response is not None
        assert "受付カード" in response["answer"]
        assert "akarenga-112years" not in response["answer"]

    def test_bringing_laptop_does_not_match_food_policy(self):
        """bringだけで飲食持ち込み回答へ倒さない"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("Can I bring my laptop?", "facility", "en")

        assert response is None

    def test_temporary_exit_canonical_response_japanese(self):
        """gt-038: 一時外出ルールは受付カード保持/返却条件まで固定する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("一時外出のルールは？", "temporary_exit", "ja")

        assert response is not None
        assert "15分以内" in response["answer"]
        assert "受付カード" in response["answer"]
        assert "15分以上" in response["answer"]
        assert "退館手続き" in response["answer"]
        assert response["metadata"]["sources"] == ["enhanced_rag"]

    def test_pet_policy_canonical_response_japanese(self):
        """gt-057: 補助犬は可、それ以外のペットはテラス含め不可に固定する"""
        agent = FacilityAgent()
        response = agent._get_canonical_response("ペットを連れて入れますか？", "pets", "ja")

        assert response is not None
        assert "補助犬" in response["answer"]
        assert "同伴できます" in response["answer"]
        assert "それ以外のペット" in response["answer"]
        assert "テラス" in response["answer"]
        assert "同伴できません" in response["answer"]
        assert response["metadata"]["sources"] == ["enhanced_rag"]

    def test_pet_policy_does_not_match_pet_bottle_or_english_substrings(self):
        """ペットボトル and English substrings should not use the pet policy answer."""
        agent = FacilityAgent()

        assert not agent._asks_pet_policy("ペットボトルは持ち込めますか？")
        assert not agent._asks_pet_policy("Tell me about the competition rules.")

    def test_pet_policy_uses_policy_rag_category_when_not_canonical(self):
        """ペット系 request_type は policy カテゴリのKBを検索する"""
        agent = FacilityAgent()

        assert agent._map_request_type_to_rag_category("pets") == "policy"

    @pytest.mark.asyncio
    async def test_smoking_query_uses_smoking_rag_category(self):
        """喫煙ポリシーはfacility-infoではなくsmokingカテゴリで検索する"""
        agent = FacilityAgent()

        with (
            patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
            patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_rag.return_value = {
                "success": True,
                "data": {
                    "context": "エンジニアカフェは全館禁煙です。",
                    "results": [],
                    "totalResults": 1,
                },
            }
            mock_llm.return_value = "[relaxed]실내에서는 흡연할 수 없습니다."

            result = await agent.answer_facility_query(
                query="실내에서 흡연할 수 있나요?",
                request_type="smoking",
                language="ko",
            )

        assert result["metadata"]["sources"] == ["enhanced_rag"]
        assert result["metadata"]["category"] == "smoking"
        mock_rag.assert_awaited_once()
        assert mock_rag.await_args.kwargs["category"] == "smoking"

    def test_determine_emotion_default(self):
        """デフォルト感情タグ"""
        agent = FacilityAgent()

        # requestTypeに基づくデフォルト
        assert agent._determine_emotion("wifi", "Wi-Fiがあります") == "informative"
        assert agent._determine_emotion("facility", "電源があります") == "informative"
        assert agent._determine_emotion("basement", "地下施設があります") == "guiding"

    # ==========================================================================
    # エラーハンドリングテスト
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_error_handling_rag_failure(self):
        """RAG検索失敗時のエラーハンドリング"""
        agent = FacilityAgent()

        with patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag:

            mock_rag.return_value = {"success": False, "error": "RAG search failed"}

            result = await agent.answer_facility_query(
                query="Wi-Fiはありますか？",
                request_type="wifi",
                language="ja",
                session_id="test_session",
            )

            # フォールバック応答を返す
            assert result["answer"] is not None
            assert result["emotion"] == "apologetic"
            assert result["metadata"]["confidence"] == 0.3
            assert result["metadata"]["sources"] == ["fallback"]

    @pytest.mark.asyncio
    async def test_error_handling_empty_context(self):
        """コンテキストが空の場合のエラーハンドリング"""
        agent = FacilityAgent()

        with patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag:

            mock_rag.return_value = {"success": True, "data": {"context": "", "results": []}}

            result = await agent.answer_facility_query(
                query="Wi-Fiはありますか？",
                request_type="wifi",
                language="ja",
                session_id="test_session",
            )

            # フォールバック応答を返す
            assert result["answer"] is not None
            assert result["emotion"] == "apologetic"

    @pytest.mark.asyncio
    async def test_error_handling_llm_failure(self):
        """LLM生成失敗時のエラーハンドリング"""
        agent = FacilityAgent()

        with (
            patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
            patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
        ):

            mock_rag.return_value = {
                "success": True,
                "data": {"context": "Wi-Fiがあります", "results": []},
            }

            mock_llm.side_effect = Exception("LLM error")

            result = await agent.answer_facility_query(
                query="Wi-Fiはありますか？",
                request_type="wifi",
                language="ja",
                session_id="test_session",
            )

            # フォールバック応答を返す
            assert result["answer"] is not None
            assert result["emotion"] == "apologetic"

    # ==========================================================================
    # 英語クエリテスト
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_wifi_query_english(self):
        """Wi-Fi関連のクエリテスト（英語）"""
        agent = FacilityAgent()

        with (
            patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
            patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
        ):

            mock_rag.return_value = {
                "success": True,
                "data": {"context": "Free Wi-Fi is available.", "results": []},
            }

            mock_llm.return_value = "[relaxed]Free Wi-Fi is available."

            result = await agent.answer_facility_query(
                query="Is there Wi-Fi?",
                request_type="wifi",
                language="en",
                session_id="test_session",
            )

            assert result["answer"] is not None
            assert result["emotion"] in ["relaxed", "informative", "helpful"]

    # ==========================================================================
    # 統合テスト
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_integration_multiple_request_types(self):
        """複数のrequestTypeで正常に動作するか"""
        agent = FacilityAgent()

        request_types = ["wifi", "facility", "basement"]

        for request_type in request_types:
            with (
                patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
                patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
            ):

                mock_rag.return_value = {
                    "success": True,
                    "data": {"context": "テスト情報", "results": []},
                }

                mock_llm.return_value = f"[relaxed]テスト応答 for {request_type}"

                result = await agent.answer_facility_query(
                    query=f"{request_type}について教えて",
                    request_type=request_type,
                    language="ja",
                    session_id="test_session",
                )

                assert result["answer"] is not None
                assert result["metadata"]["request_type"] == request_type


class TestAccessibilitySummary:
    """get_accessibility_summary() のテスト"""

    def test_default_accessibility_info_japanese(self):
        """日本語デフォルトアクセシビリティ情報"""
        info = FacilityAgent._get_default_accessibility_info("ja")

        assert "1909" in info["summary"]
        assert "車椅子" in info["summary"] or "1階" in info["summary"]
        assert "wheelchair" in info or "車椅子" in info.get("wheelchair", "")
        assert info["building_note"] is not None

    def test_default_accessibility_info_english(self):
        """英語デフォルトアクセシビリティ情報"""
        info = FacilityAgent._get_default_accessibility_info("en")

        assert "1909" in info["summary"]
        assert "wheelchair" in info["summary"].lower()
        assert info["elevator"] is not None

    @pytest.mark.asyncio
    async def test_returns_rag_based_summary(self):
        """RAG成功時にLLMサマリーを返すこと"""
        agent = FacilityAgent()

        with (
            patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag,
            patch.object(agent.llm_provider, "generate", new_callable=AsyncMock) as mock_llm,
        ):
            mock_rag.return_value = {
                "success": True,
                "data": {
                    "context": "1階は車椅子対応。地下はアクセス制限あり。",
                    "results": [],
                },
            }
            mock_llm.return_value = "1階は車椅子でご利用可能です。地下は制限があります。"

            result = await agent.get_accessibility_summary("ja")

            assert result["has_info"] is True
            assert "車椅子" in result["summary"]
            assert result["details"]["raw_context"] is not None

    @pytest.mark.asyncio
    async def test_returns_default_on_rag_failure(self):
        """RAG失敗時にデフォルト情報を返すこと"""
        agent = FacilityAgent()

        with patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag:
            mock_rag.return_value = {"success": False, "error": "search failed"}

            result = await agent.get_accessibility_summary("ja")

            assert result["has_info"] is False
            assert "1909" in result["summary"]

    @pytest.mark.asyncio
    async def test_returns_default_on_exception(self):
        """例外発生時にデフォルト情報を返すこと"""
        agent = FacilityAgent()

        with patch.object(agent.enhanced_rag, "search", new_callable=AsyncMock) as mock_rag:
            mock_rag.side_effect = Exception("connection error")

            result = await agent.get_accessibility_summary("en")

            assert result["has_info"] is False
            assert "1909" in result["summary"]
            assert "wheelchair" in result["summary"].lower()
