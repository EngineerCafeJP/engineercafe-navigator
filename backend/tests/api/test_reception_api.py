"""Tests for the active Reception API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import backend.api.reception as reception_module
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    """Wipe the in-memory session store before every test."""
    reception_module._reset_session_storage()
    yield
    reception_module._reset_session_storage()


@pytest.fixture(autouse=True)
def mock_sensor_event_db():
    """Stub Supabase sensor-event calls so tests run without a real DB."""
    fake_repo = AsyncMock()
    fake_repo.store_sensor_event = AsyncMock()
    fake_repo.get_latest_sensor_event = AsyncMock(return_value=None)
    fake_repo.store_session = AsyncMock()
    fake_repo.get_session_record = AsyncMock(return_value=None)
    reception_module._session_repository = fake_repo
    yield
    reception_module._session_repository = None


def _start_session(session_id: str = "sess-001", language: str = "ja") -> dict:
    response = client.post(
        "/api/reception/start",
        json={"session_id": session_id, "language": language, "trigger_type": "button_press"},
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestStartReception:
    def test_start_creates_new_session(self):
        data = _start_session(session_id="s1", language="ja")
        assert "reception_session_id" in data
        assert len(data["reception_session_id"]) > 0
        assert data["stage"] == "greeting"
        assert len(data["greeting"]) > 0

    def test_start_japanese_greeting(self):
        data = _start_session(language="ja")
        assert any(
            kw in data["greeting"] for kw in ["ようこそ", "エンジニアカフェ", "こんにちは"]
        ), f"Unexpected greeting: {data['greeting']}"

    def test_start_english_greeting(self):
        data = _start_session(language="en")
        assert any(
            kw in data["greeting"] for kw in ["Welcome", "Engineer Cafe", "visit"]
        ), f"Unexpected greeting: {data['greeting']}"

    def test_start_sessions_are_independent(self):
        id_1 = _start_session(session_id="s1")["reception_session_id"]
        id_2 = _start_session(session_id="s2")["reception_session_id"]
        assert id_1 != id_2

    def test_start_stores_session_in_memory(self):
        data = _start_session(session_id="s1")
        assert data["reception_session_id"] in reception_module._active_sessions


class TestReceptionStatus:
    def test_status_returns_initial_stage(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        response = client.get(f"/api/reception/status/{rid}", params={"session_id": "s1"})
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "s1"
        assert data["stage"] == "greeting"
        assert data["visitor_type"] is None
        assert data["purpose"] is None

    def test_status_non_uuid_reception_session_id_uses_memory_without_db(self, caplog):
        synthetic_id = "alpha-a-20260502_020830-a-A2-EN-002"
        fake_repo = AsyncMock()
        fake_repo.get_session_record.side_effect = AssertionError(
            "non-UUID reception_session_id should not query persistence"
        )
        reception_module._session_repository = fake_repo

        session = reception_module.ReceptionSession(
            id=synthetic_id,
            session_id="sess-alpha",
            stage="greeting",
            language="en",
            trigger_type="button_press",
        )
        reception_module._store_session(session)

        with caplog.at_level("DEBUG", logger="backend.api.reception"):
            response = client.get(
                f"/api/reception/status/{synthetic_id}",
                params={"session_id": "sess-alpha"},
            )

        assert response.status_code == 200
        assert response.json()["stage"] == "greeting"
        fake_repo.get_session_record.assert_not_awaited()
        assert "invalid input syntax for type uuid" not in caplog.text
        assert not [record for record in caplog.records if record.levelname in {"WARNING", "ERROR"}]

    def test_status_reflects_cached_stage_and_purpose(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]
        session = reception_module._active_sessions[rid]
        session.set_purpose(reception_module.VisitPurpose(category="event_participation"))
        session.advance_to("purpose_hearing")
        session.advance_to("routing")
        reception_module._store_session(session)

        response = client.get(f"/api/reception/status/{rid}", params={"session_id": "s1"})
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "routing"
        assert data["purpose"] == "event_participation"

    def test_status_404_for_nonexistent_session(self):
        response = client.get("/api/reception/status/no-such-id", params={"session_id": "s1"})
        assert response.status_code == 404

    def test_status_with_different_languages(self):
        for lang in ("ja", "en"):
            reception_module._active_sessions.clear()
            start = _start_session(session_id="s1", language=lang)
            rid = start["reception_session_id"]

            response = client.get(f"/api/reception/status/{rid}", params={"session_id": "s1"})
            assert response.status_code == 200
            assert response.json()["stage"] == "greeting"


class TestRetiredReceptionEndpoints:
    def test_respond_and_complete_routes_are_removed(self):
        for path in ("/api/reception/respond", "/api/reception/complete"):
            response = client.post(path, json={})
            assert response.status_code == 404


class TestSensorTriggerEndpoint:
    """Tests for POST /api/reception/sensor-trigger (#353)."""

    def test_sensor_trigger_success(self):
        response = client.post(
            "/api/reception/sensor-trigger",
            json={
                "sensor_type": "tof",
                "distance_mm": 500,
                "device_id": "m5stack-001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action"] == "trigger_received"
        assert "m5stack-001" in data["message"]

    def test_sensor_trigger_validation_negative_distance(self):
        response = client.post(
            "/api/reception/sensor-trigger",
            json={
                "sensor_type": "tof",
                "distance_mm": -1,
                "device_id": "m5stack-001",
            },
        )
        assert response.status_code == 422

    def test_sensor_trigger_validation_missing_fields(self):
        response = client.post(
            "/api/reception/sensor-trigger",
            json={},
        )
        assert response.status_code == 422

    def test_sensor_trigger_validation_device_id_too_long(self):
        response = client.post(
            "/api/reception/sensor-trigger",
            json={
                "sensor_type": "tof",
                "distance_mm": 300,
                "device_id": "x" * 101,
            },
        )
        assert response.status_code == 422

    def test_sensor_trigger_rate_limited(self):
        payload = {
            "sensor_type": "tof",
            "distance_mm": 500,
            "device_id": "m5stack-ratelimit-test",
        }

        resp1 = client.post("/api/reception/sensor-trigger", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["success"] is True
        assert resp1.json()["action"] == "trigger_received"

        resp2 = client.post("/api/reception/sensor-trigger", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["success"] is False
        assert resp2.json()["action"] == "rate_limited"

    def test_sensor_trigger_rate_limit_different_devices(self):
        payload_a = {
            "sensor_type": "tof",
            "distance_mm": 500,
            "device_id": "m5stack-device-a",
        }
        payload_b = {
            "sensor_type": "tof",
            "distance_mm": 500,
            "device_id": "m5stack-device-b",
        }

        resp_a = client.post("/api/reception/sensor-trigger", json=payload_a)
        assert resp_a.status_code == 200
        assert resp_a.json()["success"] is True

        resp_b = client.post("/api/reception/sensor-trigger", json=payload_b)
        assert resp_b.status_code == 200
        assert resp_b.json()["success"] is True

    def test_sensor_status_returns_new_event(self):
        payload = {
            "sensor_type": "tof",
            "distance_mm": 500,
            "device_id": "m5stack-status-test",
        }

        trigger_response = client.post("/api/reception/sensor-trigger", json=payload)
        assert trigger_response.status_code == 200

        status_response = client.get(
            "/api/reception/sensor-status",
            params={"device_id": payload["device_id"]},
        )
        assert status_response.status_code == 200
        data = status_response.json()
        assert data["triggered"] is True
        assert data["device_id"] == payload["device_id"]
        assert data["sensor_type"] == payload["sensor_type"]
        assert data["distance_mm"] == payload["distance_mm"]
        assert isinstance(data["timestamp"], float)

    def test_sensor_status_ignores_already_seen_event(self):
        payload = {
            "sensor_type": "tof",
            "distance_mm": 500,
            "device_id": "m5stack-seen-test",
        }

        client.post("/api/reception/sensor-trigger", json=payload)
        status_response = client.get(
            "/api/reception/sensor-status",
            params={"device_id": payload["device_id"]},
        )
        timestamp = status_response.json()["timestamp"]

        seen_response = client.get(
            "/api/reception/sensor-status",
            params={"device_id": payload["device_id"], "since": timestamp},
        )
        assert seen_response.status_code == 200
        assert seen_response.json() == {"triggered": False}
