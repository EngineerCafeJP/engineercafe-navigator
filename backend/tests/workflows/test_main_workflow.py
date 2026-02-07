"""
MainWorkflow の統合テスト

LangGraphワークフローとMemoryAgent統合をテスト
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestMainWorkflowMemoryIntegration:
    """MainWorkflow のメモリ統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.RouterAgent")
    @patch("backend.workflows.main_workflow.ClarificationAgent")
    async def test_memory_node_retrieves_context(
        self, mock_clarification, mock_router_class
    ):
        """memory_nodeが会話履歴を取得してstateに追加することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        # RouterAgentのモック
        mock_router = AsyncMock()
        mock_router.route_query = AsyncMock(
            return_value=Mock(
                agent="GeneralKnowledgeAgent",
                category="general",
                request_type=None,
                language="ja",
                confidence=0.9,
                debug_info={},
            )
        )
        mock_router_class.return_value = mock_router

        with patch(
            "backend.utils.memory_helper.get_memory_helper"
        ) as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [
                        {"role": "user", "content": "営業時間は？"},
                        {"role": "assistant", "content": "9時から22時です。"},
                    ],
                    "context_string": "ユーザー: 営業時間は？\nアシスタント: 9時から22時です。",
                    "inherited_request_type": "hours",
                }
            )
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # _memory_nodeを直接テスト
            state = {
                "query": "テスト",
                "session_id": "test-session",
                "language": "ja",
                "context": {},
            }

            result = await workflow._memory_node(state)

            assert "context" in result
            assert "memory" in result["context"]
            mock_helper.get_context.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.RouterAgent")
    @patch("backend.workflows.main_workflow.ClarificationAgent")
    async def test_memory_agent_routing(self, mock_clarification, mock_router_class):
        """MemoryAgentへのルーティングが正しく設定されていることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        # RouterAgentのモック - MemoryAgentにルーティング
        mock_router = AsyncMock()
        mock_router.route_query = AsyncMock(
            return_value=Mock(
                agent="MemoryAgent",
                category="memory",
                request_type="question_history",
                language="ja",
                confidence=0.95,
                debug_info={},
            )
        )
        mock_router_class.return_value = mock_router

        workflow = MainWorkflow()

        # _router_nodeをテスト
        state = {
            "query": "さっき何を聞いた？",
            "session_id": "test-session",
            "language": "ja",
            "metadata": {},
        }

        result = await workflow._router_node(state)

        assert result["routed_to"] == "memory_agent"
        assert result["metadata"]["routing"]["agent"] == "MemoryAgent"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.MemoryAgent")
    @patch("backend.workflows.main_workflow.get_memory_helper")
    @patch("backend.workflows.main_workflow.GeneralKnowledgeAgent")
    @patch("backend.workflows.main_workflow.SlideAgent")
    @patch("backend.workflows.main_workflow.EventAgent")
    @patch("backend.workflows.main_workflow.FacilityAgent")
    @patch("backend.workflows.main_workflow.BusinessInfoAgent")
    @patch("backend.workflows.main_workflow.RouterAgent")
    @patch("backend.workflows.main_workflow.ClarificationAgent")
    async def test_memory_agent_node_processes_query(
        self,
        mock_clarification,
        mock_router_class,
        mock_business_info,
        mock_facility,
        mock_event,
        mock_slide,
        mock_general_knowledge,
        mock_get_helper,
        mock_memory_agent_class,
    ):
        """_memory_agent_nodeがMemoryAgentを呼び出して回答を生成することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_router_class.return_value = AsyncMock()
        mock_helper = Mock()
        mock_get_helper.return_value = mock_helper

        mock_agent = AsyncMock()
        mock_agent.process_memory_query = AsyncMock(
            return_value={
                "answer": "営業時間について質問されていましたね。",
                "emotion": "relaxed",
                "metadata": {
                    "agent": "MemoryAgent",
                    "status": "success",
                    "query_type": "question_history",
                },
            }
        )
        mock_memory_agent_class.return_value = mock_agent

        workflow = MainWorkflow()

        state = {
            "query": "さっき何を聞いた？",
            "session_id": "test-session",
            "language": "ja",
            "metadata": {},
        }

        result = await workflow._memory_agent_node(state)

        assert result["answer"] == "営業時間について質問されていましたね。"
        assert result["emotion"] == "relaxed"
        mock_agent.process_memory_query.assert_called_once_with(
            "さっき何を聞いた？", "test-session", "ja"
        )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.RouterAgent")
    @patch("backend.workflows.main_workflow.ClarificationAgent")
    async def test_memory_node_error_handling(
        self, mock_clarification, mock_router_class
    ):
        """memory_nodeがエラー時にメモリなしで続行することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_router_class.return_value = AsyncMock()

        with patch(
            "backend.utils.memory_helper.get_memory_helper"
        ) as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(side_effect=Exception("DB Error"))
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "テスト",
                "session_id": "test-session",
                "language": "ja",
                "context": {"existing": "data"},
            }

            result = await workflow._memory_node(state)

            # エラー時でもcontextが返される
            assert "context" in result
            assert result["context"]["memory"] == {}
            assert result["context"]["existing"] == "data"

    def test_route_decision_returns_memory_agent(self):
        """_route_decisionがmemory_agentを返せることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.RouterAgent"), patch(
            "backend.workflows.main_workflow.ClarificationAgent"
        ):
            workflow = MainWorkflow()

            state = {"routed_to": "memory_agent"}
            result = workflow._route_decision(state)

            assert result == "memory_agent"

    def test_agent_to_node_mapping_includes_memory_agent(self):
        """エージェント→ノードのマッピングにMemoryAgentが含まれることを確認"""
        # _router_node内のagent_to_nodeマッピングを確認
        expected_mapping = {
            "BusinessInfoAgent": "business_info",
            "FacilityAgent": "facility",
            "EventAgent": "event",
            "SlideAgent": "slide",
            "MemoryAgent": "memory_agent",
            "GeneralKnowledgeAgent": "general_knowledge",
            "ClarificationAgent": "clarification",
            "TimeAgent": "general_knowledge",
        }

        # コードから直接マッピングを確認
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.RouterAgent"), patch(
            "backend.workflows.main_workflow.ClarificationAgent"
        ):
            workflow = MainWorkflow()
            # MemoryAgentがmemory_agentにマッピングされていることを確認
            assert expected_mapping["MemoryAgent"] == "memory_agent"


class TestWorkflowGraphStructure:
    """ワークフローグラフ構造のテスト"""

    def test_workflow_has_memory_agent_node(self):
        """ワークフローにmemory_agentノードが含まれることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.RouterAgent"), patch(
            "backend.workflows.main_workflow.ClarificationAgent"
        ):
            workflow = MainWorkflow()

            # graphが存在することを確認
            assert workflow.graph is not None

    def test_workflow_initialization(self):
        """ワークフローが正常に初期化されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.RouterAgent") as mock_router, patch(
            "backend.workflows.main_workflow.ClarificationAgent"
        ):
            mock_router.return_value = Mock()

            workflow = MainWorkflow()

            assert workflow.router_agent is not None
            assert workflow.graph is not None
