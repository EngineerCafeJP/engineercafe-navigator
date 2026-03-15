"""Persistence helpers for reception API session state."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from supabase import Client

from backend.utils.supabase_helper import get_supabase_client

logger = logging.getLogger(__name__)


def _parse_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    try:
        return str(UUID(value))
    except ValueError:
        return None


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
            "session_id": _parse_uuid(data.get("session_id")),
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

        client.table("reception_sessions").upsert(payload).execute()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await self.get_session_record(session_id)

    async def get_session_record(
        self, session_id: str, *, include_completed: bool = False
    ) -> dict[str, Any] | None:
        client = await self._get_client()
        query = client.table("reception_sessions").select("*").eq("id", session_id)
        if include_completed:
            query = query.in_("status", ["active", "completed"])
        else:
            query = query.eq("status", "active")

        result = query.limit(1).execute()
        if result.data:
            return result.data[0]
        return None

    async def complete_session(self, session_id: str) -> None:
        client = await self._get_client()
        client.table("reception_sessions").update({"status": "completed"}).eq(
            "id", session_id
        ).execute()

    async def list_active_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        await self.cleanup_expired()

        client = await self._get_client()
        result = (
            client.table("reception_sessions")
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
        result = (
            client.table("reception_sessions")
            .update({"status": "expired"})
            .eq("status", "active")
            .lt("expires_at", cutoff)
            .execute()
        )
        return len(result.data) if result.data else 0
