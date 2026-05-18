"""Memory helper observability constants and logging helpers."""

import time
from typing import Any

_AGENT_MEMORY_SESSION_COLUMN = "value->>sessionId"
_DURATION_EVENT_ALIASES = {
    "memory_loader_get_recent_messages_duration_ms": (
        "memory_loader_get_recent_messages",
        "memory_loader_get_recent_messages_duration_ms",
    ),
    "memory_loader_get_previous_request_type_duration_ms": (
        "memory_loader_get_previous_request_type",
        "memory_loader_get_previous_request_type_duration_ms",
    ),
    "memory_cleanup_session_duration_ms": (
        "memory_cleanup_session",
        "memory_cleanup_session_duration_ms",
    ),
}


def _log_memory_event_safely(event: str, **fields: Any) -> None:
    try:
        from backend.observability.structured_logger import log_memory_event

        alias = _DURATION_EVENT_ALIASES.get(event)
        if alias:
            alias_event, duration_field = alias
            if "duration_ms" in fields:
                fields.setdefault(duration_field, fields["duration_ms"])
            log_memory_event(event=alias_event, **fields)
            log_memory_event(event=event, **fields)
            return

        log_memory_event(event=event, **fields)
    except Exception:
        pass


def _duration_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))
