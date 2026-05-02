"""Supabase-backed reception repository implementation.

Provides concrete persistence for ``ReceptionSession`` and visit records
using the Supabase Python client.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, List, Optional

from backend.domain.reception.models import (
    ReceptionSession,
    VisitPurpose,
    VisitorIdentity,
    VisitorType,
)
from backend.domain.reception.repository import ReceptionSessionRepository, VisitRepository

logger = logging.getLogger(__name__)


class SupabaseReceptionSessionRepository(ReceptionSessionRepository):
    """Supabase-backed implementation of ``ReceptionSessionRepository``.

    Args:
        supabase_client: Optional pre-configured client.  Resolved lazily
            when ``None``.
    """

    def __init__(self, supabase_client: Any = None) -> None:
        self._supabase = supabase_client

    async def _get_client(self) -> Any:
        """Return the Supabase client, resolving lazily if needed."""
        if self._supabase:
            return self._supabase
        from backend.utils.supabase_helper import get_supabase_client

        return get_supabase_client()

    async def save(self, session: ReceptionSession) -> None:
        """Persist a reception session via upsert.

        Args:
            session: The ``ReceptionSession`` aggregate to persist.

        Raises:
            Exception: If the Supabase upsert fails.
        """
        client = await self._get_client()
        data = {
            "id": session.id,
            "session_id": session.session_id,
            "visitor_id": None,  # Set from context
            "user_id": session.visitor_identity.user_id if session.visitor_identity else None,
            "stage": session.stage,
            "purpose": session.purpose.category if session.purpose else None,
            "language": session.language,
            "trigger_type": session.trigger_type,
            "updated_at": datetime.now().isoformat(),
        }
        try:
            client.table("reception_sessions").upsert(data).execute()
        except Exception as e:
            logger.error("Failed to save reception session: %s", e)
            raise

    async def find_by_id(self, session_id: str) -> Optional[ReceptionSession]:
        """Find a reception session by its primary key.

        Args:
            session_id: The UUID primary key of the reception session.

        Returns:
            A ``ReceptionSession`` or ``None``.
        """
        try:
            uuid.UUID(session_id)
        except (TypeError, ValueError):
            logger.debug("Skipping reception session UUID lookup for non-UUID session_id")
            return None

        client = await self._get_client()
        try:
            result = client.table("reception_sessions").select("*").eq("id", session_id).execute()
            if result.data:
                return self._to_domain(result.data[0])
        except Exception as e:
            logger.warning("Failed to find reception session: %s", e)
        return None

    async def find_by_conversation_session(
        self, conversation_session_id: str
    ) -> Optional[ReceptionSession]:
        """Find the most recent reception session for a conversation.

        Args:
            conversation_session_id: The UUID of the related conversation session.

        Returns:
            A ``ReceptionSession`` or ``None``.
        """
        try:
            uuid.UUID(conversation_session_id)
        except (TypeError, ValueError):
            logger.debug("Skipping reception session conversation lookup for non-UUID session_id")
            return None

        client = await self._get_client()
        try:
            result = (
                client.table("reception_sessions")
                .select("*")
                .eq("session_id", conversation_session_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return self._to_domain(result.data[0])
        except Exception as e:
            logger.warning("Failed to find reception session by conversation: %s", e)
        return None

    @staticmethod
    def _to_domain(row: dict) -> ReceptionSession:
        """Map a database row to a ``ReceptionSession`` domain object."""
        visitor_identity: Optional[VisitorIdentity] = None
        if row.get("user_id"):
            visitor_identity = VisitorIdentity(
                visitor_type=VisitorType(value="returning"),
                user_id=row["user_id"],
            )

        purpose: Optional[VisitPurpose] = None
        if row.get("purpose"):
            purpose = VisitPurpose(category=row["purpose"])

        return ReceptionSession(
            id=row["id"],
            session_id=row.get("session_id", ""),
            visitor_identity=visitor_identity,
            purpose=purpose,
            stage=row.get("stage", "initiated"),
            language=row.get("language", "ja"),
            trigger_type=row.get("trigger_type", "button_press"),
        )


class SupabaseVisitRepository(VisitRepository):
    """Supabase-backed implementation of ``VisitRepository``.

    Args:
        supabase_client: Optional pre-configured client.  Resolved lazily
            when ``None``.
    """

    def __init__(self, supabase_client: Any = None) -> None:
        self._supabase = supabase_client

    async def _get_client(self) -> Any:
        """Return the Supabase client, resolving lazily if needed."""
        if self._supabase:
            return self._supabase
        from backend.utils.supabase_helper import get_supabase_client

        return get_supabase_client()

    async def record_visit(self, session: ReceptionSession) -> str:
        """Create a visit record from a completed reception session.

        Args:
            session: The ``ReceptionSession`` to record.

        Returns:
            The generated visit UUID string.

        Raises:
            Exception: If the Supabase insert fails.
        """
        client = await self._get_client()
        visit_id = str(uuid.uuid4())
        data = {
            "id": visit_id,
            "session_id": session.session_id,
            "user_id": session.visitor_identity.user_id if session.visitor_identity else None,
            "purpose": session.purpose.category if session.purpose else "other",
            "purpose_detail": session.purpose.detail if session.purpose else None,
            "visitor_type": (
                session.visitor_identity.visitor_type.value if session.visitor_identity else "new"
            ),
        }
        try:
            client.table("visits").insert(data).execute()
        except Exception as e:
            logger.error("Failed to record visit: %s", e)
            raise
        return visit_id

    async def get_recent_visits(self, user_id: int, limit: int = 5) -> List[dict]:
        """Return recent visit records for a given user.

        Args:
            user_id: The database user ID.
            limit: Maximum number of records to return.

        Returns:
            A list of visit dicts ordered most-recent-first.
        """
        client = await self._get_client()
        try:
            result = (
                client.table("visits")
                .select("*")
                .eq("user_id", user_id)
                .order("started_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning("Failed to get recent visits: %s", e)
            return []
