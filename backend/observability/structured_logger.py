"""Structured observability logs consumed by Cloud Logging metrics."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Literal, cast

CHAT_RESPONSE_EVENT = "chat_response"
CHAT_RESPONSE_LOGGER_NAME = "backend.observability.chat_response"
STT_LOGGER_NAME = "backend.observability.stt"
TTS_LOGGER_NAME = "backend.observability.tts"
TTS_CACHE_LOGGER_NAME = "backend.observability.tts_cache"

LtmStoreWrite = Literal["success", "failed", "skipped"]

_CHAT_LOG_HANDLER_MARKER = "_engineer_cafe_chat_response_json_handler"
_STT_LOG_HANDLER_MARKER = "_engineer_cafe_stt_json_handler"
_TTS_LOG_HANDLER_MARKER = "_engineer_cafe_tts_json_handler"
_TTS_CACHE_LOG_HANDLER_MARKER = "_engineer_cafe_tts_cache_json_handler"


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


def _get_chat_response_logger() -> logging.Logger:
    logger = logging.getLogger(CHAT_RESPONSE_LOGGER_NAME)
    logger.setLevel(logging.INFO)

    if not any(getattr(handler, _CHAT_LOG_HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ChatResponseJsonFormatter())
        setattr(handler, _CHAT_LOG_HANDLER_MARKER, True)
        logger.addHandler(handler)

    return logger


def _get_stt_logger() -> logging.Logger:
    logger = logging.getLogger(STT_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = True

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
    logger.propagate = True

    if not any(getattr(handler, _TTS_LOG_HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_SttJsonFormatter())
        setattr(handler, _TTS_LOG_HANDLER_MARKER, True)
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
        or metadata.get("agent")
        or metadata.get("request_type")
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
        "sources": sources,
        "rag_fallback": rag_fallback,
        "hallucination_flag": bool(metadata.get("hallucination_flag", False)),
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
