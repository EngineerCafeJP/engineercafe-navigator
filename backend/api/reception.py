"""Reception API endpoints.

FastAPI router for the autonomous reception flow.
Handles session lifecycle: start -> respond -> status.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
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


def _store_session(session: ReceptionSession) -> None:
    """Store a session, evicting the oldest if at capacity."""
    if session.id in _active_sessions:
        _active_sessions.move_to_end(session.id)
    else:
        if len(_active_sessions) >= _MAX_SESSIONS:
            _active_sessions.popitem(last=False)
    _active_sessions[session.id] = session


# ---------------------------------------------------------------------------
# Purpose keyword classifier (lightweight, no LLM required for basic cases)
# ---------------------------------------------------------------------------

_PURPOSE_KEYWORDS: dict[str, list[str]] = {
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


class ReceptionStartRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    language: Literal["ja", "en", "zh", "ko"] = "ja"
    trigger_type: Literal["face_detection", "button_press", "wake_word", "nfc"] = "button_press"


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
    """Initiate a new reception session."""
    session = ReceptionSession(
        session_id=request.session_id,
        language=request.language,
        trigger_type=request.trigger_type,
    )
    session.advance_to("greeting")

    _store_session(session)

    greeting_result = get_reception_response(request.language, is_returning=False)
    logger.info(
        "Reception session started: id=%s session_id=%s language=%s",
        session.id,
        request.session_id,
        request.language,
    )

    return ReceptionStartResponse(
        reception_session_id=session.id,
        greeting=greeting_result.text,
        stage=session.stage,
    )


@reception_router.post("/respond", response_model=ReceptionRespondResponse)
async def respond_reception(request: ReceptionRespondRequest) -> ReceptionRespondResponse:
    """Continue the reception conversation."""
    session = _active_sessions.get(request.reception_session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Reception session not found: {request.reception_session_id}",
        )
    _active_sessions.move_to_end(request.reception_session_id)

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

        followup_result = get_purpose_followup(language, category)
        return ReceptionRespondResponse(
            response=followup_result.text,
            stage=session.stage,
            purpose={"category": category, "detail": request.message},
            next_action="route_to_agent",
        )

    if current_stage == "routing":
        session.advance_to("completed")

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


@reception_router.get("/status/{reception_session_id}", response_model=ReceptionStatusResponse)
async def get_reception_status(reception_session_id: str) -> ReceptionStatusResponse:
    """Return the current state of a reception session."""
    session = _active_sessions.get(reception_session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Reception session not found: {reception_session_id}",
        )
    _active_sessions.move_to_end(reception_session_id)

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
