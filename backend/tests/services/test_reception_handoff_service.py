"""Tests for ReceptionHandoffService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.domain.reception.models import (
    ReceptionSession,
    VisitPurpose,
    VisitorIdentity,
    VisitorType,
)
from backend.services.purpose_flow_service import PurposeFlowResult
from backend.services.reception_handoff_service import HandoffResult, ReceptionHandoffService


def _make_identity(
    visitor_type: str = "new",
    name: str | None = "Tanaka",
    visit_count: int = 2,
) -> VisitorIdentity:
    return VisitorIdentity(
        visitor_type=VisitorType(value=visitor_type),
        name=name,
        visit_count=visit_count,
    )


def _make_purpose(
    category: str = "facility_use",
    detail: str | None = "I want to use the coworking space",
) -> VisitPurpose:
    return VisitPurpose(category=category, detail=detail)


def _make_session(
    *,
    language: str = "ja",
    purpose: VisitPurpose | None = None,
    visitor_identity: VisitorIdentity | None = None,
) -> ReceptionSession:
    return ReceptionSession(
        id="reception-123",
        session_id="session-123",
        language=language,
        purpose=purpose,
        visitor_identity=visitor_identity,
        stage="routing",
    )


def _make_purpose_flow_result(
    *,
    response_text: str = "Handled by mocked purpose flow",
    target_agent: str = "facility",
    action_type: str = "guide",
    action_data: dict | None = None,
    requires_staff: bool = False,
) -> PurposeFlowResult:
    return PurposeFlowResult(
        response_text=response_text,
        target_agent=target_agent,
        action_type=action_type,
        action_data=action_data or {"source": "mock"},
        requires_staff=requires_staff,
    )


def _make_service(
    purpose_flow_result: PurposeFlowResult,
) -> tuple[ReceptionHandoffService, MagicMock]:
    purpose_flow_service = MagicMock()
    purpose_flow_service.resolve = AsyncMock(return_value=purpose_flow_result)
    service = ReceptionHandoffService(purpose_flow_service=purpose_flow_service)
    return service, purpose_flow_service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category", "expected_agent", "requires_staff", "action_type"),
    [
        ("facility_use", "facility", False, "guide"),
        ("event_participation", "event", False, "lookup"),
        ("tour", "slide", False, "handoff"),
        ("consultation", "general_knowledge", True, "escalate"),
        ("other", "general_knowledge", False, "handoff"),
    ],
)
async def test_prepare_handoff_routes_by_purpose_category(
    category: str,
    expected_agent: str,
    requires_staff: bool,
    action_type: str,
) -> None:
    purpose = _make_purpose(category=category, detail=f"detail for {category}")
    identity = _make_identity(visitor_type="returning", name="Aki", visit_count=5)
    session = _make_session(language="en", purpose=purpose, visitor_identity=identity)
    purpose_flow_result = _make_purpose_flow_result(
        target_agent=expected_agent,
        action_type=action_type,
        requires_staff=requires_staff,
    )
    service, purpose_flow_service = _make_service(purpose_flow_result)

    result = await service.prepare_handoff(session)

    assert isinstance(result, HandoffResult)
    assert result.target_agent == expected_agent
    assert result.purpose_flow == purpose_flow_result
    assert result.requires_staff is requires_staff
    assert result.workflow_state["routing"]["agent"] == expected_agent
    purpose_flow_service.resolve.assert_awaited_once_with(
        purpose=purpose,
        language="en",
        session_id="session-123",
        visitor_identity=identity,
    )


@pytest.mark.asyncio
async def test_prepare_handoff_raises_when_purpose_is_missing() -> None:
    session = _make_session(purpose=None, visitor_identity=_make_identity())
    service, purpose_flow_service = _make_service(_make_purpose_flow_result())

    with pytest.raises(ValueError, match="purpose not set"):
        await service.prepare_handoff(session)

    purpose_flow_service.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_handoff_raises_when_visitor_identity_is_missing() -> None:
    session = _make_session(purpose=_make_purpose(), visitor_identity=None)
    service, purpose_flow_service = _make_service(_make_purpose_flow_result())

    with pytest.raises(ValueError, match="visitor_identity not set"):
        await service.prepare_handoff(session)

    purpose_flow_service.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_handoff_builds_expected_workflow_state_structure() -> None:
    purpose = _make_purpose(category="event_participation", detail="Join tonight's meetup")
    identity = _make_identity(name="Mika")
    session = _make_session(language="ja", purpose=purpose, visitor_identity=identity)
    purpose_flow_result = _make_purpose_flow_result(
        target_agent="event",
        action_type="lookup",
        action_data={"events": [{"id": 1, "title": "Night Meetup"}]},
    )
    service, _ = _make_service(purpose_flow_result)

    result = await service.prepare_handoff(session)

    workflow_state = result.workflow_state

    assert {
        "messages",
        "query",
        "session_id",
        "language",
        "routing",
        "answer",
        "emotion",
        "metadata",
        "context",
        "image_data",
        "ocr_result",
    }.issubset(workflow_state)
    assert workflow_state["messages"] == []
    assert workflow_state["query"] == "Join tonight's meetup"
    assert workflow_state["session_id"] == "session-123"
    assert workflow_state["language"] == "ja"
    assert workflow_state["answer"] is None
    assert workflow_state["emotion"] is None
    assert workflow_state["image_data"] is None
    assert workflow_state["routing"] == {
        "agent": "event",
        "category": "event_participation",
        "request_type": "lookup",
        "confidence": 1.0,
        "reasoning": "Routed from autonomous reception flow",
        "debug_info": {},
    }


@pytest.mark.asyncio
async def test_prepare_handoff_generates_synthetic_query_when_detail_is_missing() -> None:
    purpose = _make_purpose(category="consultation", detail=None)
    session = _make_session(
        language="en",
        purpose=purpose,
        visitor_identity=_make_identity(name="John"),
    )
    purpose_flow_result = _make_purpose_flow_result(
        target_agent="general_knowledge",
        action_type="escalate",
        requires_staff=True,
    )
    service, _ = _make_service(purpose_flow_result)

    result = await service.prepare_handoff(session)

    assert result.workflow_state["query"] == "I'd like to consult about something"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected_query"),
    [
        ("ja", "施設を利用したいです"),
        ("en", "I'd like to use the facility"),
        ("zh", "我想使用设施"),
        ("ko", "시설을 이용하고 싶습니다"),
    ],
)
async def test_prepare_handoff_uses_language_specific_synthetic_queries(
    language: str,
    expected_query: str,
) -> None:
    purpose = _make_purpose(category="facility_use", detail=None)
    session = _make_session(
        language=language,
        purpose=purpose,
        visitor_identity=_make_identity(),
    )
    service, _ = _make_service(_make_purpose_flow_result())

    result = await service.prepare_handoff(session)

    assert result.workflow_state["query"] == expected_query


@pytest.mark.asyncio
async def test_prepare_handoff_prefers_custom_purpose_detail_over_synthetic_query() -> None:
    purpose = _make_purpose(category="tour", detail="Please guide me to the startup exhibits")
    session = _make_session(
        language="ko",
        purpose=purpose,
        visitor_identity=_make_identity(name="Sora"),
    )
    service, _ = _make_service(
        _make_purpose_flow_result(target_agent="slide", action_type="handoff")
    )

    result = await service.prepare_handoff(session)

    assert result.workflow_state["query"] == "Please guide me to the startup exhibits"


@pytest.mark.asyncio
async def test_prepare_handoff_metadata_contains_reception_information() -> None:
    purpose = _make_purpose(category="consultation", detail="Need startup funding advice")
    identity = _make_identity(visitor_type="returning", name="Yuki", visit_count=7)
    session = _make_session(language="ja", purpose=purpose, visitor_identity=identity)
    purpose_flow_result = _make_purpose_flow_result(
        response_text="Staff has been notified",
        target_agent="general_knowledge",
        action_type="escalate",
        action_data={"reason": "consultation", "notification_sent": True},
        requires_staff=True,
    )
    service, _ = _make_service(purpose_flow_result)

    result = await service.prepare_handoff(session)

    assert result.workflow_state["metadata"] == {
        "reception_session_id": "reception-123",
        "reception_handoff": True,
        "visitor_type": "returning",
        "purpose_category": "consultation",
        "purpose_detail": "Need startup funding advice",
        "purpose_flow_action": "escalate",
        "purpose_flow_data": {"reason": "consultation", "notification_sent": True},
        "requires_staff": True,
    }


@pytest.mark.asyncio
async def test_prepare_handoff_context_contains_reception_visitor_information() -> None:
    purpose = _make_purpose(category="other", detail="I have a package delivery")
    identity = _make_identity(visitor_type="new", name="Chris", visit_count=0)
    session = _make_session(language="en", purpose=purpose, visitor_identity=identity)
    purpose_flow_result = _make_purpose_flow_result(
        response_text="I'll connect you to the right guidance",
        target_agent="general_knowledge",
        action_type="handoff",
        action_data={"purpose_category": "other"},
    )
    service, _ = _make_service(purpose_flow_result)

    result = await service.prepare_handoff(session)

    assert result.workflow_state["context"] == {
        "reception_context": {
            "visitor_name": "Chris",
            "visitor_type": "new",
            "visit_count": 0,
            "purpose_response_text": "I'll connect you to the right guidance",
        }
    }
