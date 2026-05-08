from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from cachetools import TTLCache

import backend.agents.voice_agent as voice_agent_module
from backend.agents.voice_agent import VoiceAgent


def _make_new_voice_agent(*, audio_b64: str = "A" * 128):
    agent = VoiceAgent.__new__(VoiceAgent)
    agent.tts_provider = "voicevox"
    agent.kokoro_client = None
    agent.voicevox_fallback_client = None
    agent.clarification_agent = None
    agent.language_processor = SimpleNamespace()
    calls = {"count": 0}

    async def fake_synthesize(text: str, language: str, speaker_id: int | None = None) -> str:
        del text, language, speaker_id
        calls["count"] += 1
        return audio_b64

    agent.tts_client = SimpleNamespace(synthesize_wav_base64=fake_synthesize)
    return agent, calls


def _cache_key(agent: VoiceAgent, text: str, language: str = "ja", emotion: str = "neutral") -> str:
    return agent._tts_cache_key(text, language, agent.tts_provider, emotion)


def _assert_cached_audio_entry(
    agent: VoiceAgent,
    cache_key: str,
    *,
    audio_b64: str,
    audio_format: str = "audio/wav",
    fallback_used: bool = False,
    fallback_provider: str | None = None,
    actual_provider: str | None = "voicevox",
) -> None:
    cached = agent._tts_cache[cache_key]
    assert cached == {
        "audioResponse": audio_b64,
        "format": audio_format,
        "fallback_used": fallback_used,
        "fallback_provider": fallback_provider,
        "actual_provider": actual_provider,
    }


@pytest.mark.asyncio
async def test_text_to_speech_lazy_inits_cache_for_new_bypass():
    agent, calls = _make_new_voice_agent()

    assert not hasattr(agent, "_tts_cache")

    result = await agent.text_to_speech(text="こんにちは", language="ja")

    assert result["success"] is True
    assert calls["count"] == 1
    assert isinstance(agent._tts_cache, TTLCache)


@pytest.mark.asyncio
async def test_text_to_speech_cache_hit_returns_cached_audio_without_tts(monkeypatch):
    agent, calls = _make_new_voice_agent(audio_b64="B" * 128)
    agent._tts_cache = TTLCache(maxsize=200, ttl=3600)
    cache_key = _cache_key(agent, "こんにちは")
    agent._tts_cache[cache_key] = "C" * 128
    log_tts_cache_event = Mock()

    monkeypatch.setattr(voice_agent_module, "log_tts_cache_event", log_tts_cache_event)

    result = await agent.text_to_speech(text="こんにちは", language="ja")

    assert result["success"] is True
    assert result["audioResponse"] == "C" * 128
    assert result["tts_cache_hit"] is True
    assert calls["count"] == 0
    log_tts_cache_event.assert_called_once_with(hit=True, cache_key=cache_key, language="ja")


@pytest.mark.asyncio
async def test_text_to_speech_ignores_invalid_cached_audio(monkeypatch):
    agent, calls = _make_new_voice_agent(audio_b64="D" * 128)
    agent._tts_cache = TTLCache(maxsize=200, ttl=3600)
    cache_key = _cache_key(agent, "こんにちは")
    agent._tts_cache[cache_key] = "short-audio"
    log_tts_cache_event = Mock()

    monkeypatch.setattr(voice_agent_module, "log_tts_cache_event", log_tts_cache_event)

    result = await agent.text_to_speech(text="こんにちは", language="ja")

    assert result["success"] is True
    assert result["audioResponse"] == "D" * 128
    assert result["tts_cache_hit"] is False
    assert calls["count"] == 1
    _assert_cached_audio_entry(agent, cache_key, audio_b64="D" * 128)
    log_tts_cache_event.assert_called_once_with(hit=False, cache_key=cache_key, language="ja")


@pytest.mark.asyncio
async def test_text_to_speech_does_not_cache_short_audio():
    agent, calls = _make_new_voice_agent(audio_b64="short-audio")

    result = await agent.text_to_speech(text="こんにちは", language="ja")

    assert result["success"] is True
    assert result["tts_cache_hit"] is False
    assert calls["count"] == 1
    assert len(agent._tts_cache) == 0


@pytest.mark.asyncio
async def test_text_to_speech_caches_valid_audio():
    agent, _calls = _make_new_voice_agent(audio_b64="D" * 128)

    await agent.text_to_speech(text="こんにちは", language="ja")

    cache_key = _cache_key(agent, "こんにちは")
    _assert_cached_audio_entry(agent, cache_key, audio_b64="D" * 128)


@pytest.mark.asyncio
async def test_text_to_speech_logs_cache_hit_and_miss(monkeypatch):
    agent, calls = _make_new_voice_agent(audio_b64="E" * 128)
    log_tts_cache_event = Mock()
    cache_key = _cache_key(agent, "こんにちは")

    monkeypatch.setattr(voice_agent_module, "log_tts_cache_event", log_tts_cache_event)

    first = await agent.text_to_speech(text="こんにちは", language="ja")
    second = await agent.text_to_speech(text="こんにちは", language="ja")

    assert first["tts_cache_hit"] is False
    assert second["tts_cache_hit"] is True
    assert calls["count"] == 1
    assert log_tts_cache_event.call_args_list == [
        call(hit=False, cache_key=cache_key, language="ja"),
        call(hit=True, cache_key=cache_key, language="ja"),
    ]
