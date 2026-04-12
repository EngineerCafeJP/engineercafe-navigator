"""Shared test fixtures for the full voice pipeline (STT -> LangGraph -> TTS).

Provides reusable mock factories, scripted test data, and WAV generation
helpers used across voice pipeline integration tests.
"""

from __future__ import annotations

import base64
import struct
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# 1. fake_wav_bytes — minimal valid WAV (PCM, 1ch, 16kHz, 16-bit, ~0.5s)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_wav_bytes() -> bytes:
    """Generate a minimal valid WAV file: ~0.5 seconds of silence."""
    return _build_wav_silence()


def _build_wav_silence(
    duration_sec: float = 0.5,
    sample_rate: int = 16000,
    bits_per_sample: int = 16,
    num_channels: int = 1,
) -> bytes:
    num_samples = int(sample_rate * duration_sec)
    byte_rate = sample_rate * num_channels * (bits_per_sample // 8)
    block_align = num_channels * (bits_per_sample // 8)
    data_size = num_samples * block_align

    # RIFF header
    riff = b"RIFF"
    riff += struct.pack("<I", 36 + data_size)  # file size - 8
    riff += b"WAVE"

    # fmt sub-chunk
    fmt = b"fmt "
    fmt += struct.pack("<I", 16)  # sub-chunk size (PCM)
    fmt += struct.pack("<H", 1)  # audio format (1 = PCM)
    fmt += struct.pack("<H", num_channels)
    fmt += struct.pack("<I", sample_rate)
    fmt += struct.pack("<I", byte_rate)
    fmt += struct.pack("<H", block_align)
    fmt += struct.pack("<H", bits_per_sample)

    # data sub-chunk (silence = all zeros)
    data = b"data"
    data += struct.pack("<I", data_size)
    data += b"\x00" * data_size

    return riff + fmt + data


# ---------------------------------------------------------------------------
# 2. fake_wav_b64 — base64-encoded WAV
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_wav_b64(fake_wav_bytes: bytes) -> str:
    """Base64-encoded version of ``fake_wav_bytes``."""
    return base64.b64encode(fake_wav_bytes).decode("ascii")


# ---------------------------------------------------------------------------
# 3. scripted_stt_results — pre-built STT result dicts
# ---------------------------------------------------------------------------

SCRIPTED_STT_RESULTS: Dict[str, Dict[str, Any]] = {
    "ja_business": {
        "success": True,
        "transcript": "営業時間を教えてください",
        "confidence": 0.95,
        "language": "ja",
        "provider": "qwen",
        "fallback_used": False,
    },
    "en_facility": {
        "success": True,
        "transcript": "Do you have Wi-Fi?",
        "confidence": 0.92,
        "language": "en",
        "provider": "qwen",
        "fallback_used": False,
    },
    "ja_autodetect": {
        "success": True,
        "transcript": "会議室の予約について",
        "confidence": 0.88,
        "language": "ja",
        "provider": "qwen",
        "fallback_used": False,
    },
    "failure": {
        "success": False,
        "transcript": "",
        "confidence": 0.0,
        "language": "ja",
        "provider": "qwen",
        "error": "Audio too short",
    },
}


@pytest.fixture
def scripted_stt_results() -> Dict[str, Dict[str, Any]]:
    """Pre-scripted STT result dicts keyed by scenario name."""
    return {k: dict(v) for k, v in SCRIPTED_STT_RESULTS.items()}


# ---------------------------------------------------------------------------
# 4. scripted_workflow_responses — pre-built LangGraph workflow results
# ---------------------------------------------------------------------------

SCRIPTED_WORKFLOW_RESPONSES: Dict[str, Dict[str, Any]] = {
    "business_info": {
        "answer": "エンジニアカフェの営業時間は平日9:00〜22:00、土日祝10:00〜20:00です。",
        "emotion": "happy",
        "routing": {"agent": "business_info"},
        "metadata": {},
    },
    "facility": {
        "answer": "Yes, we offer free Wi-Fi throughout the building.",
        "emotion": "neutral",
        "routing": {"agent": "facility"},
        "metadata": {},
    },
    "event": {
        "answer": "本日のイベントはLT大会が19:00から開催されます。",
        "emotion": "excited",
        "routing": {"agent": "event"},
        "metadata": {},
    },
    "general_knowledge": {
        "answer": "福岡はスタートアップが盛んな街です。",
        "emotion": "neutral",
        "routing": {"agent": "general_knowledge"},
        "metadata": {},
    },
}


@pytest.fixture
def scripted_workflow_responses() -> Dict[str, Dict[str, Any]]:
    """Pre-scripted workflow result dicts keyed by agent type."""
    return {k: dict(v) for k, v in SCRIPTED_WORKFLOW_RESPONSES.items()}


# ---------------------------------------------------------------------------
# 5. mock_stt_agent_factory — creates a mock STTAgent
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_stt_agent_factory():
    """Factory that returns a mock STTAgent with a pre-scripted speech_to_text result."""

    def _factory(
        transcript: str,
        language: str = "ja",
        confidence: float = 0.95,
        provider: str = "qwen",
    ) -> MagicMock:
        agent = MagicMock()
        agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": transcript,
                "confidence": confidence,
                "language": language,
                "provider": provider,
                "fallback_used": False,
            }
        )
        return agent

    return _factory


# ---------------------------------------------------------------------------
# 6. mock_voice_agent_factory — creates a mock VoiceAgent
# ---------------------------------------------------------------------------

_DEFAULT_AUDIO_B64 = "ZmFrZWF1ZGlv"


@pytest.fixture
def mock_voice_agent_factory():
    """Factory that returns a mock VoiceAgent with a pre-scripted text_to_speech result."""

    def _factory(
        audio_b64: str = _DEFAULT_AUDIO_B64,
        emotion: str = "neutral",
        language: str = "ja",
        audio_format: str = "audio/wav",
    ) -> MagicMock:
        agent = MagicMock()
        agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": audio_b64,
                "emotion": emotion,
                "cleanText": "テスト応答",
                "format": audio_format,
                "language": language,
            }
        )
        return agent

    return _factory


# ---------------------------------------------------------------------------
# 7. mock_workflow_factory — creates a mock MainWorkflow
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_workflow_factory():
    """Factory that returns a mock simulating MainWorkflow.graph.ainvoke()."""

    def _factory(
        answer: str,
        emotion: str = "neutral",
        routing_agent: str = "general_knowledge",
        language: str = "ja",
    ) -> MagicMock:
        workflow = MagicMock()
        workflow.graph = MagicMock()
        workflow.graph.ainvoke = AsyncMock(
            return_value={
                "query": "",
                "session_id": "test_session",
                "language": language,
                "messages": [],
                "routing": {"agent": routing_agent},
                "answer": answer,
                "emotion": emotion,
                "metadata": {},
                "context": {},
            }
        )
        return workflow

    return _factory
