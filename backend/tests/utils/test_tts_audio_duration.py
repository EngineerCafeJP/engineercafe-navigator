"""Tests for backend.utils.tts_audio_duration."""

import io
import wave

from backend.utils.tts_audio_duration import (
    audio_duration_seconds_from_audio_bytes,
    audio_duration_seconds_from_base64,
)


def _minimal_wav_bytes(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Build a minimal valid WAV (silence) in memory."""
    nframes = int(duration_sec * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * nframes)
    return buf.getvalue()


def test_wav_duration_from_bytes():
    raw = _minimal_wav_bytes(duration_sec=0.25, sample_rate=8000)
    d = audio_duration_seconds_from_audio_bytes(raw)
    assert d is not None
    assert abs(d - 0.25) < 0.01


def test_wav_duration_from_base64():
    import base64

    raw = _minimal_wav_bytes(0.1, 8000)
    b64 = base64.b64encode(raw).decode("ascii")
    d = audio_duration_seconds_from_base64(b64)
    assert d is not None
    assert abs(d - 0.1) < 0.02
