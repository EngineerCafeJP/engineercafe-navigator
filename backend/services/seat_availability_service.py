"""Seat Availability Service - Read-only access to reception seat data.

Queries the ``seats`` and ``seat_categories`` tables managed by the
engineercafe-reception-2025 system.  This service is strictly READ ONLY
and never mutates the underlying data.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SeatAvailabilityService:
    """Provides seat availability information from the shared Supabase project.

    The reception system (engineercafe-reception-2025) owns the ``seats`` and
    ``seat_categories`` tables.  This service reads them to power Navigator
    queries such as "Are there any free desks?".

    Args:
        supabase_client: Optional pre-configured Supabase client.  When
            ``None`` the client is resolved lazily via ``supabase_helper``.
    """

    def __init__(self, supabase_client: Any = None) -> None:
        self._supabase = supabase_client

    async def _get_supabase(self) -> Any:
        """Return the Supabase client, resolving lazily if needed."""
        if self._supabase:
            return self._supabase
        try:
            from backend.utils.supabase_helper import get_supabase_client

            return get_supabase_client()
        except Exception as e:
            logger.warning("Supabase client unavailable: %s", e)
            return None

    # ------------------------------------------------------------------
    # Public query methods (READ ONLY)
    # ------------------------------------------------------------------

    async def get_available_seats(self) -> list[dict[str, Any]]:
        """Return a list of currently available seats with category info.

        Returns:
            A list of seat dicts for seats where ``is_available`` is True.
            Returns an empty list when Supabase is unavailable or on error.
        """
        client = await self._get_supabase()
        if not client:
            return []
        try:
            result = (
                client.table("seats")
                .select(
                    "id, name, seat_category_id, is_available,"
                    " seat_categories(id, name, description)"
                )
                .eq("is_available", True)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning("Failed to fetch available seats: %s", e)
            return []

    async def get_seat_summary(self) -> dict[str, Any]:
        """Return an aggregate summary of seat availability.

        Returns:
            A dict containing:
                - ``total``: Total number of seats.
                - ``available``: Number of available seats.
                - ``occupied``: Number of occupied seats.
                - ``categories``: Per-category breakdown with name, total,
                  and available counts.
            Returns zero-value defaults on error.
        """
        default: dict[str, Any] = {
            "total": 0,
            "available": 0,
            "occupied": 0,
            "categories": [],
        }
        client = await self._get_supabase()
        if not client:
            return default
        try:
            result = (
                client.table("seats")
                .select(
                    "id, name, seat_category_id, is_available,"
                    " seat_categories(id, name, description)"
                )
                .execute()
            )
            seats = result.data or []
            if not seats:
                return default

            total = len(seats)
            available = sum(1 for s in seats if s.get("is_available"))
            occupied = total - available

            # Build per-category breakdown
            cat_map: dict[str, dict[str, Any]] = {}
            for seat in seats:
                cat_info = seat.get("seat_categories") or {}
                cat_name = cat_info.get("name", "Unknown")
                if cat_name not in cat_map:
                    cat_map[cat_name] = {"name": cat_name, "total": 0, "available": 0}
                cat_map[cat_name]["total"] += 1
                if seat.get("is_available"):
                    cat_map[cat_name]["available"] += 1

            return {
                "total": total,
                "available": available,
                "occupied": occupied,
                "categories": list(cat_map.values()),
            }
        except Exception as e:
            logger.warning("Failed to fetch seat summary: %s", e)
            return default

    async def is_seat_available(self, seat_id: int) -> bool:
        """Check whether a specific seat is available.

        Args:
            seat_id: The database ID of the seat to check.

        Returns:
            ``True`` if the seat exists and is available, ``False`` otherwise
            (including when Supabase is unavailable or on error).
        """
        client = await self._get_supabase()
        if not client:
            return False
        try:
            result = client.table("seats").select("id, is_available").eq("id", seat_id).execute()
            if result.data:
                return bool(result.data[0].get("is_available", False))
            return False
        except Exception as e:
            logger.warning("Failed to check seat %s availability: %s", seat_id, e)
            return False
