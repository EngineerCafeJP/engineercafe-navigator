from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import backend.api.reception as reception_module
import backend.main as main_mod

client = TestClient(main_mod.app)


def _make_request(api_key: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if api_key is not None:
        headers.append((b"x-api-key", api_key.encode()))

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "query_string": b"",
        "headers": headers,
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.fixture
def api_key_guard(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")
    monkeypatch.setattr(main_mod, "_ENVIRONMENT", "test")
    return {"X-API-Key": "expected-key"}


@pytest.fixture(autouse=True)
def reset_reception_sessions() -> None:
    reception_module._reset_session_storage()


def _start_reception(headers: dict[str, str], session_id: str = "session-001") -> dict:
    response = client.post(
        "/api/reception/start",
        json={
            "session_id": session_id,
            "language": "ja",
            "trigger_type": "button_press",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_reception_endpoints_require_api_key(api_key_guard: dict[str, str]) -> None:
    start_without_key = client.post(
        "/api/reception/start",
        json={
            "session_id": "session-001",
            "language": "ja",
            "trigger_type": "button_press",
        },
    )
    assert start_without_key.status_code == 403

    started = _start_reception(api_key_guard)
    reception_session_id = started["reception_session_id"]

    respond_without_key = client.post(
        "/api/reception/respond",
        json={
            "session_id": "session-001",
            "reception_session_id": reception_session_id,
            "message": "こんにちは",
        },
    )
    assert respond_without_key.status_code == 403

    status_without_key = client.get(
        f"/api/reception/status/{reception_session_id}",
        params={"session_id": "session-001"},
    )
    assert status_without_key.status_code == 403

    complete_without_key = client.post(
        "/api/reception/complete",
        json={
            "session_id": "session-001",
            "reception_session_id": reception_session_id,
        },
    )
    assert complete_without_key.status_code == 403


def test_legacy_slides_content_removed(api_key_guard: dict[str, str]) -> None:
    response = client.post("/api/slides/content", json={"language": "ja"})
    assert response.status_code == 404

    authorized = client.post(
        "/api/slides/content",
        json={"language": "ja"},
        headers=api_key_guard,
    )
    assert authorized.status_code == 404


def test_voice_get_supported_languages(api_key_guard: dict[str, str]) -> None:
    response = client.get(
        "/api/voice",
        params={"action": "supported_languages"},
        headers=api_key_guard,
    )

    assert response.status_code == 200
    assert response.json() == {
        "languages": [
            {"code": "ja", "name": "日本語"},
            {"code": "en", "name": "English"},
        ]
    }


@pytest.mark.asyncio
async def test_verify_api_key_rejects_staging_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)
    monkeypatch.setattr(main_mod, "_ENVIRONMENT", "staging")

    with pytest.raises(main_mod.HTTPException) as exc_info:
        await main_mod.verify_api_key(_make_request())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Server misconfigured"
