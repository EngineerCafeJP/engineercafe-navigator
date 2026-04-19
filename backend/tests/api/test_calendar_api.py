from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.main as main_mod

client = TestClient(main_mod.app)


def test_calendar_get_returns_service_payload(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)

    with patch.object(
        main_mod.CalendarService,
        "search_events",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = {
            "success": True,
            "data": {
                "events": [
                    {
                        "id": "evt-1",
                        "title": "Engineer Cafe Meetup",
                        "start": "2026-03-21T10:00:00Z",
                        "end": "2026-03-21T12:00:00Z",
                    }
                ],
                "timeRange": "today",
                "eventCount": 1,
            },
        }

        response = client.get("/api/calendar?timeRange=today")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "events": [
                {
                    "id": "evt-1",
                    "title": "Engineer Cafe Meetup",
                    "start": "2026-03-21T10:00:00Z",
                    "end": "2026-03-21T12:00:00Z",
                }
            ],
            "timeRange": "today",
            "eventCount": 1,
        },
    }
    mock_search.assert_awaited_once_with("today")


def test_calendar_get_rejects_invalid_time_range(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)

    response = client.get("/api/calendar?timeRange=invalid")

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid timeRange"}


def test_calendar_get_accepts_tomorrow(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)

    with patch.object(
        main_mod.CalendarService,
        "search_events",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = {
            "success": True,
            "data": {"events": [], "timeRange": "tomorrow", "eventCount": 0},
        }

        response = client.get("/api/calendar?timeRange=tomorrow")

    assert response.status_code == 200
    assert response.json()["data"]["timeRange"] == "tomorrow"
    mock_search.assert_awaited_once_with("tomorrow")


def test_calendar_get_surfaces_backend_fetch_failures(monkeypatch):
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)

    with patch.object(
        main_mod.CalendarService,
        "search_events",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = {
            "success": False,
            "error": "ICS upstream unavailable",
        }

        response = client.get("/api/calendar")

    assert response.status_code == 502
    assert response.json() == {"detail": "ICS upstream unavailable"}
    mock_search.assert_awaited_once_with("thisWeek")
