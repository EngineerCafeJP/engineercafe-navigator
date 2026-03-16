"""
MainWorkflow のストリーミング実行とメモリ統合テスト

astream() によるストリーミングイベント発行、メモリヘルパーとの統合、
並行実行の安全性、get_workflow() シングルトンの動作を検証する。
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from backend.agents.orchestrator_agent import OrchestratorDecision
from backend.workflows.main_workflow import MainWorkflow, get_workflow, reset_workflow


def _mock_runtime():
    """テスト用モック Runtime を生成"""
    rt = MagicMock()
    rt.context = MagicMock()
    rt.context.user_id = "anonymous"
    rt.store = None
    return rt


# ---------------------------------------------------------------------------
# Helper: 全外部依存をまとめてモックするコンテキストマネージャ
# ---------------------------------------------------------------------------


def _build_patches():
    """全外部依存のパッチ辞書を返す。

    Returns:
        dict[str, patch]: パッチ名 -> patch オブジェクト
    """
    targets = {
        "orchestrator": "backend.workflows.main_workflow.OrchestratorAgent",
        "business_info": "backend.agents.business_info_agent.BusinessInfoAgent",
        "event_agent": "backend.agents.event_agent.EventAgent",
        "facility_agent": "backend.agents.facility_agent.FacilityAgent",
        "gka": "backend.agents.general_knowledge_agent.GeneralKnowledgeAgent",
        "slide_agent": "backend.agents.slide_agent.SlideAgent",
        "memory_helper": "backend.utils.memory_helper.get_memory_helper",
        "vision_agent": "backend.agents.ocr_agent.VisionAgent",
        "rag": "backend.tools.enhanced_rag.EnhancedRAGSearch",
        "classifier": "backend.utils.query_classifier.QueryClassifier",
        "checkpointer": "backend.utils.checkpointer.get_checkpointer",
        "clarification": "backend.utils.clarification_templates.get_clarification_response",
        "priority_engine": "backend.utils.context_priority.ContextPriorityEngine",
    }
    return {name: patch(target) for name, target in targets.items()}


def _make_orchestrator_decision(
    next_agent="general_knowledge",
    category="general",
    language="ja",
    request_type="general",
    confidence=0.9,
    reasoning="test routing",
):
    """テスト用 OrchestratorDecision を生成する。"""
    return OrchestratorDecision(
        next_agent=next_agent,
        language=language,
        category=category,
        request_type=request_type,
        confidence=confidence,
        reasoning=reasoning,
        debug_info={},
    )


def _make_mock_memory_helper(
    context_return=None,
    store_side_effect=None,
):
    """テスト用 mock memory_helper を生成する。

    Args:
        context_return: get_context の戻り値。None の場合はデフォルト値を使用。
        store_side_effect: store_message の side_effect。None なら正常動作。

    Returns:
        AsyncMock: memory_helper のモック
    """
    helper = AsyncMock()
    helper.get_context = AsyncMock(
        return_value=context_return
        or {
            "recent_messages": [],
            "knowledge_results": [],
            "context_string": "",
            "inherited_request_type": None,
        }
    )
    if store_side_effect:
        helper.store_message = AsyncMock(side_effect=store_side_effect)
    else:
        helper.store_message = AsyncMock()
    return helper


def _default_input(query="Hello", session_id="test-session", language="ja"):
    """テスト用入力データを生成する。"""
    return {
        "query": query,
        "session_id": session_id,
        "language": language,
    }


# ===========================================================================
# TestStreamingExecution
# ===========================================================================


class TestStreamingExecution:
    """astream() によるストリーミング実行のテスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_yields_events(self, mock_orch_cls):
        """astream() がトークンまたは完了イベントを少なくとも 1 つ yield する"""
        mock_orch_cls.return_value = AsyncMock()
        workflow = MainWorkflow()

        mock_chunk = Mock()
        mock_chunk.content = "streaming token"

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk},
                "name": "model",
            }
            yield {
                "event": "on_chain_end",
                "name": "format_response",
                "data": {"output": {"answer": "done"}},
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream(_default_input()):
            events.append(event)

        # token と complete の両方が含まれる
        event_types = {e["type"] for e in events}
        assert "token" in event_types or "complete" in event_types
        assert len(events) >= 1

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_completes_with_result(self, mock_orch_cls):
        """astream() が最終的に type=complete のイベントを yield する"""
        mock_orch_cls.return_value = AsyncMock()
        workflow = MainWorkflow()

        output_data = {"answer": "final answer", "emotion": "happy"}

        mock_chunk = Mock()
        mock_chunk.content = "partial"

        async def mock_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": mock_chunk},
                "name": "model",
            }
            yield {
                "event": "on_chain_end",
                "name": "format_response",
                "data": {"output": output_data},
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream(_default_input()):
            events.append(event)

        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["data"] == output_data

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_multiple_tokens_then_complete(self, mock_orch_cls):
        """astream() が複数トークンの後に complete を yield する"""
        mock_orch_cls.return_value = AsyncMock()
        workflow = MainWorkflow()

        chunks = []
        for text in ["Hello", " ", "World"]:
            c = Mock()
            c.content = text
            chunks.append(c)

        async def mock_events(*args, **kwargs):
            for chunk in chunks:
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": chunk},
                    "name": "model",
                }
            yield {
                "event": "on_chain_end",
                "name": "format_response",
                "data": {"output": {"answer": "Hello World"}},
            }

        workflow.graph.astream_events = mock_events

        events = []
        async for event in workflow.astream(_default_input()):
            events.append(event)

        token_events = [e for e in events if e["type"] == "token"]
        # " " (space) is truthy, so all 3 tokens should appear
        assert len(token_events) == 3
        assert token_events[0]["content"] == "Hello"
        assert token_events[1]["content"] == " "
        assert token_events[2]["content"] == "World"

        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_astream_uses_checkpointer_config(self, mock_orch_cls):
        """checkpointer 設定時に astream が config を渡すことを確認"""
        from langgraph.checkpoint.memory import MemorySaver

        mock_orch_cls.return_value = AsyncMock()
        checkpointer = MemorySaver()
        workflow = MainWorkflow(checkpointer=checkpointer)

        captured_kwargs = {}

        async def mock_events(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return
            yield  # noqa: F841 - make async generator

        workflow.graph.astream_events = mock_events

        async for _ in workflow.astream(_default_input(session_id="cfg-test")):
            pass

        assert captured_kwargs.get("config") is not None
        assert captured_kwargs["config"]["configurable"]["thread_id"] == "cfg-test"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_ainvoke_retries_after_stale_checkpointer_probe(self, mock_orch_cls):
        """stale connection を検知したら pool refresh 後に ainvoke を続行する"""
        mock_orch_cls.return_value = AsyncMock()
        workflow = MainWorkflow()

        mock_checkpointer = AsyncMock()
        mock_checkpointer.aget_tuple = AsyncMock(
            side_effect=[RuntimeError("the connection is closed"), None]
        )
        mock_checkpointer.recreate = AsyncMock()
        workflow.checkpointer = mock_checkpointer

        workflow.graph = MagicMock()
        workflow.graph.ainvoke = AsyncMock(
            return_value={"answer": "recovered", "emotion": "neutral", "metadata": {}}
        )

        result = await workflow.ainvoke(_default_input(session_id="reconnect-session"))

        assert result["answer"] == "recovered"
        assert mock_checkpointer.aget_tuple.await_count == 2
        mock_checkpointer.recreate.assert_awaited_once()
        workflow.graph.ainvoke.assert_awaited_once()


# ===========================================================================
# TestMemoryIntegration
# ===========================================================================


class TestMemoryIntegration:
    """メモリヘルパーとの統合テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_user_message_stored_in_memory_loader(self, mock_orch_cls):
        """_memory_loader_node が store_message(role='user') を呼ぶ"""
        mock_orch_cls.return_value = AsyncMock()

        mock_helper = _make_mock_memory_helper()

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            state = {
                "query": "WiFi password is what?",
                "session_id": "mem-test-1",
                "language": "en",
                "context": {},
            }

            await workflow._memory_loader_node(state, _mock_runtime())

            mock_helper.store_message.assert_called_once_with(
                session_id="mem-test-1",
                role="user",
                content="WiFi password is what?",
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_assistant_message_stored_in_format_response(self, mock_orch_cls):
        """_format_response_node が store_message(role='assistant') を呼ぶ"""
        mock_orch_cls.return_value = AsyncMock()

        mock_helper = _make_mock_memory_helper()

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            state = {
                "query": "What are the hours?",
                "answer": "We are open 9 AM to 10 PM.",
                "session_id": "mem-test-2",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            mock_helper.store_message.assert_called_once_with(
                session_id="mem-test-2",
                role="assistant",
                content="We are open 9 AM to 10 PM.",
            )
            # messages も正しく返る
            assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_context_loaded(self, mock_orch_cls):
        """_memory_loader_node が get_context の結果を state['context']['memory'] に格納する"""
        mock_orch_cls.return_value = AsyncMock()

        memory_context = {
            "recent_messages": [
                {"role": "user", "content": "previous question"},
                {"role": "assistant", "content": "previous answer"},
            ],
            "knowledge_results": [],
            "context_string": "User: previous question\nAssistant: previous answer",
            "inherited_request_type": "hours",
        }
        mock_helper = _make_mock_memory_helper(context_return=memory_context)

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            state = {
                "query": "And what about weekends?",
                "session_id": "mem-test-3",
                "language": "en",
                "context": {},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            assert "context" in result
            assert "memory" in result["context"]
            assert result["context"]["memory"] == memory_context

            mock_helper.get_context.assert_called_once_with(
                query="And what about weekends?",
                session_id="mem-test-3",
                options={
                    "include_knowledge_base": False,
                    "language": "en",
                    "inherit_context": True,
                },
            )

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_store_failure_does_not_break_workflow(self, mock_orch_cls):
        """store_message が例外を投げてもワークフローは正常に完了する"""
        mock_orch_cls.return_value = AsyncMock()

        mock_helper = _make_mock_memory_helper(
            store_side_effect=Exception("Supabase connection refused")
        )

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            # memory_loader_node: store_message 失敗してもコンテキストは返る
            state_loader = {
                "query": "test query",
                "session_id": "mem-test-4",
                "language": "ja",
                "context": {},
            }
            result_loader = await workflow._memory_loader_node(state_loader, _mock_runtime())

            assert "context" in result_loader
            assert "memory" in result_loader["context"]

            # format_response_node: store_message 失敗してもメッセージは返る
            state_format = {
                "query": "test query",
                "answer": "test answer",
                "session_id": "mem-test-4",
            }
            result_format = await workflow._format_response_node(state_format, _mock_runtime())

            assert "messages" in result_format
            assert len(result_format["messages"]) == 2
            assert result_format["messages"][1].content == "test answer"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_empty_query_skips_store(self, mock_orch_cls):
        """空のクエリの場合 store_message は呼ばれない"""
        mock_orch_cls.return_value = AsyncMock()

        mock_helper = _make_mock_memory_helper()

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            state = {
                "query": "",
                "session_id": "mem-test-5",
                "language": "ja",
                "context": {},
            }

            await workflow._memory_loader_node(state, _mock_runtime())

            # 空クエリなので store_message は呼ばれない
            mock_helper.store_message.assert_not_called()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_get_context_failure_returns_empty_memory(self, mock_orch_cls):
        """get_context が例外を投げた場合、memory は空の dict になる"""
        mock_orch_cls.return_value = AsyncMock()

        mock_helper = AsyncMock()
        mock_helper.get_context = AsyncMock(side_effect=Exception("Redis timeout"))

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            state = {
                "query": "test",
                "session_id": "mem-test-6",
                "language": "ja",
                "context": {"existing_key": "preserved"},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            assert result["context"]["memory"] == {}
            # 既存のコンテキストキーが保持される
            assert result["context"]["existing_key"] == "preserved"


# ===========================================================================
# TestConcurrentInvocations
# ===========================================================================


class TestConcurrentInvocations:
    """並行 ainvoke の安全性テスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_concurrent_ainvoke_different_sessions(self, mock_orch_cls):
        """異なる session_id での並行 ainvoke が互いに干渉しない"""
        mock_orch = AsyncMock()
        mock_orch.decide_next_agent = AsyncMock(return_value=_make_orchestrator_decision())
        mock_orch.close = AsyncMock()
        mock_orch_cls.return_value = mock_orch

        mock_helper = _make_mock_memory_helper()

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            # GKA の answer_query をモック
            workflow._general_knowledge_agent.answer_query = AsyncMock(
                side_effect=lambda query, **kwargs: {
                    "answer": f"Answer for: {query}",
                    "emotion": "neutral",
                    "metadata": {"session": kwargs.get("session_id", "")},
                }
            )

            tasks = [
                workflow.ainvoke(
                    _default_input(
                        query=f"Question {i}",
                        session_id=f"session-{i}",
                    )
                )
                for i in range(3)
            ]

            results = await asyncio.gather(*tasks)

            assert len(results) == 3
            for result in results:
                assert "answer" in result
                assert result["answer"] != ""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_concurrent_ainvoke_same_session(self, mock_orch_cls):
        """同じ session_id での並行 ainvoke が互いのデータを破壊しない"""
        mock_orch = AsyncMock()
        mock_orch.decide_next_agent = AsyncMock(return_value=_make_orchestrator_decision())
        mock_orch.close = AsyncMock()
        mock_orch_cls.return_value = mock_orch

        mock_helper = _make_mock_memory_helper()

        with patch(
            "backend.utils.memory_helper.get_memory_helper",
            return_value=mock_helper,
        ):
            workflow = MainWorkflow()

            call_count = 0

            async def mock_answer(query, **kwargs):
                nonlocal call_count
                call_count += 1
                # asyncio.sleep で並行性をシミュレート
                await asyncio.sleep(0.01)
                return {
                    "answer": f"Response to: {query}",
                    "emotion": "neutral",
                    "metadata": {},
                }

            workflow._general_knowledge_agent.answer_query = AsyncMock(side_effect=mock_answer)

            tasks = [
                workflow.ainvoke(
                    _default_input(
                        query=f"Query {i}",
                        session_id="shared-session",
                    )
                )
                for i in range(2)
            ]

            results = await asyncio.gather(*tasks)

            assert len(results) == 2
            for result in results:
                assert "answer" in result
                assert result["answer"].startswith("Response to:")

            # 両方の呼び出しが完了した
            assert call_count == 2


# ===========================================================================
# TestGetWorkflowSingleton
# ===========================================================================


class TestGetWorkflowSingleton:
    """get_workflow() シングルトンの動作テスト"""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        """各テストの前後でシングルトンをリセット"""
        reset_workflow()
        yield
        reset_workflow()

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    @patch("backend.utils.checkpointer.get_checkpointer", new_callable=AsyncMock)
    async def test_get_workflow_returns_same_instance(self, mock_get_cp, mock_orch_cls):
        """get_workflow() を 2 回呼ぶと同一インスタンスが返る"""
        mock_orch_cls.return_value = AsyncMock()
        mock_get_cp.side_effect = ValueError("No SUPABASE_DB_URI")

        wf1 = await get_workflow()
        wf2 = await get_workflow()

        assert wf1 is wf2

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    @patch("backend.utils.checkpointer.get_checkpointer", new_callable=AsyncMock)
    async def test_get_workflow_thread_safe(self, mock_get_cp, mock_orch_cls):
        """複数タスクから同時に get_workflow() を呼んでもシングルトンが保証される"""
        mock_orch_cls.return_value = AsyncMock()
        mock_get_cp.side_effect = ValueError("No SUPABASE_DB_URI")

        results = await asyncio.gather(*[get_workflow() for _ in range(5)])

        # 全て同一インスタンス
        first = results[0]
        for wf in results[1:]:
            assert wf is first

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    @patch("backend.utils.checkpointer.get_checkpointer", new_callable=AsyncMock)
    async def test_reset_workflow_clears_instance(self, mock_get_cp, mock_orch_cls):
        """reset_workflow() 後の get_workflow() は新しいインスタンスを返す"""
        mock_orch_cls.return_value = AsyncMock()
        mock_get_cp.side_effect = ValueError("No SUPABASE_DB_URI")

        wf1 = await get_workflow()
        reset_workflow()
        wf2 = await get_workflow()

        assert wf1 is not wf2

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    @patch("backend.utils.checkpointer.get_checkpointer", new_callable=AsyncMock)
    async def test_get_workflow_without_checkpointer(self, mock_get_cp, mock_orch_cls):
        """get_checkpointer が ValueError を投げても永続化なしで動作する"""
        mock_orch_cls.return_value = AsyncMock()
        mock_get_cp.side_effect = ValueError("SUPABASE_DB_URI environment variable is not set.")

        wf = await get_workflow()

        assert wf is not None
        assert isinstance(wf, MainWorkflow)
        assert wf.checkpointer is None

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    @patch("backend.utils.checkpointer.get_checkpointer", new_callable=AsyncMock)
    async def test_get_workflow_with_checkpointer_failure(self, mock_get_cp, mock_orch_cls):
        """get_checkpointer が一般例外を投げても永続化なしで動作する"""
        mock_orch_cls.return_value = AsyncMock()
        mock_get_cp.side_effect = ConnectionError("DB unreachable")

        wf = await get_workflow()

        assert wf is not None
        assert isinstance(wf, MainWorkflow)
        assert wf.checkpointer is None
