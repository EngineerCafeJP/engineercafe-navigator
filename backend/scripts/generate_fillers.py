"""Generate static filler WAV files for `/api/voice/filler`.

The script prefers PiperPlus through `VoiceAgent(tts_provider="piper")`.
When PiperPlus is unavailable in local/CI environments, it writes a short
valid silent WAV so the endpoint can still degrade without runtime synthesis.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import math
import struct
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = Path(__file__).resolve().parents[1] / "static" / "fillers"
SAMPLE_RATE = 16_000
SILENCE_SECONDS = 0.18


def _silent_wav() -> bytes:
    frames = int(SAMPLE_RATE * SILENCE_SECONDS)
    data = bytearray()
    # Low-amplitude tone avoids browser/player edge cases with all-zero WAVs
    # while remaining unobtrusive as a fallback placeholder.
    for i in range(frames):
        sample = int(150 * math.sin(2 * math.pi * 440 * (i / SAMPLE_RATE)))
        data.extend(struct.pack("<h", sample))

    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(data))
    return buffer.getvalue()


async def _try_piper(text: str, language: str) -> bytes | None:
    try:
        from backend.agents.voice_agent import VoiceAgent

        agent = VoiceAgent(tts_provider="piper")
        result = await agent.text_to_speech(text=text, language=language, emotion="neutral")
        if not result.get("success") or not result.get("audioResponse"):
            return None
        return base64.b64decode(result["audioResponse"])
    except Exception:
        return None


async def generate_fillers(*, use_piper: bool) -> list[Path]:
    from backend.utils.filler_catalog import FILLER_TEXTS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    fallback_audio = _silent_wav()

    for intent, by_language in FILLER_TEXTS.items():
        for language, text in by_language.items():
            audio = await _try_piper(text, language) if use_piper else None
            path = OUT_DIR / f"{intent}_{language}.wav"
            path.write_bytes(audio or fallback_audio)
            written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static filler WAV catalog.")
    parser.add_argument(
        "--piper",
        action="store_true",
        help="Try PiperPlus TTS; otherwise generate placeholder WAV files.",
    )
    args = parser.parse_args()

    written = asyncio.run(generate_fillers(use_piper=args.piper))
    print(f"generated {len(written)} filler wav files in {OUT_DIR}")


if __name__ == "__main__":
    main()
