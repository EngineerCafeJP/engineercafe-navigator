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
