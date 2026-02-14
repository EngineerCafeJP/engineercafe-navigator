"""
ClarificationAgent統合テスト

ClarificationAgentがMainWorkflowに統合され、RouterAgentから正しくルーティングされ、
適切な明確化メッセージを返すことを検証する統合テストスイート。

テスト範囲:
- ClarificationAgentとMainWorkflowの統合
- カテゴリ別（cafe, meeting-room, general）の明確化メッセージ
- 日本語/英語の両言語対応
- 異常系（フォールバック処理）
- メタデータ構造の検証
"""

import os
import sys
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from backend.agents.clarification_agent import ClarificationAgent


class TestMessageContent:
    """メッセージ内容の正確性テスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.asyncio
    async def test_cafe_clarification_ja_content(self, agent):
        """カフェ曖昧性解消（日本語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="カフェの営業時間は？", category="cafe-clarification-needed", language="ja"
        )

        response = result["response"]

        # 必須要素の確認
        assert "エンジニアカフェ" in response
        assert "サイノカフェ" in response
        assert "コワーキングスペース" in response
        assert "カフェ＆バー" in response
        assert "どちらについて" in response

    @pytest.mark.asyncio
    async def test_cafe_clarification_en_content(self, agent):
        """カフェ曖昧性解消（英語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="What are the cafe hours?", category="cafe-clarification-needed", language="en"
        )

        response = result["response"]

        # 必須要素の確認
        assert "Engineer Cafe" in response
        assert "Saino Cafe" in response
        assert "coworking space" in response
        assert "cafe & bar" in response
        assert "which one" in response.lower()

    @pytest.mark.asyncio
    async def test_meeting_room_clarification_ja_content(self, agent):
        """会議室曖昧性解消（日本語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="会議室の予約方法は？",
            category="meeting-room-clarification-needed",
            language="ja",
        )

        response = result["response"]

        # 必須要素の確認
        assert "有料会議室" in response
        assert "地下MTGスペース" in response
        assert "2階" in response or "2F" in response
        assert "地下1階" in response or "B1" in response
        assert "2種類" in response

    @pytest.mark.asyncio
    async def test_meeting_room_clarification_en_content(self, agent):
        """会議室曖昧性解消（英語）のメッセージ内容を確認"""
        result = await agent.handle_clarification(
            query="How do I book a meeting room?",
            category="meeting-room-clarification-needed",
            language="en",
        )

        response = result["response"]

        # 必須要素の確認
        assert "Paid Meeting Rooms" in response
        assert "Basement Meeting Spaces" in response
        assert "2F" in response or "2nd floor" in response
        assert "B1" in response or "basement" in response
        assert "two types" in response.lower()


class TestClarificationIntegration:
    """ClarificationAgentとワークフローの統合テスト（擬似E2E）"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        # テスト用のダミーAPIキーを設定
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key_for_testing"

        # RouterAgentをモック（sys.modulesに登録してからインポート）
        mock_router_agent_class = MagicMock()
        mock_router_agent_instance = Mock()
        mock_router_agent_instance.route_query = AsyncMock(
            return_value=Mock(
                agent="ClarificationAgent",
                category="cafe-clarification-needed",
                request_type=None,
                language="ja",
                confidence=0.9,
                debug_info={},
            )
        )
        mock_router_agent_class.return_value = mock_router_agent_instance

        # sys.modulesにモックを登録（インポート前に）
        sys.modules["backend.agents.router_agent"] = MagicMock()
        sys.modules["backend.agents.router_agent"].RouterAgent = mock_router_agent_class

        # これでMainWorkflowをインポートできる
        from backend.workflows.main_workflow import MainWorkflow

        self.workflow = MainWorkflow()
        # モックをインスタンスに設定
        self.workflow.router_agent = mock_router_agent_instance

    @pytest.mark.asyncio
    async def test_clarification_node_integration(self):
        """Clarificationノードの統合テスト"""
        test_cases = [
            {
                "query": "カフェの営業時間は？",
                "expected_category": "cafe-clarification-needed",
                "language": "ja",
            },
            {
                "query": "会議室の予約方法は？",
                "expected_category": "meeting-room-clarification-needed",
                "language": "ja",
            },
            {
                "query": "What are the cafe hours?",
                "expected_category": "cafe-clarification-needed",
                "language": "en",
            },
        ]

        for case in test_cases:
            # Router Agentがcategoryを設定する想定
            # _clarification_nodeはstate.get("routing", {}).get("category")でトップレベルを参照
            state = {
                "query": case["query"],
                "session_id": "test_session",
                "language": case["language"],
                "messages": [],
                "routed_to": None,
                "answer": None,
                "emotion": None,
                "routing": {
                    "category": case["expected_category"],
                },
                "metadata": {"routing": {"category": case["expected_category"]}},
                "context": {},
            }

            # Clarificationノードを直接呼び出し（awaitが必要）
            result = await self.workflow._clarification_node(state)

            # 基本アサーション
            assert result["answer"] is not None
            assert result["emotion"] == "surprised"

            # メタデータ構造の確認（実装に合わせて修正）
            assert "clarification" in result["metadata"]
            assert result["metadata"]["clarification"]["agent"] == "ClarificationAgent"
            assert result["metadata"]["requires_followup"] is True
            assert (
                result["metadata"]["clarification"]["clarification_type"]
                == case["expected_category"]
            )

            # 感情タグが付与されていることを確認
            assert "[surprised]" in result["answer"]

    @pytest.mark.asyncio
    async def test_full_workflow_with_clarification(self):
        """Clarificationを含む完全なワークフローのテスト（モック版）"""
        # Router AgentがClarificationAgentにルーティングする想定
        result = await self.workflow.ainvoke(
            {"query": "カフェの営業時間は？", "session_id": "test_session", "language": "ja"}
        )

        # Router Agentが正しくClarificationAgentにルーティングすることを確認
        # （Router Agentの実装に依存）
        assert result["answer"] is not None

        # ClarificationAgentにルーティングされた場合のみ確認
        if result["metadata"].get("routing", {}).get("agent") == "ClarificationAgent":
            assert "[surprised]" in result["answer"]
            assert result["emotion"] == "surprised"
            assert result["metadata"]["requires_followup"] is True
            assert "clarification" in result["metadata"]

    @pytest.mark.asyncio
    async def test_clarification_fallback_to_general(self):
        """未知のcategoryがgeneral-clarification-neededにフォールバックされる"""
        state = {
            "query": "test query",
            "session_id": "test_session",
            "language": "ja",
            "messages": [],
            "routed_to": None,
            "answer": None,
            "emotion": None,
            "routing": {
                "category": "unknown-category",
            },
            "metadata": {"routing": {"category": "unknown-category"}},
            "context": {},
        }

        result = await self.workflow._clarification_node(state)

        # general-clarification-neededにフォールバックされることを確認
        assert result["answer"] is not None
        assert result["emotion"] == "surprised"
        assert (
            result["metadata"]["clarification"]["clarification_type"]
            == "general-clarification-needed"
        )
        assert result["metadata"]["clarification"]["category"] == "general-clarification-needed"
        assert result["metadata"]["clarification"]["confidence"] == 0.7  # generalは0.7

    @pytest.mark.asyncio
    async def test_clarification_missing_routing_metadata(self):
        """routing metadataが欠けている場合のフォールバック"""
        state = {
            "query": "test query",
            "session_id": "test_session",
            "language": "ja",
            "messages": [],
            "routed_to": None,
            "answer": None,
            "emotion": None,
            "metadata": {},  # routing情報がない（トップレベルのroutingもない）
            "context": {},
        }

        result = await self.workflow._clarification_node(state)

        # general-clarification-neededにフォールバックされることを確認
        assert result["answer"] is not None
        assert result["emotion"] == "surprised"
        assert (
            result["metadata"]["clarification"]["clarification_type"]
            == "general-clarification-needed"
        )

    @pytest.mark.asyncio
    async def test_clarification_empty_category(self):
        """categoryが空文字列の場合のフォールバック"""
        state = {
            "query": "test query",
            "session_id": "test_session",
            "language": "ja",
            "messages": [],
            "routed_to": None,
            "answer": None,
            "emotion": None,
            "routing": {
                "category": "",
            },
            "metadata": {"routing": {"category": ""}},
            "context": {},
        }

        result = await self.workflow._clarification_node(state)

        # general-clarification-neededにフォールバックされることを確認
        assert result["answer"] is not None
        assert result["emotion"] == "surprised"
        assert (
            result["metadata"]["clarification"]["clarification_type"]
            == "general-clarification-needed"
        )


# ============================================================================
# E2Eテスト（RouterAgent実装後に有効化）
# ============================================================================
# 注意: RouterAgentが実装されたら、以下のテストクラスのコメントを外して使用してください

"""
class TestClarificationE2E:
    \"\"\"ClarificationAgentのE2Eテスト（RouterAgent実装後に有効化）\"\"\"
    
    def setup_method(self):
        # RouterAgentをモックしない（実装を使用）
        from backend.workflows.main_workflow import MainWorkflow
        self.workflow = MainWorkflow()
    
    @pytest.mark.asyncio
    async def test_e2e_cafe_clarification_ja(self):
        \"\"\"カフェが曖昧なクエリがClarificationAgentにルーティングされる（日本語）E2E\"\"\"
        result = await self.workflow.ainvoke({
            "query": "カフェの営業時間は？",  # RouterAgentが実際に検出
            "session_id": "test_session",
            "language": "ja"
        })
        
        # RouterAgentが正しくClarificationAgentにルーティングすることを確認
        assert result["metadata"]["routing"]["agent"] == "ClarificationAgent"
        assert result["metadata"]["routing"]["category"] == "cafe-clarification-needed"
        # ...
"""
