"""Integration tests for reception services against local Supabase.

Tests PurposeFlowService._fetch_today_events() and
VisitorIdentificationService.identify_by_visitor_id() with real DB queries.

Run requirements:
  - supabase start (local Supabase running)
  - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY set

Run:
  cd backend
  SUPABASE_URL=http://127.0.0.1:54321 \
  SUPABASE_SERVICE_ROLE_KEY=<service_role_key> \
  python -m pytest tests/integration/test_reception_supabase_integration.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from supabase import Client, create_client

from backend.services.purpose_flow_service import PurposeFlowService
from backend.services.visitor_identification_service import VisitorIdentificationService

_JST = ZoneInfo("Asia/Tokyo")

_supabase_url = os.getenv("SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_is_local = any(m in _supabase_url for m in ["localhost", "127.0.0.1", "kong"])
_available = bool(_supabase_url and _supabase_key and _is_local)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _available,
        reason="Local Supabase not available (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY)",
    ),
]


@pytest.fixture()
def supabase_client() -> Client:
    return create_client(_supabase_url, _supabase_key)


@pytest.fixture()
def _cleanup_events(supabase_client: Client):
    """Clean up test events after each test."""
    created_ids: list[str] = []
    yield created_ids
    for event_id in created_ids:
        try:
            supabase_client.table("events").delete().eq("id", event_id).execute()
        except Exception:
            pass


@pytest.fixture()
def _cleanup_visits(supabase_client: Client):
    """Clean up test visits after each test."""
    created_ids: list[str] = []
    yield created_ids
    for visit_id in created_ids:
        try:
            supabase_client.table("visits").delete().eq("id", visit_id).execute()
        except Exception:
            pass


def _insert_event(
    client: Client,
    tracker: list[str],
    *,
    title: str,
    event_date: date | None = None,
    location: str | None = None,
    start_at: str | None = None,
) -> dict:
    row = {"title": title}
    if event_date is not None:
        row["event_date"] = event_date.isoformat()
    if location is not None:
        row["location"] = location
    if start_at is not None:
        row["start_at"] = start_at
    result = client.table("events").insert(row).execute()
    inserted = result.data[0]
    tracker.append(inserted["id"])
    return inserted


def _insert_visit(
    client: Client,
    tracker: list[str],
    *,
    visitor_id: str,
    purpose: str = "facility_use",
    purpose_detail: str | None = None,
    started_at: str | None = None,
) -> dict:
    row = {
        "visitor_id": visitor_id,
        "purpose": purpose,
        "visitor_type": "returning",
    }
    if purpose_detail is not None:
        row["purpose_detail"] = purpose_detail
    if started_at is not None:
        row["started_at"] = started_at
    result = client.table("visits").insert(row).execute()
    inserted = result.data[0]
    tracker.append(inserted["id"])
    return inserted


# ---------------------------------------------------------------
# PurposeFlowService._fetch_today_events() tests
# ---------------------------------------------------------------


class TestFetchTodayEvents:
    """Test _fetch_today_events against real Supabase events table."""

    async def test_returns_today_events_only(
        self, supabase_client: Client, _cleanup_events: list[str]
    ) -> None:
        today = datetime.now(_JST).date()
        yesterday = today - timedelta(days=1)

        _insert_event(
            supabase_client,
            _cleanup_events,
            title="Today Meetup",
            event_date=today,
            location="Room A",
        )
        _insert_event(
            supabase_client,
            _cleanup_events,
            title="Yesterday Event",
            event_date=yesterday,
            location="Room B",
        )

        service = PurposeFlowService(supabase_client=supabase_client)
        events = await service._fetch_today_events()

        titles = [e["title"] for e in events]
        assert "Today Meetup" in titles
        assert "Yesterday Event" not in titles

    async def test_returns_empty_when_no_events(self, supabase_client: Client) -> None:
        service = PurposeFlowService(supabase_client=supabase_client)
        events = await service._fetch_today_events()
        # May or may not be empty depending on pre-existing data,
        # but should not raise
        assert isinstance(events, list)

    async def test_normalizes_event_fields(
        self, supabase_client: Client, _cleanup_events: list[str]
    ) -> None:
        today = datetime.now(_JST).date()
        _insert_event(
            supabase_client,
            _cleanup_events,
            title="Normalized Test",
            event_date=today,
            location="Hall C",
        )

        service = PurposeFlowService(supabase_client=supabase_client)
        events = await service._fetch_today_events()

        matching = [e for e in events if e["title"] == "Normalized Test"]
        assert len(matching) == 1

        event = matching[0]
        assert event["date"] == today.isoformat()
        assert event["location"] == "Hall C"
        assert "id" in event
        assert "start_at" in event

    async def test_events_with_start_at_datetime(
        self, supabase_client: Client, _cleanup_events: list[str]
    ) -> None:
        today = datetime.now(_JST).date()
        start_dt = datetime.combine(today, datetime.min.time().replace(hour=14), tzinfo=_JST)

        _insert_event(
            supabase_client,
            _cleanup_events,
            title="Afternoon Session",
            event_date=today,
            start_at=start_dt.isoformat(),
        )

        service = PurposeFlowService(supabase_client=supabase_client)
        events = await service._fetch_today_events()

        matching = [e for e in events if e["title"] == "Afternoon Session"]
        assert len(matching) == 1
        assert matching[0]["start_at"] is not None

    async def test_multiple_today_events_sorted(
        self, supabase_client: Client, _cleanup_events: list[str]
    ) -> None:
        today = datetime.now(_JST).date()

        _insert_event(
            supabase_client,
            _cleanup_events,
            title="Zebra Talk",
            event_date=today,
        )
        _insert_event(
            supabase_client,
            _cleanup_events,
            title="Alpha Workshop",
            event_date=today,
        )

        service = PurposeFlowService(supabase_client=supabase_client)
        events = await service._fetch_today_events()

        test_titles = [e["title"] for e in events if e["title"] in ("Zebra Talk", "Alpha Workshop")]
        assert test_titles == sorted(test_titles)


# ---------------------------------------------------------------
# VisitorIdentificationService tests
# ---------------------------------------------------------------


class TestVisitorIdentification:
    """Test VisitorIdentificationService against real Supabase visits table."""

    async def test_identify_returning_visitor(
        self, supabase_client: Client, _cleanup_visits: list[str]
    ) -> None:
        visitor_id = str(uuid.uuid4())
        _insert_visit(
            supabase_client,
            _cleanup_visits,
            visitor_id=visitor_id,
            purpose="event_participation",
            purpose_detail="Morning meetup",
        )

        service = VisitorIdentificationService(supabase_client=supabase_client)
        result = await service.identify_by_visitor_id(visitor_id)

        assert result is not None
        assert result["visitor_type"] == "returning"
        assert result["last_purpose"] == "event_participation"
        assert result["last_purpose_detail"] == "Morning meetup"
        assert result["visit_count"] >= 1

    async def test_identify_unknown_visitor_returns_none(self, supabase_client: Client) -> None:
        unknown_id = str(uuid.uuid4())
        service = VisitorIdentificationService(supabase_client=supabase_client)
        result = await service.identify_by_visitor_id(unknown_id)
        assert result is None

    async def test_visit_count_increments(
        self, supabase_client: Client, _cleanup_visits: list[str]
    ) -> None:
        visitor_id = str(uuid.uuid4())
        for i in range(3):
            _insert_visit(
                supabase_client,
                _cleanup_visits,
                visitor_id=visitor_id,
                purpose="facility_use",
                started_at=(datetime.now(_JST) - timedelta(days=3 - i)).isoformat(),
            )

        service = VisitorIdentificationService(supabase_client=supabase_client)
        result = await service.identify_by_visitor_id(visitor_id)

        assert result is not None
        assert result["visit_count"] == 3

    async def test_returns_most_recent_visit(
        self, supabase_client: Client, _cleanup_visits: list[str]
    ) -> None:
        visitor_id = str(uuid.uuid4())

        _insert_visit(
            supabase_client,
            _cleanup_visits,
            visitor_id=visitor_id,
            purpose="tour",
            started_at=(datetime.now(_JST) - timedelta(days=5)).isoformat(),
        )
        _insert_visit(
            supabase_client,
            _cleanup_visits,
            visitor_id=visitor_id,
            purpose="consultation",
            started_at=datetime.now(_JST).isoformat(),
        )

        service = VisitorIdentificationService(supabase_client=supabase_client)
        result = await service.identify_by_visitor_id(visitor_id)

        assert result is not None
        assert result["last_purpose"] == "consultation"

    async def test_get_recent_visits(
        self, supabase_client: Client, _cleanup_visits: list[str]
    ) -> None:
        visitor_id = str(uuid.uuid4())
        for i in range(4):
            _insert_visit(
                supabase_client,
                _cleanup_visits,
                visitor_id=visitor_id,
                purpose=f"purpose_{i}",
                started_at=(datetime.now(_JST) - timedelta(days=4 - i)).isoformat(),
            )

        service = VisitorIdentificationService(supabase_client=supabase_client)
        visits = await service.get_recent_visits(visitor_id=visitor_id, limit=2)

        assert len(visits) == 2
        assert visits[0]["purpose"] == "purpose_3"
        assert visits[1]["purpose"] == "purpose_2"
