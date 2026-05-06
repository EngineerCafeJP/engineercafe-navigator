"""Tests for greeting fast-path integration with the reception gate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_state(query: str, *, session_id: str = "chat-session-123", language: str = "ja") -> dict:
    return {
        "messages": [],
        "query": query,
        "session_id": session_id,
        "language": language,
        "routing": {},
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": {},
        "image_data": None,
        "ocr_result": None,
    }


def _make_decision(
    *,
    category: str,
    next_agent: str,
    request_type: str,
    language: str = "ja",
) -> MagicMock:
    decision = MagicMock()
    decision.category = category
    decision.next_agent = next_agent
    decision.request_type = request_type
    decision.language = language
    decision.confidence = 0.95
    decision.reasoning = "test"
    decision.debug_info = {}
    return decision


@pytest.mark.asyncio
async def test_greeting_fast_path_drives_multi_turn_reception_flow() -> None:
    from backend.workflows.main_workflow import MainWorkflow

    persisted_sessions: dict[str, dict] = {}

    async def fake_store_session(_self, reception_session_id: str, data: dict) -> None:
        persisted_sessions[reception_session_id] = {
            "id": reception_session_id,
            "session_id": data.get("session_id"),
            "status": data.get("status", "active"),
            "stage": data.get("stage", "initiated"),
            "session_data": dict(data),
        }

    async def fake_check_reception_status(session_id: str) -> dict:
        record = persisted_sessions.get(session_id)
        if record is None:
            return {"completed": True, "stage": "none"}

        session_data = record["session_data"]
        stage = session_data.get("stage", "none")
        return {
            "completed": stage == "completed",
            "stage": stage,
            "reception_session_id": record["id"],
            "visitor_identity": session_data.get("visitor_identity"),
            "purpose": session_data.get("purpose"),
        }

    greeting_decision = _make_decision(
        category="greeting",
        next_agent="format_response",
        request_type="greeting",
    )
    hours_decision = _make_decision(
        category="business-info",
        next_agent="business_info",
        request_type="business_hours",
    )
    with (
        patch.object(MainWorkflow, "__init__", lambda self, **kwargs: None),
        patch(
            "backend.utils.reception_repository.ReceptionRepository.store_session",
            new=fake_store_session,
        ),
        patch(
            "backend.utils.reception_status.check_reception_status",
            new=fake_check_reception_status,
        ),
        patch(
            "backend.utils.purpose_classifier.classify_purpose",
            new=AsyncMock(return_value=("facility_use", "作業したいです", 0.97)),
        ),
    ):
        workflow = MainWorkflow()
        workflow.orchestrator = AsyncMock()
        workflow.orchestrator.decide_next_agent = AsyncMock(
            side_effect=[greeting_decision, hours_decision]
        )

        turn_1 = await workflow._orchestrator_node(_make_state("こんにちは"))
        assert turn_1.goto == "format_response"
        assert turn_1.update["metadata"]["reception_action"] == "start_reception"
        assert persisted_sessions["chat-session-123"]["session_data"]["stage"] == "greeting"

        turn_2 = await workflow._orchestrator_node(_make_state("作業したいです"))
        assert turn_2.goto == "format_response"
        assert turn_2.update["metadata"]["reception_stage"] == "purpose_hearing"
        assert persisted_sessions["chat-session-123"]["session_data"]["stage"] == "purpose_hearing"

        turn_3 = await workflow._orchestrator_node(_make_state("作業したいです"))
        assert turn_3.goto == "format_response"
        assert turn_3.update["metadata"]["reception_stage"] == "routing"
        assert turn_3.update["metadata"]["purpose"]["category"] == "facility_use"
        assert persisted_sessions["chat-session-123"]["session_data"]["stage"] == "routing"

        turn_4 = await workflow._orchestrator_node(_make_state("営業時間は？"))
        assert turn_4.goto == "business_info"
        assert persisted_sessions["chat-session-123"]["session_data"]["stage"] == "completed"
        assert persisted_sessions["chat-session-123"]["session_data"]["status"] == "completed"
        assert turn_4.update["routing"]["category"] == "business-info"
        assert workflow.orchestrator.decide_next_agent.await_count == 2


@pytest.mark.asyncio
async def test_greeting_stage_information_query_bypasses_reception() -> None:
    """greeting 段階でも明確な情報質問は受付目的ヒアリングに横取りされない。"""
    from backend.workflows.main_workflow import MainWorkflow

    persisted_sessions: dict[str, dict] = {}

    async def fake_store_session(_self, reception_session_id: str, data: dict) -> None:
        persisted_sessions[reception_session_id] = {
            "id": reception_session_id,
            "session_id": data.get("session_id"),
            "status": data.get("status", "active"),
            "stage": data.get("stage", "initiated"),
            "session_data": dict(data),
        }

    async def fake_check_reception_status(session_id: str) -> dict:
        record = persisted_sessions.get(session_id)
        if record is None:
            return {"completed": True, "stage": "none"}
        session_data = record["session_data"]
        stage = session_data.get("stage", "none")
        return {
            "completed": stage == "completed",
            "stage": stage,
            "reception_session_id": record["id"],
            "visitor_identity": session_data.get("visitor_identity"),
            "purpose": session_data.get("purpose"),
        }

    greeting_decision = _make_decision(
        category="greeting",
        next_agent="format_response",
        request_type="greeting",
    )
    hours_decision = _make_decision(
        category="business-info",
        next_agent="business_info",
        request_type="hours",
    )

    with (
        patch.object(MainWorkflow, "__init__", lambda self, **kwargs: None),
        patch(
            "backend.utils.reception_repository.ReceptionRepository.store_session",
            new=fake_store_session,
        ),
        patch(
            "backend.utils.reception_status.check_reception_status",
            new=fake_check_reception_status,
        ),
    ):
        workflow = MainWorkflow()
        workflow.orchestrator = AsyncMock()
        workflow.orchestrator.decide_next_agent = AsyncMock(
            side_effect=[greeting_decision, hours_decision]
        )

        turn_1 = await workflow._orchestrator_node(_make_state("こんにちは"))
        assert turn_1.goto == "format_response"
        assert persisted_sessions["chat-session-123"]["session_data"]["stage"] == "greeting"

        turn_2 = await workflow._orchestrator_node(_make_state("営業時間は？"))

        assert turn_2.goto == "business_info"
        assert turn_2.update["routing"]["request_type"] == "hours"
        assert persisted_sessions["chat-session-123"]["session_data"]["stage"] == "completed"
        assert persisted_sessions["chat-session-123"]["session_data"]["status"] == "completed"
        assert workflow.orchestrator.decide_next_agent.await_count == 2


@pytest.mark.asyncio
async def test_purpose_other_stays_in_purpose_hearing() -> None:
    """曖昧な目的(other)は purpose_hearing に留まりclarification を促す"""
    from backend.workflows.main_workflow import MainWorkflow

    persisted_sessions: dict[str, dict] = {}

    async def fake_store_session(_self, reception_session_id: str, data: dict) -> None:
        persisted_sessions[reception_session_id] = {
            "id": reception_session_id,
            "session_id": data.get("session_id"),
            "status": data.get("status", "active"),
            "stage": data.get("stage", "initiated"),
            "session_data": dict(data),
        }

    async def fake_check_reception_status(session_id: str) -> dict:
        record = persisted_sessions.get(session_id)
        if record is None:
            return {"completed": True, "stage": "none"}
        session_data = record["session_data"]
        stage = session_data.get("stage", "none")
        return {
            "completed": stage == "completed",
            "stage": stage,
            "reception_session_id": record["id"],
            "visitor_identity": session_data.get("visitor_identity"),
            "purpose": session_data.get("purpose"),
        }

    with (
        patch.object(MainWorkflow, "__init__", lambda self, **kwargs: None),
        patch(
            "backend.utils.reception_repository.ReceptionRepository.store_session",
            new=fake_store_session,
        ),
        patch(
            "backend.utils.reception_status.check_reception_status",
            new=fake_check_reception_status,
        ),
        patch(
            "backend.utils.purpose_classifier.classify_purpose",
            new=AsyncMock(return_value=("other", None, 0.3)),
        ),
    ):
        workflow = MainWorkflow()
        workflow.orchestrator = AsyncMock()

        # Seed session at purpose_hearing stage
        persisted_sessions["chat-session-123"] = {
            "id": "chat-session-123",
            "session_id": "chat-session-123",
            "status": "active",
            "stage": "purpose_hearing",
            "session_data": {
                "session_id": "chat-session-123",
                "stage": "purpose_hearing",
                "language": "ja",
                "status": "active",
            },
        }

        result = await workflow._orchestrator_node(_make_state("なんとなく来ました"))

        # Should stay in purpose_hearing -- NOT advance to routing
        assert result.goto == "format_response"
        assert result.update["metadata"]["reception_stage"] == "purpose_hearing"
        assert result.update["metadata"]["reception_action"] == "clarify_purpose"

        # Session stage must NOT have been updated to "routing"
        stage = persisted_sessions["chat-session-123"]["session_data"]["stage"]
        assert stage == "purpose_hearing", f"Expected purpose_hearing but got {stage}"

        # Orchestrator LLM should NOT have been called
        workflow.orchestrator.decide_next_agent.assert_not_awaited()
