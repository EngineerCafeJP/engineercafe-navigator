"""
OrchestratorAgent統合テスト

OrchestratorAgentが各エージェント（business_info, facility, event）に
正しくルーティングし、MainWorkflowで完全なフローが動作することを検証する統合テストスイート。

WorkflowStateDictの構造に合わせてテスト:
- routing: トップレベルフィールド（OrchestratorAgentの決定結果）
- metadata: 各エージェントが追加するメタ情報
"""

import os
import pytest
from backend.workflows.main_workflow import MainWorkflow

pytestmark = pytest.mark.integration


def _make_state(
    query: str, language: str = "ja", session_id: str = "test_session", metadata: dict | None = None
):
    """テスト用のWorkflowStateDict互換の状態を生成"""
    return {
        "query": query,
        "session_id": session_id,
        "language": language,
        "messages": [],
        "routing": {},
        "answer": None,
        "emotion": None,
        "metadata": metadata or {},
        "context": {},
    }


class TestOrchestratorIntegration:
    """OrchestratorAgent統合テスト - MainWorkflowとの統合"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        # テスト用のダミーAPIキーを設定
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key_for_testing"
        self.workflow = MainWorkflow()

    @pytest.mark.asyncio
    async def test_route_to_business_info_agent(self):
        """営業時間クエリがbusiness_infoにルーティングされる"""
        result = await self.workflow.graph.ainvoke(_make_state("エンジニアカフェの営業時間は?"))

        # ルーティング情報を確認（トップレベルのroutingフィールド）
        assert "routing" in result
        routing = result["routing"]
        assert routing["agent"] == "business_info"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_route_to_facility_agent(self):
        """Wi-Fiクエリがfacilityにルーティングされる"""
        result = await self.workflow.graph.ainvoke(_make_state("Wi-Fiはありますか?"))

        # ルーティング情報を確認
        assert "routing" in result
        routing = result["routing"]
        assert routing["agent"] == "facility"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_route_to_event_agent(self):
        """イベントクエリがeventにルーティングされる"""
        result = await self.workflow.graph.ainvoke(_make_state("今日のイベントは?"))

        # ルーティング情報を確認
        assert "routing" in result
        routing = result["routing"]
        assert routing["agent"] == "event"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_english_query_routing(self):
        """英語クエリが正しくルーティングされる"""
        result = await self.workflow.graph.ainvoke(
            _make_state("What are your opening hours?", language="en")
        )

        # 言語が検出されることを確認
        assert result["language"] == "en"

        # ルーティング情報を確認
        assert "routing" in result
        routing = result["routing"]
        assert routing["agent"] == "business_info"

        # 回答が存在することを確認
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_routing_confidence(self):
        """ルーティングの信頼度が適切に設定される"""
        result = await self.workflow.graph.ainvoke(_make_state("営業時間を教えてください"))

        # 信頼度が含まれることを確認
        routing = result["routing"]
        assert "confidence" in routing
        assert isinstance(routing["confidence"], (int, float))
        assert 0 <= routing["confidence"] <= 1

    @pytest.mark.asyncio
    async def test_metadata_preservation(self):
        """既存のmetadataが保持される"""
        initial_metadata = {"custom_key": "custom_value"}
        result = await self.workflow.graph.ainvoke(
            _make_state("営業時間は?", metadata=initial_metadata)
        )

        # カスタムmetadataが保持されることを確認
        assert "custom_key" in result["metadata"]
        assert result["metadata"]["custom_key"] == "custom_value"

        # ルーティング情報がトップレベルに存在することを確認
        assert "routing" in result
        assert result["routing"]["agent"] == "business_info"

    @pytest.mark.asyncio
    async def test_emotion_field_populated(self):
        """感情フィールドが設定される"""
        result = await self.workflow.graph.ainvoke(_make_state("営業時間を教えてください"))

        # 感情フィールドが設定されることを確認
        assert result["emotion"] is not None
        valid_emotions = [
            "neutral",
            "happy",
            "sad",
            "surprised",
            "relaxed",
            "angry",
            "apologetic",
            "helpful",
        ]
        assert result["emotion"] in valid_emotions

    @pytest.mark.asyncio
    async def test_routing_with_multiple_intents(self):
        """複数の意図を持つクエリが適切にルーティングされる"""
        result = await self.workflow.graph.ainvoke(_make_state("営業時間とWi-Fiについて教えて"))

        # いずれかのエージェントにルーティングされることを確認
        routing = result["routing"]
        valid_agents = ["business_info", "facility", "general_knowledge"]
        assert routing["agent"] in valid_agents

        # 回答が存在することを確認
        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_basement_keyword_detection(self):
        """地下施設キーワードが検出される"""
        result = await self.workflow.graph.ainvoke(_make_state("地下の設備は?"))

        # facilityにルーティングされることを確認
        routing = result["routing"]
        assert routing["agent"] == "facility"

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
        result = await self.workflow.graph.ainvoke(_make_state("", session_id="test_session"))

        # デフォルトエージェント（general_knowledge）にルーティングされることを確認
        assert result["routing"]["agent"] == "general_knowledge"

    @pytest.mark.asyncio
    async def test_invalid_session_id_handling(self):
        """不正なセッションIDのハンドリング"""
        result = await self.workflow.graph.ainvoke(_make_state("営業時間は?", session_id=""))

        # エラーにならず、適切にルーティングされることを確認
        assert "routing" in result
        assert result["answer"] is not None
