"""Persistence helpers for reception API session state."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, TypeVar

from supabase import Client

from backend.utils.supabase_helper import get_supabase_client

logger = logging.getLogger(__name__)
_T = TypeVar("_T")


def _db_timeout_seconds() -> float:
    raw = os.getenv("RECEPTION_DB_TIMEOUT_SECONDS", "3.0")
    try:
        value = float(raw)
    except ValueError:
        return 3.0
    return value if value > 0 else 3.0


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (TypeError, ValueError):
        return False
    return True


async def _run_db_call(call: Callable[[], _T]) -> _T:
    """Run the synchronous Supabase client without blocking the event loop."""
    return await asyncio.wait_for(asyncio.to_thread(call), timeout=_db_timeout_seconds())


class ReceptionRepository:
    """Persist reception sessions in Supabase."""

    def __init__(self, supabase: Client | None = None):
        self._supabase = supabase

    async def _get_client(self) -> Client:
        if self._supabase is not None:
            return self._supabase
        return get_supabase_client()

    async def store_session(self, session_id: str, data: dict[str, Any]) -> None:
        client = await self._get_client()
        now = datetime.now(timezone.utc)

        visitor_identity = data.get("visitor_identity") or {}
        purpose = data.get("purpose") or {}
        metadata = data.get("metadata") or {}

        payload = {
            "id": session_id,
            "session_id": data.get("session_id"),
            "user_id": visitor_identity.get("user_id"),
            "stage": data.get("stage", "initiated"),
            "purpose": purpose.get("category") if isinstance(purpose, dict) else purpose,
            "language": data.get("language", "ja"),
            "trigger_type": data.get("trigger_type", "button_press"),
            "metadata": metadata,
            "session_data": data,
            "visitor_name": visitor_identity.get("name") or data.get("visitor_name"),
            "visitor_type": visitor_identity.get("visitor_type") or data.get("visitor_type"),
            "status": data.get("status", "active"),
            "created_at": data.get("created_at", now.isoformat()),
            "updated_at": now.isoformat(),
            "expires_at": data.get("expires_at", (now + timedelta(hours=24)).isoformat()),
        }

        await _run_db_call(lambda: client.table("reception_sessions").upsert(payload).execute())

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await self.get_session_record(session_id)

    async def get_session_record(
        self, session_id: str, *, include_completed: bool = False
    ) -> dict[str, Any] | None:
        if not _is_uuid(session_id):
            logger.debug("Skipping reception_sessions UUID lookup for non-UUID session_id")
            return None
        client = await self._get_client()
        query = client.table("reception_sessions").select("*").eq("id", session_id)
        if include_completed:
            query = query.in_("status", ["active", "completed"])
        else:
            query = query.eq("status", "active")

        result = await _run_db_call(lambda: query.limit(1).execute())
        if result.data:
            return result.data[0]
        return None

    async def get_session_by_conversation_id(self, session_id: str) -> Optional[dict[str, Any]]:
        """Look up the most recent reception session for a conversation session_id.

        Unlike ``get_session_record`` which queries by the reception session's
        own ``id``, this method queries by the conversation ``session_id`` column.
        Both active and completed sessions are returned so that the orchestrator
        can recognise that a session has already finished reception.

        Args:
            session_id: The conversation session ID (any string format).

        Returns:
            The most recent reception session record, or ``None``.
        """
        if not session_id or not session_id.strip():
            return None
        # Do NOT validate as UUID -- session_id can be any string format
        # (e.g. "voice-session-*" from the browser).
        try:
            client = await self._get_client()
            result = await _run_db_call(
                lambda: client.table("reception_sessions")
                .select("*")
                .eq("session_id", session_id)
                .in_("status", ["active", "completed"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as exc:
            logger.warning("Failed to look up reception session: %s", exc)
            return None

    async def get_active_session_by_conversation_id(
        self, session_id: str
    ) -> Optional[dict[str, Any]]:
        """Backward-compatible alias for ``get_session_by_conversation_id``."""
        return await self.get_session_by_conversation_id(session_id)

    async def complete_session(self, session_id: str) -> None:
        if not _is_uuid(session_id):
            logger.debug("Skipping reception_sessions completion for non-UUID session_id")
            return
        client = await self._get_client()
        await _run_db_call(
            lambda: client.table("reception_sessions")
            .update({"status": "completed"})
            .eq("id", session_id)
            .execute()
        )

    async def list_active_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        await self.cleanup_expired()

        client = await self._get_client()
        result = await _run_db_call(
            lambda: client.table("reception_sessions")
            .select("*")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    async def cleanup_expired(self) -> int:
        client = await self._get_client()
        cutoff = datetime.now(timezone.utc).isoformat()
        result = await _run_db_call(
            lambda: client.table("reception_sessions")
            .update({"status": "expired"})
            .eq("status", "active")
            .lt("expires_at", cutoff)
            .execute()
        )
        return len(result.data) if result.data else 0

    # ------------------------------------------------------------------
    # Sensor events
    # ------------------------------------------------------------------

    async def store_sensor_event(self, device_id: str, sensor_type: str, distance_mm: int) -> None:
        """Insert a new sensor trigger event into ``sensor_events``."""
        client = await self._get_client()
        await _run_db_call(
            lambda: client.table("sensor_events")
            .insert(
                {
                    "device_id": device_id,
                    "sensor_type": sensor_type,
                    "distance_mm": distance_mm,
                }
            )
            .execute()
        )

    async def get_latest_sensor_event(
        self, device_id: str, since_epoch: float = 0
    ) -> Optional[dict[str, Any]]:
        """Return the most recent sensor event for *device_id*.

        If *since_epoch* is provided (UNIX seconds), only events after that
        timestamp are considered.  Returns ``None`` when no matching row
        exists or the event is older than 30 seconds.
        """
        client = await self._get_client()
        query = (
            client.table("sensor_events")
            .select("device_id, sensor_type, distance_mm, triggered_at")
            .eq("device_id", device_id)
            .order("triggered_at", desc=True)
            .limit(1)
        )

        if since_epoch > 0:
            since_dt = datetime.fromtimestamp(since_epoch, tz=timezone.utc).isoformat()
            query = query.gt("triggered_at", since_dt)

        result = await _run_db_call(lambda: query.execute())
        if not result.data:
            return None

        row = result.data[0]
        triggered_at = row["triggered_at"]
        if isinstance(triggered_at, str):
            triggered_at = datetime.fromisoformat(triggered_at.replace("Z", "+00:00"))

        if triggered_at < datetime.now(timezone.utc) - timedelta(seconds=30):
            return None

        row["triggered_at"] = triggered_at
        return row
