"""Visitor Identification Service - Infrastructure layer for visitor lookup.

Identifies visitors using persisted visit history and returns structured
identity information to the reception flow.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VisitorIdentificationService:
    """Identifies visitors using multiple signals.

    Resolution priority (highest confidence first):
        1. visitor_id -> visits table lookup
        2. LangGraph Store long-term memories (existing behaviour)
        3. None -> new visitor

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
    # Public identification methods
    # ------------------------------------------------------------------

    async def identify_by_nfc(self, nfc_id: str) -> Optional[Dict[str, Any]]:
        """Return no identity until the NFC schema is formally introduced.

        Production migrations do not define an ``nfcs`` table. Querying a
        speculative table makes the reception path look more capable than it
        is, so NFC recognition intentionally degrades to a non-personalized
        visitor until a reviewed NFC schema is added.
        """
        if nfc_id:
            logger.info("NFC lookup skipped until NFC schema is available")
        return None

    async def identify_by_visitor_id(self, visitor_id: str) -> Optional[Dict[str, Any]]:
        """Look up a visitor by frontend-generated persistent visitor_id.

        Queries the ``visits`` table for prior visits associated with this
        visitor_id and returns summary information.

        Args:
            visitor_id: UUID string generated and persisted by the frontend.

        Returns:
            A dict with visit history summary, or ``None`` when the visitor
            has no prior visits or Supabase is unavailable.
        """
        client = await self._get_supabase()
        if not client:
            return None
        try:
            result = (
                client.table("visits")
                .select("*")
                .eq("visitor_id", visitor_id)
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                visit = result.data[0]
                return {
                    "visitor_type": "returning",
                    "last_visit_date": visit.get("started_at"),
                    "last_purpose": visit.get("purpose"),
                    "last_purpose_detail": visit.get("purpose_detail"),
                    "visit_count": await self._count_visits(visitor_id),
                }
        except Exception as e:
            logger.warning("Visitor ID lookup failed: %s", e)
        return None

    async def get_recent_visits(
        self,
        visitor_id: Optional[str] = None,
        user_id: Optional[int] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return recent visit records for a visitor or user.

        At least one of ``visitor_id`` or ``user_id`` must be provided.

        Args:
            visitor_id: Frontend-generated persistent visitor ID.
            user_id: Database user ID.
            limit: Maximum number of records to return.

        Returns:
            A list of visit dicts ordered by most recent first.
        """
        client = await self._get_supabase()
        if not client:
            return []
        try:
            query = client.table("visits").select("*").order("started_at", desc=True).limit(limit)
            if user_id:
                query = query.eq("user_id", user_id)
            elif visitor_id:
                query = query.eq("visitor_id", visitor_id)
            else:
                return []
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.warning("Recent visits lookup failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_visit_profile_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a returning-visitor summary from the ``visits`` table."""
        client = await self._get_supabase()
        if not client:
            return None
        try:
            result = (
                client.table("visits")
                .select("*")
                .eq("user_id", user_id)
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                visit = result.data[0]
                visit_count = await self._count_visits_by_user(user_id)
                profile = {
                    "visitor_type": "returning",
                    "user_id": user_id,
                    "last_visit_date": visit.get("started_at"),
                    "last_purpose": visit.get("purpose"),
                    "last_purpose_detail": visit.get("purpose_detail"),
                    "visit_count": visit_count,
                }
                metadata = visit.get("metadata") if isinstance(visit.get("metadata"), dict) else {}
                name = metadata.get("visitor_name") or metadata.get("name")
                if name:
                    profile["name"] = name
                return profile
        except Exception as e:
            logger.warning("User visit lookup failed: %s", e)
        return None

    async def _count_visits(self, visitor_id: str) -> int:
        """Count total visits for a given ``visitor_id``."""
        client = await self._get_supabase()
        if not client:
            return 0
        try:
            result = (
                client.table("visits")
                .select("id", count="exact")
                .eq("visitor_id", visitor_id)
                .execute()
            )
            return result.count or 0
        except Exception:
            return 0

    async def _count_visits_by_user(self, user_id: int) -> int:
        """Count total visits for a given ``user_id``."""
        client = await self._get_supabase()
        if not client:
            return 0
        try:
            result = (
                client.table("visits").select("id", count="exact").eq("user_id", user_id).execute()
            )
            return result.count or 0
        except Exception:
            return 0
