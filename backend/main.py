"""
Engineer Cafe Navigator Backend
FastAPIアプリケーションとLangGraphエージェントの統合
"""

import hmac
import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.tools.calendar_service import CalendarService, TimeRange
from backend.utils.structured_logging import (
    request_id_var,
    generate_request_id,
    setup_structured_logging,
)
from backend.utils.session_task_manager import get_session_task_manager

logger = logging.getLogger(__name__)


_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """X-Request-ID ヘッダーの生成/伝播"""

    async def dispatch(self, request: Request, call_next):
        raw_id = request.headers.get("X-Request-ID")
        if raw_id and _VALID_REQUEST_ID.match(raw_id):
            req_id = raw_id
        else:
            req_id = generate_request_id()
        token = request_id_var.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_var.reset(token)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """リクエストごとのduration_ms記録"""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning(
                "Request %s %s failed after %.2fms",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        logger.info(
            "Request %s %s completed in %.2fms",
            request.method,
            request.url.path,
            duration_ms,
        )
        return response


class TokenTrackerMiddleware(BaseHTTPMiddleware):
    """Per-request token usage tracking"""

    async def dispatch(self, request: Request, call_next):
        from backend.utils.token_tracker import get_token_tracker, reset_token_tracker

        reset_token_tracker()  # Clean state for each request
        try:
            response = await call_next(request)
            # Log token summary for this request
            tracker = get_token_tracker()
            if tracker.total_tokens > 0:
                logger.info(
                    "Token usage: %d tokens, $%.6f estimated cost",
                    tracker.total_tokens,
                    tracker.total_cost_usd,
                )
            return response
        finally:
            reset_token_tracker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown"""
    # Startup
    from backend.utils.env_validator import validate_startup

    try:
        validate_startup()
    except ValueError:
        logger.error("起動時バリデーション失敗。環境変数を確認してください。")
        raise

    if _ENVIRONMENT == "production":
        setup_structured_logging()

    try:
        from backend.utils.checkpoint_cleanup import CheckpointCleanup

        cleanup = CheckpointCleanup()
        app.state.checkpoint_cleanup = cleanup
        logger.info("Checkpoint cleanup configured (TTL: 24h)")
    except Exception as e:
        logger.warning("Checkpoint cleanup setup failed (non-critical): %s", e)

    try:
        session_task_manager = get_session_task_manager()
        await session_task_manager.initialize()
        app.state.session_task_manager = session_task_manager
        logger.info("Session task manager initialized")
    except Exception as e:
        logger.warning("Session task manager setup failed (non-critical): %s", e)

    try:
        from backend.utils.checkpointer import prewarm_checkpointer

        await prewarm_checkpointer()
    except ValueError:
        logger.warning("SUPABASE_DB_URI not set, skipping checkpointer warm-up.")
    except Exception as e:
        logger.warning("Checkpointer warm-up failed (non-critical): %s", e)

    yield

    # Shutdown
    from backend.utils.checkpointer import close_checkpointer

    try:
        await close_checkpointer()
        logger.info("Checkpointer closed on shutdown")
    except Exception as e:
        logger.warning("Error closing checkpointer on shutdown: %s", e)

    try:
        from backend.utils.store import close_store

        await close_store()
        logger.info("Store closed on shutdown")
    except Exception as e:
        logger.warning("Error closing store on shutdown: %s", e)

    try:
        session_task_manager = get_session_task_manager()
        await session_task_manager.shutdown()
        logger.info("Session task manager shutdown complete")
    except Exception as e:
        logger.warning("Error shutting down session task manager: %s", e)


app = FastAPI(
    title="Engineer Cafe Navigator Backend",
    description="Python LangGraph backend for Engineer Cafe Navigator",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
limiter: Any

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, cast(Any, _rate_limit_exceeded_handler))
except ImportError as exc:
    logger.critical("slowapi is required for rate limiting but could not be imported: %s", exc)
    if _ENVIRONMENT == "production":
        sys.exit(1)
    raise RuntimeError("slowapi is required for rate limiting") from exc


def _rate_limit(limit_string: str):
    """Return the configured rate-limit decorator."""
    return limiter.limit(limit_string)


# Add custom middleware
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TokenTrackerMiddleware)


_raw_api_key = os.getenv("API_SECRET_KEY", "").strip()
_API_SECRET_KEY = _raw_api_key if _raw_api_key else None

if _ENVIRONMENT == "production" and not _API_SECRET_KEY:
    logger.critical("API_SECRET_KEY is required in production. Refusing to start.")
    sys.exit(1)


async def verify_api_key(request: Request) -> None:
    """Verify API key, allowing missing keys only outside protected environments."""
    if not _API_SECRET_KEY:
        if _ENVIRONMENT in ("production", "staging", "preview"):
            raise HTTPException(status_code=503, detail="Server misconfigured")
        return
    api_key = request.headers.get("X-API-Key")
    if not api_key or not hmac.compare_digest(api_key, _API_SECRET_KEY):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://frontend-delta-six-20.vercel.app").split(
    ","
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    is_docs_path = request.url.path.startswith("/docs") or request.url.path.startswith("/redoc")
    if is_docs_path:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://openrouter.ai; "
            "media-src 'self' blob:; "
            "frame-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://openrouter.ai; "
            "media-src 'self' blob:; "
            "frame-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'"
        )
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


class ChatRequest(BaseModel):
    query: str = Field(max_length=2000)
    session_id: Optional[str] = None
    language: Optional[str] = Field(default="ja", max_length=10)
    context: Optional[Dict[str, Any]] = None
    visitor_id: Optional[str] = None  # Cross-session visitor identification
    image_data: str | None = None  # Base64 encoded image


class ChatResponse(BaseModel):
    answer: str
    emotion: str
    metadata: Dict[str, Any]
    vrm_control: Optional[Dict[str, Any]] = None


class InterruptRequest(BaseModel):
    session_id: str


@app.post("/api/interrupt", dependencies=[Depends(verify_api_key)])
@_rate_limit("60/minute")
async def interrupt_session(request: Request, body: InterruptRequest):
    """フロントエンドからの割り込みシグナルを受信"""
    from backend.utils.interrupt_manager import get_interrupt_manager

    manager = get_interrupt_manager()
    manager.request_interrupt(body.session_id)
    return {"status": "interrupted", "session_id": body.session_id}


async def _run_workflow_with_tracking(payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    from backend.workflows.main_workflow import get_workflow

    workflow = await get_workflow()
    await _get_stm().register_session(session_id)
    llm_task = asyncio.create_task(workflow.ainvoke(payload))
    await _get_stm().set_llm_task(session_id, llm_task)

    try:
        return cast(Dict[str, Any], await llm_task)
    except asyncio.CancelledError:
        logger.info("LLM task cancelled for session %s", session_id)
        raise HTTPException(status_code=409, detail="Request interrupted")


def _build_workflow_payload(body: ChatRequest, session_id: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "query": body.query,
        "session_id": session_id,
        "language": body.language,
        "context": body.context or {},
        "visitor_id": body.visitor_id,
    }
    if body.image_data:
        payload["image_data"] = body.image_data
    return payload


@app.get("/health")
@_rate_limit("60/minute")
async def health_check(request: Request):
    """ヘルスチェックエンドポイント（依存関係確認付き）"""
    checks = {"api": "ok"}

    # Supabase connection check
    supabase_url = os.getenv("SUPABASE_URL")
    if supabase_url:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{supabase_url}/rest/v1/",
                    headers={
                        "apikey": os.getenv("SUPABASE_KEY", ""),
                    },
                )
                checks["supabase"] = "ok" if resp.status_code < 500 else "error"
        except Exception:
            checks["supabase"] = "error"
    else:
        checks["supabase"] = "not_configured"

    checks["llm_provider"] = "configured" if os.getenv("OPENROUTER_API_KEY") else "not_configured"

    overall = "ok" if all(v not in ("error",) for v in checks.values()) else "degraded"

    return {
        "status": overall,
        "service": "engineer-cafe-navigator-backend",
        "checks": checks,
    }


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
@_rate_limit("30/minute")
async def chat(request: Request, body: ChatRequest):
    """
    チャットエンドポイント
    LangGraphエージェントを使用してクエリを処理します
    """
    import uuid as _uuid

    from backend.utils.interrupt_manager import get_interrupt_manager

    session_id = body.session_id or str(_uuid.uuid4())

    get_interrupt_manager().clear_interrupt(session_id)

    try:
        result = await _run_workflow_with_tracking(
            payload=_build_workflow_payload(body, session_id),
            session_id=session_id,
        )

        answer = result.get("answer", "回答を生成できませんでした。")

        # Output PII scanning
        try:
            from backend.utils.pii_scanner import scan_and_mask

            masked_answer, pii_items = scan_and_mask(answer)
            if pii_items:
                logger.warning(
                    "PII detected in response (%d items), masked before delivery",
                    len(pii_items),
                )
                answer = masked_answer
        except Exception as e:
            logger.debug("PII scan skipped (non-critical): %s", e)

        metadata = result.get("metadata", {"query": body.query, "session_id": session_id})

        return ChatResponse(
            answer=answer,
            emotion=result.get("emotion", "neutral"),
            metadata=metadata,
            vrm_control=metadata.get("vrm_control"),
        )
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


@app.post("/api/chat/stream", dependencies=[Depends(verify_api_key)])
@_rate_limit("30/minute")
async def chat_stream(request: Request, body: ChatRequest):
    """
    SSEストリーミングチャットエンドポイント
    Server-Sent Events でレスポンスをストリーミング
    """
    import uuid as _uuid

    from backend.utils.interrupt_manager import get_interrupt_manager

    session_id = body.session_id or str(_uuid.uuid4())

    interrupt_mgr = get_interrupt_manager()
    interrupt_mgr.clear_interrupt(session_id)

    async def event_generator():
        try:
            from backend.workflows.main_workflow import get_workflow

            workflow = await get_workflow()

            # Use astream for streaming
            async for event in workflow.astream(_build_workflow_payload(body, session_id)):
                if interrupt_mgr.is_interrupted(body.session_id):
                    yield f'data: {json.dumps({"type": "interrupted"})}\n\n'
                    break
                if isinstance(event, dict):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("SSE stream error: %s", e)
            yield f'data: {json.dumps({"error": "An internal error occurred"})}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/agent/invoke", dependencies=[Depends(verify_api_key)])
@_rate_limit("30/minute")
async def invoke_agent(request: Request, body: ChatRequest):
    """
    LangGraphエージェントの直接実行エンドポイント
    """
    import uuid as _uuid

    from backend.utils.interrupt_manager import get_interrupt_manager

    session_id = body.session_id or str(_uuid.uuid4())
    get_interrupt_manager().clear_interrupt(session_id)

    try:
        result = await _run_workflow_with_tracking(
            payload=_build_workflow_payload(body, session_id),
            session_id=session_id,
        )

        return {"status": "success", "result": result}
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


# Voice API Models
class VoiceRequest(BaseModel):
    action: str
    audioData: Optional[str] = None
    sessionId: Optional[str] = None
    language: Optional[str] = Field(default="ja", max_length=10)
    text: Optional[str] = Field(default=None, max_length=5000)
    streaming: Optional[bool] = False
    conversationStage: Optional[str] = None
    emotion: Optional[str] = None  # Emotion for TTS synthesis


class VoiceResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    response: Optional[str] = None
    audioResponse: Optional[str] = None
    emotion: Optional[str] = None
    sessionId: Optional[str] = None
    error: Optional[str] = None
    detectedLanguage: Optional[str] = None
    confidence: Optional[float] = None
    interruptStatus: Optional[str] = None


_voice_agent: Optional[Any] = None  # VoiceAgent (lazy-loaded)
_stt_agent: Optional[Any] = None  # STTAgent (lazy-loaded)
_slide_agent: Optional[Any] = None  # SlideAgent (lazy-loaded)
_session_task_manager: Optional[Any] = None


def _get_stm():
    global _session_task_manager
    if _session_task_manager is None:
        _session_task_manager = get_session_task_manager()
    return _session_task_manager


def _get_voice_agent():
    global _voice_agent
    if _voice_agent is None:
        from backend.agents.voice_agent import VoiceAgent

        tts_provider = os.getenv("TTS_PROVIDER", "voicevox")
        _voice_agent = VoiceAgent(tts_provider=tts_provider)
    return _voice_agent


def _get_stt_agent():
    global _stt_agent
    if _stt_agent is None:
        from backend.agents.stt_agent import STTAgent

        _stt_agent = STTAgent()
    return _stt_agent


def _get_slide_agent():
    global _slide_agent
    if _slide_agent is None:
        from backend.agents.slide_agent import SlideAgent

        _slide_agent = SlideAgent()
    return _slide_agent


async def _handle_stt(body: VoiceRequest) -> VoiceResponse:
    """Shared STT processing for process_voice and speech_to_text actions."""
    if not body.audioData:
        raise HTTPException(status_code=400, detail="Missing audioData")

    audio_bytes = base64.b64decode(body.audioData)

    stt_result = await _get_stt_agent().speech_to_text(
        audio_bytes,
        language=body.language,
        conversation_stage=body.conversationStage,
    )

    if not stt_result["success"]:
        return VoiceResponse(
            success=False,
            error=stt_result.get("error", "STT failed"),
            sessionId=body.sessionId,
        )

    return VoiceResponse(
        success=True,
        transcript=stt_result["transcript"],
        emotion="neutral",
        detectedLanguage=stt_result.get("language"),
        confidence=stt_result.get("confidence"),
        sessionId=body.sessionId,
    )


@app.get("/api/voice", dependencies=[Depends(verify_api_key)])
async def voice_get_api(action: str = ""):
    if action == "supported_languages":
        return {
            "languages": [
                {"code": "ja", "name": "日本語"},
                {"code": "en", "name": "English"},
            ]
        }
    return {"status": "ok", "actions": ["speech_to_text", "text_to_speech", "supported_languages"]}


_CALENDAR_TIME_RANGES = {"today", "thisWeek", "nextWeek", "thisMonth"}


@app.get("/api/calendar", dependencies=[Depends(verify_api_key)])
@_rate_limit("60/minute")
async def calendar_api(request: Request, timeRange: str = "thisWeek"):
    """Return calendar events fetched from the backend-managed ICS feed."""
    if timeRange not in _CALENDAR_TIME_RANGES:
        raise HTTPException(status_code=400, detail="Invalid timeRange")

    result = await CalendarService().search_events(cast(TimeRange, timeRange))
    if not result.get("success"):
        raise HTTPException(
            status_code=502,
            detail=result.get("error", "Failed to fetch calendar events"),
        )

    return result


@app.post("/api/voice", response_model=VoiceResponse, dependencies=[Depends(verify_api_key)])
@_rate_limit("20/minute")
async def voice_api(request: Request, body: VoiceRequest):
    try:
        if body.action == "text_to_speech":
            if not body.text or not body.text.strip():
                raise HTTPException(status_code=400, detail="Missing text for text_to_speech")

            if body.sessionId:
                await _get_stm().register_session(body.sessionId)

            tts_task = asyncio.create_task(
                _get_voice_agent().text_to_speech(
                    text=body.text,
                    language=body.language or "ja",
                    emotion=body.emotion,  # Use requested emotion for TTS
                )
            )
            if body.sessionId:
                await _get_stm().set_tts_task(body.sessionId, tts_task)

            result = await tts_task

            if body.sessionId and result.get("audioResponse"):
                try:
                    audio_bytes = base64.b64decode(result["audioResponse"])
                    await _get_stm().set_tts_buffer(body.sessionId, BytesIO(audio_bytes))
                except Exception:
                    logger.debug("Failed to register TTS buffer for session %s", body.sessionId)

            if not result.get("success"):
                return VoiceResponse(
                    success=False,
                    error=result.get("error", "TTS failed"),
                    emotion=result.get("emotion"),
                    sessionId=body.sessionId,
                )

            return VoiceResponse(
                success=True,
                audioResponse=result.get("audioResponse"),
                emotion=result.get("emotion"),
                sessionId=body.sessionId,
            )

        elif body.action == "process_voice":
            return await _handle_stt(body)

        elif body.action == "set_language":
            return VoiceResponse(success=True, sessionId=body.sessionId)

        elif body.action == "speech_to_text":
            return await _handle_stt(body)

        elif body.action == "interrupt":
            if not body.sessionId:
                raise HTTPException(status_code=400, detail="Missing sessionId for interrupt")

            cancelled = await _get_stm().cancel_all_tasks(body.sessionId)
            return VoiceResponse(
                success=True,
                sessionId=body.sessionId,
                interruptStatus="cancelled" if cancelled else "no_active_task",
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )


# Slides API Models
class SlidesRequest(BaseModel):
    action: str
    slideId: Optional[str] = None
    targetSlide: Optional[int] = None
    slideNumber: Optional[int] = None  # FE互換エイリアス (targetSlide)
    query: Optional[str] = None
    question: Optional[str] = None  # FE互換エイリアス (query)
    sessionId: Optional[str] = None
    language: Optional[str] = "ja"


class SlidesResponse(BaseModel):
    success: bool
    slide: Optional[Dict[str, Any]] = None
    narration: Optional[str] = None
    answer: Optional[str] = None
    emotion: Optional[str] = None
    slideNumber: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


SUPPORTED_SLIDE_LANGUAGES = {"ja", "en"}


class SlideContentRequest(BaseModel):
    language: str = "ja"


class SlideContentResponse(BaseModel):
    success: bool
    markdown: Optional[str] = None
    narrationData: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@app.post(
    "/api/slides/content",
    response_model=SlideContentResponse,
    dependencies=[Depends(verify_api_key)],
)
async def slides_content_api(body: SlideContentRequest):
    """Return raw slide markdown and narration data for frontend rendering."""
    try:
        language = body.language or "ja"
        if language not in SUPPORTED_SLIDE_LANGUAGES:
            language = "ja"
        backend_dir = os.path.dirname(os.path.abspath(__file__))

        md_path = os.path.join(backend_dir, "slides", language, "engineer-cafe.md")
        if not os.path.exists(md_path):
            md_path = os.path.join(backend_dir, "slides", "engineer-cafe.md")

        if not os.path.exists(md_path):
            return SlideContentResponse(success=False, error="Slide file not found")

        with open(md_path, "r", encoding="utf-8") as file:
            markdown = file.read()

        narration_path = os.path.join(
            backend_dir, "slides", "narration", f"engineer-cafe-{language}.json"
        )
        narration_data = None
        if os.path.exists(narration_path):
            with open(narration_path, "r", encoding="utf-8") as file:
                narration_data = json.load(file)

        title = "Engineer Cafe"
        if narration_data:
            title = narration_data.get("metadata", {}).get("title", title)

        return SlideContentResponse(
            success=True,
            markdown=markdown,
            narrationData=narration_data,
            metadata={"language": language, "title": title},
        )
    except Exception as e:
        logger.exception("slides_content error: %s", e)
        return SlideContentResponse(success=False, error="Internal server error")


@app.post("/api/slides", response_model=SlidesResponse, dependencies=[Depends(verify_api_key)])
@_rate_limit("20/minute")
async def slides_api(request: Request, body: SlidesRequest):
    """
    スライド制御エンドポイント
    SlideAgentを使用してスライドナレーションと質問応答を処理
    """
    try:
        slide_agent = _get_slide_agent()

        # アクションマッピング（FE互換エイリアス含む）
        action_map = {
            "narrate": "narrate",
            "narrate_current": "narrate",
            "next": "next",
            "previous": "previous",
            "goto": "goto",
            "question": "question",
            "answer_question": "question",
        }

        slide_action = action_map.get(body.action)
        if not slide_action:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

        # FE互換: slideNumber → targetSlide, question → query
        query = body.query or body.question
        target_slide = body.targetSlide or body.slideNumber

        # SlideAgentのhandle_slide_action呼び出し
        result = await slide_agent.handle_slide_action(
            action=slide_action,
            query=query,
            target_slide=target_slide,
            language=body.language,
            session_id=body.sessionId or "default",
        )

        return SlidesResponse(
            success=True,
            answer=result.get("answer"),
            emotion=result.get("emotion"),
            slideNumber=result.get("slideNumber"),
            metadata=result.get("metadata"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


# Character API Models
class CharacterRequest(BaseModel):
    action: str
    emotion: Optional[str] = None
    animation: Optional[str] = None


class CharacterResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


@app.post(
    "/api/character", response_model=CharacterResponse, dependencies=[Depends(verify_api_key)]
)
@_rate_limit("20/minute")
async def character_api(request: Request, body: CharacterRequest):
    """
    キャラクター制御エンドポイント
    フロントエンドからのプロキシリクエストを処理
    """
    try:
        from backend.agents.character_control_agent import CharacterControlAgent

        agent = CharacterControlAgent()
        result = await asyncio.wait_for(
            agent.process(
                emotion=body.emotion or "neutral",
                text=None,
                context={"action": body.action, "animation": body.animation},
            ),
            timeout=10.0,
        )
        return CharacterResponse(
            success=True,
            message=(
                json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            ),
        )
    except asyncio.TimeoutError:
        logger.warning("CharacterControlAgent timed out after 10s")
        raise HTTPException(
            status_code=504,
            detail="Character action timed out",
        )
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


# Knowledge CRUD API Router
from backend.api.knowledge import router as knowledge_router  # noqa: E402

app.include_router(knowledge_router, prefix="/api", dependencies=[Depends(verify_api_key)])

# STT Custom Vocabulary API Router
from backend.api.stt_vocabulary import router as stt_vocabulary_router  # noqa: E402

app.include_router(stt_vocabulary_router, prefix="/api", dependencies=[Depends(verify_api_key)])

# Monitoring API Router
from backend.api.monitoring import router as monitoring_router  # noqa: E402

app.include_router(monitoring_router, dependencies=[Depends(verify_api_key)])

# Alerts API Router
from backend.api.alerts import router as alerts_router  # noqa: E402

app.include_router(alerts_router, dependencies=[Depends(verify_api_key)])

# Reception API Router
from backend.api.reception import reception_router  # noqa: E402

app.include_router(reception_router, dependencies=[Depends(verify_api_key)])

# OCR API Router
from backend.api.ocr import ocr_router  # noqa: E402

app.include_router(ocr_router, dependencies=[Depends(verify_api_key)])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
