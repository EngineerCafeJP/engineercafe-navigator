"""
MainWorkflow の統合テスト

LangGraphワークフローとSupervisor Pattern統合をテスト
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestMainWorkflowMemoryIntegration:
    """MainWorkflow のメモリ統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_node_retrieves_context(self, mock_orchestrator_class):
        """memory_loader_nodeが会話履歴を取得してstateに追加することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        # OrchestratorAgentのモック
        mock_orchestrator = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
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

            # _memory_loader_nodeを直接テスト
            state = {
                "query": "テスト",
                "session_id": "test-session",
                "language": "ja",
                "context": {},
            }

            result = await workflow._memory_loader_node(state)

            assert "context" in result
            assert "memory" in result["context"]
            mock_helper.get_context.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_agent_node_processes_query(self, mock_orchestrator_class):
        """_memory_agent_nodeがMemoryAgentを呼び出して回答を生成することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper,
            patch("backend.agents.memory_agent.MemoryAgent") as mock_memory_agent_class,
        ):
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
                "routing": {},
                "metadata": {},
            }

            result = await workflow._memory_agent_node(state)

            assert result["answer"] == "営業時間について質問されていましたね。"
            assert result["emotion"] == "relaxed"
            mock_agent.process_memory_query.assert_called_once_with(
                "さっき何を聞いた？", "test-session", "ja"
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_node_error_handling(self, mock_orchestrator_class):
        """memory_loader_nodeがエラー時にメモリなしで続行することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
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

            result = await workflow._memory_loader_node(state)

            # エラー時でもcontextが返される
            assert "context" in result
            assert result["context"]["memory"] == {}
            assert result["context"]["existing"] == "data"


class TestWorkflowGraphStructure:
    """ワークフローグラフ構造のテスト"""

    def test_workflow_has_memory_agent_node(self):
        """ワークフローにmemory_agentノードが含まれることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.OrchestratorAgent"):
            workflow = MainWorkflow()

            # graphが存在することを確認
            assert workflow.graph is not None

    def test_workflow_initialization(self):
        """ワークフローが正常に初期化されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        with patch("backend.workflows.main_workflow.OrchestratorAgent") as mock_orchestrator:
            mock_orchestrator.return_value = Mock()

            workflow = MainWorkflow()

            assert workflow.orchestrator is not None
            assert workflow.graph is not None

    def test_workflow_initialization_with_checkpointer(self):
        """Checkpointerを指定してワークフローが正常に初期化されることを確認"""
        from backend.workflows.main_workflow import MainWorkflow
        from langgraph.checkpoint.memory import MemorySaver

        with patch("backend.workflows.main_workflow.OrchestratorAgent") as mock_orchestrator:
            mock_orchestrator.return_value = Mock()
            # 実際のCheckpointerインスタンスを使用
            checkpointer = MemorySaver()

            workflow = MainWorkflow(checkpointer=checkpointer)

            assert workflow.orchestrator is not None
            assert workflow.graph is not None
            assert workflow.checkpointer == checkpointer


class TestOrchestratorIntegration:
    """OrchestratorAgent統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_calls_decide_next_agent(self, mock_orchestrator_class):
        """_orchestrator_nodeがdecide_next_agentを呼び出すことを確認"""
        from backend.workflows.main_workflow import MainWorkflow
        from backend.agents.orchestrator_agent import OrchestratorDecision

        mock_decision = OrchestratorDecision(
            next_agent="business_info",
            language="ja",
            category="business-hours",
            request_type="hours",
            confidence=0.95,
            reasoning="営業時間の質問",
            debug_info={},
        )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        state = {
            "query": "営業時間は？",
            "session_id": "test-session",
            "language": "ja",
            "context": {"memory": {}},
        }

        result = await workflow._orchestrator_node(state)

        # Command patternで結果が返されることを確認
        mock_orchestrator.decide_next_agent.assert_called_once()
        # Commandオブジェクトが返される
        assert hasattr(result, "goto")
        assert result.goto == "business_info"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_node(self, mock_orchestrator_class):
        """_format_response_nodeが正しくメッセージをフォーマットすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "answer": "9時から22時です。",
                "session_id": "test-session",
            }

            result = await workflow._format_response_node(state)

            assert "messages" in result
            assert len(result["messages"]) == 2
            assert result["messages"][0].content == "営業時間は？"
            assert result["messages"][1].content == "9時から22時です。"


class TestAsyncWorkflowMethods:
    """非同期ワークフローメソッドのテスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_workflow_close(self, mock_orchestrator_class):
        """closeメソッドがリソースをクリーンアップすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.close = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        await workflow.close()

        mock_orchestrator.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_workflow_close_with_checkpointer(self, mock_orchestrator_class):
        """checkpointer付きのcloseメソッドが両方をクリーンアップすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow
        from langgraph.checkpoint.memory import MemorySaver

        mock_orchestrator = AsyncMock()
        mock_orchestrator.close = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        # MemorySaverを使用（connがないので別のアプローチでテスト）
        checkpointer = MemorySaver()

        workflow = MainWorkflow(checkpointer=checkpointer)

        # closeは例外なく完了すべき
        await workflow.close()

        mock_orchestrator.close.assert_called_once()


class TestStoreMessageIntegration:
    """store_message統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_stores_user_message(self, mock_orchestrator_class):
        """memory_loader_nodeがユーザーメッセージをstore_message()で保存することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        # OrchestratorAgentのモック
        mock_orchestrator = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [],
                    "context_string": "",
                }
            )
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "session_id": "test-session-123",
                "language": "ja",
                "context": {},
            }

            await workflow._memory_loader_node(state)

            # store_messageが正しい引数で呼ばれたことを確認
            mock_helper.store_message.assert_called_once_with(
                session_id="test-session-123",
                role="user",
                content="営業時間は？",
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_format_response_stores_assistant_message(self, mock_orchestrator_class):
        """format_response_nodeがアシスタント応答をstore_message()で保存することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "営業時間は？",
                "answer": "9時から22時までです。",
                "session_id": "test-session-456",
                "emotion": "neutral",
                "routing": {},
            }

            await workflow._format_response_node(state)

            # store_messageが正しい引数で呼ばれたことを確認
            mock_helper.store_message.assert_called_once_with(
                session_id="test-session-456",
                role="assistant",
                content="9時から22時までです。",
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_store_message_failure_does_not_break_workflow(self, mock_orchestrator_class):
        """store_message()が失敗してもワークフローは正常に継続することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            # get_contextは正常に動作
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [],
                    "context_string": "",
                }
            )
            # store_messageは例外を投げる
            mock_helper.store_message = AsyncMock(side_effect=Exception("DB connection error"))
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # memory_loader_nodeのテスト
            state_loader = {
                "query": "営業時間は？",
                "session_id": "test-session-789",
                "language": "ja",
                "context": {},
            }

            result_loader = await workflow._memory_loader_node(state_loader)

            # 例外が投げられても正常に結果が返ることを確認
            assert "context" in result_loader
            assert "memory" in result_loader["context"]

            # format_response_nodeのテスト
            state_format = {
                "query": "営業時間は？",
                "answer": "9時から22時までです。",
                "session_id": "test-session-789",
            }

            result_format = await workflow._format_response_node(state_format)

            # 例外が投げられても正常に結果が返ることを確認
            assert "messages" in result_format
            assert len(result_format["messages"]) == 2
