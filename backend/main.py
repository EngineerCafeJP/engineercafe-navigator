"""
Engineer Cafe Navigator Backend
FastAPIアプリケーションとLangGraphエージェントの統合
"""

import hmac
import asyncio
import base64
import binascii
import json
import logging
import os
import re
import sys
import time
import wave
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.tools.calendar_service import CalendarService, TimeRange
from backend.observability.structured_logger import log_chat_response, log_stt_event
from backend.services.stt_warmup_service import get_stt_warmup_service
from backend.utils.structured_logging import (
    get_request_id,
    request_id_var,
    generate_request_id,
    setup_structured_logging,
)
from backend.utils.session_task_manager import get_session_task_manager
from backend.utils.intent_classifier import (
    FILLER_INTENTS,
    classify_fast_intent,
    filler_intent_for_query,
)
from backend.utils.filler_catalog import FILLER_TEXTS

logger = logging.getLogger(__name__)


_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using %.0f", name, raw, default)
        return default
    return value if value >= 0 else default


_REQUEST_TIMING_LOG_THRESHOLD_MS = _float_env("REQUEST_TIMING_LOG_THRESHOLD_MS", 10000)
MIN_STT_AUDIO_BYTES = int(_float_env("STT_MIN_AUDIO_BYTES", 512))
_SUPPORTED_RESPONSE_LANGUAGES = frozenset({"ja", "en", "zh", "ko"})


def _voice_stt_request_timeout_seconds() -> float:
    return _float_env("VOICE_STT_REQUEST_TIMEOUT_SECONDS", 12.0)


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
                "request_failed",
                extra={
                    "event": "request_failed",
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        should_log = response.status_code >= 500 or (
            request.url.path != "/health" and duration_ms >= _REQUEST_TIMING_LOG_THRESHOLD_MS
        )
        if should_log:
            level = logging.WARNING if response.status_code >= 500 else logging.INFO
            logger.log(
                level,
                "request_completed_slow",
                extra={
                    "event": "request_completed_slow",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
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
                logger.debug(
                    "token_usage",
                    extra={
                        "event": "token_usage",
                        "total_tokens": tracker.total_tokens,
                        "estimated_cost_usd": round(tracker.total_cost_usd, 6),
                    },
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

    if os.getenv("STT_PROVIDER") == "qwen-primary":
        try:
            await get_stt_warmup_service().warmup(
                provider=os.getenv("STT_PROVIDER"),
                warmup_factory=lambda: _get_stt_agent().warmup(),
                wait=True,
                raise_on_failure=_ENVIRONMENT == "production",
            )
        except Exception as e:
            logger.error("STT warm-up failed: %s", e)
            if _ENVIRONMENT == "production":
                raise

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
        await _close_voice_agents()
        logger.info("Voice agents closed on shutdown")
    except Exception as e:
        logger.warning("Error closing voice agents on shutdown: %s", e)

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
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
    if not api_key or not hmac.compare_digest(api_key, _API_SECRET_KEY):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


DEFAULT_FRONTEND_PRODUCTION_ORIGIN = os.getenv(
    "FRONTEND_PRODUCTION_ORIGIN", "https://frontend-delta-six-20.vercel.app"
)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", DEFAULT_FRONTEND_PRODUCTION_ORIGIN).split(",")
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
    requestId: Optional[str] = None
    phase: Optional[str] = None
    upstreamStatus: Optional[Dict[str, Any]] = None


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


def _general_fast_path_answer(query: str, language: str, request_type: str) -> tuple[str, str]:
    lower_query = query.lower()
    if request_type == "assistant_profile":
        if language == "en":
            return (
                "I am Engineer Cafe Navigator, the reception kiosk for Engineer Cafe in "
                "Fukuoka. I can help with facilities, events, membership check-in, Wi-Fi, "
                "slide guidance, and everyday questions visitors commonly ask at reception.",
                "helpful",
            )
        if language == "ko":
            return (
                "저는 Engineer Cafe Navigator 입니다. 후쿠오카의 엔지니어 카페 안내 키오스크로서, "
                "시설 이용, 이벤트, 회원증, Wi-Fi, 슬라이드 안내와 함께 접수처에서 자주 받는 "
                "일상적인 질문에도 답해 드립니다.",
                "helpful",
            )
        if language == "zh":
            return (
                "我是 Engineer Cafe Navigator，福冈工程师咖啡馆的前台导览终端。我可以为您介绍"
                "设施使用、活动信息、会员证、Wi-Fi、幻灯片导览，以及前台常见的日常问题。",
                "helpful",
            )
        return (
            "私は Engineer Cafe Navigator です。福岡市のエンジニアカフェの受付キオスク"
            "として、施設利用、イベント、会員証、Wi-Fi、スライド案内に加えて、"
            "受付でよくある日常的な質問にもお答えします。",
            "helpful",
        )

    if any(marker in lower_query for marker in ("ありがとう", "サンキュー", "thanks", "thank you")):
        return (
            (
                "どういたしまして。ほかにも気になることがあれば、気軽に聞いてください。"
                if language == "ja"
                else "You're welcome. Feel free to ask me anything else."
            ),
            "relaxed",
        )
    if any(marker in lower_query for marker in ("疲れた", "i am tired", "i'm tired")):
        return (
            (
                "少し休憩しましょう。エンジニアカフェでは、落ち着いて作業したり一息ついたりできます。"
                if language == "ja"
                else "Take a short break. Engineer Cafe is a good place to settle in and recharge."
            ),
            "relaxed",
        )
    if any(marker in lower_query for marker in ("元気", "how are you")):
        return (
            (
                "元気です。今日は受付として、施設案内でも雑談でもすぐお手伝いできます。"
                if language == "ja"
                else "I'm doing well. I can help with reception guidance or a quick casual chat."
            ),
            "relaxed",
        )
    return (
        (
            "もちろんです。短くお話ししましょう。施設のことでも、今日の過ごし方でも気軽に聞いてください。"
            if language == "ja"
            else (
                "Of course. We can keep it light. Ask me about the facility "
                "or anything practical for your visit."
            )
        ),
        "relaxed",
    )


def _general_static_fast_path_answer(query: str, language: str) -> tuple[str, str, str] | None:
    """Return stable general-knowledge answers that do not need workflow/LLM."""
    if language != "ja":
        return None

    normalized_query = re.sub(r"\s+", "", query.lower())
    python_definition_queries = {
        "pythonって何?",
        "pythonって何？",
        "pythonとは何?",
        "pythonとは何？",
        "pythonとは何ですか?",
        "pythonとは何ですか？",
    }
    if normalized_query not in python_definition_queries:
        return None

    return (
        "Pythonは、読み書きしやすい文法が特徴のプログラミング言語です。"
        "Webアプリ、データ分析、AI、自動化など幅広い用途で使われ、"
        "初心者にも学びやすい言語としてよく選ばれます。",
        "helpful",
        "general_light",
    )


def _try_chat_general_fast_path(
    body: ChatRequest,
    *,
    session_id: str,
    request_id: str,
    started_at: float,
) -> ChatResponse | None:
    if body.image_data or body.context or body.visitor_id:
        return None

    intent = classify_fast_intent(body.query)
    language = body.language or "ja"
    static_answer = _general_static_fast_path_answer(body.query, language)
    if intent is None and static_answer is not None:
        answer, emotion, request_type = static_answer
        metadata = {
            "query": body.query,
            "session_id": session_id,
            "agent": "GeneralKnowledgeAgent",
            "category": "general_knowledge",
            "route": "general_knowledge",
            "request_type": request_type,
            "query_type": request_type,
            "sources": [],
            "web_search_used": False,
            "rag_used": False,
            "provider_called": False,
            "fast_path": "chat_endpoint",
        }
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        log_chat_response(
            request_id=request_id,
            language=language,
            metadata=metadata,
            latency_ms=latency_ms,
        )
        return ChatResponse(
            answer=answer,
            emotion=emotion,
            metadata=metadata,
            requestId=request_id,
            phase="chat",
            upstreamStatus=_upstream_status("chat_endpoint_fast_path", route="general_knowledge"),
        )

    if (
        intent is None
        or intent.agent != "general_knowledge"
        or intent.request_type not in {"assistant_profile", "daily_conversation"}
    ):
        return None

    answer, emotion = _general_fast_path_answer(body.query, language, intent.request_type)
    metadata = {
        "query": body.query,
        "session_id": session_id,
        "agent": "GeneralKnowledgeAgent",
        "category": "general_knowledge",
        "route": "general_knowledge",
        "request_type": intent.request_type,
        "query_type": intent.request_type,
        "sources": [],
        "web_search_used": False,
        "rag_used": False,
        "provider_called": False,
        "fast_path": "chat_endpoint",
    }
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    log_chat_response(
        request_id=request_id,
        language=language,
        metadata=metadata,
        latency_ms=latency_ms,
    )
    return ChatResponse(
        answer=answer,
        emotion=emotion,
        metadata=metadata,
        requestId=request_id,
        phase="chat",
        upstreamStatus=_upstream_status("chat_endpoint_fast_path", route="general_knowledge"),
    )


def _request_id_from_request(request: Request) -> str:
    return get_request_id() or request.headers.get("X-Request-ID") or generate_request_id()


def _upstream_status(phase: str, ok: bool = True, **extra: Any) -> Dict[str, Any]:
    return {"phase": phase, "ok": ok, **extra}


def _normalize_response_language(value: Any, fallback: str = "ja") -> str:
    if isinstance(value, str) and value.strip():
        normalized = value.strip().lower().split("-", 1)[0]
        if normalized in _SUPPORTED_RESPONSE_LANGUAGES:
            return normalized
    return fallback if fallback in _SUPPORTED_RESPONSE_LANGUAGES else "ja"


def _resolve_chat_response_language(
    *,
    query: str,
    requested_language: Optional[str],
    result: Dict[str, Any],
    metadata: Dict[str, Any],
) -> str:
    fallback = _normalize_response_language(requested_language)
    for key in ("response_language", "language", "detected_language"):
        if key in metadata:
            return _normalize_response_language(metadata.get(key), fallback)
    for key in ("response_language", "language", "detected_language"):
        if key in result:
            return _normalize_response_language(result.get(key), fallback)

    try:
        from backend.utils.language_processor import LanguageProcessor

        language_processor = LanguageProcessor()
        language_result = language_processor.detect_language(query)
        detected = language_processor.determine_response_language(language_result)
        return _normalize_response_language(detected, fallback)
    except Exception as exc:
        logger.debug("Response language detection skipped: %s", exc)
        return fallback


def _stt_failure_response(
    *,
    body: "VoiceRequest",
    request_id: str,
    error: str,
    provider: Optional[str] = None,
    error_type: Optional[str] = None,
) -> "VoiceResponse":
    return VoiceResponse(
        success=False,
        error=error,
        sessionId=body.sessionId,
        requestId=request_id,
        phase="speech_to_text",
        upstreamStatus=_upstream_status(
            "stt",
            ok=False,
            provider=provider,
            error=error,
            errorType=error_type,
        ),
    )


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

    Frontend proxy note: `/api/chat` responses include requestId, phase, and
    upstreamStatus so `frontend/src/app/api/qa` can surface traceable failures.
    """
    import uuid as _uuid

    from backend.utils.interrupt_manager import get_interrupt_manager
    from backend.utils.input_sanitizer import (
        contains_prompt_injection,
        prompt_injection_refusal,
        sanitize_input,
    )

    started_at = time.perf_counter()
    session_id = body.session_id or str(_uuid.uuid4())
    request_id = _request_id_from_request(request)

    get_interrupt_manager().clear_interrupt(session_id)

    try:
        if contains_prompt_injection(body.query):
            sanitized_query = sanitize_input(body.query)
            metadata = {
                "query": sanitized_query,
                "session_id": session_id,
                "agent": "SafetyGuard",
                "category": "safety",
                "route": "safety_guard",
                "safety_guard": True,
                "sources": [],
                "rag_fallback": False,
            }
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            log_chat_response(
                request_id=request_id,
                language=body.language,
                metadata=metadata,
                latency_ms=latency_ms,
            )
            return ChatResponse(
                answer=prompt_injection_refusal(body.language),
                emotion="neutral",
                metadata=metadata,
                requestId=request_id,
                phase="chat",
                upstreamStatus=_upstream_status("safety_guard"),
            )

        body = body.copy(update={"query": sanitize_input(body.query)})
        fast_response = _try_chat_general_fast_path(
            body,
            session_id=session_id,
            request_id=request_id,
            started_at=started_at,
        )
        if fast_response is not None:
            return fast_response

        result = await _run_workflow_with_tracking(
            payload=_build_workflow_payload(body, session_id),
            session_id=session_id,
        )

        raw_answer = result.get("answer", "回答を生成できませんでした。")

        # Strip emotion tags (emotion is carried separately in the response)
        from backend.utils.emotion_utils import strip_emotion_tags

        answer = strip_emotion_tags(raw_answer)

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
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        response_language = _resolve_chat_response_language(
            query=body.query,
            requested_language=body.language,
            result=result,
            metadata=metadata_dict,
        )
        if isinstance(metadata, dict):
            metadata.setdefault("response_language", response_language)
            metadata.setdefault("language", response_language)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        log_chat_response(
            request_id=request_id,
            language=response_language,
            metadata=metadata_dict,
            latency_ms=latency_ms,
        )

        return ChatResponse(
            answer=answer,
            emotion=result.get("emotion", "neutral"),
            metadata=metadata,
            vrm_control=metadata_dict.get("vrm_control"),
            requestId=request_id,
            phase="chat",
            upstreamStatus=_upstream_status(
                "workflow",
                route=metadata_dict.get("route")
                or metadata_dict.get("category")
                or metadata_dict.get("agent"),
            ),
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
                    yield f"data: {json.dumps({'type': 'interrupted'})}\n\n"
                    break
                if isinstance(event, dict):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("SSE stream error: %s", e)
            yield f"data: {json.dumps({'error': 'An internal error occurred'})}\n\n"

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
    outputEncoding: Optional[str] = Field(default=None, max_length=10)  # e.g. "mp3" for WAV→MP3
    ttsProvider: Optional[str] = Field(
        default=None,
        max_length=20,
    )  # voicevox | piper | google — overrides TTS_PROVIDER for this request
    # True: CharacterControlAgent → chat metadata.vrm_control 相当
    includeVrmControl: Optional[bool] = False


class VoiceResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    response: Optional[str] = None
    audioResponse: Optional[str] = None
    audioFormat: Optional[str] = None  # "audio/wav" or "audio/mpeg"
    emotion: Optional[str] = None
    sessionId: Optional[str] = None
    error: Optional[str] = None
    detectedLanguage: Optional[str] = None
    confidence: Optional[float] = None
    sttProvider: Optional[str] = None
    sttPostprocessed: Optional[bool] = None
    interruptStatus: Optional[str] = None
    sttWarmupStatus: Optional[str] = None
    sttWarmupProvider: Optional[str] = None
    sttWarmupError: Optional[str] = None
    sttWarmupDurationMs: Optional[int] = None
    cleanText: Optional[str] = None  # TTS 前処理後（includeVrmControl 時）
    # CharacterControlAgent.process（チャット metadata 相当）
    vrmControl: Optional[Dict[str, Any]] = None
    requestId: Optional[str] = None
    phase: Optional[str] = None
    upstreamStatus: Optional[Dict[str, Any]] = None


class FillerRequest(BaseModel):
    query: str = Field(max_length=2000)
    language: Literal["ja", "en", "zh", "ko"] = "ja"


class FillerResponse(BaseModel):
    audioResponse: str
    intent: str
    audioFormat: str = "audio/wav"
    fillerText: str
    source: str = "static"
    requestId: Optional[str] = None
    phase: Optional[str] = "filler"
    upstreamStatus: Optional[Dict[str, Any]] = None


_FILLER_DIR = Path(__file__).resolve().parent / "static" / "fillers"
# Piper filler clips exceed ~8KiB; silent placeholder (~5804 B) stays below this floor.
MIN_FILLER_WAV_BYTES = 8192
_filler_audio_cache: dict[tuple[str, str], str] = {}


def _read_filler_audio(intent: str, language: str) -> str:
    cache_key = (intent, language)
    cached = _filler_audio_cache.get(cache_key)
    if cached is not None:
        return cached

    path = _FILLER_DIR / f"{intent}_{language}.wav"
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size < MIN_FILLER_WAV_BYTES:
        logger.warning(
            "Filler WAV too small (silent/corrupt?): intent=%s language=%s bytes=%s min=%s",
            intent,
            language,
            size,
            MIN_FILLER_WAV_BYTES,
        )
        raise ValueError("filler wav below minimum size")

    with path.open("rb") as file:
        encoded = base64.b64encode(file.read()).decode("ascii")
    _filler_audio_cache[cache_key] = encoded
    return encoded


def _read_filler_audio_with_static_fallback(
    intent: str,
    language: str,
) -> tuple[str, str, str, bool]:
    candidates: list[tuple[str, str]] = [(intent, language)]
    for candidate in (("fallback", language), ("fallback", "ja")):
        if candidate not in candidates:
            candidates.append(candidate)

    first_error: Exception | None = None
    for candidate_intent, candidate_language in candidates:
        try:
            audio = _read_filler_audio(candidate_intent, candidate_language)
            return (
                audio,
                candidate_intent,
                candidate_language,
                (candidate_intent, candidate_language) != (intent, language),
            )
        except Exception as exc:
            if first_error is None:
                first_error = exc
            logger.warning(
                "Filler audio unavailable: intent=%s language=%s error=%s",
                candidate_intent,
                candidate_language,
                exc,
            )

    if first_error is not None:
        raise first_error
    raise FileNotFoundError(f"No filler audio candidates for {intent}_{language}")


def _filler_text(intent: str, language: str) -> str:
    fallback = FILLER_TEXTS["fallback"]["ja"]
    return FILLER_TEXTS.get(intent, FILLER_TEXTS["fallback"]).get(language, fallback)


@app.post(
    "/api/voice/filler",
    response_model=FillerResponse,
    dependencies=[Depends(verify_api_key)],
)
@_rate_limit("60/minute")
async def voice_filler_api(request: Request, body: FillerRequest):
    """
    Return a pre-recorded filler clip for frontend parallel playback.

    Frontend proxy note: `frontend/src/app/api/voice/filler` can safely degrade
    when audioResponse is empty; this endpoint keeps HTTP 200 for asset misses.
    """
    request_id = _request_id_from_request(request)
    started_at = time.perf_counter()
    intent = filler_intent_for_query(body.query)
    if intent not in FILLER_INTENTS:
        intent = "fallback"

    actual_intent = intent
    actual_language = body.language
    fallback_used = False
    try:
        audio, actual_intent, actual_language, fallback_used = (
            _read_filler_audio_with_static_fallback(intent, body.language)
        )
        ok = bool(audio)
    except Exception as exc:
        logger.warning(
            "Filler audio unavailable after static fallback: intent=%s language=%s error=%s",
            intent,
            body.language,
            exc,
        )
        audio = ""
        ok = False

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    return FillerResponse(
        audioResponse=audio,
        intent=intent,
        fillerText=_filler_text(intent, body.language),
        requestId=request_id,
        upstreamStatus=_upstream_status(
            "filler",
            ok=ok,
            latencyMs=latency_ms,
            fallbackUsed=fallback_used,
            actualIntent=actual_intent,
            actualLanguage=actual_language,
        ),
    )


_voice_agent: Optional[Any] = None  # VoiceAgent (lazy-loaded)
_voice_agents_by_provider: dict[str, Any] = {}
_ALLOWED_TTS_PROVIDERS = frozenset({"voicevox", "piper", "google"})
_stt_agent: Optional[Any] = None  # STTAgent (lazy-loaded)
_slide_agent: Optional[Any] = None  # SlideAgent (lazy-loaded)
_session_task_manager: Optional[Any] = None


async def _close_voice_agents() -> None:
    """Close cached VoiceAgent instances and clear the singletons."""
    global _voice_agent, _voice_agents_by_provider

    agents = []
    if _voice_agent is not None:
        agents.append(_voice_agent)
    agents.extend(_voice_agents_by_provider.values())

    seen: set[int] = set()
    try:
        for agent in agents:
            agent_id = id(agent)
            if agent_id in seen:
                continue
            seen.add(agent_id)

            close = getattr(agent, "close", None)
            if callable(close):
                result = close()
                if asyncio.iscoroutine(result):
                    await result
                continue

            aclose = getattr(agent, "aclose", None)
            if callable(aclose):
                result = aclose()
                if asyncio.iscoroutine(result):
                    await result
    finally:
        _voice_agent = None
        _voice_agents_by_provider = {}


def _get_stm():
    global _session_task_manager
    if _session_task_manager is None:
        _session_task_manager = get_session_task_manager()
    return _session_task_manager


def _normalize_tts_provider_override(raw: str) -> str:
    key = raw.lower().strip()
    if key not in _ALLOWED_TTS_PROVIDERS:
        allowed = ", ".join(sorted(_ALLOWED_TTS_PROVIDERS))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ttsProvider: {raw!r} (allowed: {allowed})",
        )
    return key


def _get_voice_agent_for_provider_key(provider_key: str):
    """Lazily construct and cache VoiceAgent per TTS provider (for per-request override)."""
    global _voice_agents_by_provider
    if provider_key not in _voice_agents_by_provider:
        from backend.agents.voice_agent import VoiceAgent

        _voice_agents_by_provider[provider_key] = VoiceAgent(tts_provider=provider_key)
    return _voice_agents_by_provider[provider_key]


def _get_voice_agent():
    global _voice_agent
    if _voice_agent is None:
        from backend.agents.voice_agent import VoiceAgent

        tts_provider = os.getenv("TTS_PROVIDER", "voicevox")
        _voice_agent = VoiceAgent(tts_provider=tts_provider)
    return _voice_agent


def _resolve_tts_agent(body: VoiceRequest):
    """Default env-based singleton, or a cached agent when ttsProvider is set."""
    if body.ttsProvider and body.ttsProvider.strip():
        return _get_voice_agent_for_provider_key(_normalize_tts_provider_override(body.ttsProvider))
    return _get_voice_agent()


def _get_stt_agent():
    global _stt_agent
    if _stt_agent is None:
        from backend.agents.stt_agent import STTAgent

        # None のとき STTAgent 側で STT_PROVIDER / ENVIRONMENT に基づく既定を解決
        _stt_agent = STTAgent(stt_provider=os.getenv("STT_PROVIDER"))
    return _stt_agent


def _get_slide_agent():
    global _slide_agent
    if _slide_agent is None:
        from backend.agents.slide_agent import SlideAgent

        _slide_agent = SlideAgent()
    return _slide_agent


async def _generate_vrm_control_for_lab_tts(
    *, clean_text: str, emotion: Optional[str], tts_wav_b64: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Voice Lab: /api/chat の metadata.vrm_control と同系のキーフレームを生成。"""
    try:
        ctx: Optional[Dict[str, Any]] = None
        duration_sec: Optional[float] = None
        if tts_wav_b64:
            ctx = {"audio_data": tts_wav_b64}
            try:
                raw = base64.b64decode(tts_wav_b64)
                with wave.open(BytesIO(raw), "rb") as wf:
                    nframes = wf.getnframes()
                    rate = wf.getframerate()
                    if rate and nframes >= 0:
                        duration_sec = nframes / float(rate)
            except Exception:
                duration_sec = None

        from backend.agents.character_control_agent import CharacterControlAgent

        agent = CharacterControlAgent()
        return await agent.process(
            emotion=emotion or "neutral",
            text=clean_text,
            audio_duration=duration_sec,
            context=ctx,
        )
    except Exception as e:
        logger.warning("includeVrmControl: CharacterControlAgent failed: %s", e, exc_info=True)
        return None


async def _handle_stt(body: VoiceRequest, request_id: str) -> VoiceResponse:
    """Shared STT processing for speech_to_text action."""
    if not body.audioData:
        raise HTTPException(status_code=400, detail="Missing audioData")

    stt_request_started_at = time.perf_counter()
    decode_started_at = time.perf_counter()
    try:
        audio_bytes = base64.b64decode(body.audioData, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid audioData")
    base64_decode_duration_ms = int((time.perf_counter() - decode_started_at) * 1000)

    if len(audio_bytes) < MIN_STT_AUDIO_BYTES:
        logger.info(
            "STT skipped: audio too short request_id=%s bytes=%s min=%s",
            request_id,
            len(audio_bytes),
            MIN_STT_AUDIO_BYTES,
        )
        log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=os.getenv("STT_PROVIDER"),
            language=body.language,
            success=False,
            error_type="AudioTooShort",
            audio_bytes=len(audio_bytes),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
        )
        return _stt_failure_response(
            body=body,
            request_id=request_id,
            error="No speech detected",
            error_type="AudioTooShort",
        )

    try:
        stt_call = _get_stt_agent().speech_to_text(
            audio_bytes,
            language=body.language,
            conversation_stage=body.conversationStage,
        )
        stt_timeout_s = _voice_stt_request_timeout_seconds()
        if stt_timeout_s > 0:
            stt_result = await asyncio.wait_for(stt_call, timeout=stt_timeout_s)
        else:
            stt_result = await stt_call
    except asyncio.TimeoutError:
        logger.warning(
            "STT request timed out: request_id=%s timeout_s=%.2f",
            request_id,
            _voice_stt_request_timeout_seconds(),
        )
        log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=os.getenv("STT_PROVIDER"),
            language=body.language,
            success=False,
            error_type="TimeoutError",
            audio_bytes=len(audio_bytes),
            timeout_s=_voice_stt_request_timeout_seconds(),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
        )
        return _stt_failure_response(
            body=body,
            request_id=request_id,
            error="No speech detected",
            provider=os.getenv("STT_PROVIDER"),
            error_type="TimeoutError",
        )
    except RuntimeError as exc:
        logger.warning("STT runtime failure: %s", exc)
        log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=os.getenv("STT_PROVIDER"),
            language=body.language,
            success=False,
            error_type=type(exc).__name__,
            audio_bytes=len(audio_bytes),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
        )
        return _stt_failure_response(
            body=body,
            request_id=request_id,
            error="No speech detected",
            error_type=type(exc).__name__,
        )

    if not stt_result["success"]:
        log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=stt_result.get("provider"),
            language=body.language,
            success=False,
            error_type=stt_result.get("error"),
            audio_bytes=len(audio_bytes),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
        )
        return _stt_failure_response(
            body=body,
            request_id=request_id,
            error=stt_result.get("error", "STT failed"),
            provider=stt_result.get("provider"),
        )

    log_stt_event(
        event="stt_request_complete",
        request_id=request_id,
        provider=stt_result.get("provider"),
        language=stt_result.get("language") or body.language,
        success=True,
        audio_bytes=len(audio_bytes),
        transcript_chars=len(stt_result.get("transcript") or ""),
        stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
        stt_base64_decode_duration_ms=base64_decode_duration_ms,
    )
    return VoiceResponse(
        success=True,
        transcript=stt_result["transcript"],
        emotion="neutral",
        detectedLanguage=stt_result.get("language"),
        confidence=stt_result.get("confidence"),
        sttProvider=stt_result.get("provider"),
        sttPostprocessed=stt_result.get("postprocessed"),
        sessionId=body.sessionId,
        requestId=request_id,
        phase="speech_to_text",
        upstreamStatus=_upstream_status("stt", provider=stt_result.get("provider")),
    )


async def _handle_stt_warmup(body: VoiceRequest, request_id: str) -> VoiceResponse:
    """Start STT model warmup without tying it to the user audio request."""
    snapshot = await get_stt_warmup_service().warmup(
        provider=os.getenv("STT_PROVIDER"),
        warmup_factory=lambda: _get_stt_agent().warmup(),
        session_id=body.sessionId,
        wait=False,
    )
    return VoiceResponse(
        success=True,
        sessionId=body.sessionId,
        sttWarmupStatus=snapshot.status,
        sttWarmupProvider=snapshot.provider,
        sttWarmupError=snapshot.error,
        sttWarmupDurationMs=snapshot.duration_ms,
        requestId=request_id,
        phase="warmup",
        upstreamStatus=_upstream_status(
            "stt_warmup",
            ok=snapshot.error is None,
            provider=snapshot.provider,
            status=snapshot.status,
        ),
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
    default_tts = (os.getenv("TTS_PROVIDER", "voicevox") or "voicevox").strip().lower()
    return {
        "status": "ok",
        "actions": [
            "speech_to_text",
            "text_to_speech",
            "warmup",
            "supported_languages",
            "filler",
        ],
        "defaultTtsProvider": default_tts,
        "ttsProviders": [
            {"id": "voicevox", "label": "VoiceVox"},
            {"id": "piper", "label": "Piper-plus"},
            {"id": "google", "label": "Google Cloud TTS"},
        ],
    }


_CALENDAR_TIME_RANGES = {"today", "tomorrow", "thisWeek", "nextWeek", "thisMonth"}


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
    """
    Voice endpoint.

    Frontend proxy note: `/api/voice` responses include requestId, phase, and
    upstreamStatus for `frontend/src/app/api/voice` error display and tracing.
    """
    request_id = _request_id_from_request(request)
    try:
        if body.action == "text_to_speech":
            if not body.text or not body.text.strip():
                raise HTTPException(status_code=400, detail="Missing text for text_to_speech")

            if body.sessionId:
                await _get_stm().register_session(body.sessionId)

            tts_task = asyncio.create_task(
                _resolve_tts_agent(body).text_to_speech(
                    text=body.text,
                    language=body.language or "ja",
                    emotion=body.emotion,  # Use requested emotion for TTS
                )
            )
            if body.sessionId:
                await _get_stm().set_tts_task(body.sessionId, tts_task)

            result = await tts_task

            if not result.get("success"):
                return VoiceResponse(
                    success=False,
                    error=result.get("error", "TTS failed"),
                    emotion=result.get("emotion"),
                    audioFormat=result.get("format"),
                    sessionId=body.sessionId,
                    requestId=request_id,
                    phase="text_to_speech",
                    upstreamStatus=_upstream_status(
                        "tts",
                        ok=False,
                        provider=body.ttsProvider or os.getenv("TTS_PROVIDER", "voicevox"),
                        actualProvider=result.get("actual_provider"),
                        latencyMs=result.get("tts_duration_ms"),
                        cacheHit=result.get("tts_cache_hit"),
                        fallbackUsed=bool(result.get("fallback_used")),
                        fallbackProvider=result.get("fallback_provider"),
                        error=result.get("error", "TTS failed"),
                    ),
                )

            audio_b64 = result.get("audioResponse")
            audio_format = result.get("format")
            if not isinstance(audio_b64, str) or not audio_b64.strip():
                error_message = "TTS completed without audioResponse"
                logger.error(
                    "%s: request_id=%s provider=%s actual_provider=%s",
                    error_message,
                    request_id,
                    body.ttsProvider or os.getenv("TTS_PROVIDER", "voicevox"),
                    result.get("actual_provider"),
                )
                return VoiceResponse(
                    success=False,
                    error=error_message,
                    emotion=result.get("emotion"),
                    audioFormat=audio_format,
                    sessionId=body.sessionId,
                    requestId=request_id,
                    phase="text_to_speech",
                    upstreamStatus=_upstream_status(
                        "tts",
                        ok=False,
                        provider=body.ttsProvider or os.getenv("TTS_PROVIDER", "voicevox"),
                        actualProvider=result.get("actual_provider"),
                        latencyMs=result.get("tts_duration_ms"),
                        cacheHit=result.get("tts_cache_hit"),
                        fallbackUsed=bool(result.get("fallback_used")),
                        fallbackProvider=result.get("fallback_provider"),
                        error=error_message,
                    ),
                )
            tts_wav_b64_for_vrm: Optional[str] = None
            if audio_format == "audio/wav" and audio_b64:
                tts_wav_b64_for_vrm = audio_b64

            if (
                body.outputEncoding
                and body.outputEncoding.lower() == "mp3"
                and audio_format == "audio/wav"
                and audio_b64
            ):
                try:
                    from backend.utils.audio_encode import wav_base64_to_mp3_base64_async

                    audio_b64 = await wav_base64_to_mp3_base64_async(audio_b64)
                    audio_format = "audio/mpeg"
                except Exception as e:
                    logger.exception("WAV to MP3 conversion failed: %s", e)
                    raise HTTPException(
                        status_code=502,
                        detail="Audio encoding to MP3 failed (ensure ffmpeg is installed).",
                    )

            if body.sessionId and audio_b64:
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                    await _get_stm().set_tts_buffer(body.sessionId, BytesIO(audio_bytes))
                except Exception:
                    logger.debug("Failed to register TTS buffer for session %s", body.sessionId)

            clean_txt = (result.get("cleanText") or "").strip() or body.text.strip()
            emo_for_vrm = result.get("emotion") or body.emotion
            vrm_out: Optional[Dict[str, Any]] = None
            if body.includeVrmControl:
                logger.warning(
                    "DEPRECATED: includeVrmControl=true in /api/voice is deprecated. "
                    "Use POST /api/character/auto instead. session=%s",
                    body.sessionId,
                )
                vrm_out = await _generate_vrm_control_for_lab_tts(
                    clean_text=clean_txt,
                    emotion=emo_for_vrm if isinstance(emo_for_vrm, str) else None,
                    tts_wav_b64=tts_wav_b64_for_vrm,
                )

            requested_tts_provider = body.ttsProvider or os.getenv("TTS_PROVIDER", "voicevox")
            actual_tts_provider = result.get("actual_provider") or (
                result.get("fallback_provider")
                if result.get("fallback_used")
                else requested_tts_provider
            )
            return VoiceResponse(
                success=True,
                audioResponse=audio_b64,
                audioFormat=audio_format,
                emotion=result.get("emotion"),
                sessionId=body.sessionId,
                cleanText=clean_txt if body.includeVrmControl else None,
                vrmControl=vrm_out if body.includeVrmControl else None,
                requestId=request_id,
                phase="text_to_speech",
                upstreamStatus=_upstream_status(
                    "tts",
                    provider=requested_tts_provider,
                    actualProvider=actual_tts_provider,
                    format=audio_format,
                    language=result.get("language"),
                    latencyMs=result.get("tts_duration_ms"),
                    cacheHit=result.get("tts_cache_hit"),
                    fallbackUsed=bool(result.get("fallback_used")),
                    fallbackProvider=result.get("fallback_provider"),
                    error=result.get("error") if result.get("fallback_used") else None,
                ),
            )

        elif body.action == "set_language":
            return VoiceResponse(
                success=True,
                sessionId=body.sessionId,
                requestId=request_id,
                phase="set_language",
                upstreamStatus=_upstream_status("set_language"),
            )

        elif body.action == "speech_to_text":
            return await _handle_stt(body, request_id)

        elif body.action == "warmup":
            return await _handle_stt_warmup(body, request_id)

        elif body.action == "interrupt":
            if not body.sessionId:
                raise HTTPException(status_code=400, detail="Missing sessionId for interrupt")

            cancelled = await _get_stm().cancel_all_tasks(body.sessionId)
            return VoiceResponse(
                success=True,
                sessionId=body.sessionId,
                interruptStatus="cancelled" if cancelled else "no_active_task",
                requestId=request_id,
                phase="interrupt",
                upstreamStatus=_upstream_status("interrupt", cancelled=cancelled),
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


@app.get("/api/character", dependencies=[Depends(verify_api_key)])
@_rate_limit("20/minute")
async def character_get_api(request: Request, action: str = ""):
    """GET handler for character state queries from frontend polling."""
    if action == "supported_features":
        from backend.agents.character_control_agent import CharacterControlAgent

        agent = CharacterControlAgent()
        animations = (
            agent.get_supported_animations() if hasattr(agent, "get_supported_animations") else []
        )
        return {
            "success": True,
            "expressions": [
                "neutral",
                "happy",
                "sad",
                "angry",
                "relaxed",
                "surprised",
            ],
            "animations": animations,
        }
    # Default: return current state
    return {
        "success": True,
        "current_emotion": "neutral",
        "current_expression": "neutral",
    }


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


class CharacterAutoRequest(BaseModel):
    """Request body for auto VRM control generation from TTS output."""

    cleanText: str = Field(..., max_length=5000)
    emotion: str = Field(default="neutral", max_length=50)
    ttsWavB64: Optional[str] = None


class CharacterAutoResponse(BaseModel):
    success: bool
    vrmControl: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@app.post(
    "/api/character/auto",
    response_model=CharacterAutoResponse,
    dependencies=[Depends(verify_api_key)],
)
@_rate_limit("20/minute")
async def character_auto_api(request: Request, body: CharacterAutoRequest):
    """Auto-generate VRM control data from TTS output.

    Frontend can call this in parallel with /api/voice to avoid
    blocking the audio response on VRM generation.
    """
    try:
        vrm_result = await asyncio.wait_for(
            _generate_vrm_control_for_lab_tts(
                clean_text=body.cleanText,
                emotion=body.emotion,
                tts_wav_b64=body.ttsWavB64,
            ),
            timeout=15.0,
        )
        return CharacterAutoResponse(success=True, vrmControl=vrm_result)
    except asyncio.TimeoutError:
        logger.warning("Character auto VRM timed out after 15s")
        raise HTTPException(status_code=504, detail="VRM generation timed out")
    except Exception as e:
        logger.exception("Character auto VRM error: %s", e)
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
