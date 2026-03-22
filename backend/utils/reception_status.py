"""Reception status checker for orchestrator integration.

Provides a lightweight check to determine if a session has completed
the reception flow, used by MainWorkflow to gate agent routing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_repository: Optional[Any] = None


def _get_repository() -> Any:
    """Lazy-load ReceptionRepository singleton."""
    global _repository
    if _repository is None:
        from backend.utils.reception_repository import ReceptionRepository

        _repository = ReceptionRepository()
    return _repository


async def check_reception_status(session_id: str) -> dict[str, Any]:
    """Check if a session has completed reception.

    Used by the orchestrator node as a lightweight pre-check before
    LLM routing. Fails open (returns completed=True) on errors so
    that chat continues uninterrupted.

    Args:
        session_id: The conversation session ID to look up.

    Returns:
        dict with keys:
        - completed: bool -- True if reception is done
        - stage: str -- current reception stage (or "none" if no session)
        - reception_session_id: Optional[str]
        - visitor_identity: Optional[dict]
        - purpose: Optional[dict]
    """
    if not session_id:
        return {"completed": False, "stage": "none"}

    try:
        repo = _get_repository()
        record = await repo.get_active_session_by_conversation_id(session_id)

        if record is None:
            return {"completed": False, "stage": "none"}

        session_data = record.get("session_data", {})
        stage = session_data.get("stage", record.get("stage", "initiated"))

        return {
            "completed": stage == "completed",
            "stage": stage,
            "reception_session_id": record.get("id"),
            "visitor_identity": session_data.get("visitor_identity"),
            "purpose": session_data.get("purpose"),
        }
    except Exception as exc:
        logger.warning("Reception status check failed: %s", exc)
        # Fail open -- allow chat to proceed without reception
        return {"completed": True, "stage": "unknown"}
