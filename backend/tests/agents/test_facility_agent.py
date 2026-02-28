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
