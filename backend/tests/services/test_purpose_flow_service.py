"""Tests for PurposeFlowService."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.domain.reception.models import VisitPurpose, VisitorIdentity, VisitorType
from backend.services.purpose_flow_service import PurposeFlowResult, PurposeFlowService

_JST = ZoneInfo("Asia/Tokyo")


def _make_query_result(data=None) -> MagicMock:
    result = MagicMock()
    result.data = data or []
    return result


def _make_identity(visitor_type: str = "new", name: str | None = None) -> VisitorIdentity:
    return VisitorIdentity(visitor_type=VisitorType(value=visitor_type), name=name)


def _make_event_client(rows: list[dict]) -> MagicMock:
    client = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.limit.return_value = builder
    builder.execute.return_value = _make_query_result(rows)
    client.table.return_value = builder
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [
        ("ja", "施設利用"),
        ("en", "use the facility"),
    ],
)
async def test_handle_facility_use_returns_guide_result(
    language: str,
    expected_fragment: str,
) -> None:
    service = PurposeFlowService()

    result = await service.handle_facility_use(language, "session-test", _make_identity())

    assert isinstance(result, PurposeFlowResult)
    assert expected_fragment in result.response_text
    assert result.target_agent == "facility"
    assert result.action_type == "guide"
    assert result.requires_staff is False
    assert result.action_data == {"purpose_category": "facility_use", "visitor_type": "new"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [
        ("ja", "確認できたイベント"),
        ("en", "events I found for today"),
    ],
)
async def test_handle_event_participation_returns_today_events(
    language: str,
    expected_fragment: str,
) -> None:
    today = datetime.now(_JST).date().isoformat()
    rows = [
        {"id": 1, "title": "Morning Meetup", "event_date": today, "location": "Main Hall"},
        {"id": 2, "title": "Old Event", "event_date": "2026-01-01", "location": "B1"},
    ]
    service = PurposeFlowService(supabase_client=_make_event_client(rows))

    result = await service.handle_event_participation(
        language, "session-test", _make_identity("returning")
    )

    assert expected_fragment in result.response_text
    assert result.target_agent == "event"
    assert result.action_type == "lookup"
    assert result.requires_staff is False
    assert result.action_data == {
        "events": [
            {
                "id": 1,
                "title": "Morning Meetup",
                "date": today,
                "location": "Main Hall",
                "start_at": None,
            }
        ],
        "event_count": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [
        ("ja", "受付で確認できるイベント情報がない"),
        ("en", "couldn't find a confirmed event listing"),
    ],
)
async def test_handle_event_participation_without_events_uses_default_message(
    language: str,
    expected_fragment: str,
) -> None:
    service = PurposeFlowService(supabase_client=_make_event_client([]))

    result = await service.handle_event_participation(language, "session-test", _make_identity())

    assert expected_fragment in result.response_text
    assert result.action_data == {"events": [], "event_count": 0}


@pytest.mark.asyncio
async def test_handle_event_participation_falls_back_on_supabase_error() -> None:
    client = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.limit.return_value = builder
    builder.execute.side_effect = RuntimeError("supabase unavailable")
    client.table.return_value = builder
    service = PurposeFlowService(supabase_client=client)

    result = await service.handle_event_participation("en", "session-test", _make_identity())

    assert "couldn't check today's event listing right now" in result.response_text
    assert result.action_data == {"events": [], "lookup_failed": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [
        ("ja", "ツアー案内"),
        ("en", "tour guidance flow"),
    ],
)
async def test_handle_tour_returns_handoff_result(
    language: str,
    expected_fragment: str,
) -> None:
    service = PurposeFlowService()

    result = await service.handle_tour(language, "session-test", _make_identity())

    assert expected_fragment in result.response_text
    assert result.target_agent == "slide"
    assert result.action_type == "handoff"
    assert result.requires_staff is False
    assert result.action_data == {"purpose_category": "tour"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [
        ("ja", "スタッフへお知らせしました"),
        ("en", "notified the staff"),
    ],
)
async def test_handle_consultation_sends_discord_notification(
    language: str,
    expected_fragment: str,
) -> None:
    notifier = AsyncMock(return_value=True)
    service = PurposeFlowService(escalation_notifier=notifier)
    identity = _make_identity("returning", name="Tanaka")

    result = await service.handle_consultation(language, "session-123", identity)

    assert expected_fragment in result.response_text
    assert result.target_agent == "general_knowledge"
    assert result.action_type == "escalate"
    assert result.requires_staff is True
    assert result.action_data == {
        "reason": (
            "来訪者が相談対応を希望"
            if language == "ja"
            else "Visitor requested consultation support"
        ),
        "notification_sent": True,
        "session_id": "session-123",
    }
    notifier.assert_awaited_once_with(
        "session-123",
        "来訪者が相談対応を希望" if language == "ja" else "Visitor requested consultation support",
        "Tanaka",
        language,
    )


@pytest.mark.asyncio
async def test_handle_consultation_falls_back_when_notification_fails() -> None:
    notifier = AsyncMock(side_effect=RuntimeError("discord failed"))
    service = PurposeFlowService(escalation_notifier=notifier)

    result = await service.handle_consultation("en", "session-456", _make_identity(name="John"))

    assert "arranging staff assistance now" in result.response_text
    assert result.requires_staff is True
    assert result.action_data == {
        "reason": "Visitor requested consultation support",
        "notification_sent": False,
        "session_id": "session-456",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [
        ("ja", "適切な案内"),
        ("en", "appropriate guidance"),
    ],
)
async def test_handle_other_returns_general_handoff(
    language: str,
    expected_fragment: str,
) -> None:
    service = PurposeFlowService()

    result = await service.handle_other(language, "session-test", _make_identity())

    assert expected_fragment in result.response_text
    assert result.target_agent == "general_knowledge"
    assert result.action_type == "handoff"
    assert result.requires_staff is False
    assert result.action_data == {"purpose_category": "other"}


@pytest.mark.asyncio
async def test_resolve_dispatches_to_matching_handler() -> None:
    service = PurposeFlowService()
    purpose = VisitPurpose(category="consultation")

    with patch.object(service, "handle_consultation", new=AsyncMock()) as mock_handler:
        sentinel = PurposeFlowResult(
            response_text="ok",
            target_agent="general_knowledge",
            action_type="escalate",
            action_data=None,
            requires_staff=True,
        )
        mock_handler.return_value = sentinel

        result = await service.resolve(purpose, "ja", "session-789", _make_identity())

    assert result is sentinel
    mock_handler.assert_awaited_once()
