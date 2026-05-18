"""Voice, filler, and speech API routes."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import sys
import time
import wave
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from backend.api.voice_models import (
    FillerRequest,
    FillerResponse,
    VoiceRequest,
    VoiceResponse,
)
from backend.utils.filler_catalog import FILLER_TEXTS
from backend.utils.intent_classifier import FILLER_INTENTS, filler_intent_for_query

logger = logging.getLogger(__name__)
deps = sys.modules[__name__]


def configure_dependencies(module: Any) -> None:
    global deps
    deps = module


_FILLER_DIR = Path(__file__).resolve().parent.parent / "static" / "fillers"
# Piper filler clips exceed ~8KiB; silent placeholder (~5804 B) stays below this floor.
MIN_FILLER_WAV_BYTES = 8192
_filler_audio_cache: dict[tuple[str, str], str] = {}


def _stt_failure_response(
    *,
    body: "VoiceRequest",
    request_id: str,
    error: str,
    provider: Optional[str] = None,
    error_type: Optional[str] = None,
) -> "VoiceResponse":
    return deps.VoiceResponse(
        success=False,
        error=error,
        sessionId=body.sessionId,
        requestId=request_id,
        phase="speech_to_text",
        upstreamStatus=deps._upstream_status(
            "stt",
            ok=False,
            provider=provider,
            error=error,
            errorType=error_type,
        ),
    )


def _read_filler_audio(intent: str, language: str) -> str:
    cache_key = (intent, language)
    cache = deps._filler_audio_cache
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    path = deps._FILLER_DIR / f"{intent}_{language}.wav"
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size < deps.MIN_FILLER_WAV_BYTES:
        logger.warning(
            "Filler WAV too small (silent/corrupt?): intent=%s language=%s bytes=%s min=%s",
            intent,
            language,
            size,
            deps.MIN_FILLER_WAV_BYTES,
        )
        raise ValueError("filler wav below minimum size")

    with path.open("rb") as file:
        encoded = base64.b64encode(file.read()).decode("ascii")
    cache[cache_key] = encoded
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


async def voice_filler_api(request: Request, body: FillerRequest):
    """
    Return a pre-recorded filler clip for frontend parallel playback.

    Frontend proxy note: `frontend/src/app/api/voice/filler` can safely degrade
    when audioResponse is empty; this endpoint keeps HTTP 200 for asset misses.
    """
    request_id = deps._request_id_from_request(request)
    started_at = time.perf_counter()
    intent = filler_intent_for_query(body.query)
    if intent not in FILLER_INTENTS:
        intent = "fallback"

    actual_intent = intent
    actual_language = body.language
    fallback_used = False
    try:
        audio, actual_intent, actual_language, fallback_used = (
            deps._read_filler_audio_with_static_fallback(intent, body.language)
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
    return deps.FillerResponse(
        audioResponse=audio,
        intent=intent,
        fillerText=deps._filler_text(intent, body.language),
        requestId=request_id,
        upstreamStatus=deps._upstream_status(
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
_ALLOWED_TTS_PROVIDERS = frozenset({"voicevox", "piper"})
_stt_agent: Optional[Any] = None  # STTAgent (lazy-loaded)
_slide_agent: Optional[Any] = None  # SlideAgent (lazy-loaded)
_session_task_manager: Optional[Any] = None


async def _close_voice_agents() -> None:
    """Close cached VoiceAgent instances and clear the singletons."""
    agents = []
    if deps._voice_agent is not None:
        agents.append(deps._voice_agent)
    agents.extend(deps._voice_agents_by_provider.values())

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
        deps._voice_agent = None
        deps._voice_agents_by_provider = {}


def _get_stm():
    if deps._session_task_manager is None:
        deps._session_task_manager = deps.get_session_task_manager()
    return deps._session_task_manager


def _normalize_tts_provider_override(raw: str) -> str:
    key = raw.lower().strip()
    if key not in deps._ALLOWED_TTS_PROVIDERS:
        default_provider = (os.getenv("TTS_PROVIDER", "voicevox") or "voicevox").strip().lower()
        if deps._tts_require_primary_provider() and default_provider == "piper":
            raise HTTPException(
                status_code=400,
                detail=(
                    "ttsProvider overrides are disabled while "
                    "TTS_REQUIRE_PRIMARY_PROVIDER=true and TTS_PROVIDER=piper"
                ),
            )
        allowed = ", ".join(sorted(deps._ALLOWED_TTS_PROVIDERS))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ttsProvider: {raw!r} (allowed: {allowed})",
        )
    return key


def _tts_require_primary_provider() -> bool:
    raw = os.getenv("TTS_REQUIRE_PRIMARY_PROVIDER", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _get_voice_agent_for_provider_key(provider_key: str):
    """Lazily construct and cache VoiceAgent per TTS provider (for per-request override)."""
    if provider_key not in deps._voice_agents_by_provider:
        from backend.agents.voice_agent import VoiceAgent

        deps._voice_agents_by_provider[provider_key] = VoiceAgent(tts_provider=provider_key)
    return deps._voice_agents_by_provider[provider_key]


def _get_voice_agent():
    if deps._voice_agent is None:
        from backend.agents.voice_agent import VoiceAgent

        tts_provider = os.getenv("TTS_PROVIDER", "voicevox")
        deps._voice_agent = VoiceAgent(tts_provider=tts_provider)
    return deps._voice_agent


def _resolve_tts_agent(body: VoiceRequest):
    """Default env-based singleton, or a cached agent when ttsProvider is set."""
    if body.ttsProvider and body.ttsProvider.strip():
        requested_provider = body.ttsProvider.strip()
        default_provider = (os.getenv("TTS_PROVIDER", "voicevox") or "voicevox").strip().lower()
        if (
            deps._tts_require_primary_provider()
            and default_provider == "piper"
            and requested_provider.lower() != "piper"
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "ttsProvider overrides are disabled while "
                    "TTS_REQUIRE_PRIMARY_PROVIDER=true and TTS_PROVIDER=piper"
                ),
            )
        provider_key = deps._normalize_tts_provider_override(requested_provider)
        return deps._get_voice_agent_for_provider_key(provider_key)
    return deps._get_voice_agent()


def _get_stt_agent():
    if deps._stt_agent is None:
        from backend.agents.stt_agent import STTAgent

        # None のとき STTAgent 側で STT_PROVIDER / ENVIRONMENT に基づく既定を解決
        deps._stt_agent = STTAgent(stt_provider=os.getenv("STT_PROVIDER"))
    return deps._stt_agent


def _get_slide_agent():
    if deps._slide_agent is None:
        from backend.agents.slide_agent import SlideAgent

        deps._slide_agent = SlideAgent()
    return deps._slide_agent


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

    if len(audio_bytes) < deps.MIN_STT_AUDIO_BYTES:
        logger.info(
            "STT skipped: audio too short request_id=%s bytes=%s min=%s",
            request_id,
            len(audio_bytes),
            deps.MIN_STT_AUDIO_BYTES,
        )
        deps.log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=os.getenv("STT_PROVIDER"),
            language=body.language,
            success=False,
            error_type="AudioTooShort",
            audio_bytes=len(audio_bytes),
            timeout_s=deps._voice_stt_request_timeout_seconds(),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
            **deps._stt_warmup_telemetry_fields(),
        )
        return deps._stt_failure_response(
            body=body,
            request_id=request_id,
            error="No speech detected",
            error_type="AudioTooShort",
        )

    try:
        stt_call = deps._get_stt_agent().speech_to_text(
            audio_bytes,
            language=body.language,
            conversation_stage=body.conversationStage,
        )
        stt_timeout_s = deps._voice_stt_request_timeout_seconds()
        if stt_timeout_s > 0:
            stt_result = await asyncio.wait_for(stt_call, timeout=stt_timeout_s)
        else:
            stt_result = await stt_call
    except asyncio.TimeoutError:
        logger.warning(
            "STT request timed out: request_id=%s timeout_s=%.2f",
            request_id,
            deps._voice_stt_request_timeout_seconds(),
        )
        deps.log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=os.getenv("STT_PROVIDER"),
            language=body.language,
            success=False,
            error_type="TimeoutError",
            audio_bytes=len(audio_bytes),
            timeout_s=deps._voice_stt_request_timeout_seconds(),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
            **deps._stt_warmup_telemetry_fields(),
        )
        return deps._stt_failure_response(
            body=body,
            request_id=request_id,
            error="No speech detected",
            provider=os.getenv("STT_PROVIDER"),
            error_type="TimeoutError",
        )
    except RuntimeError as exc:
        logger.warning("STT runtime failure: %s", exc)
        deps.log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=os.getenv("STT_PROVIDER"),
            language=body.language,
            success=False,
            error_type=type(exc).__name__,
            audio_bytes=len(audio_bytes),
            timeout_s=deps._voice_stt_request_timeout_seconds(),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
            **deps._stt_warmup_telemetry_fields(),
        )
        return deps._stt_failure_response(
            body=body,
            request_id=request_id,
            error="No speech detected",
            error_type=type(exc).__name__,
        )

    if not stt_result["success"]:
        deps.log_stt_event(
            event="stt_request_complete",
            request_id=request_id,
            provider=stt_result.get("provider"),
            language=body.language,
            success=False,
            error_type=stt_result.get("error"),
            audio_bytes=len(audio_bytes),
            timeout_s=deps._voice_stt_request_timeout_seconds(),
            stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
            stt_base64_decode_duration_ms=base64_decode_duration_ms,
            **deps._stt_warmup_telemetry_fields(),
        )
        return deps._stt_failure_response(
            body=body,
            request_id=request_id,
            error=stt_result.get("error", "STT failed"),
            provider=stt_result.get("provider"),
        )

    deps.log_stt_event(
        event="stt_request_complete",
        request_id=request_id,
        provider=stt_result.get("provider"),
        language=stt_result.get("language") or body.language,
        success=True,
        audio_bytes=len(audio_bytes),
        transcript_chars=len(stt_result.get("transcript") or ""),
        timeout_s=deps._voice_stt_request_timeout_seconds(),
        stt_request_duration_ms=int((time.perf_counter() - stt_request_started_at) * 1000),
        stt_base64_decode_duration_ms=base64_decode_duration_ms,
        **deps._stt_warmup_telemetry_fields(),
    )
    return deps.VoiceResponse(
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
        upstreamStatus=deps._upstream_status("stt", provider=stt_result.get("provider")),
    )


async def _handle_stt_warmup(body: VoiceRequest, request_id: str) -> VoiceResponse:
    """Start STT model warmup without tying it to the user audio request."""
    snapshot = await deps.get_stt_warmup_service().warmup(
        provider=os.getenv("STT_PROVIDER"),
        warmup_factory=lambda: deps._get_stt_agent().warmup(),
        session_id=body.sessionId,
        wait=False,
    )
    return deps.VoiceResponse(
        success=True,
        sessionId=body.sessionId,
        sttWarmupStatus=snapshot.status,
        sttWarmupProvider=snapshot.provider,
        sttWarmupError=snapshot.error,
        sttWarmupDurationMs=snapshot.duration_ms,
        requestId=request_id,
        phase="warmup",
        upstreamStatus=deps._upstream_status(
            "stt_warmup",
            ok=snapshot.error is None,
            provider=snapshot.provider,
            status=snapshot.status,
        ),
    )


async def voice_get_api(action: str = ""):
    if action == "supported_languages":
        return {
            "languages": [
                {"code": "ja", "name": "日本語"},
                {"code": "en", "name": "English"},
            ]
        }
    default_tts = (os.getenv("TTS_PROVIDER", "voicevox") or "voicevox").strip().lower()
    tts_providers = [
        {"id": "voicevox", "label": "VoiceVox"},
        {"id": "piper", "label": "Piper-plus"},
    ]
    override_enabled = True
    if deps._tts_require_primary_provider() and default_tts == "piper":
        tts_providers = [{"id": "piper", "label": "Piper-plus"}]
        override_enabled = False
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
        "ttsProviderOverrideEnabled": override_enabled,
        "ttsProviders": tts_providers,
    }


async def voice_api(request: Request, body: VoiceRequest):
    """
    Voice endpoint.

    Frontend proxy note: `/api/voice` responses include requestId, phase, and
    upstreamStatus for `frontend/src/app/api/voice` error display and tracing.
    """
    request_id = deps._request_id_from_request(request)
    try:
        if body.action == "text_to_speech":
            if not body.text or not body.text.strip():
                raise HTTPException(status_code=400, detail="Missing text for text_to_speech")

            if body.sessionId:
                await deps._get_stm().register_session(body.sessionId)

            tts_task = asyncio.create_task(
                deps._resolve_tts_agent(body).text_to_speech(
                    text=body.text,
                    language=body.language or "ja",
                    emotion=body.emotion,  # Use requested emotion for TTS
                )
            )
            if body.sessionId:
                await deps._get_stm().set_tts_task(body.sessionId, tts_task)

            result = await tts_task

            if not result.get("success"):
                return deps.VoiceResponse(
                    success=False,
                    error=result.get("error", "TTS failed"),
                    emotion=result.get("emotion"),
                    audioFormat=result.get("format"),
                    sessionId=body.sessionId,
                    requestId=request_id,
                    phase="text_to_speech",
                    upstreamStatus=deps._upstream_status(
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
                return deps.VoiceResponse(
                    success=False,
                    error=error_message,
                    emotion=result.get("emotion"),
                    audioFormat=audio_format,
                    sessionId=body.sessionId,
                    requestId=request_id,
                    phase="text_to_speech",
                    upstreamStatus=deps._upstream_status(
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
                    from backend.utils.audio_encode import (
                        wav_base64_to_mp3_base64_async,
                    )

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
                    await deps._get_stm().set_tts_buffer(body.sessionId, BytesIO(audio_bytes))
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
                vrm_out = await deps._generate_vrm_control_for_lab_tts(
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
            return deps.VoiceResponse(
                success=True,
                audioResponse=audio_b64,
                audioFormat=audio_format,
                emotion=result.get("emotion"),
                sessionId=body.sessionId,
                cleanText=clean_txt if body.includeVrmControl else None,
                vrmControl=vrm_out if body.includeVrmControl else None,
                requestId=request_id,
                phase="text_to_speech",
                upstreamStatus=deps._upstream_status(
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
            return deps.VoiceResponse(
                success=True,
                sessionId=body.sessionId,
                requestId=request_id,
                phase="set_language",
                upstreamStatus=deps._upstream_status("set_language"),
            )

        elif body.action == "speech_to_text":
            return await deps._handle_stt(body, request_id)

        elif body.action == "warmup":
            return await deps._handle_stt_warmup(body, request_id)

        elif body.action == "interrupt":
            if not body.sessionId:
                raise HTTPException(status_code=400, detail="Missing sessionId for interrupt")

            cancelled = await deps._get_stm().cancel_all_tasks(body.sessionId)
            return deps.VoiceResponse(
                success=True,
                sessionId=body.sessionId,
                interruptStatus="cancelled" if cancelled else "no_active_task",
                requestId=request_id,
                phase="interrupt",
                upstreamStatus=deps._upstream_status("interrupt", cancelled=cancelled),
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


def create_router(rate_limit: Callable[[str], Callable[[Any], Any]]) -> APIRouter:
    router = APIRouter(tags=["voice"])
    router.add_api_route("/api/voice", voice_get_api, methods=["GET"])
    router.add_api_route(
        "/api/voice/filler",
        rate_limit("60/minute")(voice_filler_api),
        methods=["POST"],
        response_model=FillerResponse,
    )
    router.add_api_route(
        "/api/voice",
        rate_limit("20/minute")(voice_api),
        methods=["POST"],
        response_model=VoiceResponse,
    )
    return router
