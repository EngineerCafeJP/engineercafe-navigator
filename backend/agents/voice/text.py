from __future__ import annotations

import logging
import os
import re
from typing import Dict

logger = logging.getLogger("backend.agents.voice_agent")

# -----------------------------------------------------------------------------
# Text processing and TTS configuration helpers
# -----------------------------------------------------------------------------


def preprocess_tts(text: str, lang: str) -> str:
    replacement = "ミーティング" if lang == "ja" else "meeting"
    # Keep it simple and robust (tests expect MTG to be replaced)
    return re.sub(r"MTG", replacement, text, flags=re.IGNORECASE)


# -----------------------------------------------------------------------------
# Text cleaning for TTS (TS voice-output-agent.ts cleanTextForTTS compatible)
# -----------------------------------------------------------------------------


def clean_text_for_tts(text: str) -> str:
    t = text

    # Remove fenced code blocks ```...``` (non-greedy, before inline markers)
    t = re.sub(r"```[\s\S]*?```", "", t)

    # Remove markdown emphasis markers
    t = re.sub(r"\*\*", "", t)
    t = re.sub(r"\*", "", t)

    # Numbered list prefixes
    t = re.sub(r"^\d+\.\s*", "", t, flags=re.M)

    # Bullet points: - item or * item at start of line
    t = re.sub(r"^[-\*]\s+", "", t, flags=re.M)

    # Headers (requires # at start of line)
    t = re.sub(r"^#+\s+", "", t, flags=re.M)

    # Blockquotes: > text at start of line
    t = re.sub(r"^>\s*", "", t, flags=re.M)

    # Horizontal rules: ---, ***, ___ (3+ chars on their own line)
    t = re.sub(r"^[-\*_]{3,}\s*$", "", t, flags=re.M)

    # HTML tags: replace with space to prevent word concatenation
    # (preserves non-HTML angle brackets like vector<int>, 1 < 2)
    t = re.sub(
        r"</?(?:br|p|div|span|strong|em|b|i|u|a|h[1-6]"
        r"|ul|ol|li|table|tr|td|th|hr|img|pre|code|blockquote)(?=[\s>/])[^>]*>",
        " ",
        t,
        flags=re.I,
    )

    # Table syntax: remove separator rows, convert data rows to plain text
    t = re.sub(r"^\|?[-:]+\|[-:|]+\|?\s*$", "", t, flags=re.M)
    t = re.sub(
        r"^\s*\|(.+\|.+)\s*$",
        lambda m: m.group(1).replace("|", " ").strip(),
        t,
        flags=re.M,
    )

    # Convert markdown links [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)

    # Inline code `code` -> code
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Normalize multiple newlines to single space
    t = re.sub(r"\n{2,}", " ", t)

    # Normalize whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


# -----------------------------------------------------------------------------
# Truncate by UTF-8 bytes
# -----------------------------------------------------------------------------

DEFAULT_TTS_MAX_BYTES = 900
MIN_CACHEABLE_TTS_AUDIO_BASE64_CHARS = 100
DEFAULT_TTS_CACHE_MAX_ENTRIES = 200
DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES = 5 * 1024 * 1024
DEFAULT_PIPER_PLUS_MAX_ATTEMPTS = 2
DEFAULT_PIPER_PLUS_RETRY_BACKOFF_SECONDS = 0.15
DEFAULT_PIPER_FAILURE_COOLDOWN_SECONDS = 10.0
_DEFAULT_TTS_TIMEOUTS: Dict[str, float] = {
    "piper": 20.0,
    "kokoro": 3.0,
    "voicevox": 4.0,
}


def tts_require_primary_provider() -> bool:
    raw = os.getenv("TTS_REQUIRE_PRIMARY_PROVIDER", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_tts_max_bytes() -> int:
    raw = os.getenv("TTS_MAX_BYTES", "").strip()
    if not raw:
        return DEFAULT_TTS_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid TTS_MAX_BYTES=%r; using %d", raw, DEFAULT_TTS_MAX_BYTES)
        return DEFAULT_TTS_MAX_BYTES
    return max(200, value)


def get_tts_cache_max_audio_bytes() -> int:
    raw = os.getenv("TTS_CACHE_MAX_AUDIO_BYTES", "").strip()
    if not raw:
        return DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid TTS_CACHE_MAX_AUDIO_BYTES=%r; using default", raw)
        return DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES
    if value <= 0:
        logger.warning("TTS_CACHE_MAX_AUDIO_BYTES must be positive; using default")
        return DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES
    return value


def get_piper_plus_max_attempts() -> int:
    raw = os.getenv("PIPER_PLUS_MAX_ATTEMPTS", "").strip()
    if not raw:
        return DEFAULT_PIPER_PLUS_MAX_ATTEMPTS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Invalid PIPER_PLUS_MAX_ATTEMPTS=%r; using %d",
            raw,
            DEFAULT_PIPER_PLUS_MAX_ATTEMPTS,
        )
        return DEFAULT_PIPER_PLUS_MAX_ATTEMPTS
    return max(1, min(value, 3))


def get_piper_plus_retry_backoff_seconds() -> float:
    raw = os.getenv("PIPER_PLUS_RETRY_BACKOFF_SECONDS", "").strip()
    if not raw:
        return DEFAULT_PIPER_PLUS_RETRY_BACKOFF_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Invalid PIPER_PLUS_RETRY_BACKOFF_SECONDS=%r; using %.2fs",
            raw,
            DEFAULT_PIPER_PLUS_RETRY_BACKOFF_SECONDS,
        )
        return DEFAULT_PIPER_PLUS_RETRY_BACKOFF_SECONDS
    return max(0.0, min(value, 1.0))


def get_tts_provider_failure_cooldown_seconds(provider: str) -> float:
    provider_key = (provider or "").strip().upper()
    env_names = [
        f"TTS_{provider_key}_FAILURE_COOLDOWN_SECONDS",
        "TTS_PROVIDER_FAILURE_COOLDOWN_SECONDS",
    ]
    for name in env_names:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid %s=%r; using %.1fs",
                name,
                raw,
                DEFAULT_PIPER_FAILURE_COOLDOWN_SECONDS,
            )
            return DEFAULT_PIPER_FAILURE_COOLDOWN_SECONDS
        return max(0.0, min(value, 60.0))

    if provider_key == "PIPER":
        return DEFAULT_PIPER_FAILURE_COOLDOWN_SECONDS
    return 0.0


def get_tts_timeout_seconds(provider: str, role: str = "primary") -> float:
    """Soft timeout for one TTS provider attempt.

    HTTP clients keep their larger socket timeouts, but the voice turn should
    move to the next recovery path quickly when a local TTS server is wedged.
    """

    provider_key = (provider or "").strip().lower()
    role_key = (role or "primary").strip().upper()
    env_names = [
        f"TTS_{provider_key.upper()}_{role_key}_TIMEOUT_SECONDS",
        f"TTS_{role_key}_TIMEOUT_SECONDS",
        f"TTS_{provider_key.upper()}_TIMEOUT_SECONDS",
    ]
    default = _DEFAULT_TTS_TIMEOUTS.get(provider_key, 4.0)

    for name in env_names:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning("Invalid %s=%r; using %.1fs", name, raw, default)
            return default
        if value <= 0:
            logger.warning("Invalid %s=%r; using %.1fs", name, raw, default)
            return default
        return max(0.05, value)
    return default


def truncate_by_bytes(text: str, max_bytes: int = 5000) -> str:
    def byte_len(s: str) -> int:
        return len(s.encode("utf-8"))

    truncated = text
    while truncated and byte_len(truncated) > max_bytes:
        if "。" in truncated:
            parts = [part for part in truncated.split("。") if part.strip()]
            if len(parts) > 1:
                parts.pop()
                truncated = "。".join(parts).strip()
                if truncated and not truncated.endswith("。"):
                    truncated += "。"
            else:
                truncated = truncated[:-10]
        else:
            # Generic fallback
            truncated = truncated[:-10]

    return truncated.strip()


def fallback_error_message(lang: str) -> str:
    return (
        "申し訳ございません。音声の生成に失敗しました。"
        if lang == "ja"
        else "I apologize, but I failed to generate the audio response."
    )
