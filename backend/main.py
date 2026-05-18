"""
Engineer Cafe Navigator Backend
FastAPIアプリケーションとLangGraphエージェントの統合
"""

# Compatibility re-exports keep legacy tests and callers that patch backend.main working.
# ruff: noqa: F401

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


def _stt_warmup_telemetry_fields() -> Dict[str, Any]:
    try:
        snapshot = get_stt_warmup_service().snapshot()
    except Exception as exc:
        logger.debug("STT warmup telemetry skipped: %s", exc)
        return {}

    fields: Dict[str, Any] = {
        "stt_warmup_status": snapshot.status,
        "stt_warmup_provider": snapshot.provider,
    }
    if snapshot.duration_ms is not None:
        fields["stt_warmup_duration_ms"] = snapshot.duration_ms
    if snapshot.error:
        fields["stt_warmup_error_type"] = snapshot.error.split(":", 1)[0]
    return fields


def _configure_langsmith_tracing() -> bool:
    """Enable LangSmith/LangChain tracing for production when configured."""

    from backend.config.settings import get_settings

    app_settings = get_settings()
    if not app_settings.is_production:
        return False

    api_key = (
        app_settings.langsmith_api_key
        or os.getenv("LANGSMITH_API_KEY", "").strip()
        or os.getenv("LANGCHAIN_API_KEY", "").strip()
    )
    if not api_key:
        logger.warning("LANGSMITH_API_KEY not set; LangSmith tracing disabled")
        return False

    project = (
        app_settings.langsmith_project
        or os.getenv("LANGSMITH_PROJECT", "").strip()
        or os.getenv("LANGCHAIN_PROJECT", "").strip()
    )

    os.environ.setdefault("LANGSMITH_API_KEY", api_key)
    os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    if project:
        os.environ["LANGSMITH_PROJECT"] = project
        os.environ["LANGCHAIN_PROJECT"] = project

    logger.info("LangSmith tracing enabled for project=%s", project or "default")
    return True


def _attach_latest_llm_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Attach request-scoped LLM provider/model metadata when available."""

    try:
        from backend.utils.token_tracker import get_latest_llm_metadata

        latest = get_latest_llm_metadata()
    except Exception as exc:
        logger.debug("LLM metadata attachment skipped: %s", exc)
        return metadata

    for key, value in latest.items():
        metadata.setdefault(key, value)
    return metadata


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
    _configure_langsmith_tracing()

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


def _request_id_from_request(request: Request) -> str:
    return get_request_id() or request.headers.get("X-Request-ID") or generate_request_id()


def _upstream_status(phase: str, ok: bool = True, **extra: Any) -> Dict[str, Any]:
    return {"phase": phase, "ok": ok, **extra}


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


# Split API route modules
import sys as _sys  # noqa: E402

from backend.api.admin import (  # noqa: E402
    CharacterAutoRequest,
    CharacterAutoResponse,
    CharacterRequest,
    CharacterResponse,
    SlidesRequest,
    SlidesResponse,
    character_api,
    character_auto_api,
    character_get_api,
    configure_dependencies as configure_admin_dependencies,
    create_router as create_admin_router,
    slides_api,
)
from backend.api.calendar import (  # noqa: E402
    _CALENDAR_TIME_RANGES,
    calendar_api,
    configure_dependencies as configure_calendar_dependencies,
    create_router as create_calendar_router,
)
from backend.api.chat import (  # noqa: E402
    ChatRequest,
    ChatResponse,
    InterruptRequest,
    _build_workflow_payload,
    _general_fast_path_answer,
    _general_static_fast_path_answer,
    _normalize_response_language,
    _resolve_chat_response_language,
    _run_workflow_with_tracking,
    _try_chat_general_fast_path,
    chat,
    chat_stream,
    configure_dependencies as configure_chat_dependencies,
    create_router as create_chat_router,
    interrupt_session,
    invoke_agent,
)
from backend.api.voice import (  # noqa: E402
    FillerRequest,
    FillerResponse,
    MIN_FILLER_WAV_BYTES,
    VoiceRequest,
    VoiceResponse,
    _ALLOWED_TTS_PROVIDERS,
    _FILLER_DIR,
    _close_voice_agents,
    _filler_audio_cache,
    _filler_text,
    _generate_vrm_control_for_lab_tts,
    _get_slide_agent,
    _get_stm,
    _get_stt_agent,
    _get_voice_agent,
    _get_voice_agent_for_provider_key,
    _handle_stt,
    _handle_stt_warmup,
    _normalize_tts_provider_override,
    _read_filler_audio,
    _read_filler_audio_with_static_fallback,
    _resolve_tts_agent,
    _slide_agent,
    _stt_agent,
    _stt_failure_response,
    _session_task_manager,
    _tts_require_primary_provider,
    _voice_agent,
    _voice_agents_by_provider,
    configure_dependencies as configure_voice_dependencies,
    create_router as create_voice_router,
    voice_api,
    voice_filler_api,
    voice_get_api,
)
from backend.api.telemetry import create_router as create_telemetry_router  # noqa: E402

_current_module = _sys.modules[__name__]
configure_chat_dependencies(_current_module)
configure_voice_dependencies(_current_module)
configure_calendar_dependencies(_current_module)
configure_admin_dependencies(_current_module)

app.include_router(create_chat_router(_rate_limit), dependencies=[Depends(verify_api_key)])
app.include_router(create_voice_router(_rate_limit), dependencies=[Depends(verify_api_key)])
app.include_router(create_calendar_router(_rate_limit), dependencies=[Depends(verify_api_key)])
app.include_router(create_admin_router(_rate_limit), dependencies=[Depends(verify_api_key)])
app.include_router(create_telemetry_router(_rate_limit), dependencies=[Depends(verify_api_key)])

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
