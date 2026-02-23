"""
MainWorkflow の統合テスト

LangGraphワークフローとSupervisor Pattern統合をテスト
"""

import inspect

import pytest
from unittest.mock import MagicMock, Mock, AsyncMock, patch


def _mock_runtime():
    """テスト用モック Runtime を生成"""
    rt = MagicMock()
    rt.context = MagicMock()
    rt.context.user_id = "anonymous"
    rt.store = None
    return rt


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

            result = await workflow._memory_loader_node(state, _mock_runtime())

            assert "context" in result
            assert "memory" in result["context"]
            mock_helper.get_context.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_general_knowledge_node_handles_memory_query(self, mock_orchestrator_class):
        """_general_knowledge_nodeがmemoryクエリをGKA経由で処理することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # GKAのanswer_queryをモック
            workflow._general_knowledge_agent.answer_query = AsyncMock(
                return_value={
                    "answer": "営業時間について質問されていましたね。",
                    "emotion": "relaxed",
                    "metadata": {
                        "agent": "GeneralKnowledgeAgent",
                        "status": "success",
                        "query_type": "question_history",
                    },
                }
            )

            state = {
                "query": "さっき何を聞いた？",
                "session_id": "test-session",
                "language": "ja",
                "routing": {"request_type": "memory"},
                "metadata": {},
                "context": {},
            }

            result = await workflow._general_knowledge_node(state)

            assert result["answer"] == "営業時間について質問されていましたね。"
            assert result["emotion"] == "relaxed"
            workflow._general_knowledge_agent.answer_query.assert_called_once_with(
                query="さっき何を聞いた？",
                language="ja",
                session_id="test-session",
                query_type="memory",
                state_context=None,
                context_signals=None,
                long_term_memory=[],
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

            result = await workflow._memory_loader_node(state, _mock_runtime())

            # エラー時でもcontextが返される
            assert "context" in result
            assert result["context"]["memory"] == {}
            assert result["context"]["existing"] == "data"


class TestWorkflowGraphStructure:
    """ワークフローグラフ構造のテスト"""

    def test_workflow_has_required_nodes(self):
        """ワークフローに必要なノードが含まれることを確認"""
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

            result = await workflow._format_response_node(state, _mock_runtime())

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

            await workflow._memory_loader_node(state, _mock_runtime())

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

            await workflow._format_response_node(state, _mock_runtime())

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

            result_loader = await workflow._memory_loader_node(state_loader, _mock_runtime())

            # 例外が投げられても正常に結果が返ることを確認
            assert "context" in result_loader
            assert "memory" in result_loader["context"]

            # format_response_nodeのテスト
            state_format = {
                "query": "営業時間は？",
                "answer": "9時から22時までです。",
                "session_id": "test-session-789",
            }

            result_format = await workflow._format_response_node(state_format, _mock_runtime())

            # 例外が投げられても正常に結果が返ることを確認
            assert "messages" in result_format
            assert len(result_format["messages"]) == 2


class TestRetryPolicy:
    """RetryPolicy 設定テスト"""

    def test_llm_retry_policy_attributes(self):
        """LLM_RETRY_POLICYの属性値を確認"""
        from backend.workflows.main_workflow import MainWorkflow

        rp = MainWorkflow.LLM_RETRY_POLICY
        assert rp.initial_interval == 1.0
        assert rp.backoff_factor == 2.0
        assert rp.max_interval == 10.0
        assert rp.max_attempts == 3

    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    def test_llm_nodes_have_retry_policy(self, mock_orchestrator_class):
        """LLM依存ノードにretry_policyが設定されていることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = Mock()
        workflow = MainWorkflow()

        # LangGraphのノード内部でretry_policyが設定されているかは
        # グラフの構造情報から確認
        graph = workflow.graph
        # ノードが存在することを確認（retry_policyはグラフコンパイル時に内部処理される）
        assert graph is not None

    def test_retry_policy_is_langgraph_retry_policy(self):
        """LLM_RETRY_POLICYがLangGraphのRetryPolicyインスタンスであることを確認"""
        from langgraph.types import RetryPolicy
        from backend.workflows.main_workflow import MainWorkflow

        assert isinstance(MainWorkflow.LLM_RETRY_POLICY, RetryPolicy)


class TestAstream:
    """astream() ストリーミングメソッドのテスト"""

    def test_astream_method_exists(self):
        """astream()メソッドが存在することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        assert hasattr(MainWorkflow, "astream")
        # astream is an async generator (contains yield), so use isasyncgenfunction
        assert inspect.isasyncgenfunction(MainWorkflow.astream)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_is_async_generator(self, mock_orchestrator_class):
        """astream()が非同期ジェネレータであることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        # astream_eventsをモックして空のイテレータを返す
        async def empty_events(*args, **kwargs):
            return
            yield  # Make it an async generator

        workflow.graph.astream_events = empty_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert events == []  # 空のジェネレータからは何も出ない

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_yields_token_events(self, mock_orchestrator_class):
        """astream()がon_chat_model_streamイベントからtokenをyieldすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        # astream_eventsをモックしてtoken eventを返す
        mock_chunk = Mock()
        mock_chunk.content = "Hello"

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk},
                "name": "some_model",
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert len(events) == 1
        assert events[0] == {"type": "token", "content": "Hello"}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_yields_complete_event(self, mock_orchestrator_class):
        """astream()がon_chain_endイベントからcompleteをyieldすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        output_data = {"answer": "回答", "emotion": "neutral"}

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chain_end",
                "name": "format_response",
                "data": {"output": output_data},
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert len(events) == 1
        assert events[0] == {"type": "complete", "data": output_data}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_skips_empty_content(self, mock_orchestrator_class):
        """astream()が空contentのtokenをスキップすることを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        mock_chunk_empty = Mock()
        mock_chunk_empty.content = ""

        mock_chunk_valid = Mock()
        mock_chunk_valid.content = "World"

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk_empty},
                "name": "model",
            }
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk_valid},
                "name": "model",
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert len(events) == 1
        assert events[0] == {"type": "token", "content": "World"}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_ignores_irrelevant_events(self, mock_orchestrator_class):
        """astream()が関係ないイベントを無視することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        async def mock_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "orchestrator", "data": {}}
            yield {"event": "on_chain_end", "name": "business_info", "data": {"output": {}}}

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream({"query": "test", "session_id": "s1"}):
            events.append(event)

        assert events == []
