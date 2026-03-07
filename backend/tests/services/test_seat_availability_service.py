"""Tests for SeatAvailabilityService.

All Supabase interactions are mocked to ensure tests run without
external dependencies.  Follows the same patterns established in
``test_visitor_identification_service.py``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.seat_availability_service import SeatAvailabilityService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client() -> MagicMock:
    """Build a mock Supabase client with chainable query builder."""
    client = MagicMock()

    def _table(name: str) -> MagicMock:
        builder = MagicMock()
        for method in ("select", "eq", "order", "limit", "neq"):
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
# Sample data
# ---------------------------------------------------------------------------

SEAT_CATEGORIES = [
    {"id": 1, "name": "Hot Desk", "description": "Open seating area"},
    {"id": 2, "name": "Meeting Room", "description": "Private meeting rooms"},
]

AVAILABLE_SEATS = [
    {
        "id": 1,
        "name": "A-1",
        "seat_category_id": 1,
        "is_available": True,
        "seat_categories": {"id": 1, "name": "Hot Desk", "description": "Open seating area"},
    },
    {
        "id": 2,
        "name": "A-2",
        "seat_category_id": 1,
        "is_available": True,
        "seat_categories": {"id": 1, "name": "Hot Desk", "description": "Open seating area"},
    },
    {
        "id": 3,
        "name": "B-1",
        "seat_category_id": 2,
        "is_available": True,
        "seat_categories": {
            "id": 2,
            "name": "Meeting Room",
            "description": "Private meeting rooms",
        },
    },
]

ALL_SEATS = [
    {
        "id": 1,
        "name": "A-1",
        "seat_category_id": 1,
        "is_available": True,
        "seat_categories": {"id": 1, "name": "Hot Desk", "description": "Open seating area"},
    },
    {
        "id": 2,
        "name": "A-2",
        "seat_category_id": 1,
        "is_available": False,
        "seat_categories": {"id": 1, "name": "Hot Desk", "description": "Open seating area"},
    },
    {
        "id": 3,
        "name": "B-1",
        "seat_category_id": 2,
        "is_available": True,
        "seat_categories": {
            "id": 2,
            "name": "Meeting Room",
            "description": "Private meeting rooms",
        },
    },
    {
        "id": 4,
        "name": "B-2",
        "seat_category_id": 2,
        "is_available": False,
        "seat_categories": {
            "id": 2,
            "name": "Meeting Room",
            "description": "Private meeting rooms",
        },
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> MagicMock:
    return _make_mock_client()


@pytest.fixture
def service(mock_client: MagicMock) -> SeatAvailabilityService:
    return SeatAvailabilityService(supabase_client=mock_client)


# ---------------------------------------------------------------------------
# get_available_seats
# ---------------------------------------------------------------------------


async def test_get_available_seats_returns_available(
    service: SeatAvailabilityService, mock_client: MagicMock
):
    """Should return only seats where is_available is True."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.execute.return_value = _make_query_result(data=AVAILABLE_SEATS)

    mock_client.table = MagicMock(return_value=builder)

    result = await service.get_available_seats()

    assert len(result) == 3
    assert all(seat["is_available"] for seat in result)
    mock_client.table.assert_called_with("seats")


async def test_get_available_seats_none_available(
    service: SeatAvailabilityService, mock_client: MagicMock
):
    """Should return an empty list when all seats are occupied."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.execute.return_value = _make_query_result(data=[])

    mock_client.table = MagicMock(return_value=builder)

    result = await service.get_available_seats()

    assert result == []


# ---------------------------------------------------------------------------
# get_seat_summary
# ---------------------------------------------------------------------------


async def test_get_seat_summary(service: SeatAvailabilityService, mock_client: MagicMock):
    """Should return a summary with total, available, and per-category counts."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.execute.return_value = _make_query_result(data=ALL_SEATS)

    mock_client.table = MagicMock(return_value=builder)

    result = await service.get_seat_summary()

    assert result["total"] == 4
    assert result["available"] == 2
    assert result["occupied"] == 2

    # Category breakdown
    categories = result["categories"]
    assert len(categories) == 2

    hot_desk = next(c for c in categories if c["name"] == "Hot Desk")
    assert hot_desk["total"] == 2
    assert hot_desk["available"] == 1

    meeting = next(c for c in categories if c["name"] == "Meeting Room")
    assert meeting["total"] == 2
    assert meeting["available"] == 1


async def test_get_seat_summary_all_available(
    service: SeatAvailabilityService, mock_client: MagicMock
):
    """Summary should report zero occupied when all seats are free."""
    all_free = [
        {
            "id": 1,
            "name": "A-1",
            "seat_category_id": 1,
            "is_available": True,
            "seat_categories": {"id": 1, "name": "Hot Desk", "description": "Open area"},
        },
    ]
    builder = MagicMock()
    builder.select.return_value = builder
    builder.execute.return_value = _make_query_result(data=all_free)

    mock_client.table = MagicMock(return_value=builder)

    result = await service.get_seat_summary()

    assert result["total"] == 1
    assert result["available"] == 1
    assert result["occupied"] == 0


# ---------------------------------------------------------------------------
# is_seat_available
# ---------------------------------------------------------------------------


async def test_is_seat_available_true(service: SeatAvailabilityService, mock_client: MagicMock):
    """Should return True when the seat exists and is_available is True."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.execute.return_value = _make_query_result(
        data=[{"id": 1, "name": "A-1", "is_available": True}]
    )

    mock_client.table = MagicMock(return_value=builder)

    result = await service.is_seat_available(1)

    assert result is True


async def test_is_seat_available_false(service: SeatAvailabilityService, mock_client: MagicMock):
    """Should return False when the seat exists but is_available is False."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.execute.return_value = _make_query_result(
        data=[{"id": 2, "name": "A-2", "is_available": False}]
    )

    mock_client.table = MagicMock(return_value=builder)

    result = await service.is_seat_available(2)

    assert result is False


async def test_is_seat_available_nonexistent(
    service: SeatAvailabilityService, mock_client: MagicMock
):
    """Should return False when the seat_id does not exist."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.execute.return_value = _make_query_result(data=[])

    mock_client.table = MagicMock(return_value=builder)

    result = await service.is_seat_available(999)

    assert result is False


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


async def test_supabase_unavailable_get_available_seats():
    """get_available_seats should return [] when Supabase is unavailable."""
    service = SeatAvailabilityService(supabase_client=None)

    with patch(
        "backend.services.seat_availability_service.SeatAvailabilityService._get_supabase",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await service.get_available_seats()
        assert result == []


async def test_supabase_unavailable_get_seat_summary():
    """get_seat_summary should return a default summary when Supabase is unavailable."""
    service = SeatAvailabilityService(supabase_client=None)

    with patch(
        "backend.services.seat_availability_service.SeatAvailabilityService._get_supabase",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await service.get_seat_summary()
        assert result["total"] == 0
        assert result["available"] == 0
        assert result["occupied"] == 0
        assert result["categories"] == []


async def test_supabase_unavailable_is_seat_available():
    """is_seat_available should return False when Supabase is unavailable."""
    service = SeatAvailabilityService(supabase_client=None)

    with patch(
        "backend.services.seat_availability_service.SeatAvailabilityService._get_supabase",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await service.is_seat_available(1)
        assert result is False


async def test_supabase_query_exception(service: SeatAvailabilityService, mock_client: MagicMock):
    """All methods should handle query exceptions gracefully."""
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.execute.side_effect = Exception("Connection reset")

    mock_client.table = MagicMock(return_value=builder)

    assert await service.get_available_seats() == []
    assert await service.is_seat_available(1) is False

    summary = await service.get_seat_summary()
    assert summary["total"] == 0
    assert summary["available"] == 0
