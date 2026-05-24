"""Reception API endpoints.

FastAPI router for the autonomous reception flow.
Handles session lifecycle: start -> status, plus sensor trigger polling.
Conversation turns are advanced by MainWorkflow.invoke_reception_subgraph.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from backend.domain.reception.models import (
    ReceptionSession,
    VisitPurpose,
    VisitorIdentity,
    VisitorType,
)
from backend.utils.reception_templates import get_reception_response
from backend.utils.reception_repository import ReceptionRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

reception_router = APIRouter(prefix="/api/reception", tags=["reception"])

# ---------------------------------------------------------------------------
# In-memory session store (short-lived, bounded to prevent unbounded growth)
# ---------------------------------------------------------------------------

_MAX_SESSIONS = 1000

_active_sessions: OrderedDict[str, ReceptionSession] = OrderedDict()
_session_repository: Optional[ReceptionRepository] = None


def _store_session(session: ReceptionSession) -> None:
    """Cache a session locally, evicting the oldest if at capacity."""
    if session.id in _active_sessions:
        _active_sessions.move_to_end(session.id)
    else:
        if len(_active_sessions) >= _MAX_SESSIONS:
            _active_sessions.popitem(last=False)
    _active_sessions[session.id] = session


def _get_session_repository() -> ReceptionRepository:
    global _session_repository
    if _session_repository is None:
        _session_repository = ReceptionRepository()
    return _session_repository


def _reset_session_storage() -> None:
    """Reset cache and repository singleton for test isolation."""
    global _session_repository
    _session_repository = None
    _active_sessions.clear()
    _sensor_trigger_cooldowns.clear()
    _latest_sensor_events.clear()


def _serialize_session(session: ReceptionSession, *, status: str = "active") -> dict[str, Any]:
    visitor_identity: dict[str, Any] | None = None
    if session.visitor_identity is not None:
        visitor_identity = {
            "visitor_type": session.visitor_identity.visitor_type.value,
            "user_id": session.visitor_identity.user_id,
            "name": session.visitor_identity.name,
            "last_visit_date": (
                session.visitor_identity.last_visit_date.isoformat()
                if session.visitor_identity.last_visit_date is not None
                else None
            ),
            "last_purpose": (
                {
                    "category": session.visitor_identity.last_purpose.category,
                    "detail": session.visitor_identity.last_purpose.detail,
                }
                if session.visitor_identity.last_purpose is not None
                else None
            ),
            "visit_count": session.visitor_identity.visit_count,
        }

    purpose: dict[str, Any] | None = None
    if session.purpose is not None:
        purpose = {
            "category": session.purpose.category,
            "detail": session.purpose.detail,
        }

    return {
        "id": session.id,
        "session_id": session.session_id,
        "stage": session.stage,
        "language": session.language,
        "trigger_type": session.trigger_type,
        "created_at": session.created_at.isoformat(),
        "metadata": session.metadata,
        "purpose": purpose,
        "visitor_identity": visitor_identity,
        "visitor_name": session.visitor_identity.name if session.visitor_identity else None,
        "visitor_type": (
            session.visitor_identity.visitor_type.value if session.visitor_identity else None
        ),
        "status": status,
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (TypeError, ValueError):
        return False
    return True


def _deserialize_session(record: dict[str, Any]) -> ReceptionSession:
    session_data = record.get("session_data") or {}

    visitor_identity_data = session_data.get("visitor_identity") or {}
    last_purpose_data = visitor_identity_data.get("last_purpose")
    last_purpose = None
    if isinstance(last_purpose_data, dict) and last_purpose_data.get("category"):
        last_purpose = VisitPurpose(
            category=last_purpose_data["category"],
            detail=last_purpose_data.get("detail"),
        )

    visitor_identity = None
    visitor_type = (
        visitor_identity_data.get("visitor_type")
        or record.get("visitor_type")
        or ("returning" if record.get("user_id") else None)
    )
    if visitor_type in {"new", "returning"}:
        visitor_identity = VisitorIdentity(
            visitor_type=VisitorType(value=visitor_type),
            user_id=visitor_identity_data.get("user_id", record.get("user_id")),
            name=visitor_identity_data.get("name", record.get("visitor_name")),
            last_visit_date=_parse_datetime(visitor_identity_data.get("last_visit_date")),
            last_purpose=last_purpose,
            visit_count=visitor_identity_data.get("visit_count", 0),
        )

    purpose_data = session_data.get("purpose")
    if isinstance(purpose_data, dict):
        purpose = (
            VisitPurpose(
                category=purpose_data["category"],
                detail=purpose_data.get("detail"),
            )
            if purpose_data.get("category")
            else None
        )
    else:
        purpose = VisitPurpose(category=record["purpose"]) if record.get("purpose") else None

    created_at = _parse_datetime(session_data.get("created_at")) or _parse_datetime(
        record.get("created_at")
    )
    if created_at is None:
        created_at = datetime.now()

    return ReceptionSession(
        id=record["id"],
        session_id=session_data.get("session_id", ""),
        visitor_identity=visitor_identity,
        purpose=purpose,
        stage=session_data.get("stage", record.get("stage", "initiated")),
        language=session_data.get("language", record.get("language", "ja")),
        trigger_type=session_data.get("trigger_type", record.get("trigger_type", "button_press")),
        created_at=created_at,
        metadata=session_data.get("metadata", record.get("metadata", {})),
    )


async def _persist_session(session: ReceptionSession, *, status: str = "active") -> None:
    _store_session(session)
    try:
        await _get_session_repository().store_session(
            session.id, _serialize_session(session, status=status)
        )
    except Exception as exc:
        logger.warning("Reception persistence unavailable; using in-memory fallback: %s", exc)


async def _load_session(
    reception_session_id: str, *, allow_completed: bool = False
) -> Optional[ReceptionSession]:
    record = None
    if _is_uuid(reception_session_id):
        try:
            record = await _get_session_repository().get_session_record(
                reception_session_id,
                include_completed=allow_completed,
            )
        except Exception as exc:
            logger.warning("Reception persistence read failed; using in-memory fallback: %s", exc)
            record = None
    else:
        logger.debug("Skipping reception persistence UUID lookup for non-UUID reception_session_id")

    if record is not None:
        persisted_session = _deserialize_session(record)
        _store_session(persisted_session)
        return persisted_session

    cached_session = _active_sessions.get(reception_session_id)
    if cached_session is not None:
        _active_sessions.move_to_end(reception_session_id)
    return cached_session


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class VisitorIdentityInput(BaseModel):
    user_id: Optional[int] = None
    name: Optional[str] = Field(None, max_length=256)
    visit_count: int = 0
    last_purpose: Optional[dict] = None


class ReceptionStartRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    language: Literal["ja", "en", "zh", "ko"] = "ja"
    trigger_type: Literal[
        "face_detection", "button_press", "wake_word", "nfc", "sensor_trigger"
    ] = "button_press"
    visitor_identity: Optional[VisitorIdentityInput] = None  # From OCR identification


class ReceptionStartResponse(BaseModel):
    reception_session_id: str
    greeting: str
    stage: str


class ReceptionStatusResponse(BaseModel):
    session_id: str
    stage: str
    visitor_type: Optional[str] = None
    purpose: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class SensorTriggerRequest(BaseModel):
    sensor_type: str = Field(..., max_length=50)
    distance_mm: int = Field(..., ge=0)
    device_id: str = Field(..., max_length=100)


class SensorTriggerResponse(BaseModel):
    success: bool
    action: str
    message: Optional[str] = None


class SensorStatusResponse(BaseModel):
    triggered: bool
    device_id: Optional[str] = None
    sensor_type: Optional[str] = None
    distance_mm: Optional[int] = None
    timestamp: Optional[float] = None


# ---------------------------------------------------------------------------
# Per-device rate limiting for sensor triggers
# ---------------------------------------------------------------------------

_sensor_trigger_cooldowns: dict[str, float] = {}
_latest_sensor_events: dict[str, dict[str, Any]] = {}
SENSOR_TRIGGER_RATE_LIMIT_SECONDS = 5
DEFAULT_SENSOR_TRIGGER_EVENT_TTL_SECONDS = 60


def _sensor_trigger_event_ttl_seconds() -> float:
    raw = os.getenv(
        "SENSOR_TRIGGER_EVENT_TTL_SECONDS",
        str(DEFAULT_SENSOR_TRIGGER_EVENT_TTL_SECONDS),
    )
    try:
        value = float(raw)
    except ValueError:
        return float(DEFAULT_SENSOR_TRIGGER_EVENT_TTL_SECONDS)
    return value if value > 0 else float(DEFAULT_SENSOR_TRIGGER_EVENT_TTL_SECONDS)


@reception_router.post("/sensor-trigger", response_model=SensorTriggerResponse)
async def sensor_trigger(request: SensorTriggerRequest) -> SensorTriggerResponse:
    """Receive sensor trigger from M5Stack device."""
    now = time.time()
    last_trigger = _sensor_trigger_cooldowns.get(request.device_id, 0)
    if now - last_trigger < SENSOR_TRIGGER_RATE_LIMIT_SECONDS:
        return SensorTriggerResponse(
            success=False,
            action="rate_limited",
            message=f"Device {request.device_id} is rate limited",
        )
    _sensor_trigger_cooldowns[request.device_id] = now
    _latest_sensor_events[request.device_id] = {
        "device_id": request.device_id,
        "sensor_type": request.sensor_type,
        "distance_mm": request.distance_mm,
        "timestamp": now,
    }
    try:
        await _get_session_repository().store_sensor_event(
            request.device_id, request.sensor_type, request.distance_mm
        )
    except Exception as exc:
        logger.warning("Sensor event persistence failed; in-memory only: %s", exc)

    logger.info(
        "Sensor trigger received: device=%s sensor=%s distance=%dmm",
        request.device_id,
        request.sensor_type,
        request.distance_mm,
    )
    return SensorTriggerResponse(
        success=True,
        action="trigger_received",
        message=f"Sensor trigger from {request.device_id} acknowledged",
    )


@reception_router.get(
    "/sensor-status",
    response_model=SensorStatusResponse,
    response_model_exclude_none=True,
)
async def get_sensor_status(
    device_id: str = Query(default="m5stack-001", max_length=100),
    since: float = Query(default=0),
) -> SensorStatusResponse:
    """Return whether a new sensor trigger exists for polling clients.

    Reads from Supabase first (shared across Cloud Run instances),
    falling back to in-memory storage when the database is unavailable.
    """
    # Try Supabase first (shared across Cloud Run instances)
    try:
        record = await _get_session_repository().get_latest_sensor_event(
            device_id, since_epoch=since
        )
        if record is not None:
            triggered_at = record["triggered_at"]
            if isinstance(triggered_at, str):
                from datetime import datetime as _dt, timezone as _tz

                triggered_at = _dt.fromisoformat(triggered_at).replace(tzinfo=_tz.utc)
            event_epoch = triggered_at.timestamp()
            if event_epoch <= since:
                return SensorStatusResponse(triggered=False)
            return SensorStatusResponse(
                triggered=True,
                device_id=device_id,
                sensor_type=record["sensor_type"],
                distance_mm=record["distance_mm"],
                timestamp=event_epoch,
            )
    except Exception as exc:
        logger.warning("Sensor status DB read failed; falling back to in-memory: %s", exc)

    # Fallback: in-memory
    event = _latest_sensor_events.get(device_id)
    if event is None:
        return SensorStatusResponse(triggered=False)

    if time.time() - float(event["timestamp"]) > _sensor_trigger_event_ttl_seconds():
        _latest_sensor_events.pop(device_id, None)
        return SensorStatusResponse(triggered=False)

    if float(event["timestamp"]) <= since:
        return SensorStatusResponse(triggered=False)

    return SensorStatusResponse(triggered=True, **event)


@reception_router.post("/start", response_model=ReceptionStartResponse)
async def start_reception(request: ReceptionStartRequest) -> ReceptionStartResponse:
    """Initiate a new reception session.

    If ``visitor_identity`` is provided (e.g. from OCR identification),
    the visitor is identified immediately and a personalized greeting
    is generated.
    """
    session = ReceptionSession(
        session_id=request.session_id,
        language=request.language,
        trigger_type=request.trigger_type,
    )

    # If visitor_identity provided (from OCR), identify immediately
    has_resolved_visitor_identity = bool(
        request.visitor_identity and request.visitor_identity.user_id
    )
    if has_resolved_visitor_identity:
        from backend.utils.reception_templates import get_personalized_greeting

        identity = VisitorIdentity(
            visitor_type=VisitorType(value="returning"),
            user_id=request.visitor_identity.user_id,
            name=request.visitor_identity.name,
            visit_count=request.visitor_identity.visit_count,
        )
        session.identify_visitor(identity)

        greeting_result = get_personalized_greeting(
            language=request.language,
            name=request.visitor_identity.name or "",
            last_purpose=request.visitor_identity.last_purpose,
        )
    else:
        greeting_result = get_reception_response(request.language, is_returning=False)

    session.advance_to("greeting")
    await _persist_session(session)

    logger.info(
        "Reception session started: id=%s session_id=%s visitor=%s",
        session.id,
        request.session_id,
        "identified" if has_resolved_visitor_identity else "new",
    )

    return ReceptionStartResponse(
        reception_session_id=session.id,
        greeting=greeting_result.text,
        stage=session.stage,
    )


@reception_router.get("/status/{reception_session_id}", response_model=ReceptionStatusResponse)
async def get_reception_status(
    reception_session_id: str = Path(..., min_length=1, max_length=128),
    session_id: str = Query(..., min_length=1, max_length=128),
) -> ReceptionStatusResponse:
    """Return the current state of a reception session."""
    session = await _load_session(reception_session_id, allow_completed=True)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Reception session not found",
        )

    if session.session_id != session_id:
        raise HTTPException(
            status_code=403,
            detail="Session ID mismatch",
        )

    visitor_type: Optional[str] = None
    purpose_str: Optional[str] = None

    if session.visitor_identity is not None:
        visitor_type = session.visitor_identity.visitor_type.value

    if session.purpose is not None:
        purpose_str = session.purpose.category

    return ReceptionStatusResponse(
        session_id=session.session_id,
        stage=session.stage,
        visitor_type=visitor_type,
        purpose=purpose_str,
    )
