"""
RouterAgent統合テスト

RouterAgentが各エージェント（BusinessInfoAgent, FacilityAgent, EventAgent）に
正しくルーティングし、MainWorkflowで完全なフローが動作することを検証する統合テストスイート。
"""

import os
import pytest
from backend.workflows.main_workflow import MainWorkflow


class TestRouterAgentIntegration:
    """RouterAgent統合テスト - MainWorkflowとの統合"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        # テスト用のダミーAPIキーを設定
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key_for_testing"
        self.workflow = MainWorkflow()

    @pytest.mark.asyncio
    async def test_route_to_business_info_agent(self):
        """営業時間クエリがBusinessInfoAgentにルーティングされる"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "エンジニアカフェの営業時間は?",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # ルーティング情報を確認
        assert "routing" in result["metadata"]
        routing = result["metadata"]["routing"]
        assert routing["agent"] == "BusinessInfoAgent"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_route_to_facility_agent(self):
        """Wi-FiクエリがFacilityAgentにルーティングされる"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "Wi-Fiはありますか?",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # ルーティング情報を確認
        assert "routing" in result["metadata"]
        routing = result["metadata"]["routing"]
        assert routing["agent"] == "FacilityAgent"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_route_to_event_agent(self):
        """イベントクエリがEventAgentにルーティングされる"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "今日のイベントは?",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # ルーティング情報を確認
        assert "routing" in result["metadata"]
        routing = result["metadata"]["routing"]
        assert routing["agent"] == "EventAgent"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_english_query_routing(self):
        """英語クエリが正しくルーティングされる"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "What are your opening hours?",
                "session_id": "test_session",
                "language": "en",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # 言語が検出されることを確認
        assert result["language"] == "en"

        # ルーティング情報を確認
        assert "routing" in result["metadata"]
        routing = result["metadata"]["routing"]
        assert routing["agent"] == "BusinessInfoAgent"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_routing_confidence(self):
        """ルーティングの信頼度が適切に設定される"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "営業時間を教えてください",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # 信頼度が含まれることを確認
        routing = result["metadata"]["routing"]
        assert "confidence" in routing
        assert isinstance(routing["confidence"], (int, float))
        assert 0 <= routing["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_metadata_preservation(self):
        """既存のmetadataが保持される"""
        initial_metadata = {"custom_key": "custom_value"}
        result = await self.workflow.graph.ainvoke(
            {
                "query": "営業時間は?",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": initial_metadata,
                "context": {},
            }
        )

        # カスタムmetadataが保持されることを確認
        assert "custom_key" in result["metadata"]
        assert result["metadata"]["custom_key"] == "custom_value"

        # ルーティング情報も追加されていることを確認
        assert "routing" in result["metadata"]

    @pytest.mark.asyncio
    async def test_emotion_field_populated(self):
        """感情フィールドが設定される"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "営業時間を教えてください",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # 感情フィールドが設定されることを確認
        assert result["emotion"] is not None
        valid_emotions = ["neutral", "happy", "sad", "surprised", "relaxed", "angry"]
        assert result["emotion"] in valid_emotions

    @pytest.mark.asyncio
    async def test_routing_with_multiple_intents(self):
        """複数の意図を持つクエリが適切にルーティングされる"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "営業時間とWi-Fiについて教えて",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # いずれかのエージェントにルーティングされることを確認
        routing = result["metadata"]["routing"]
        valid_agents = ["BusinessInfoAgent", "FacilityAgent", "GeneralKnowledgeAgent"]
        assert routing["agent"] in valid_agents

        # 回答が存在することを確認
        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_basement_keyword_detection(self):
        """地下施設キーワードが検出される"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "地下の設備は?",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # FacilityAgentにルーティングされることを確認
        routing = result["metadata"]["routing"]
        assert routing["agent"] == "FacilityAgent"

        # request_typeが施設関連（facility または basement）であることを確認
        assert routing.get("request_type") in ["basement", "facility"]


class TestWorkflowErrorHandling:
    """ワークフローのエラーハンドリングテスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key_for_testing"
        self.workflow = MainWorkflow()

    @pytest.mark.asyncio
    async def test_empty_query_handling(self):
        """空クエリのハンドリング"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "",
                "session_id": "test_session",
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # デフォルトエージェント（general_knowledge）にルーティングされることを確認
        assert result["routed_to"] == "general_knowledge"

    @pytest.mark.asyncio
    async def test_invalid_session_id_handling(self):
        """不正なセッションIDのハンドリング"""
        result = await self.workflow.graph.ainvoke(
            {
                "query": "営業時間は?",
                "session_id": "",  # 空のセッションID
                "language": "ja",
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "metadata": {},
                "context": {},
            }
        )

        # エラーにならず、適切にルーティングされることを確認
        assert "routing" in result["metadata"]
        assert result["answer"] is not None
