"""
Engineer Cafe Navigator Backend
FastAPIアプリケーションとLangGraphエージェントの統合
"""

import hmac
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.utils.structured_logging import (
    request_id_var,
    generate_request_id,
    setup_structured_logging,
)

logger = logging.getLogger(__name__)


_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


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

    if os.getenv("ENV", "development") == "production":
        setup_structured_logging()

    try:
        from backend.utils.checkpoint_cleanup import CheckpointCleanup

        cleanup = CheckpointCleanup()
        app.state.checkpoint_cleanup = cleanup
        logger.info("Checkpoint cleanup configured (TTL: 24h)")
    except Exception as e:
        logger.warning("Checkpoint cleanup setup failed (non-critical): %s", e)

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


app = FastAPI(
    title="Engineer Cafe Navigator Backend",
    description="Python LangGraph backend for Engineer Cafe Navigator",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting (optional - requires slowapi)
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _HAS_SLOWAPI = True
except ImportError:
    _HAS_SLOWAPI = False
    limiter = None


def _rate_limit(limit_string: str):
    """Return a rate-limit decorator; no-op when slowapi is unavailable."""
    if _HAS_SLOWAPI and limiter is not None:
        return limiter.limit(limit_string)

    def _noop(func):
        return func

    return _noop


# Add custom middleware
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TokenTrackerMiddleware)


# Optional API key authentication
_API_SECRET_KEY = os.getenv("API_SECRET_KEY")


async def verify_api_key(request: Request) -> None:
    """Optional API key verification - skipped if API_SECRET_KEY not set"""
    if not _API_SECRET_KEY:
        return
    api_key = request.headers.get("X-API-Key")
    if not api_key or not hmac.compare_digest(api_key, _API_SECRET_KEY):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


# CORS設定
_default_origins = ["http://localhost:3000", "http://localhost:3001"]
_allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
] or _default_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
)


class ChatRequest(BaseModel):
    query: str
    session_id: str
    language: Optional[str] = "ja"
    context: Optional[Dict[str, Any]] = None
    visitor_id: Optional[str] = None  # Cross-session visitor identification


class ChatResponse(BaseModel):
    answer: str
    emotion: str
    metadata: Dict[str, Any]


@app.get("/health")
async def health_check():
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
    try:
        from backend.workflows.main_workflow import get_workflow

        workflow = await get_workflow()
        result = await workflow.ainvoke(
            {
                "query": body.query,
                "session_id": body.session_id,
                "language": body.language,
                "context": body.context or {},
                "visitor_id": body.visitor_id,
            }
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

        return ChatResponse(
            answer=answer,
            emotion=result.get("emotion", "neutral"),
            metadata=result.get("metadata", {"query": body.query, "session_id": body.session_id}),
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

    async def event_generator():
        try:
            from backend.workflows.main_workflow import get_workflow

            workflow = await get_workflow()

            # Use astream for streaming
            async for event in workflow.astream(
                {
                    "query": body.query,
                    "session_id": body.session_id,
                    "language": body.language,
                    "context": body.context or {},
                    "visitor_id": body.visitor_id,
                }
            ):
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
    try:
        from backend.workflows.main_workflow import get_workflow

        workflow = await get_workflow()
        result = await workflow.ainvoke(
            {
                "query": body.query,
                "session_id": body.session_id,
                "language": body.language,
                "context": body.context or {},
                "visitor_id": body.visitor_id,
            }
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
    language: Optional[str] = "ja"
    text: Optional[str] = None
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


_voice_agent: Optional[Any] = None  # VoiceAgent (lazy-loaded)
_stt_agent: Optional[Any] = None  # STTAgent (lazy-loaded)
_slide_agent: Optional[Any] = None  # SlideAgent (lazy-loaded)


def _get_voice_agent():
    global _voice_agent
    if _voice_agent is None:
        from backend.agents.voice_agent import VoiceAgent

        _voice_agent = VoiceAgent()
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


@app.post("/api/voice", response_model=VoiceResponse, dependencies=[Depends(verify_api_key)])
@_rate_limit("20/minute")
async def voice_api(request: Request, body: VoiceRequest):
    try:
        if body.action == "text_to_speech":
            if not body.text or not body.text.strip():
                raise HTTPException(status_code=400, detail="Missing text for text_to_speech")

            result = await _get_voice_agent().text_to_speech(
                text=body.text,
                language=body.language or "ja",
                emotion=body.emotion,  # Use requested emotion for TTS
            )
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
            if not body.audioData:
                raise HTTPException(status_code=400, detail="Missing audioData for process_voice")

            import base64

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
    query: Optional[str] = None
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
async def slides_api(request: Request, body: SlidesRequest):
    """
    スライド制御エンドポイント
    SlideAgentを使用してスライドナレーションと質問応答を処理
    """
    try:
        slide_agent = _get_slide_agent()

        # アクションマッピング
        action_map = {
            "narrate": "narrate",
            "next": "next",
            "previous": "previous",
            "goto": "goto",
            "question": "question",
        }

        slide_action = action_map.get(body.action)
        if not slide_action:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

        # SlideAgentのhandle_slide_action呼び出し
        result = await slide_agent.handle_slide_action(
            action=slide_action,
            query=body.query,
            target_slide=body.targetSlide,
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
async def character_api(request: Request, body: CharacterRequest):
    """
    キャラクター制御エンドポイント
    フロントエンドからのプロキシリクエストを処理
    """
    try:
        from backend.agents.character_control_agent import CharacterControlAgent

        agent = CharacterControlAgent()
        result = await agent.process(
            emotion=body.emotion or "neutral",
            text=None,
            context={"action": body.action, "animation": body.animation},
        )
        return CharacterResponse(
            success=True,
            message=(
                json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            ),
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
