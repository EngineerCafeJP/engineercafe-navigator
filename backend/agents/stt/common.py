from __future__ import annotations

import concurrent.futures
import io
import logging
import math
import os
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx as _stt_httpx

from backend.observability.structured_logger import (
    log_stt_event as log_stt_event,
    log_stt_qwen_complete as log_stt_qwen_complete,
    log_stt_winner as log_stt_winner,
)

logger = logging.getLogger("backend.agents.stt_agent")

# ---------------------------------------------------------------------------
# Shared httpx client and executors
# ---------------------------------------------------------------------------

_stt_postprocess_client: Optional["_stt_httpx.AsyncClient"] = None
_qwen_stt_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
_vosk_stt_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None


def _is_real_openrouter_key(value: str) -> bool:
    """Reject placeholder / test API keys to avoid network calls in unit tests.

    backend/tests/conftest.py sets OPENROUTER_API_KEY=test-openrouter-key by
    default, which would otherwise trigger real OpenRouter HTTP calls during
    every Qwen ja transcribe in tests.
    """
    if not value:
        return False
    lower = value.lower()
    if lower.startswith("test-") or lower.startswith("placeholder"):
        return False
    if value in ("your_key_here", "your-key-here", "sk-or-v1-your-key-here"):
        return False
    return True


def _get_stt_postprocess_client() -> "_stt_httpx.AsyncClient":
    global _stt_postprocess_client
    if _stt_postprocess_client is None or _stt_postprocess_client.is_closed:
        _stt_postprocess_client = _stt_httpx.AsyncClient(timeout=3.0)
    return _stt_postprocess_client


def _get_qwen_stt_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _qwen_stt_executor
    if _qwen_stt_executor is None:
        _qwen_stt_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="qwen-stt",
        )
    return _qwen_stt_executor


def _get_vosk_stt_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _vosk_stt_executor
    if _vosk_stt_executor is None:
        _vosk_stt_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="vosk-stt",
        )
    return _vosk_stt_executor


WAV_RIFF_HEADER = b"RIFF"
MIN_WAV_HEADER_BYTES = 44
MAX_AUDIO_UPLOAD_BYTES = 10 * 1024 * 1024
TRUNCATED_WAV_AUDIO_ERROR = (
    "Audio data must be in WAV format (RIFF) and include a complete WAV header "
    "(minimum 44 bytes). Received truncated data."
)
AUDIO_CONVERSION_ERROR_PREFIX = "Failed to convert WebM audio to WAV for STT transcription"
PYDUB_IMPORT_ERROR = "WebM audio conversion requires pydub. Install backend dependencies with pydub included."  # noqa: E501
_MEDIA_CONTAINER_SIGNATURES = (
    b"\x1a\x45\xdf\xa3",  # WebM / Matroska EBML
    b"OggS",
    b"fLaC",
    b"ID3",
)


def _duration_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _looks_like_non_wav_media(audio_data: bytes) -> bool:
    return any(audio_data.startswith(signature) for signature in _MEDIA_CONTAINER_SIGNATURES)


def _wav_metadata(audio_data: bytes) -> dict[str, Any]:
    if not audio_data.startswith(WAV_RIFF_HEADER) or len(audio_data) < MIN_WAV_HEADER_BYTES:
        return {}

    try:
        with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            duration_ms = int((frame_count / sample_rate) * 1000) if sample_rate else None
            return {
                "audio_sample_rate_hz": sample_rate,
                "audio_channels": wav_file.getnchannels(),
                "audio_sample_width_bytes": wav_file.getsampwidth(),
                "audio_frame_count": frame_count,
                "audio_duration_ms": duration_ms,
            }
    except Exception as exc:
        return {"audio_probe_error_type": type(exc).__name__}


def _parse_qwen_stt_timeout(raw_value: Optional[str], default: float = 24.0) -> float:
    """Parse QWEN_STT_TIMEOUT defensively; production once had `true`."""

    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        timeout = float(raw_value)
    except (TypeError, ValueError):
        logger.warning("Invalid QWEN_STT_TIMEOUT=%r; falling back to %.1fs", raw_value, default)
        return default

    if not math.isfinite(timeout) or timeout <= 0:
        logger.warning("Invalid QWEN_STT_TIMEOUT=%r; falling back to %.1fs", raw_value, default)
        return default

    return timeout


class HedgedFallback(Exception):
    """Qwen exceeded the latency budget, so Vosk was allowed to race it."""


class RejectedVoskFallback(Exception):
    """Vosk fallback produced a transcript too risky to treat as user intent."""


class RejectedQwenPrimary(Exception):
    """Qwen primary produced a transcript too risky to treat as user intent."""


def _parse_qwen_stt_hedge_delay(
    raw_value: Optional[str],
    *,
    hard_timeout: float,
) -> float | None:
    """Parse the latency budget before Vosk fallback starts racing Qwen."""

    # Cloud Run /api/stt has a 12s HTTP budget in production; starting the
    # fallback earlier keeps slow Qwen runs from making Vosk finish just after
    # the caller has already timed out.
    default = 2.0
    if raw_value is None or raw_value.strip() == "":
        timeout = default
    else:
        try:
            timeout = float(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid QWEN_STT_HEDGE_DELAY_SECONDS=%r; falling back to %.1fs",
                raw_value,
                default,
            )
            timeout = default

    if not math.isfinite(timeout):
        logger.warning(
            "Invalid QWEN_STT_HEDGE_DELAY_SECONDS=%r; falling back to %.1fs",
            raw_value,
            default,
        )
        timeout = default

    if timeout <= 0:
        return None

    if timeout >= hard_timeout:
        adjusted = max(0.05, hard_timeout * 0.8)
        logger.warning(
            "QWEN_STT_HEDGE_DELAY_SECONDS %.2fs must be less than QWEN_STT_TIMEOUT %.2fs; "
            "using %.2fs",
            timeout,
            hard_timeout,
            adjusted,
        )
        return adjusted

    return timeout


def _parse_qwen_stt_hedge_grace(
    raw_value: Optional[str],
    *,
    hard_timeout: float,
    hedge_delay: float | None,
) -> float:
    """Parse the extra wait for Qwen after a hedged Vosk result is ready."""

    default = 6.0
    if raw_value is None or raw_value.strip() == "":
        timeout = default
    else:
        try:
            timeout = float(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid QWEN_STT_HEDGE_GRACE_SECONDS=%r; falling back to %.1fs",
                raw_value,
                default,
            )
            timeout = default

    if not math.isfinite(timeout):
        logger.warning(
            "Invalid QWEN_STT_HEDGE_GRACE_SECONDS=%r; falling back to %.1fs",
            raw_value,
            default,
        )
        timeout = default

    if timeout <= 0 or hedge_delay is None:
        return 0.0

    max_grace = max(0.0, hard_timeout - hedge_delay)
    if timeout >= max_grace:
        adjusted = max(0.0, max_grace * 0.8)
        logger.warning(
            "QWEN_STT_HEDGE_GRACE_SECONDS %.2fs plus hedge delay %.2fs must be less "
            "than QWEN_STT_TIMEOUT %.2fs; using %.2fs",
            timeout,
            hedge_delay,
            hard_timeout,
            adjusted,
        )
        return adjusted

    return timeout


def _parse_qwen_stt_latency_budget(
    raw_value: Optional[str],
    *,
    hard_timeout: float,
) -> float | None:
    """Parse the end-to-end STT budget used to cap optional Qwen grace wait."""

    default = 10.0
    if raw_value is None or raw_value.strip() == "":
        budget = default
    else:
        try:
            budget = float(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid QWEN_STT_LATENCY_BUDGET_SECONDS=%r; falling back to %.1fs",
                raw_value,
                default,
            )
            budget = default

    if not math.isfinite(budget):
        logger.warning(
            "Invalid QWEN_STT_LATENCY_BUDGET_SECONDS=%r; falling back to %.1fs",
            raw_value,
            default,
        )
        budget = default

    if budget <= 0:
        return None

    if budget >= hard_timeout:
        adjusted = max(0.05, hard_timeout * 0.8)
        logger.warning(
            "QWEN_STT_LATENCY_BUDGET_SECONDS %.2fs must be less than QWEN_STT_TIMEOUT %.2fs; "
            "using %.2fs",
            budget,
            hard_timeout,
            adjusted,
        )
        return adjusted

    return budget


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _stt_preload_vosk_fallback_enabled() -> bool:
    """Preload fallback Vosk models by default in production qwen-primary mode."""

    return _env_flag(
        "STT_PRELOAD_VOSK_FALLBACK",
        default=os.getenv("ENVIRONMENT") == "production" and not _env_flag("CI"),
    )


def _stt_preload_qwen_primary_enabled() -> bool:
    """Preload Qwen primary model before serving production traffic."""

    return _env_flag(
        "STT_PRELOAD_QWEN_PRIMARY",
        default=os.getenv("ENVIRONMENT") == "production" and not _env_flag("CI"),
    )


def _qwen_postprocess_enabled() -> bool:
    return os.getenv("STT_QWEN_POSTPROCESS_ENABLED", "false").lower() == "true"


def convert_audio_to_wav_bytes(audio_data: bytes) -> bytes:
    """Convert WebM/Opus audio bytes to 16kHz/16-bit/mono WAV PCM."""
    if len(audio_data) > MAX_AUDIO_UPLOAD_BYTES:
        raise ValueError(
            f"Audio payload too large ({len(audio_data)} bytes). "
            f"Maximum: {MAX_AUDIO_UPLOAD_BYTES} bytes."
        )

    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise ValueError(PYDUB_IMPORT_ERROR) from exc

    try:
        segment = AudioSegment.from_file(io.BytesIO(audio_data), format=None)
        normalized = segment.set_frame_rate(16000).set_sample_width(2).set_channels(1)
        wav_buffer = io.BytesIO()
        normalized.export(wav_buffer, format="wav")
        wav_bytes = wav_buffer.getvalue()
    except Exception as exc:
        raise ValueError(f"{AUDIO_CONVERSION_ERROR_PREFIX}: {exc}") from exc

    if not wav_bytes.startswith(WAV_RIFF_HEADER) or len(wav_bytes) < MIN_WAV_HEADER_BYTES:
        raise ValueError(
            f"{AUDIO_CONVERSION_ERROR_PREFIX}: converted output is not a valid WAV file"
        )

    return wav_bytes


@dataclass
class TranscriptionResult:
    """Vosk 認識結果（confidence 付き）"""

    text: str
    confidence: Optional[float]  # 平均 word confidence (0.0-1.0)
    language: str
    word_confidences: List[Dict[str, Any]] = field(default_factory=list)
