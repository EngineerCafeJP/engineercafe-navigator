"""
Error Propagation and RetryPolicy Tests for MainWorkflow

Tests cover:
1. RetryPolicy configuration validation
2. Error propagation through format_response
3. Orchestrator failure handling
4. Vision node failure handling
5. Memory loader failure handling (graceful degradation)
6. Error message security (no internal detail leakage)
"""

import re
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from langgraph.types import RetryPolicy


def _mock_runtime():
    """テスト用モック Runtime を生成"""
    rt = MagicMock()
    rt.context = MagicMock()
    rt.context.user_id = "anonymous"
    rt.store = None
    return rt


# ---------------------------------------------------------------------------
# Helper: create a MainWorkflow with all external deps mocked out
# ---------------------------------------------------------------------------


def _create_workflow():
    """Create a MainWorkflow instance with OrchestratorAgent mocked."""
    from backend.workflows.main_workflow import MainWorkflow

    with patch("backend.workflows.main_workflow.OrchestratorAgent") as mock_orch:
        mock_orch.return_value = AsyncMock()
        workflow = MainWorkflow()
    return workflow


# ===========================================================================
# 1. RetryPolicy Configuration Tests
# ===========================================================================


class TestRetryPolicyConfiguration:
    """RetryPolicy values and node assignment verification."""

    def test_retry_policy_is_langgraph_type(self):
        """LLM_RETRY_POLICY is a LangGraph RetryPolicy instance."""
        from backend.workflows.main_workflow import MainWorkflow

        assert isinstance(MainWorkflow.LLM_RETRY_POLICY, RetryPolicy)

    def test_retry_policy_max_attempts(self):
        """max_attempts is set to 3."""
        from backend.workflows.main_workflow import MainWorkflow

        assert MainWorkflow.LLM_RETRY_POLICY.max_attempts == 3

    def test_retry_policy_backoff_factor(self):
        """backoff_factor is set to 2.0."""
        from backend.workflows.main_workflow import MainWorkflow

        assert MainWorkflow.LLM_RETRY_POLICY.backoff_factor == 2.0

    def test_retry_policy_initial_interval(self):
        """initial_interval is set to 1.0 seconds."""
        from backend.workflows.main_workflow import MainWorkflow

        assert MainWorkflow.LLM_RETRY_POLICY.initial_interval == 1.0

    def test_retry_policy_max_interval(self):
        """max_interval is set to 10.0 seconds."""
        from backend.workflows.main_workflow import MainWorkflow

        assert MainWorkflow.LLM_RETRY_POLICY.max_interval == 10.0

    def test_retry_policy_retry_on_is_callable(self):
        """retry_on is a callable (default_retry_on function)."""
        from backend.workflows.main_workflow import MainWorkflow

        assert callable(MainWorkflow.LLM_RETRY_POLICY.retry_on)

    def test_retry_policy_retry_on_accepts_exception(self):
        """retry_on returns True for generic Exception."""
        from backend.workflows.main_workflow import MainWorkflow

        retry_fn = MainWorkflow.LLM_RETRY_POLICY.retry_on
        assert retry_fn(Exception("transient error")) is True

    def test_retry_policy_retry_on_rejects_runtime_error(self):
        """default_retry_on returns False for RuntimeError (non-retryable)."""
        from backend.workflows.main_workflow import MainWorkflow

        retry_fn = MainWorkflow.LLM_RETRY_POLICY.retry_on
        # LangGraph's default_retry_on only retries on specific transient
        # errors, not RuntimeError which is considered non-retryable
        assert retry_fn(RuntimeError("runtime failure")) is False

    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    def test_retry_policy_applied_to_llm_nodes(self, mock_orchestrator_class):
        """Verify retry policy is applied to LLM-dependent nodes during build."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = Mock()

        # Patch StateGraph.add_node to capture retry_policy assignments
        node_retry_map = {}

        with patch("backend.workflows.main_workflow.StateGraph") as mock_sg_class:
            mock_graph = Mock()
            mock_sg_class.return_value = mock_graph

            def capture_add_node(name, func, **kwargs):
                node_retry_map[name] = kwargs.get("retry_policy")

            mock_graph.add_node = capture_add_node
            mock_graph.add_edge = Mock()
            mock_graph.add_conditional_edges = Mock()
            mock_graph.compile = Mock(return_value=Mock())

            MainWorkflow()

        # LLM-dependent nodes MUST have retry_policy
        llm_nodes = [
            "vision",
            "orchestrator",
            "business_info",
            "facility",
            "event",
            "slide",
            "general_knowledge",
        ]
        for node_name in llm_nodes:
            assert node_name in node_retry_map, f"Node '{node_name}' was not added to the graph"
            assert (
                node_retry_map[node_name] is not None
            ), f"Node '{node_name}' should have a retry_policy but got None"

    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    def test_non_llm_nodes_have_no_retry_policy(self, mock_orchestrator_class):
        """memory_loader and format_response do not need retry policy."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = Mock()

        node_retry_map = {}

        with patch("backend.workflows.main_workflow.StateGraph") as mock_sg_class:
            mock_graph = Mock()
            mock_sg_class.return_value = mock_graph

            def capture_add_node(name, func, **kwargs):
                node_retry_map[name] = kwargs.get("retry_policy")

            mock_graph.add_node = capture_add_node
            mock_graph.add_edge = Mock()
            mock_graph.add_conditional_edges = Mock()
            mock_graph.compile = Mock(return_value=Mock())

            MainWorkflow()

        # Non-LLM nodes should NOT have retry_policy
        non_llm_nodes = ["memory_loader", "format_response"]
        for node_name in non_llm_nodes:
            assert node_name in node_retry_map, f"Node '{node_name}' was not added to the graph"
            assert (
                node_retry_map[node_name] is None
            ), f"Node '{node_name}' should NOT have a retry_policy"


# ===========================================================================
# 2. Error Propagation in format_response
# ===========================================================================


class TestFormatResponseErrorPropagation:
    """Verify format_response handles errors gracefully and securely."""

    @pytest.mark.asyncio
    async def test_format_response_with_no_answer(self):
        """When answer is missing, a default fallback message is used."""
        workflow = _create_workflow()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            state = {
                "query": "test query",
                "session_id": "test-session",
                # "answer" is intentionally omitted
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            assert "messages" in result
            assert len(result["messages"]) == 2
            # The fallback default from the code
            assert result["messages"][1].content == "回答を生成できませんでした。"

    @pytest.mark.asyncio
    async def test_format_response_with_none_answer(self):
        """When answer is explicitly None, strip_emotion_tags returns empty.

        Note: state.get("answer", default) returns None when the key exists
        with value None, so strip_emotion_tags(None) produces "".
        """
        workflow = _create_workflow()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            state = {
                "query": "test query",
                "answer": None,
                "session_id": "test-session",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            # None answer goes through strip_emotion_tags(None) -> ""
            assert result["messages"][1].content == ""

    @pytest.mark.asyncio
    async def test_format_response_memory_store_failure_does_not_crash(self):
        """format_response continues even when store_message raises."""
        workflow = _create_workflow()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock(side_effect=Exception("Database write failed"))
            mock_get_helper.return_value = mock_helper

            state = {
                "query": "test",
                "answer": "some answer",
                "session_id": "test-session",
            }

            # Should NOT raise despite store_message failure
            result = await workflow._format_response_node(state, _mock_runtime())

            assert "messages" in result
            assert result["messages"][1].content == "some answer"

    @pytest.mark.asyncio
    async def test_format_response_strips_emotion_tags(self):
        """format_response strips emotion tags before formatting."""
        workflow = _create_workflow()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            state = {
                "query": "How are you?",
                "answer": "[happy:0.9]I am great![/happy]",
                "session_id": "test-session",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            # Emotion tags should be stripped
            assert "[happy" not in result["messages"][1].content
            assert "I am great!" in result["messages"][1].content


# ===========================================================================
# 3. Orchestrator Failure Handling
# ===========================================================================


class TestOrchestratorFailure:
    """Verify behavior when the orchestrator LLM raises an exception."""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_raises_propagates(self, mock_orchestrator_class):
        """When orchestrator.decide_next_agent raises, the exception propagates.

        LangGraph's retry policy will catch and retry, but the node itself
        does not swallow exceptions -- it lets them propagate for the
        retry mechanism to handle.
        """
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=Exception("LLM API timeout"))
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        state = {
            "query": "test query",
            "session_id": "test-session",
            "language": "ja",
            "context": {"memory": {}},
        }

        with pytest.raises(Exception, match="LLM API timeout"):
            await workflow._orchestrator_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_runtime_error(self, mock_orchestrator_class):
        """RuntimeError from orchestrator propagates for retry."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=RuntimeError("Model not found"))
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        state = {
            "query": "test query",
            "session_id": "test-session",
            "language": "ja",
            "context": {"memory": {}},
        }

        with pytest.raises(RuntimeError, match="Model not found"):
            await workflow._orchestrator_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_node_connection_error(self, mock_orchestrator_class):
        """ConnectionError from orchestrator propagates for retry."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(
            side_effect=ConnectionError("Failed to connect to LLM endpoint")
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        workflow = MainWorkflow()

        state = {
            "query": "test query",
            "session_id": "test-session",
            "language": "ja",
            "context": {"memory": {}},
        }

        with pytest.raises(ConnectionError, match="Failed to connect to LLM endpoint"):
            await workflow._orchestrator_node(state)


# ===========================================================================
# 4. Vision Node Failure Handling
# ===========================================================================


class TestVisionNodeFailure:
    """Verify behavior when VisionAgent is unavailable or raises errors."""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_vision_node_raises_when_agent_unavailable(self, mock_orchestrator_class):
        """When VisionAgent is None, _vision_node raises RuntimeError."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()
        workflow._vision_agent = None  # Simulate unavailable VisionAgent

        state = {
            "image_data": b"fake_image_data",
            "query": "",
            "session_id": "test-session",
            "language": "ja",
            "metadata": {},
        }

        with pytest.raises(RuntimeError, match="VisionAgent is not available"):
            await workflow._vision_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_vision_node_run_raises_propagates(self, mock_orchestrator_class):
        """When VisionAgent.run() raises, the error propagates for retry."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()

        mock_vision = AsyncMock()
        mock_vision.run = AsyncMock(side_effect=RuntimeError("OCR processing failed"))
        workflow._vision_agent = mock_vision

        state = {
            "image_data": b"fake_image_data",
            "query": "",
            "session_id": "test-session",
            "language": "ja",
            "metadata": {},
        }

        with pytest.raises(RuntimeError, match="OCR processing failed"):
            await workflow._vision_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_vision_node_error_message_no_internal_details(self, mock_orchestrator_class):
        """Vision node error message does not leak API keys or paths."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        workflow = MainWorkflow()
        workflow._vision_agent = None

        state = {
            "image_data": b"data",
            "query": "",
            "session_id": "test",
            "language": "ja",
            "metadata": {},
        }

        with pytest.raises(RuntimeError) as exc_info:
            await workflow._vision_node(state)

        error_msg = str(exc_info.value)
        # Should not contain sensitive info
        assert "api_key" not in error_msg.lower()
        assert "sk-" not in error_msg
        assert "/Users/" not in error_msg
        assert "openai" not in error_msg.lower()


# ===========================================================================
# 5. Memory Loader Failure (Graceful Degradation)
# ===========================================================================


class TestMemoryLoaderFailure:
    """Verify memory_loader degrades gracefully when dependencies fail."""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_db_error_returns_empty_memory(self, mock_orchestrator_class):
        """DB error in get_context results in empty memory, not crash."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                side_effect=Exception("PostgreSQL connection refused")
            )
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "test",
                "session_id": "test-session",
                "language": "ja",
                "context": {},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            assert "context" in result
            assert result["context"]["memory"] == {}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_preserves_existing_context(self, mock_orchestrator_class):
        """Existing context data is preserved when memory loading fails."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(side_effect=Exception("Timeout"))
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "test",
                "session_id": "test-session",
                "language": "ja",
                "context": {"existing_key": "existing_value"},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            assert result["context"]["existing_key"] == "existing_value"
            assert result["context"]["memory"] == {}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_connection_error_graceful(self, mock_orchestrator_class):
        """ConnectionError in memory loading is handled gracefully."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(side_effect=ConnectionError("Redis down"))
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "test",
                "session_id": "test-session",
                "language": "ja",
                "context": {},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            assert result["context"]["memory"] == {}

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_store_message_failure_continues(self, mock_orchestrator_class):
        """store_message failure does not prevent context return."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={
                    "recent_messages": [],
                    "context_string": "",
                }
            )
            mock_helper.store_message = AsyncMock(side_effect=Exception("Write failed"))
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            state = {
                "query": "test query",
                "session_id": "test-session",
                "language": "ja",
                "context": {},
            }

            result = await workflow._memory_loader_node(state, _mock_runtime())

            # Memory context should still be loaded despite store failure
            assert "context" in result
            assert "memory" in result["context"]

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_empty_query_skips_store(self, mock_orchestrator_class):
        """Empty query skips store_message call."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

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
                "query": "",  # Empty query
                "session_id": "test-session",
                "language": "ja",
                "context": {},
            }

            await workflow._memory_loader_node(state, _mock_runtime())

            # store_message should NOT be called for empty query
            mock_helper.store_message.assert_not_called()


# ===========================================================================
# 6. Error Message Security
# ===========================================================================


class TestErrorMessageSecurity:
    """Verify error responses do not leak internal implementation details."""

    # Patterns that must NEVER appear in user-facing error messages
    _SENSITIVE_PATTERNS = [
        r"sk-[a-zA-Z0-9]{20,}",  # OpenAI API keys
        r"api[_-]?key",  # Generic API key references
        r"/Users/\w+",  # Local filesystem paths (macOS)
        r"/home/\w+",  # Local filesystem paths (Linux)
        r"/app/backend/",  # Container paths
        r"Traceback \(most recent call",  # Python stack traces
        r"File \".*\.py\", line \d+",  # Python file references
        r"openai\.api_key",  # OpenAI config references
        r"SUPABASE_KEY",  # Supabase credentials
        r"password=",  # Password parameters
        r"token=",  # Token parameters
    ]

    def _assert_no_sensitive_data(self, text: str):
        """Assert that text does not contain sensitive patterns."""
        for pattern in self._SENSITIVE_PATTERNS:
            assert not re.search(
                pattern, text, re.IGNORECASE
            ), f"Sensitive data leaked: pattern '{pattern}' found in: {text}"

    @pytest.mark.asyncio
    async def test_format_response_fallback_is_safe(self):
        """Default fallback message contains no internal details."""
        workflow = _create_workflow()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            state = {
                "query": "test",
                "session_id": "test-session",
            }

            result = await workflow._format_response_node(state, _mock_runtime())

            answer = result["messages"][1].content
            self._assert_no_sensitive_data(answer)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_vision_unavailable_error_is_safe(self, mock_orchestrator_class):
        """VisionAgent unavailable error does not leak sensitive info."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()
        workflow._vision_agent = None

        state = {
            "image_data": b"data",
            "query": "",
            "session_id": "test",
            "language": "ja",
            "metadata": {},
        }

        with pytest.raises(RuntimeError) as exc_info:
            await workflow._vision_node(state)

        self._assert_no_sensitive_data(str(exc_info.value))

    @pytest.mark.asyncio
    async def test_format_response_with_emotion_tags_no_leakage(self):
        """Answer with emotion tags is cleaned; no raw tags in output."""
        workflow = _create_workflow()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            state = {
                "query": "test",
                "answer": "[angry:0.5]Something went wrong internally[/angry]",
                "session_id": "test-session",
            }

            result = await workflow._format_response_node(state, _mock_runtime())
            answer = result["messages"][1].content

            # No raw emotion tags should remain
            assert "[angry" not in answer
            assert "[/angry]" not in answer
            self._assert_no_sensitive_data(answer)


# ===========================================================================
# 7. Specialist Agent Error Propagation
# ===========================================================================


class TestSpecialistAgentErrors:
    """Verify specialist agents propagate errors for retry handling."""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_business_info_node_raises_propagates(self, mock_orchestrator_class):
        """BusinessInfoAgent exception propagates (for retry policy)."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()

        workflow._business_info_agent.answer_business_query = AsyncMock(
            side_effect=Exception("Supabase query failed")
        )

        state = {
            "query": "What are the hours?",
            "language": "en",
            "session_id": "test-session",
            "routing": {"request_type": "hours"},
            "metadata": {},
            "context": {},
        }

        with pytest.raises(Exception, match="Supabase query failed"):
            await workflow._business_info_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_facility_node_raises_propagates(self, mock_orchestrator_class):
        """FacilityAgent exception propagates (for retry policy)."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()

        workflow._facility_agent.answer_facility_query = AsyncMock(
            side_effect=RuntimeError("Search index unavailable")
        )

        state = {
            "query": "Where is the printer?",
            "language": "en",
            "session_id": "test-session",
            "routing": {"request_type": "location"},
            "metadata": {},
            "context": {},
        }

        with pytest.raises(RuntimeError, match="Search index unavailable"):
            await workflow._facility_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_event_node_raises_propagates(self, mock_orchestrator_class):
        """EventAgent exception propagates (for retry policy)."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()

        workflow._event_agent.answer_event_query = AsyncMock(
            side_effect=TimeoutError("Event API timed out")
        )

        state = {
            "query": "What events are today?",
            "language": "en",
            "session_id": "test-session",
            "routing": {},
            "metadata": {},
            "context": {},
        }

        with pytest.raises(TimeoutError, match="Event API timed out"):
            await workflow._event_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_slide_node_raises_propagates(self, mock_orchestrator_class):
        """SlideAgent exception propagates (for retry policy)."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()

        workflow._slide_agent.handle_slide_action = AsyncMock(
            side_effect=Exception("Slide data corrupted")
        )

        state = {
            "query": "next slide",
            "language": "ja",
            "session_id": "test-session",
            "routing": {"request_type": "next"},
            "metadata": {},
            "context": {},
        }

        with pytest.raises(Exception, match="Slide data corrupted"):
            await workflow._slide_node(state)

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_general_knowledge_node_raises_propagates(self, mock_orchestrator_class):
        """GeneralKnowledgeAgent exception propagates (for retry policy)."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()

        workflow._general_knowledge_agent.answer_query = AsyncMock(
            side_effect=ConnectionError("Embedding service unreachable")
        )

        state = {
            "query": "Tell me about Fukuoka",
            "language": "en",
            "session_id": "test-session",
            "routing": {"request_type": "general"},
            "metadata": {},
            "context": {},
        }

        with pytest.raises(ConnectionError, match="Embedding service unreachable"):
            await workflow._general_knowledge_node(state)


# ===========================================================================
# 8. Input Type Decision (Edge cases)
# ===========================================================================


class TestInputTypeDecision:
    """Verify _input_type_decision routes correctly."""

    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    def test_text_input_routes_to_text(self, mock_orchestrator_class):
        """No image_data routes to 'text'."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = Mock()
        workflow = MainWorkflow()

        state = {"image_data": None, "query": "hello"}
        assert workflow._input_type_decision(state) == "text"

    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    def test_image_input_routes_to_image(self, mock_orchestrator_class):
        """With image_data routes to 'image'."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = Mock()
        workflow = MainWorkflow()

        state = {"image_data": b"some_bytes", "query": ""}
        assert workflow._input_type_decision(state) == "image"

    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    def test_missing_image_data_routes_to_text(self, mock_orchestrator_class):
        """When image_data key is absent, routes to 'text'."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = Mock()
        workflow = MainWorkflow()

        state = {"query": "hello"}
        assert workflow._input_type_decision(state) == "text"


# ===========================================================================
# 9. Workflow-Level Error Containment (ainvoke)
# ===========================================================================


class TestWorkflowLevelErrors:
    """Verify ainvoke properly propagates graph execution errors."""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_ainvoke_propagates_graph_error(self, mock_orchestrator_class):
        """When graph.ainvoke raises, the error propagates to the caller."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()

        workflow.graph.ainvoke = AsyncMock(
            side_effect=RuntimeError("Graph execution failed after retries")
        )

        with pytest.raises(RuntimeError, match="Graph execution failed after retries"):
            await workflow.ainvoke({"query": "test", "session_id": "test-session"})

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_ainvoke_returns_defaults_on_empty_result(self, mock_orchestrator_class):
        """ainvoke returns sensible defaults when result keys are missing."""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()
        workflow = MainWorkflow()

        # Graph returns empty dict
        workflow.graph.ainvoke = AsyncMock(return_value={})

        result = await workflow.ainvoke({"query": "test", "session_id": "test-session"})

        assert result["answer"] == ""
        assert result["emotion"] == "neutral"
        assert result["metadata"] == {}
