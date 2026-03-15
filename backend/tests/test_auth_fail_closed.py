import pytest
from starlette.requests import Request

import backend.main as main_mod


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


@pytest.mark.asyncio
async def test_verify_api_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")
    monkeypatch.setattr(main_mod, "_ENVIRONMENT", "test")

    with pytest.raises(main_mod.HTTPException) as exc_info:
        await main_mod.verify_api_key(_make_request("wrong-key"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid or missing API key"


@pytest.mark.asyncio
async def test_verify_api_key_rejects_missing_key(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")
    monkeypatch.setattr(main_mod, "_ENVIRONMENT", "test")

    with pytest.raises(main_mod.HTTPException) as exc_info:
        await main_mod.verify_api_key(_make_request())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid or missing API key"


@pytest.mark.asyncio
async def test_verify_api_key_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", "expected-key")
    monkeypatch.setattr(main_mod, "_ENVIRONMENT", "test")

    await main_mod.verify_api_key(_make_request("expected-key"))


@pytest.mark.asyncio
async def test_verify_api_key_returns_503_for_production_without_secret(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)
    monkeypatch.setattr(main_mod, "_ENVIRONMENT", "production")

    with pytest.raises(main_mod.HTTPException) as exc_info:
        await main_mod.verify_api_key(_make_request())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Server misconfigured"


@pytest.mark.asyncio
async def test_verify_api_key_skips_in_dev_when_no_secret(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)
    monkeypatch.setattr(main_mod, "_ENVIRONMENT", "development")

    await main_mod.verify_api_key(_make_request())
