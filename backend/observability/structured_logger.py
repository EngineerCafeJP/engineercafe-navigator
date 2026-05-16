"""Structured observability logs consumed by Cloud Logging metrics."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Literal, cast

CHAT_RESPONSE_EVENT = "chat_response"
CHAT_RESPONSE_LOGGER_NAME = "backend.observability.chat_response"
STT_LOGGER_NAME = "backend.observability.stt"
TTS_LOGGER_NAME = "backend.observability.tts"
TTS_CACHE_LOGGER_NAME = "backend.observability.tts_cache"
MEMORY_LOGGER_NAME = "backend.observability.memory"

LtmStoreWrite = Literal["success", "failed", "skipped"]

_CHAT_LOG_HANDLER_MARKER = "_engineer_cafe_chat_response_json_handler"
_STT_LOG_HANDLER_MARKER = "_engineer_cafe_stt_json_handler"
_TTS_LOG_HANDLER_MARKER = "_engineer_cafe_tts_json_handler"
_TTS_CACHE_LOG_HANDLER_MARKER = "_engineer_cafe_tts_cache_json_handler"
_MEMORY_LOG_HANDLER_MARKER = "_engineer_cafe_memory_json_handler"


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


def _coerce_agent_class(value: Any) -> str | None:
    if not value:
        return None
    agent = str(value)
    if agent.endswith("Agent") or agent in {"SafetyGuard"}:
        return agent
    return None


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
    sources = _coerce_sources(metadata.get("sources"))
    rag_fallback = bool(
        metadata.get("rag_fallback")
        or metadata.get("fallback")
        or "fallback" in {source.lower() for source in sources}
    )

    return {
        "event": CHAT_RESPONSE_EVENT,
        "request_id": request_id,
        "language": language or "unknown",
        "route": str(route),
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
    logger.info(
        CHAT_RESPONSE_EVENT,
        extra={
            **payload,
            "observability_payload": payload,
        },
    )
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
    logger.info(
        event,
        extra={
            **payload,
            "observability_payload": payload,
        },
    )
    return payload


def log_tts_event(*, event: str, **fields: Any) -> dict[str, Any]:
    """Log a TTS observability event and return the payload for tests."""

    payload = build_stt_event_payload(event=event, **fields)
    logger = _get_tts_logger()
    logger.info(event, extra={**payload, "observability_payload": payload})
    return payload


def log_memory_event(*, event: str, **fields: Any) -> dict[str, Any]:
    """Log a memory/reception/LTM observability event and return the payload."""

    payload = build_stt_event_payload(event=event, **fields)
    logger = _get_memory_logger()
    logger.info(event, extra={**payload, "observability_payload": payload})
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
    logger.info("tts_cache", extra={**payload, "observability_payload": payload})
