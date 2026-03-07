"""Tests for VisitorIdentificationService.

All Supabase interactions are mocked to ensure tests run without
external dependencies.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.visitor_identification_service import VisitorIdentificationService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client() -> MagicMock:
    """Build a mock Supabase client with chainable query builder."""
    client = MagicMock()

    def _table(name: str) -> MagicMock:
        builder = MagicMock()
        # Enable method chaining for all query-builder methods.
        for method in ("select", "eq", "order", "limit", "insert", "upsert"):
            getattr(builder, method).return_value = builder
        return builder

    client.table = MagicMock(side_effect=_table)
    return client


def _make_query_result(data=None, count=None):
    """Create a mock query result."""
    result = MagicMock()
    result.data = data or []
    result.count = count
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> MagicMock:
    return _make_mock_client()


@pytest.fixture
def service(mock_client: MagicMock) -> VisitorIdentificationService:
    return VisitorIdentificationService(supabase_client=mock_client)


# ---------------------------------------------------------------------------
# NFC identification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identify_by_nfc_found(service: VisitorIdentificationService, mock_client: MagicMock):
    """NFC lookup should resolve to a user profile when a matching record exists."""
    nfc_builder = MagicMock()
    nfc_builder.select.return_value = nfc_builder
    nfc_builder.eq.return_value = nfc_builder
    nfc_builder.execute.return_value = _make_query_result(data=[{"user_id": 42}])

    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.execute.return_value = _make_query_result(data=[{"id": 42, "name": "Taro"}])

    count_builder = MagicMock()
    count_builder.select.return_value = count_builder
    count_builder.eq.return_value = count_builder
    count_builder.execute.return_value = _make_query_result(count=5)

    tables = {"nfcs": nfc_builder, "users": user_builder, "visits": count_builder}
    mock_client.table = MagicMock(side_effect=lambda n: tables[n])

    result = await service.identify_by_nfc("nfc-abc-123")

    assert result is not None
    assert result["visitor_type"] == "returning"
    assert result["user_id"] == 42
    assert result["name"] == "Taro"
    assert result["visit_count"] == 5


@pytest.mark.asyncio
async def test_identify_by_nfc_not_found(
    service: VisitorIdentificationService, mock_client: MagicMock
):
    """NFC lookup should return ``None`` when no matching NFC record exists."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.execute.return_value = _make_query_result(data=[])

    mock_client.table = MagicMock(return_value=builder)

    result = await service.identify_by_nfc("unknown-nfc")
    assert result is None


# ---------------------------------------------------------------------------
# Visitor-ID identification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identify_by_visitor_id_returning(
    service: VisitorIdentificationService, mock_client: MagicMock
):
    """Should return visit summary for a returning visitor."""
    visit_builder = MagicMock()
    visit_builder.select.return_value = visit_builder
    visit_builder.eq.return_value = visit_builder
    visit_builder.order.return_value = visit_builder
    visit_builder.limit.return_value = visit_builder
    visit_builder.execute.return_value = _make_query_result(
        data=[
            {
                "started_at": "2026-03-01T10:00:00+09:00",
                "purpose": "facility_use",
                "purpose_detail": "Co-working",
            }
        ]
    )

    count_builder = MagicMock()
    count_builder.select.return_value = count_builder
    count_builder.eq.return_value = count_builder
    count_builder.execute.return_value = _make_query_result(count=3)

    mock_client.table = MagicMock(side_effect=lambda _: visit_builder)
    # Override count call specifically: second .table("visits") call is for count
    call_count = {"n": 0}

    def table_side_effect(name: str):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return visit_builder
        return count_builder

    mock_client.table = MagicMock(side_effect=table_side_effect)

    result = await service.identify_by_visitor_id("visitor-uuid-abc")

    assert result is not None
    assert result["visitor_type"] == "returning"
    assert result["last_purpose"] == "facility_use"
    assert result["visit_count"] == 3


@pytest.mark.asyncio
async def test_identify_by_visitor_id_new(
    service: VisitorIdentificationService, mock_client: MagicMock
):
    """Should return ``None`` for a visitor_id with no prior visits."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.order.return_value = builder
    builder.limit.return_value = builder
    builder.execute.return_value = _make_query_result(data=[])

    mock_client.table = MagicMock(return_value=builder)

    result = await service.identify_by_visitor_id("brand-new-visitor")
    assert result is None


# ---------------------------------------------------------------------------
# Recent visits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_visits(service: VisitorIdentificationService, mock_client: MagicMock):
    """Should return a list of recent visit dicts."""
    visits_data = [
        {"id": "v1", "purpose": "facility_use", "started_at": "2026-03-06T10:00:00+09:00"},
        {"id": "v2", "purpose": "tour", "started_at": "2026-03-01T14:00:00+09:00"},
    ]
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.order.return_value = builder
    builder.limit.return_value = builder
    builder.execute.return_value = _make_query_result(data=visits_data)

    mock_client.table = MagicMock(return_value=builder)

    result = await service.get_recent_visits(user_id=42, limit=5)

    assert len(result) == 2
    assert result[0]["id"] == "v1"
    assert result[1]["purpose"] == "tour"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supabase_unavailable_graceful_fallback():
    """All methods should return safe defaults when Supabase is unavailable."""
    service = VisitorIdentificationService(supabase_client=None)

    # Patch the lazy resolver to raise
    with patch(
        "backend.services.visitor_identification_service.VisitorIdentificationService._get_supabase",
        new_callable=AsyncMock,
        return_value=None,
    ):
        assert await service.identify_by_nfc("any") is None
        assert await service.identify_by_visitor_id("any") is None
        assert await service.get_recent_visits(visitor_id="any") == []
