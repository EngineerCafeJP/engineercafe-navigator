from __future__ import annotations

import pytest

from backend.services.sheets_event_source import SheetsEventSource


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, payload: dict | None = None, **kwargs) -> None:
        self.payload = payload or {}
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, params: dict[str, str]):
        assert url == "https://script.example/exec"
        assert params == {"token": "test-token"}
        return _FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_fetch_events_normalizes_gas_payload_and_ignores_pii(monkeypatch):
    payload = {
        "events": [
            {
                "row": 42,
                "status": "許可済",
                "title": "XR Vision DevCamp",
                "date": "2026-05-20",
                "event_start": "19:00",
                "event_end": "21:00",
                "description": "XR 開発イベント",
                "time_table": "19:00 開場 / 19:30 LT",
                "organizer": "Orbit Base",
                "capacity": 50,
                "facility": "Engineer Cafe メインホール",
                "メールアドレス": "private@example.com",
                "申込者氏名": "山田 太郎",
            },
            {
                "row": 43,
                "status": "中止",
                "title": "Cancelled Event",
                "date": "2026-05-20",
                "event_start": "19:00",
            },
        ]
    }

    monkeypatch.setenv("EVENT_SHEET_GAS_URL", "https://script.example/exec")
    monkeypatch.setenv("EVENT_SHEET_GAS_TOKEN", "test-token")
    monkeypatch.setattr(
        "backend.services.sheets_event_source.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(*args, payload=payload, **kwargs),
    )

    records = await SheetsEventSource().fetch_events()

    assert len(records) == 1
    record = records[0]
    assert record.external_id == "sheet:event_status:row42"
    assert record.title == "XR Vision DevCamp"
    assert record.start == "2026-05-20T19:00:00+09:00"
    assert record.end == "2026-05-20T21:00:00+09:00"
    assert record.location == "Engineer Cafe メインホール"
    assert record.source == "spreadsheet"
    assert "Orbit Base" in record.description
    assert "private@example.com" not in record.description
    assert "山田 太郎" not in record.description


@pytest.mark.asyncio
async def test_fetch_events_returns_empty_when_env_missing(monkeypatch):
    monkeypatch.delenv("EVENT_SHEET_GAS_URL", raising=False)
    monkeypatch.delenv("EVENT_SHEET_GAS_TOKEN", raising=False)

    assert await SheetsEventSource().fetch_events() == []
