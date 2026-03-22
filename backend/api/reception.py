"""Reception API endpoints.

FastAPI router for the autonomous reception flow.
Handles session lifecycle: start -> respond -> complete -> status.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from backend.domain.reception.models import (
    ReceptionSession,
    VisitPurpose,
    VisitorIdentity,
    VisitorType,
)
from backend.utils.reception_templates import (
    get_purpose_followup,
    get_purpose_hearing_prompt,
    get_reception_response,
)
from backend.utils.reception_repository import ReceptionRepository

if TYPE_CHECKING:
    from backend.services.reception_handoff_service import ReceptionHandoffService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton for handoff service
# ---------------------------------------------------------------------------

_handoff_service: Optional["ReceptionHandoffService"] = None  # noqa: F821


def _get_handoff_service() -> "ReceptionHandoffService":  # noqa: F821
    """Return a module-level singleton, created on first use."""
    global _handoff_service
    if _handoff_service is None:
        from backend.services.reception_handoff_service import ReceptionHandoffService

        _handoff_service = ReceptionHandoffService()
    return _handoff_service


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
    try:
        record = await _get_session_repository().get_session_record(
            reception_session_id,
            include_completed=allow_completed,
        )
    except Exception as exc:
        logger.warning("Reception persistence read failed; using in-memory fallback: %s", exc)
        record = None

    if record is not None:
        session = _deserialize_session(record)
        _store_session(session)
        return session

    session = _active_sessions.get(reception_session_id)
    if session is not None:
        _active_sessions.move_to_end(reception_session_id)
    return session


# ---------------------------------------------------------------------------
# Purpose keyword classifier (lightweight, no LLM required for basic cases)
# ---------------------------------------------------------------------------

_PURPOSE_KEYWORDS: dict[str, list[str]] = {
    "tour": [
        "tour",
        "guide",
        "guided",
        "guidance",
        "見学",
        "ツアー",
        "案内",
        "館内",
    ],
    "facility_use": [
        "cowork",
        "coworking",
        "コワーキング",
        "デスク",
        "facility",
        "room",
        "space",
        "施設",
        "利用",
        "部屋",
        "スペース",
    ],
    "event_participation": [
        "event",
        "seminar",
        "workshop",
        "meetup",
        "イベント",
        "セミナー",
        "ワークショップ",
        "勉強会",
    ],
    "consultation": [
        "inquiry",
        "question",
        "info",
        "ask",
        "consult",
        "問い合わせ",
        "質問",
        "相談",
        "聞きたい",
    ],
}


def _classify_purpose(message: str) -> Optional[str]:
    """Classify a visitor's message into a purpose category."""
    lower = message.lower()
    for category, keywords in _PURPOSE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return None


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
    trigger_type: Literal["face_detection", "button_press", "wake_word", "nfc"] = "button_press"
    visitor_identity: Optional[VisitorIdentityInput] = None  # From OCR identification


class ReceptionStartResponse(BaseModel):
    reception_session_id: str
    greeting: str
    stage: str


class ReceptionRespondRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    reception_session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)


class ReceptionRespondResponse(BaseModel):
    response: str
    stage: str
    purpose: Optional[dict] = None
    next_action: Optional[str] = None


class ReceptionCompleteRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    reception_session_id: str = Field(min_length=1, max_length=128)


class ReceptionCompleteResponse(BaseModel):
    response_text: str
    target_agent: str
    requires_staff: bool
    purpose_category: str
    action_type: str
    action_data: Optional[dict] = None


class ReceptionStatusResponse(BaseModel):
    session_id: str
    stage: str
    visitor_type: Optional[str] = None
    purpose: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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
    if request.visitor_identity and request.visitor_identity.user_id:
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
        "identified" if request.visitor_identity else "new",
    )

    return ReceptionStartResponse(
        reception_session_id=session.id,
        greeting=greeting_result.text,
        stage=session.stage,
    )


@reception_router.post("/respond", response_model=ReceptionRespondResponse)
async def respond_reception(request: ReceptionRespondRequest) -> ReceptionRespondResponse:
    """Continue the reception conversation."""
    session = await _load_session(request.reception_session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Reception session not found",
        )

    if session.session_id != request.session_id:
        raise HTTPException(
            status_code=403,
            detail="Session ID mismatch",
        )

    language = session.language
    current_stage = session.stage

    if current_stage == "greeting":
        identity = VisitorIdentity(visitor_type=VisitorType(value="new"))
        session.identify_visitor(identity)
        session.advance_to("purpose_hearing")
        await _persist_session(session)

        prompt_result = get_purpose_hearing_prompt(language)

        return ReceptionRespondResponse(
            response=prompt_result.text,
            stage=session.stage,
            next_action="ask_purpose",
        )

    if current_stage == "purpose_hearing":
        category = _classify_purpose(request.message)
        if category is None:
            prompt_result = get_purpose_hearing_prompt(language)
            return ReceptionRespondResponse(
                response=prompt_result.text,
                stage=session.stage,
                next_action="clarify_purpose",
            )

        purpose = VisitPurpose(category=category, detail=request.message)
        session.set_purpose(purpose)
        session.advance_to("routing")
        await _persist_session(session)

        followup_result = get_purpose_followup(language, category)
        return ReceptionRespondResponse(
            response=followup_result.text,
            stage=session.stage,
            purpose={"category": category, "detail": request.message},
            next_action="route_to_agent",
        )

    if current_stage == "routing":
        session.advance_to("completed")
        await _persist_session(session, status="completed")

        routing_messages = {
            "ja": "スタッフをお呼びします。少々お待ちください。",
            "en": "I'll call a staff member for you. Please wait a moment.",
        }
        return ReceptionRespondResponse(
            response=routing_messages.get(language, routing_messages["ja"]),
            stage=session.stage,
            next_action="completed",
        )

    raise HTTPException(
        status_code=409,
        detail=f"Cannot respond in stage: {session.stage}",
    )


@reception_router.post("/complete", response_model=ReceptionCompleteResponse)
async def complete_reception(
    request: ReceptionCompleteRequest,
) -> ReceptionCompleteResponse:
    """Complete the reception flow and prepare handoff to MainWorkflow.

    Called when the session is in the 'routing' stage. Runs purpose-specific
    preprocessing and returns the workflow state for MainWorkflow invocation.
    """
    session = await _load_session(request.reception_session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Reception session not found",
        )

    if session.session_id != request.session_id:
        raise HTTPException(
            status_code=403,
            detail="Session ID mismatch",
        )

    if session.stage != "routing":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Session must be in 'routing' stage to complete, "
                f"current stage: {session.stage}"
            ),
        )

    # Advance stage BEFORE async work to prevent duplicate processing
    # from concurrent requests (race condition guard).
    session.advance_to("completed")
    await _persist_session(session, status="completed")

    handoff_service = _get_handoff_service()
    try:
        result = await handoff_service.prepare_handoff(session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Invoke MainWorkflow with the handoff to get an agent response
    agent_response: Optional[str] = None
    try:
        from backend.workflows.main_workflow import MainWorkflow

        workflow = MainWorkflow()
        agent_result = await workflow.ainvoke_from_reception(result)
        agent_response = agent_result.get("answer")
    except Exception as exc:
        logger.warning("MainWorkflow invocation after reception failed: %s", exc)
        # Not critical -- the handoff info is still returned

    logger.info(
        "Reception completed: id=%s target=%s requires_staff=%s",
        session.id,
        result.target_agent,
        result.requires_staff,
    )

    return ReceptionCompleteResponse(
        response_text=agent_response or result.purpose_flow.response_text,
        target_agent=result.target_agent,
        requires_staff=result.requires_staff,
        purpose_category=session.purpose.category,
        action_type=result.purpose_flow.action_type,
        action_data=result.purpose_flow.action_data,
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
