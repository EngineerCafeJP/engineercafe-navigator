"""Structured observability logs consumed by Cloud Logging metrics."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Literal, cast

CHAT_RESPONSE_EVENT = "chat_response"
STT_QWEN_COMPLETE_EVENT = "stt_qwen_complete"
STT_WINNER_EVENT = "stt_winner"
TTS_SYNTHESIS_START_EVENT = "tts_synthesis_start"
TTS_SYNTHESIS_COMPLETE_EVENT = "tts_synthesis_complete"
TTS_SYNTHESIS_ERROR_EVENT = "tts_synthesis_error"
AGENT_ROUTING_EVENT = "agent_routing"
VOICE_ROUND_TRIP_EVENT = "voice_round_trip"
FRONTEND_TELEMETRY_EVENTS = {
    "voice_state_transition",
    "thinking_watchdog_expire",
    "fallback_tts_triggered",
    "user_interaction_gate_timeout",
    "audio_playback_failed",
}

CHAT_RESPONSE_LOGGER_NAME = "backend.observability.chat_response"
STT_LOGGER_NAME = "backend.observability.stt"
TTS_LOGGER_NAME = "backend.observability.tts"
TTS_CACHE_LOGGER_NAME = "backend.observability.tts_cache"
MEMORY_LOGGER_NAME = "backend.observability.memory"
AGENT_ROUTING_LOGGER_NAME = "backend.observability.agent_routing"
VOICE_ROUND_TRIP_LOGGER_NAME = "backend.observability.voice_round_trip"
FRONTEND_TELEMETRY_LOGGER_NAME = "backend.observability.frontend_telemetry"

LtmStoreWrite = Literal["success", "failed", "skipped"]

_CHAT_LOG_HANDLER_MARKER = "_engineer_cafe_chat_response_json_handler"
_STT_LOG_HANDLER_MARKER = "_engineer_cafe_stt_json_handler"
_TTS_LOG_HANDLER_MARKER = "_engineer_cafe_tts_json_handler"
_TTS_CACHE_LOG_HANDLER_MARKER = "_engineer_cafe_tts_cache_json_handler"
_MEMORY_LOG_HANDLER_MARKER = "_engineer_cafe_memory_json_handler"
_AGENT_ROUTING_LOG_HANDLER_MARKER = "_engineer_cafe_agent_routing_json_handler"
_VOICE_ROUND_TRIP_LOG_HANDLER_MARKER = "_engineer_cafe_voice_round_trip_json_handler"
_FRONTEND_TELEMETRY_LOG_HANDLER_MARKER = "_engineer_cafe_frontend_telemetry_json_handler"
_LOG_RECORD_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class _ChatResponseJsonFormatter(logging.Formatter):
    """Emit only the observability payload as a top-level JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "observability_payload", None)
        if not isinstance(payload, dict):
            payload = {"event": CHAT_RESPONSE_EVENT, "message": record.getMessage()}
        return json.dumps(payload, ensure_ascii=False, default=str)


class _SttJsonFormatter(logging.Formatter):
    """Emit STT observability payloads as top-level JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "observability_payload", None)
        if not isinstance(payload, dict):
            payload = {"event": getattr(record, "event", "stt_event")}
        return json.dumps(payload, ensure_ascii=False, default=str)


def _propagate_observability_logs() -> bool:
    raw = os.getenv("OBSERVABILITY_LOG_PROPAGATE")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("ENVIRONMENT") != "production"


def _get_chat_response_logger() -> logging.Logger:
    logger = logging.getLogger(CHAT_RESPONSE_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = _propagate_observability_logs()

    if not any(getattr(handler, _CHAT_LOG_HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ChatResponseJsonFormatter())
        setattr(handler, _CHAT_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_stt_logger() -> logging.Logger:
    logger = logging.getLogger(STT_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = _propagate_observability_logs()

    if not any(getattr(handler, _STT_LOG_HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_SttJsonFormatter())
        setattr(handler, _STT_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_tts_cache_logger() -> logging.Logger:
    logger = logging.getLogger(TTS_CACHE_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(
        getattr(handler, _TTS_CACHE_LOG_HANDLER_MARKER, False) for handler in logger.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ChatResponseJsonFormatter())
        setattr(handler, _TTS_CACHE_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_tts_logger() -> logging.Logger:
    logger = logging.getLogger(TTS_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = _propagate_observability_logs()

    if not any(getattr(handler, _TTS_LOG_HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_SttJsonFormatter())
        setattr(handler, _TTS_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_memory_logger() -> logging.Logger:
    logger = logging.getLogger(MEMORY_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = _propagate_observability_logs()

    if not any(getattr(handler, _MEMORY_LOG_HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_SttJsonFormatter())
        setattr(handler, _MEMORY_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_agent_routing_logger() -> logging.Logger:
    logger = logging.getLogger(AGENT_ROUTING_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = _propagate_observability_logs()

    if not any(
        getattr(handler, _AGENT_ROUTING_LOG_HANDLER_MARKER, False) for handler in logger.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_SttJsonFormatter())
        setattr(handler, _AGENT_ROUTING_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_voice_round_trip_logger() -> logging.Logger:
    logger = logging.getLogger(VOICE_ROUND_TRIP_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = _propagate_observability_logs()

    if not any(
        getattr(handler, _VOICE_ROUND_TRIP_LOG_HANDLER_MARKER, False) for handler in logger.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_SttJsonFormatter())
        setattr(handler, _VOICE_ROUND_TRIP_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_frontend_telemetry_logger() -> logging.Logger:
    logger = logging.getLogger(FRONTEND_TELEMETRY_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = _propagate_observability_logs()

    if not any(
        getattr(handler, _FRONTEND_TELEMETRY_LOG_HANDLER_MARKER, False)
        for handler in logger.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_SttJsonFormatter())
        setattr(handler, _FRONTEND_TELEMETRY_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _current_request_id() -> str | None:
    try:
        from backend.utils.structured_logging import get_request_id

        return get_request_id()
    except Exception:
        return None


def _coerce_sources(raw_sources: Any) -> list[str]:
    if raw_sources is None:
        return []
    if isinstance(raw_sources, str):
        return [raw_sources]
    if isinstance(raw_sources, dict):
        return [f"{key}:{value}" for key, value in raw_sources.items()]
    if isinstance(raw_sources, (list, tuple, set)):
        return [str(source) for source in raw_sources if source is not None]
    return [str(raw_sources)]


def _coerce_ltm_store_write(value: Any) -> LtmStoreWrite:
    if value in ("success", "failed", "skipped"):
        return cast(LtmStoreWrite, value)
    if value is True:
        return "success"
    if value is False:
        return "failed"
    return "skipped"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_optional_latency_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _coerce_latency_ms(value: Any) -> int:
    latency = _coerce_optional_latency_ms(value)
    return latency if latency is not None else 0


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_confidence(value: Any) -> float | None:
    confidence = _coerce_optional_float(value)
    if confidence is None:
        return None
    return max(0.0, min(1.0, confidence))


def _coerce_alternatives(raw_alternatives: Any) -> list[dict[str, Any]]:
    if raw_alternatives is None:
        return []

    alternatives: list[dict[str, Any]] = []
    if isinstance(raw_alternatives, dict):
        iterable = raw_alternatives.items()
    elif isinstance(raw_alternatives, (list, tuple)):
        iterable = raw_alternatives
    else:
        iterable = [raw_alternatives]

    for item in iterable:
        name: Any
        score: Any
        if isinstance(item, dict):
            name = item.get("name") or item.get("provider") or item.get("route")
            score = item.get("score") or item.get("confidence")
        elif isinstance(item, tuple) and len(item) >= 2:
            name, score = item[0], item[1]
        else:
            name, score = item, None

        if name is None:
            continue
        alternative: dict[str, Any] = {"name": str(name)}
        coerced_score = _coerce_optional_float(score)
        if coerced_score is not None:
            alternative["score"] = coerced_score
        alternatives.append(alternative)

    return alternatives


def _coerce_agent_class(value: Any) -> str | None:
    if not value:
        return None
    agent = str(value)
    if agent.endswith("Agent") or agent in {"SafetyGuard"}:
        return agent
    return None


def _coerce_optional_text(value: Any, *, max_length: int = 500) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:max_length] if text else None


def _mask_pii_text(text: str) -> str:
    try:
        from backend.utils.pii_scanner import scan_and_mask

        masked, _ = scan_and_mask(text)
        return masked
    except Exception:
        return text


def _stt_log_transcript_enabled() -> bool:
    raw = os.getenv("STT_LOG_TRANSCRIPT", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _safe_log_extra(payload: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {"observability_payload": payload}
    for key, value in payload.items():
        extra_key = f"payload_{key}" if key in _LOG_RECORD_RESERVED else key
        extra[extra_key] = value
    return extra


def _log_payload(logger: logging.Logger, event: str, payload: dict[str, Any]) -> None:
    logger.info(event, extra=_safe_log_extra(payload))


def _record_otel_payload(payload: dict[str, Any]) -> None:
    try:
        from backend.observability.otel_meter import get_otel_meter

        get_otel_meter().record_event_payload(payload)
    except Exception:
        return


def build_chat_response_payload(
    *,
    request_id: str | None,
    language: str | None,
    metadata: dict[str, Any],
    latency_ms: int,
) -> dict[str, Any]:
    route = (
        metadata.get("route")
        or metadata.get("category")
        or metadata.get("request_type")
        or metadata.get("reception_target_agent")
        or "unknown"
    )
    intent = metadata.get("intent") or metadata.get("category") or metadata.get("request_type")
    sources = _coerce_sources(metadata.get("sources"))
    rag_fallback = bool(
        metadata.get("rag_fallback")
        or metadata.get("fallback")
        or "fallback" in {source.lower() for source in sources}
    )

    payload = {
        "event": CHAT_RESPONSE_EVENT,
        "request_id": request_id,
        "language": language or "unknown",
        "route": str(route),
        "agent_route": str(metadata.get("agent_route") or route),
        "intent": str(intent) if intent else None,
        "confidence": _coerce_confidence(metadata.get("confidence")),
        "agent_class": _coerce_agent_class(metadata.get("agent")),
        "provider": str(metadata.get("provider") or metadata.get("llm_provider") or "unknown"),
        "model": str(metadata.get("model") or metadata.get("llm_model") or "unknown"),
        "llm_latency_ms": _coerce_optional_latency_ms(metadata.get("llm_latency_ms")),
        "sources": sources,
        "rag_fallback": rag_fallback,
        "hallucination_flag": _coerce_bool(metadata.get("hallucination_flag", False)),
        "ltm_store_write": _coerce_ltm_store_write(metadata.get("ltm_store_write")),
        "latency_ms": latency_ms,
    }
    if _stt_log_transcript_enabled():
        transcript = _coerce_optional_text(metadata.get("transcript") or metadata.get("query"))
        if transcript is not None:
            payload["transcript"] = _mask_pii_text(transcript)
    return payload


def log_chat_response(
    *,
    request_id: str | None,
    language: str | None,
    metadata: dict[str, Any] | None,
    latency_ms: int,
) -> dict[str, Any]:
    """Log the `/api/chat` response observability schema and return it for tests."""

    payload = build_chat_response_payload(
        request_id=request_id,
        language=language,
        metadata=metadata or {},
        latency_ms=latency_ms,
    )
    logger = _get_chat_response_logger()
    _log_payload(logger, CHAT_RESPONSE_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def build_stt_event_payload(*, event: str, **fields: Any) -> dict[str, Any]:
    """Build the STT structured log payload used by profiling scripts."""

    request_id = fields.pop("request_id", None) or _current_request_id()
    return {
        "event": event,
        "request_id": request_id,
        **fields,
    }


def log_stt_event(*, event: str, **fields: Any) -> dict[str, Any]:
    """Log an STT observability event and return the payload for tests."""

    payload = build_stt_event_payload(event=event, **fields)
    logger = _get_stt_logger()
    _log_payload(logger, event, payload)
    _record_otel_payload(payload)
    return payload


def log_tts_event(*, event: str, **fields: Any) -> dict[str, Any]:
    """Log a TTS observability event and return the payload for tests."""

    payload = build_stt_event_payload(event=event, **fields)
    logger = _get_tts_logger()
    _log_payload(logger, event, payload)
    _record_otel_payload(payload)
    return payload


def log_memory_event(*, event: str, **fields: Any) -> dict[str, Any]:
    """Log a memory/reception/LTM observability event and return the payload."""

    payload = build_stt_event_payload(event=event, **fields)
    logger = _get_memory_logger()
    _log_payload(logger, event, payload)
    return payload


def log_reception_transition(
    *,
    session_id: str | None,
    from_stage: str | None,
    to_stage: str | None,
    action: str | None = None,
    status: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Log a reception workflow stage transition."""

    return log_memory_event(
        event="reception_transition",
        session_id=session_id,
        from_stage=from_stage,
        to_stage=to_stage,
        action=action,
        status=status,
        **fields,
    )


def log_reception_bypass_decision(
    *,
    bypass: bool,
    reason: str,
    stage: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Log whether an utterance during reception was routed out of the reception flow.

    ``reason`` names the branch that decided the outcome, so a production log alone
    tells you why a question was (or was not) answered by an agent. Before #928 this
    path emitted nothing and the same question could be handled two different ways
    with no way to tell them apart short of inspecting the database.
    """

    return log_memory_event(
        event="reception_bypass_decision",
        bypass=bypass,
        reason=reason,
        stage=stage,
        **fields,
    )


def log_ltm_promote(
    *,
    status: str,
    user_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Log a long-term-memory promotion event."""

    return log_memory_event(
        event="ltm_promote",
        status=status,
        user_id=user_id,
        **fields,
    )


def log_tts_cache_event(*, hit: bool, cache_key: str, language: str | None = None) -> None:
    """Log TTS cache hit/miss as structured JSON."""

    logger = _get_tts_cache_logger()
    payload = {
        "event": "tts_cache",
        "request_id": _current_request_id(),
        "tts_cache_hit": hit,
        "cache_key": cache_key,
        "language": language or "unknown",
    }
    _log_payload(logger, "tts_cache", payload)


def build_stt_qwen_complete_payload(
    *,
    provider: str = "qwen-primary",
    language: str | None,
    audio_duration_ms: int | float | None,
    latency_ms: int | float | None,
    confidence: float | str | None,
    transcript_length: int | None,
    winner: bool,
    session_id: str | None = None,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    transcript = fields.pop("transcript", None)
    payload = build_stt_event_payload(
        event=STT_QWEN_COMPLETE_EVENT,
        request_id=request_id,
        provider=provider,
        language=language or "unknown",
        audio_duration_ms=_coerce_latency_ms(audio_duration_ms),
        latency_ms=_coerce_latency_ms(latency_ms),
        confidence=_coerce_confidence(confidence),
        transcript_length=max(0, int(transcript_length or 0)),
        winner=bool(winner),
        session_id=session_id,
        **fields,
    )
    if _stt_log_transcript_enabled():
        text = _coerce_optional_text(transcript, max_length=500)
        if text is not None:
            payload["transcript"] = _mask_pii_text(text)
    return payload


def log_stt_qwen_complete(**fields: Any) -> dict[str, Any]:
    payload = build_stt_qwen_complete_payload(**fields)
    logger = _get_stt_logger()
    _log_payload(logger, STT_QWEN_COMPLETE_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def build_stt_winner_payload(
    *,
    winner_provider: str,
    language: str | None = None,
    confidence: float | str | None = None,
    alternatives: Any = None,
    latency_ms: int | float | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    return build_stt_event_payload(
        event=STT_WINNER_EVENT,
        request_id=request_id,
        winner_provider=winner_provider,
        language=language or "unknown",
        confidence=_coerce_confidence(confidence),
        alternatives=_coerce_alternatives(alternatives),
        latency_ms=_coerce_optional_latency_ms(latency_ms),
        session_id=session_id,
        **fields,
    )


def log_stt_winner(**fields: Any) -> dict[str, Any]:
    payload = build_stt_winner_payload(**fields)
    logger = _get_stt_logger()
    _log_payload(logger, STT_WINNER_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def build_tts_synthesis_payload(
    *,
    event: str,
    provider: str,
    language: str | None = None,
    voice: str | None = None,
    text_length: int | None = None,
    latency_ms: int | float | None = None,
    audio_duration_ms: int | float | None = None,
    fallback_used: bool = False,
    fallback_provider: str | None = None,
    success: bool | None = None,
    error_type: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = build_stt_event_payload(
        event=event,
        request_id=request_id,
        provider=provider,
        language=language or "unknown",
        voice=voice,
        text_length=max(0, int(text_length or 0)),
        latency_ms=_coerce_optional_latency_ms(latency_ms),
        audio_duration_ms=_coerce_optional_latency_ms(audio_duration_ms),
        fallback_used=bool(fallback_used),
        fallback_provider=fallback_provider,
        success=success,
        error_type=error_type,
        session_id=session_id,
        **fields,
    )
    return {key: value for key, value in payload.items() if value is not None}


def log_tts_synthesis_start(**fields: Any) -> dict[str, Any]:
    payload = build_tts_synthesis_payload(
        event=TTS_SYNTHESIS_START_EVENT,
        success=None,
        **fields,
    )
    logger = _get_tts_logger()
    _log_payload(logger, TTS_SYNTHESIS_START_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def log_tts_synthesis_complete(**fields: Any) -> dict[str, Any]:
    payload = build_tts_synthesis_payload(
        event=TTS_SYNTHESIS_COMPLETE_EVENT,
        success=True,
        **fields,
    )
    logger = _get_tts_logger()
    _log_payload(logger, TTS_SYNTHESIS_COMPLETE_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def log_tts_synthesis_error(**fields: Any) -> dict[str, Any]:
    payload = build_tts_synthesis_payload(
        event=TTS_SYNTHESIS_ERROR_EVENT,
        success=False,
        **fields,
    )
    logger = _get_tts_logger()
    _log_payload(logger, TTS_SYNTHESIS_ERROR_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def build_agent_routing_payload(
    *,
    routed_to: str,
    intent: str | None = None,
    confidence: float | str | None = None,
    fallback_used: bool = False,
    alternatives: Any = None,
    latency_ms: int | float | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    return build_stt_event_payload(
        event=AGENT_ROUTING_EVENT,
        request_id=request_id,
        routed_to=routed_to,
        intent=intent,
        confidence=_coerce_confidence(confidence),
        fallback_used=bool(fallback_used),
        alternatives=_coerce_alternatives(alternatives),
        latency_ms=_coerce_latency_ms(latency_ms),
        session_id=session_id,
        **fields,
    )


def log_agent_routing(**fields: Any) -> dict[str, Any]:
    payload = build_agent_routing_payload(**fields)
    logger = _get_agent_routing_logger()
    _log_payload(logger, AGENT_ROUTING_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def build_voice_round_trip_payload(
    *,
    stt_ms: int | float | None,
    chat_ms: int | float | None,
    tts_ms: int | float | None,
    total_ms: int | float | None = None,
    success: bool,
    error_type: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    stt = _coerce_latency_ms(stt_ms)
    chat = _coerce_latency_ms(chat_ms)
    tts = _coerce_latency_ms(tts_ms)
    total = _coerce_optional_latency_ms(total_ms)
    return build_stt_event_payload(
        event=VOICE_ROUND_TRIP_EVENT,
        request_id=request_id,
        stt_ms=stt,
        chat_ms=chat,
        tts_ms=tts,
        total_ms=total if total is not None else stt + chat + tts,
        success=bool(success),
        error_type=error_type,
        session_id=session_id,
        **fields,
    )


def log_voice_round_trip(**fields: Any) -> dict[str, Any]:
    payload = build_voice_round_trip_payload(**fields)
    logger = _get_voice_round_trip_logger()
    _log_payload(logger, VOICE_ROUND_TRIP_EVENT, payload)
    _record_otel_payload(payload)
    return payload


def build_frontend_telemetry_payload(
    *,
    event: str,
    session_id: str | None = None,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    telemetry_event = event if event in FRONTEND_TELEMETRY_EVENTS else "frontend_telemetry"
    return build_stt_event_payload(
        event=telemetry_event,
        request_id=request_id,
        telemetry_event=event,
        source="frontend",
        session_id=session_id,
        **fields,
    )


def log_frontend_telemetry_event(**fields: Any) -> dict[str, Any]:
    payload = build_frontend_telemetry_payload(**fields)
    event = str(payload["event"])
    logger = _get_frontend_telemetry_logger()
    _log_payload(logger, event, payload)
    _record_otel_payload(payload)
    return payload
