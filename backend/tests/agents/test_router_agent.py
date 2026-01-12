"""
RouterAgent のユニットテスト
"""

import os
import pytest
from unittest.mock import AsyncMock
from backend.agents.router_agent import RouterAgent


class TestRouterAgent:
    """RouterAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        # テスト用のダミーAPIキーを設定
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key_for_testing"
        self.agent = RouterAgent(debug_mode=False)

    @pytest.mark.asyncio
    async def test_route_query_business_info(self):
        """営業情報クエリのルーティング"""
        result = await self.agent.route_query(
            query="営業時間を教えてください", session_id="test_session"
        )

        assert result.agent == "BusinessInfoAgent"
        assert result.category in ["facility-info", "hours"]
        assert result.language in ["ja", "en"]

    @pytest.mark.asyncio
    async def test_route_query_facility(self):
        """施設情報クエリのルーティング"""
        result = await self.agent.route_query(query="Wi-Fiは使えますか?", session_id="test_session")

        assert result.agent == "FacilityAgent"
        assert result.request_type == "wifi"
        assert result.language == "ja"

    @pytest.mark.asyncio
    async def test_route_query_event(self):
        """イベントクエリのルーティング"""
        result = await self.agent.route_query(query="今日のイベントは?", session_id="test_session")

        assert result.agent == "EventAgent"
        assert result.category == "calendar"

    @pytest.mark.asyncio
    async def test_route_query_memory(self):
        """メモリ関連クエリのルーティング"""
        result = await self.agent.route_query(query="さっき何を聞いた?", session_id="test_session")

        assert result.agent == "MemoryAgent"
        assert result.category == "memory"

    @pytest.mark.asyncio
    async def test_route_query_clarification(self):
        """明確化クエリのルーティング"""
        result = await self.agent.route_query(
            query="カフェの場所はどこですか?", session_id="test_session"
        )

        assert result.agent == "ClarificationAgent"
        assert result.category == "cafe-clarification-needed"

    @pytest.mark.asyncio
    async def test_route_query_general_knowledge(self):
        """一般知識クエリのルーティング"""
        result = await self.agent.route_query(query="天気はどうですか?", session_id="test_session")

        assert result.agent == "GeneralKnowledgeAgent"
        assert result.category == "general"

    @pytest.mark.asyncio
    async def test_language_detection_japanese(self):
        """日本語検出のテスト"""
        result = await self.agent.route_query(query="こんにちは", session_id="test_session")

        assert result.language == "ja"

    @pytest.mark.asyncio
    async def test_language_detection_english(self):
        """英語検出のテスト"""
        result = await self.agent.route_query(
            query="Hello, how are you?", session_id="test_session"
        )

        assert result.language == "en"

    def test_extract_request_type_wifi(self):
        """Wi-Fiリクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("Wi-Fiは使えますか?")
        assert request_type == "wifi"

    def test_extract_request_type_hours(self):
        """営業時間リクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("営業時間は何時から?")
        assert request_type == "hours"

    def test_extract_request_type_price(self):
        """料金リクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("料金はいくらですか?")
        assert request_type == "price"

    def test_extract_request_type_location(self):
        """場所リクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("場所はどこですか?")
        assert request_type == "location"

    def test_extract_request_type_facility(self):
        """設備リクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("設備について教えて")
        assert request_type == "facility"

    def test_extract_request_type_basement(self):
        """地下施設リクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("地下のスペースについて")
        assert request_type == "basement"

    def test_extract_request_type_meeting_room(self):
        """会議室リクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("会議室を使いたい")
        assert request_type == "meeting-room"

    def test_extract_request_type_event(self):
        """イベントリクエストタイプの抽出"""
        request_type = self.agent._extract_request_type("イベントの予定は?")
        assert request_type == "event"

    def test_is_memory_related_question(self):
        """メモリ関連質問の判定"""
        # メモリ関連のキーワード
        assert self.agent._is_memory_related_question("さっき何を聞いた?")
        assert self.agent._is_memory_related_question("前に話したことを覚えてる?")
        assert self.agent._is_memory_related_question("Do you remember what I asked?")

        # ビジネス関連は除外
        assert not self.agent._is_memory_related_question("メニューはどんな感じ?")
        assert not self.agent._is_memory_related_question("営業時間は何時から?")

        # 施設関連は除外
        assert not self.agent._is_memory_related_question("地下のスペースはどんな感じ?")

    def test_is_context_dependent_query(self):
        """文脈依存クエリの判定"""
        assert self.agent._is_context_dependent_query("土曜日は?")
        assert self.agent._is_context_dependent_query("日曜日も同じ?")
        assert self.agent._is_context_dependent_query("sainoの方は?")
        assert self.agent._is_context_dependent_query("じゃあエンジニアカフェ!")

        # 通常のクエリ
        assert not self.agent._is_context_dependent_query("営業時間を教えてください")

    def test_select_agent_with_request_type_price(self):
        """リクエストタイプ（料金）に基づくエージェント選択"""
        agent = self.agent._select_agent(
            category="facility-info", request_type="price", query="料金は?"
        )
        assert agent == "BusinessInfoAgent"

    def test_select_agent_with_request_type_wifi(self):
        """リクエストタイプ（Wi-Fi）に基づくエージェント選択"""
        agent = self.agent._select_agent(
            category="facility-info", request_type="wifi", query="Wi-Fiは?"
        )
        assert agent == "FacilityAgent"

    def test_select_agent_with_category_calendar(self):
        """カテゴリ（カレンダー）に基づくエージェント選択"""
        agent = self.agent._select_agent(
            category="calendar", request_type=None, query="イベントは?"
        )
        assert agent == "EventAgent"

    def test_select_agent_with_context_dependent_saino(self):
        """文脈依存（Saino）クエリのエージェント選択"""
        agent = self.agent._select_agent(
            category="general", request_type=None, query="sainoの方は?"
        )
        assert agent == "BusinessInfoAgent"

    def test_select_agent_with_context_dependent_hours(self):
        """文脈依存（営業時間）クエリのエージェント選択"""
        agent = self.agent._select_agent(category="general", request_type=None, query="土曜日は?")
        assert agent == "BusinessInfoAgent"

    @pytest.mark.asyncio
    async def test_route_query_with_memory_system(self):
        """メモリシステム連携のルーティングテスト"""
        # メモリシステムのモック作成
        mock_memory = AsyncMock()
        mock_memory.get_previous_request_type = AsyncMock(return_value="hours")

        result = await self.agent.route_query(
            query="土曜日は?", session_id="test_session", memory_system=mock_memory
        )

        # 文脈依存クエリで、前回のrequest_typeが継承される
        assert result.request_type == "hours"
        mock_memory.get_previous_request_type.assert_called_once_with("test_session")

    @pytest.mark.asyncio
    async def test_route_result_structure(self):
        """RouteResultの構造テスト"""
        result = await self.agent.route_query(query="営業時間は?", session_id="test_session")

        assert hasattr(result, "agent")
        assert hasattr(result, "category")
        assert hasattr(result, "request_type")
        assert hasattr(result, "language")
        assert hasattr(result, "confidence")
        assert hasattr(result, "debug_info")

        assert isinstance(result.debug_info, dict)
        assert "language_detection" in result.debug_info
        assert "classification" in result.debug_info

    @pytest.mark.asyncio
    async def test_close_method(self):
        """closeメソッドのテスト"""
        # closeメソッドが正常に実行できることを確認
        await self.agent.close()
        # 再度作成
        self.agent = RouterAgent(debug_mode=False)
