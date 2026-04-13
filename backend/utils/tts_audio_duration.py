"""Decode TTS output bytes and return duration in seconds (WAV / MP3)."""

from __future__ import annotations

import io
import logging
import wave
from typing import Optional

logger = logging.getLogger(__name__)


def audio_duration_seconds_from_audio_bytes(data: bytes) -> Optional[float]:
    """
    Return playback duration for raw WAV or MP3 bytes.

    WAV: stdlib wave module.
    MP3: mutagen (no ffmpeg required).
    """
    if not data or len(data) < 12:
        return None

    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(data), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate <= 0:
                    return None
                return frames / float(rate)
        except Exception as e:
            logger.debug("WAV duration parse failed: %s", e)
            return None

    try:
        from mutagen.mp3 import MP3

        mp3 = MP3(io.BytesIO(data))
        length = mp3.info.length
        if length and length > 0:
            return float(length)
    except Exception as e:
        logger.debug("MP3 duration parse failed: %s", e)
    return None


def audio_duration_seconds_from_base64(b64: str) -> Optional[float]:
    """Decode base64 audio and return duration in seconds."""
    import base64

    try:
        cleaned = b64
        if "," in cleaned:
            cleaned = cleaned.split(",", 1)[1]
        _b64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        cleaned = "".join(c for c in cleaned if c in _b64)
        raw = base64.b64decode(cleaned, validate=False)
    except Exception as e:
        logger.debug("base64 decode failed: %s", e)
        return None
    return audio_duration_seconds_from_audio_bytes(raw)
