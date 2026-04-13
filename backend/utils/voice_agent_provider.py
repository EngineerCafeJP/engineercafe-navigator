"""Lazy singleton VoiceAgent for TTS (shared by main API and workflow)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.agents.voice_agent import VoiceAgent

_voice_agent: Optional["VoiceAgent"] = None


def get_voice_agent() -> "VoiceAgent":
    """Return a process-wide VoiceAgent (TTS_PROVIDER from env, default voicevox)."""
    global _voice_agent
    if _voice_agent is None:
        from backend.agents.voice_agent import VoiceAgent

        tts_provider = os.getenv("TTS_PROVIDER", "voicevox")
        _voice_agent = VoiceAgent(tts_provider=tts_provider)
    return _voice_agent


def reset_voice_agent_for_tests() -> None:
    """Clear singleton (tests only)."""
    global _voice_agent
    _voice_agent = None
