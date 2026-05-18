"""Browser telemetry API routes for Wave 3 voice observability."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.observability.structured_logger import (
    log_frontend_telemetry_event,
    log_voice_round_trip,
)
from backend.utils.structured_logging import generate_request_id, get_request_id

logger = logging.getLogger(__name__)

_SAFE_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_RESERVED_FIELDS = {
    "action",
    "event",
    "request_id",
    "requestId",
    "session_id",
    "sessionId",
}
_ROUND_TRIP_EXPLICIT_FIELDS = {
    "chatMs",
    "durationMs",
    "error_type",
    "errorType",
    "qaMs",
    "source",
    "sttMs",
    "success",
    "telemetry_event",
    "totalMs",
    "ttsMs",
    "turnTotalMs",
}
_MAX_STRING_LENGTH = 1000
_MAX_EXTRA_FIELDS = 32


class VoiceTelemetryRequest(BaseModel):
    """Best-effort telemetry payload accepted from browser voice clients."""

    model_config = ConfigDict(extra="allow")

    event: str = Field(min_length=1, max_length=80)
    session_id: str | None = Field(default=None, max_length=128)
    sessionId: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    requestId: str | None = Field(default=None, max_length=128)
    timestamp: str | None = Field(default=None, max_length=80)
    userAgent: str | None = Field(default=None, max_length=500)

    sttMs: Any = None
    chatMs: Any = None
    qaMs: Any = None
    ttsMs: Any = None
    totalMs: Any = None
    turnTotalMs: Any = None
    durationMs: Any = None
    success: bool | None = None
    errorType: str | None = Field(default=None, max_length=120)
    error_type: str | None = Field(default=None, max_length=120)


def _request_id_from_request(request: Request, body: VoiceTelemetryRequest) -> str:
    return (
        body.request_id
        or body.requestId
        or get_request_id()
        or request.headers.get("X-Request-ID")
        or generate_request_id()
    )


def _session_id_from_body(body: VoiceTelemetryRequest) -> str | None:
    return body.session_id or body.sessionId


def _coerce_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _coerce_success(value: Any, *, error_type: str | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "ok", "success"}:
            return True
        if normalized in {"0", "false", "no", "error", "failed", "failure"}:
            return False
    return error_type is None


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:_MAX_STRING_LENGTH]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:10]]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in list(value.items())[:10]:
            safe[str(key)[:64]] = _safe_value(nested)
        return safe
    return str(value)[:_MAX_STRING_LENGTH]


def _safe_extra_fields(body: VoiceTelemetryRequest) -> dict[str, Any]:
    raw = body.model_dump(exclude_none=True)
    if body.model_extra:
        raw.update(body.model_extra)

    safe: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _RESERVED_FIELDS or not _SAFE_FIELD_NAME.match(key):
            continue
        safe[key] = _safe_value(value)
        if len(safe) >= _MAX_EXTRA_FIELDS:
            break
    return safe


def _log_voice_round_trip_if_present(
    *,
    body: VoiceTelemetryRequest,
    request_id: str,
    session_id: str | None,
    extra: dict[str, Any],
) -> dict[str, Any] | None:
    event = body.event.strip()
    total_ms = (
        _coerce_ms(body.turnTotalMs) or _coerce_ms(body.totalMs) or _coerce_ms(body.durationMs)
    )
    has_round_trip_event = event == "voice_round_trip"
    has_complete_timing = total_ms is not None and any(
        _coerce_ms(value) is not None for value in (body.sttMs, body.chatMs, body.qaMs, body.ttsMs)
    )
    if not has_round_trip_event and not has_complete_timing:
        return None

    error_type = body.error_type or body.errorType
    round_trip_extra = {
        key: value for key, value in extra.items() if key not in _ROUND_TRIP_EXPLICIT_FIELDS
    }
    payload = log_voice_round_trip(
        request_id=request_id,
        session_id=session_id,
        stt_ms=_coerce_ms(body.sttMs),
        chat_ms=(_coerce_ms(body.chatMs) if body.chatMs is not None else _coerce_ms(body.qaMs)),
        tts_ms=_coerce_ms(body.ttsMs),
        total_ms=total_ms,
        success=_coerce_success(body.success, error_type=error_type),
        error_type=error_type,
        source="frontend",
        telemetry_event=event,
        **round_trip_extra,
    )
    return payload


async def voice_telemetry_api(request: Request, body: VoiceTelemetryRequest) -> dict[str, Any]:
    """Record browser voice telemetry without impacting the voice user experience."""

    request_id = _request_id_from_request(request, body)
    session_id = _session_id_from_body(body)
    extra = _safe_extra_fields(body)

    frontend_payload = log_frontend_telemetry_event(
        event=body.event.strip(),
        request_id=request_id,
        session_id=session_id,
        **extra,
    )
    round_trip_payload = _log_voice_round_trip_if_present(
        body=body,
        request_id=request_id,
        session_id=session_id,
        extra=extra,
    )

    logger.debug(
        "voice telemetry accepted: event=%s request_id=%s session_id=%s",
        body.event,
        request_id,
        session_id,
    )
    return {
        "success": True,
        "event": frontend_payload["event"],
        "telemetryEvent": frontend_payload.get("telemetry_event"),
        "voiceRoundTrip": round_trip_payload is not None,
        "requestId": request_id,
    }


def create_router(
    rate_limit: Callable[[str], Callable[[Any], Any]] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["telemetry"])
    endpoint = voice_telemetry_api
    if rate_limit is not None:
        endpoint = rate_limit("120/minute")(endpoint)
    router.add_api_route(
        "/api/telemetry/voice",
        endpoint,
        methods=["POST"],
    )
    return router
