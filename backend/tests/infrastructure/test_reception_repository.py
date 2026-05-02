"""Tests for Supabase-backed reception repository implementations.

All Supabase interactions are mocked.
"""

from unittest.mock import MagicMock

import pytest

from backend.domain.reception.models import (
    ReceptionSession,
    VisitPurpose,
    VisitorIdentity,
    VisitorType,
)
from backend.infrastructure.reception_repository import (
    SupabaseReceptionSessionRepository,
    SupabaseVisitRepository,
)

_RECEPTION_ID = "11111111-1111-1111-1111-111111111111"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query_result(data=None, count=None):
    """Create a mock query result."""
    result = MagicMock()
    result.data = data or []
    result.count = count
    return result


def _make_mock_client() -> MagicMock:
    """Build a mock Supabase client with chainable query builder."""
    client = MagicMock()
    return client


def _chainable_builder(execute_result=None) -> MagicMock:
    """Return a mock query builder where every method returns itself."""
    builder = MagicMock()
    for method in ("select", "eq", "order", "limit", "insert", "upsert"):
        getattr(builder, method).return_value = builder
    builder.execute.return_value = execute_result or _make_query_result()
    return builder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> MagicMock:
    return _make_mock_client()


def _sample_session(
    session_id: str = "sess-001",
    with_identity: bool = False,
    with_purpose: bool = False,
) -> ReceptionSession:
    """Create a sample ``ReceptionSession`` for testing."""
    identity = None
    if with_identity:
        identity = VisitorIdentity(
            visitor_type=VisitorType(value="returning"),
            user_id=42,
            name="Taro",
        )
    purpose = None
    if with_purpose:
        purpose = VisitPurpose(category="facility_use", detail="Co-working")

    return ReceptionSession(
        id=_RECEPTION_ID,
        session_id=session_id,
        visitor_identity=identity,
        purpose=purpose,
        stage="greeting",
        language="ja",
        trigger_type="button_press",
    )


# ---------------------------------------------------------------------------
# ReceptionSessionRepository tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_find_reception_session(mock_client: MagicMock):
    """save() should upsert, and find_by_id() should return the domain object."""
    repo = SupabaseReceptionSessionRepository(supabase_client=mock_client)

    # --- save ---
    upsert_builder = _chainable_builder()
    mock_client.table = MagicMock(return_value=upsert_builder)

    session = _sample_session(with_identity=True, with_purpose=True)
    await repo.save(session)

    mock_client.table.assert_called_with("reception_sessions")
    upsert_builder.upsert.assert_called_once()
    upserted_data = upsert_builder.upsert.call_args[0][0]
    assert upserted_data["id"] == _RECEPTION_ID
    assert upserted_data["user_id"] == 42
    assert upserted_data["stage"] == "greeting"
    assert upserted_data["purpose"] == "facility_use"

    # --- find_by_id ---
    row = {
        "id": _RECEPTION_ID,
        "session_id": "sess-001",
        "user_id": 42,
        "stage": "greeting",
        "purpose": "facility_use",
        "language": "ja",
        "trigger_type": "button_press",
    }
    find_builder = _chainable_builder(execute_result=_make_query_result(data=[row]))
    mock_client.table = MagicMock(return_value=find_builder)

    found = await repo.find_by_id(_RECEPTION_ID)

    assert found is not None
    assert found.id == _RECEPTION_ID
    assert found.stage == "greeting"
    assert found.visitor_identity is not None
    assert found.visitor_identity.user_id == 42
    assert found.visitor_identity.visitor_type == VisitorType(value="returning")
    assert found.purpose is not None
    assert found.purpose.category == "facility_use"


@pytest.mark.asyncio
async def test_find_by_id_skips_non_uuid_session_id(mock_client: MagicMock):
    """Synthetic IDs should not be sent to reception_sessions.id UUID lookup."""
    repo = SupabaseReceptionSessionRepository(supabase_client=mock_client)

    found = await repo.find_by_id("alpha-b-20260502-B1-BIZ-002")

    assert found is None
    mock_client.table.assert_not_called()


@pytest.mark.asyncio
async def test_find_by_conversation_session(mock_client: MagicMock):
    """find_by_conversation_session() should query by session_id and return domain object."""
    repo = SupabaseReceptionSessionRepository(supabase_client=mock_client)

    row = {
        "id": "rs-002",
        "session_id": "conv-session-xyz",
        "user_id": None,
        "stage": "initiated",
        "purpose": None,
        "language": "en",
        "trigger_type": "face_detection",
    }
    builder = _chainable_builder(execute_result=_make_query_result(data=[row]))
    mock_client.table = MagicMock(return_value=builder)

    found = await repo.find_by_conversation_session("conv-session-xyz")

    assert found is not None
    assert found.id == "rs-002"
    assert found.session_id == "conv-session-xyz"
    assert found.visitor_identity is None
    assert found.purpose is None
    assert found.language == "en"
    assert found.trigger_type == "face_detection"


@pytest.mark.asyncio
async def test_find_by_conversation_session_not_found(mock_client: MagicMock):
    """find_by_conversation_session() should return ``None`` when no record matches."""
    repo = SupabaseReceptionSessionRepository(supabase_client=mock_client)

    builder = _chainable_builder(execute_result=_make_query_result(data=[]))
    mock_client.table = MagicMock(return_value=builder)

    found = await repo.find_by_conversation_session("nonexistent")
    assert found is None


# ---------------------------------------------------------------------------
# VisitRepository tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_visit(mock_client: MagicMock):
    """record_visit() should insert a row and return a UUID string."""
    repo = SupabaseVisitRepository(supabase_client=mock_client)

    builder = _chainable_builder()
    mock_client.table = MagicMock(return_value=builder)

    session = _sample_session(with_identity=True, with_purpose=True)
    visit_id = await repo.record_visit(session)

    assert isinstance(visit_id, str)
    assert len(visit_id) == 36  # UUID format

    mock_client.table.assert_called_with("visits")
    builder.insert.assert_called_once()
    inserted_data = builder.insert.call_args[0][0]
    assert inserted_data["session_id"] == "sess-001"
    assert inserted_data["user_id"] == 42
    assert inserted_data["purpose"] == "facility_use"
    assert inserted_data["purpose_detail"] == "Co-working"
    assert inserted_data["visitor_type"] == "returning"


@pytest.mark.asyncio
async def test_record_visit_new_visitor(mock_client: MagicMock):
    """record_visit() should handle a new (unidentified) visitor gracefully."""
    repo = SupabaseVisitRepository(supabase_client=mock_client)

    builder = _chainable_builder()
    mock_client.table = MagicMock(return_value=builder)

    session = _sample_session(with_identity=False, with_purpose=False)
    visit_id = await repo.record_visit(session)

    assert isinstance(visit_id, str)
    inserted_data = builder.insert.call_args[0][0]
    assert inserted_data["user_id"] is None
    assert inserted_data["purpose"] == "other"
    assert inserted_data["visitor_type"] == "new"


@pytest.mark.asyncio
async def test_get_recent_visits(mock_client: MagicMock):
    """get_recent_visits() should return a list of visit dicts."""
    repo = SupabaseVisitRepository(supabase_client=mock_client)

    visits_data = [
        {"id": "v1", "purpose": "facility_use", "started_at": "2026-03-06T10:00:00+09:00"},
        {"id": "v2", "purpose": "tour", "started_at": "2026-03-01T14:00:00+09:00"},
    ]
    builder = _chainable_builder(execute_result=_make_query_result(data=visits_data))
    mock_client.table = MagicMock(return_value=builder)

    result = await repo.get_recent_visits(user_id=42, limit=3)

    assert len(result) == 2
    assert result[0]["id"] == "v1"
    mock_client.table.assert_called_with("visits")
