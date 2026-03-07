"""Tests for MainWorkflow.ainvoke_from_reception (orchestrator bypass)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.purpose_flow_service import PurposeFlowResult
from backend.services.reception_handoff_service import HandoffResult


def _make_handoff_result(
    *,
    target_agent: str = "facility",
    action_type: str = "guide",
    requires_staff: bool = False,
) -> HandoffResult:
    return HandoffResult(
        workflow_state={
            "messages": [],
            "query": "I want to use the coworking space",
            "session_id": "session-test",
            "language": "en",
            "routing": {
                "agent": target_agent,
                "category": "facility_use",
                "request_type": action_type,
                "confidence": 1.0,
                "reasoning": "Routed from autonomous reception flow",
                "debug_info": {},
            },
            "answer": None,
            "emotion": None,
            "metadata": {
                "reception_session_id": "reception-123",
                "reception_handoff": True,
            },
            "context": {"reception_context": {"visitor_name": "Taro"}},
            "image_data": None,
            "ocr_result": None,
        },
        target_agent=target_agent,
        purpose_flow=PurposeFlowResult(
            response_text="Guide text",
            target_agent=target_agent,
            action_type=action_type,
            action_data={"purpose_category": "facility_use"},
            requires_staff=requires_staff,
        ),
        requires_staff=requires_staff,
    )


@pytest.mark.asyncio
async def test_ainvoke_from_reception_calls_target_agent_node() -> None:
    """Orchestrator should be bypassed; target agent node called directly."""
    from backend.workflows.main_workflow import MainWorkflow

    with patch.object(MainWorkflow, "__init__", lambda self, **kw: None):
        wf = MainWorkflow()
        wf.checkpointer = None
        wf.store = None
        wf._current_visitor_id = "test"

        mock_result = {
            "answer": "Welcome to the facility!",
            "emotion": "friendly",
            "metadata": {"reception_handoff": True},
        }
        wf._facility_node = AsyncMock(return_value=mock_result)
        wf._format_response_node = AsyncMock(
            return_value={
                "answer": "Welcome to the facility!",
                "emotion": "friendly",
                "metadata": {"reception_handoff": True},
                "messages": [],
            }
        )

        handoff = _make_handoff_result(target_agent="facility")
        result = await wf.ainvoke_from_reception(handoff)

        assert result["answer"] == "Welcome to the facility!"
        wf._facility_node.assert_awaited_once()


@pytest.mark.asyncio
async def test_ainvoke_from_reception_routes_to_event_agent() -> None:
    from backend.workflows.main_workflow import MainWorkflow

    with patch.object(MainWorkflow, "__init__", lambda self, **kw: None):
        wf = MainWorkflow()
        wf.checkpointer = None
        wf.store = None
        wf._current_visitor_id = "test"

        wf._event_node = AsyncMock(
            return_value={
                "answer": "Today's events: Meetup at 14:00",
                "emotion": "neutral",
                "metadata": {},
            }
        )
        wf._format_response_node = AsyncMock(
            return_value={
                "answer": "Today's events: Meetup at 14:00",
                "emotion": "neutral",
                "metadata": {},
                "messages": [],
            }
        )

        handoff = _make_handoff_result(target_agent="event", action_type="lookup")
        result = await wf.ainvoke_from_reception(handoff)

        assert "Meetup" in result["answer"]
        wf._event_node.assert_awaited_once()


@pytest.mark.asyncio
async def test_ainvoke_from_reception_routes_to_general_knowledge() -> None:
    from backend.workflows.main_workflow import MainWorkflow

    with patch.object(MainWorkflow, "__init__", lambda self, **kw: None):
        wf = MainWorkflow()
        wf.checkpointer = None
        wf.store = None
        wf._current_visitor_id = "test"

        wf._general_knowledge_node = AsyncMock(
            return_value={
                "answer": "Staff notified",
                "emotion": "neutral",
                "metadata": {},
            }
        )
        wf._format_response_node = AsyncMock(
            return_value={
                "answer": "Staff notified",
                "emotion": "neutral",
                "metadata": {},
                "messages": [],
            }
        )

        handoff = _make_handoff_result(
            target_agent="general_knowledge",
            action_type="escalate",
            requires_staff=True,
        )
        result = await wf.ainvoke_from_reception(handoff)

        assert result["answer"] == "Staff notified"
        wf._general_knowledge_node.assert_awaited_once()


@pytest.mark.asyncio
async def test_ainvoke_from_reception_raises_for_unknown_agent() -> None:
    from backend.workflows.main_workflow import MainWorkflow

    with patch.object(MainWorkflow, "__init__", lambda self, **kw: None):
        wf = MainWorkflow()
        wf.checkpointer = None
        wf.store = None
        wf._current_visitor_id = "test"

        handoff = _make_handoff_result(target_agent="nonexistent_agent")

        with pytest.raises(ValueError, match="Unknown target agent"):
            await wf.ainvoke_from_reception(handoff)


@pytest.mark.asyncio
async def test_ainvoke_from_reception_preserves_metadata() -> None:
    from backend.workflows.main_workflow import MainWorkflow

    with patch.object(MainWorkflow, "__init__", lambda self, **kw: None):
        wf = MainWorkflow()
        wf.checkpointer = None
        wf.store = None
        wf._current_visitor_id = "test"

        wf._facility_node = AsyncMock(
            return_value={
                "answer": "Facility info",
                "emotion": "neutral",
                "metadata": {"reception_handoff": True, "extra": "data"},
            }
        )
        wf._format_response_node = AsyncMock(
            return_value={
                "answer": "Facility info",
                "emotion": "neutral",
                "metadata": {"reception_handoff": True, "extra": "data"},
                "messages": [],
            }
        )

        handoff = _make_handoff_result(target_agent="facility")
        result = await wf.ainvoke_from_reception(handoff)

        assert result["metadata"]["reception_handoff"] is True


@pytest.mark.asyncio
async def test_ainvoke_from_reception_returns_purpose_flow_response() -> None:
    """When requires_staff is True, the purpose_flow response_text
    should be included in the result."""
    from backend.workflows.main_workflow import MainWorkflow

    with patch.object(MainWorkflow, "__init__", lambda self, **kw: None):
        wf = MainWorkflow()
        wf.checkpointer = None
        wf.store = None
        wf._current_visitor_id = "test"

        wf._general_knowledge_node = AsyncMock(
            return_value={
                "answer": "Connecting to staff...",
                "emotion": "neutral",
                "metadata": {},
            }
        )
        wf._format_response_node = AsyncMock(
            return_value={
                "answer": "Connecting to staff...",
                "emotion": "neutral",
                "metadata": {},
                "messages": [],
            }
        )

        handoff = _make_handoff_result(
            target_agent="general_knowledge",
            action_type="escalate",
            requires_staff=True,
        )
        result = await wf.ainvoke_from_reception(handoff)

        assert result["purpose_flow_response"] == "Guide text"
        assert result["requires_staff"] is True
