import asyncio
import base64
import time

import httpx
import pytest

import backend.main as main_mod
from backend.main import app

pytestmark = pytest.mark.asyncio


async def test_voice_filler_requires_api_key(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/voice/filler",
            json={"query": "WiFiのパスワードは？", "language": "ja"},
        )

    assert response.status_code == 403


async def test_voice_filler_returns_static_audio_and_request_id(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/voice/filler",
            headers={"X-API-Key": "expected-key", "X-Request-ID": "req-filler-610"},
            json={"query": "WiFiのパスワードは？", "language": "ja"},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-filler-610"
    body = response.json()
    assert body["intent"] == "wifi"
    assert body["audioFormat"] == "audio/wav"
    assert body["audioResponse"]
    assert body["source"] == "static"
    assert body["requestId"] == "req-filler-610"
    assert body["phase"] == "filler"
    assert body["upstreamStatus"]["ok"] is True


async def test_voice_filler_static_lookup_under_100ms(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)
    main_mod._filler_audio_cache.clear()

    started_at = time.perf_counter()
    response = await main_mod.voice_filler_api(
        main_mod.Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/voice/filler",
                "headers": [],
                "query_string": b"",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 12345),
            }
        ),
        main_mod.FillerRequest(query="明日のイベントは？", language="ja"),
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert response.intent == "event"
    assert response.audioResponse
    assert elapsed_ms < 100


async def test_voice_filler_rejects_undersized_wav(monkeypatch, tmp_path):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")
    monkeypatch.setattr(main_mod, "_FILLER_DIR", tmp_path)
    main_mod._filler_audio_cache.clear()

    tiny = tmp_path / "wifi_ja.wav"
    tiny.write_bytes(bytes(4096))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/voice/filler",
            headers={"X-API-Key": "expected-key"},
            json={"query": "WiFiのパスワードは？", "language": "ja"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "wifi"
    assert body["audioResponse"] == ""
    assert body["upstreamStatus"]["ok"] is False


async def test_voice_filler_accepts_wav_meeting_minimum_size(monkeypatch, tmp_path):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")
    monkeypatch.setattr(main_mod, "_FILLER_DIR", tmp_path)
    main_mod._filler_audio_cache.clear()

    ok_file = tmp_path / "wifi_ja.wav"
    ok_file.write_bytes(bytes([255]) * 9000)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/voice/filler",
            headers={"X-API-Key": "expected-key"},
            json={"query": "WiFiのパスワードは？", "language": "ja"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["upstreamStatus"]["ok"] is True
    assert len(body["audioResponse"]) > 0


async def test_voice_filler_uses_static_fallback_clip_when_intent_clip_missing(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")
    monkeypatch.setattr(main_mod, "_FILLER_DIR", tmp_path)
    main_mod._filler_audio_cache.clear()

    fallback_file = tmp_path / "fallback_ja.wav"
    fallback_file.write_bytes(bytes([255]) * 9000)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/voice/filler",
            headers={"X-API-Key": "expected-key"},
            json={"query": "WiFiのパスワードは？", "language": "ja"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "wifi"
    assert body["audioResponse"]
    assert body["upstreamStatus"]["ok"] is True
    assert body["upstreamStatus"]["fallbackUsed"] is True
    assert body["upstreamStatus"]["actualIntent"] == "fallback"
    assert body["upstreamStatus"]["actualLanguage"] == "ja"


async def test_handle_stt_times_out_and_returns_recoverable_failure(monkeypatch):
    monkeypatch.setenv("VOICE_STT_REQUEST_TIMEOUT_SECONDS", "0.01")

    class SlowSTTAgent:
        async def speech_to_text(self, audio_data, language=None, conversation_stage=None):
            await asyncio.sleep(1)
            return {
                "success": True,
                "transcript": "too late",
                "language": language or "ja",
                "provider": "slow",
            }

    monkeypatch.setattr(main_mod, "_get_stt_agent", lambda: SlowSTTAgent())

    body = main_mod.VoiceRequest(
        action="speech_to_text",
        audioData=base64.b64encode(b"\x00" * 1024).decode("ascii"),
        language="ja",
        sessionId="stt-timeout",
    )

    response = await main_mod._handle_stt(body, "req-stt-timeout")

    assert response.success is False
    assert response.error == "No speech detected"
    assert response.requestId == "req-stt-timeout"
    assert response.upstreamStatus["ok"] is False
    assert response.upstreamStatus["errorType"] == "TimeoutError"
