from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.agents.orchestrator_agent import OrchestratorAgent


@pytest.mark.asyncio
async def test_decide_next_agent_logs_agent_routing_for_fast_path():
    orchestrator = OrchestratorAgent()

    with patch("backend.agents.orchestrator_agent.log_agent_routing") as log_agent_routing:
        decision = await orchestrator.decide_next_agent(
            "営業時間を教えてください",
            session_id="session-routing-1",
        )

    assert decision.next_agent == "business_info"
    log_agent_routing.assert_called_once()
    fields = log_agent_routing.call_args.kwargs
    assert fields["routed_to"] == "business_info"
    assert fields["intent"] == "hours"
    assert fields["confidence"] == 0.9
    assert fields["fallback_used"] is False
    assert fields["session_id"] == "session-routing-1"
    assert fields["fast_path"] is True
    assert fields["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_decide_next_agent_logs_agent_routing_for_llm_fallback():
    orchestrator = OrchestratorAgent()

    class Classification:
        category = "facility-info"
        confidence = 0.42

    async def fail_generate(*args, **kwargs):
        raise RuntimeError("router unavailable")

    async def classify_with_details(query: str):
        assert query == "分類が必要な内容"
        return Classification()

    orchestrator.provider.generate = fail_generate  # type: ignore[method-assign]
    orchestrator.query_classifier.classify_with_details = classify_with_details  # type: ignore[method-assign]

    with patch("backend.agents.orchestrator_agent.log_agent_routing") as log_agent_routing:
        decision = await orchestrator.decide_next_agent(
            "分類が必要な内容",
            session_id="session-routing-2",
        )

    assert decision.next_agent == "facility"
    log_agent_routing.assert_called_once()
    fields = log_agent_routing.call_args.kwargs
    assert fields["routed_to"] == "facility"
    assert fields["intent"] == "facility-info"
    assert fields["confidence"] == 0.42
    assert fields["fallback_used"] is True
    assert fields["session_id"] == "session-routing-2"
