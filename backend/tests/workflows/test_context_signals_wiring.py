"""Tests for context_signals wiring through workflow nodes."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.utils.context_priority import ContextSignals
from backend.workflows.main_workflow import MainWorkflow


def _make_workflow():
    """Create a MainWorkflow instance with all agents mocked out."""
    wf = MainWorkflow.__new__(MainWorkflow)

    wf._business_info_agent = MagicMock()
    wf._business_info_agent.answer_business_query = AsyncMock(
        return_value={"answer": "test", "emotion": "neutral", "metadata": {}}
    )

    wf._facility_agent = MagicMock()
    wf._facility_agent.answer_facility_query = AsyncMock(
        return_value={"answer": "test", "emotion": "neutral", "metadata": {}}
    )

    wf._general_knowledge_agent = MagicMock()
    wf._general_knowledge_agent.answer_query = AsyncMock(
        return_value={"answer": "test", "emotion": "neutral", "metadata": {}}
    )

    return wf


def _make_state(priority_signals=None):
    """Create a minimal workflow state dict."""
    ctx = {
        "knowledge_results": {
            "success": True,
            "results": [],
            "context_string": "",
            "category": "general",
            "query": "test",
        }
    }
    if priority_signals is not None:
        ctx["priority_signals"] = priority_signals
    return {
        "query": "test query",
        "language": "ja",
        "session_id": "sess-1",
        "routing": {"request_type": "general"},
        "metadata": {},
        "context": ctx,
    }


SAMPLE_SIGNALS = ContextSignals(
    memory_topics=("tech",),
    rag_cache_top_score=0.85,
    request_specificity=0.7,
    conversation_depth=2,
    previous_categories=("general",),
)


@pytest.mark.asyncio
async def test_business_info_node_passes_signals():
    wf = _make_workflow()
    state = _make_state(priority_signals=SAMPLE_SIGNALS)

    await wf._business_info_node(state)

    wf._business_info_agent.answer_business_query.assert_awaited_once()
    call_kwargs = wf._business_info_agent.answer_business_query.call_args
    assert call_kwargs.kwargs.get("context_signals") is SAMPLE_SIGNALS


@pytest.mark.asyncio
async def test_facility_node_passes_signals():
    wf = _make_workflow()
    state = _make_state(priority_signals=SAMPLE_SIGNALS)

    await wf._facility_node(state)

    wf._facility_agent.answer_facility_query.assert_awaited_once()
    call_kwargs = wf._facility_agent.answer_facility_query.call_args
    assert call_kwargs.kwargs.get("context_signals") is SAMPLE_SIGNALS


@pytest.mark.asyncio
async def test_general_knowledge_node_passes_signals():
    wf = _make_workflow()
    state = _make_state(priority_signals=SAMPLE_SIGNALS)

    await wf._general_knowledge_node(state)

    wf._general_knowledge_agent.answer_query.assert_awaited_once()
    call_kwargs = wf._general_knowledge_agent.answer_query.call_args
    assert call_kwargs.kwargs.get("context_signals") is SAMPLE_SIGNALS


@pytest.mark.asyncio
async def test_nodes_work_without_signals():
    """priority_signals が state に存在しない場合でも context_signals=None で正常動作"""
    wf = _make_workflow()
    state = _make_state(priority_signals=None)
    # Remove priority_signals key entirely
    state["context"].pop("priority_signals", None)

    await wf._business_info_node(state)
    await wf._facility_node(state)
    await wf._general_knowledge_node(state)

    biz_kwargs = wf._business_info_agent.answer_business_query.call_args
    assert biz_kwargs.kwargs.get("context_signals") is None

    fac_kwargs = wf._facility_agent.answer_facility_query.call_args
    assert fac_kwargs.kwargs.get("context_signals") is None

    gka_kwargs = wf._general_knowledge_agent.answer_query.call_args
    assert gka_kwargs.kwargs.get("context_signals") is None
