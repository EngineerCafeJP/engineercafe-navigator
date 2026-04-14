"""Audio re-encoding helpers (pydub + ffmpeg)."""

from __future__ import annotations

import base64
from io import BytesIO


def wav_base64_to_mp3_base64(wav_b64: str) -> str:
    """Decode base64 WAV, export as MP3, return base64 MP3."""
    from pydub import AudioSegment

    wav_bytes = base64.b64decode(wav_b64)
    segment = AudioSegment.from_file(BytesIO(wav_bytes), format="wav")
    out = BytesIO()
    segment.export(out, format="mp3")
    return base64.b64encode(out.getvalue()).decode("utf-8")
