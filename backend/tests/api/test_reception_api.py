"""Tests for the Reception API endpoints.

All external calls (Supabase, LLM) are mocked. The in-memory session
store is cleared between tests to ensure isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
import backend.api.reception as reception_module

client = TestClient(app)


def _fake_canonical_classify_purpose(
    message: str,
    language: str = "ja",
) -> tuple[str, str | None, float]:
    lower = message.lower()

    if any(keyword in lower for keyword in ("event", "seminar", "workshop", "meetup")) or (
        "イベント" in message or "セミナー" in message or "ワークショップ" in message
    ):
        return "event_participation", message, 0.9

    if any(
        keyword in lower
        for keyword in (
            "tour",
            "guided",
            "visit",
            "look around",
            "show me",
        )
    ) or ("見学" in message or "案内" in message or "ツアー" in message):
        return "tour", message, 0.9

    if any(
        keyword in lower
        for keyword in (
            "consult",
            "advice",
            "inquiry",
            "question",
            "ask",
        )
    ) or ("相談" in message or "質問" in message):
        return "consultation", message, 0.9

    if any(
        keyword in lower
        for keyword in (
            "cowork",
            "coworking",
            "study",
            "work",
            "wifi",
            "facility",
            "space",
            "room",
        )
    ) or (
        "作業" in message
        or "利用" in message
        or "勉強" in message
        or "コワーキング" in message
        or "施設" in message
    ):
        return "facility_use", message, 0.9

    return "other", None, 0.3


@pytest.fixture(autouse=True)
def clear_sessions():
    """Wipe the in-memory session store before every test."""
    reception_module._reset_session_storage()
    yield
    reception_module._reset_session_storage()


@pytest.fixture(autouse=True)
def mock_canonical_classifier():
    with patch(
        "backend.api.reception.canonical_classify_purpose",
        side_effect=_fake_canonical_classify_purpose,
    ):
        yield


@pytest.fixture(autouse=True)
def mock_sensor_event_db():
    """Stub Supabase sensor-event calls so tests run without a real DB."""
    from backend.utils.reception_repository import ReceptionRepository

    fake_repo = ReceptionRepository.__new__(ReceptionRepository)
    fake_repo._supabase = None

    async def _store_sensor_event(device_id, sensor_type, distance_mm):
        pass  # no-op; in-memory path is what tests assert against

    async def _get_latest_sensor_event(device_id, since_epoch=0):
        return None  # forces in-memory fallback

    fake_repo.store_sensor_event = _store_sensor_event
    fake_repo.get_latest_sensor_event = _get_latest_sensor_event

    # Delegate other calls to a real repository (mocked at method level elsewhere)
    real_repo = ReceptionRepository()
    fake_repo.store_session = real_repo.store_session
    fake_repo.get_session_record = real_repo.get_session_record
    fake_repo.get_session_by_conversation_id = real_repo.get_session_by_conversation_id
    fake_repo.complete_session = real_repo.complete_session
    fake_repo.list_active_sessions = real_repo.list_active_sessions
    fake_repo.cleanup_expired = real_repo.cleanup_expired

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


# ===========================================================================
# POST /api/reception/start
# ===========================================================================


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
        rid = data["reception_session_id"]
        assert rid in reception_module._active_sessions


# ===========================================================================
# POST /api/reception/respond
# ===========================================================================


class TestRespondReception:
    def test_respond_from_greeting_advances_to_purpose_hearing(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        response = client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "こんにちは"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "purpose_hearing"
        assert len(data["response"]) > 0

    def test_respond_with_facility_purpose_classified(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        # Advance to purpose_hearing
        client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "初めて来ました"},
        )
        # Now in purpose_hearing — send purpose
        response = client.post(
            "/api/reception/respond",
            json={
                "session_id": "s1",
                "reception_session_id": rid,
                "message": "施設を利用したいです",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "routing"
        assert data["purpose"]["category"] == "facility_use"

    def test_assistant_profile_question_does_not_advance_purpose_hearing(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "初めて来ました"},
        )
        with patch(
            "backend.api.reception.canonical_classify_purpose",
            new_callable=AsyncMock,
            side_effect=AssertionError("purpose classifier must not be called"),
        ):
            response = client.post(
                "/api/reception/respond",
                json={
                    "session_id": "s1",
                    "reception_session_id": rid,
                    "message": "あなたの名前は？",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "purpose_hearing"
        assert data["next_action"] == "answer_assistant_profile"
        assert "エンナビ" in data["response"]

    def test_respond_with_event_purpose_classified(self):
        start = _start_session(session_id="s1", language="en")
        rid = start["reception_session_id"]

        client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "Hello"},
        )
        response = client.post(
            "/api/reception/respond",
            json={
                "session_id": "s1",
                "reception_session_id": rid,
                "message": "I am here for an event",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["purpose"]["category"] == "event_participation"

    def test_respond_with_tour_purpose_classified_in_japanese(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "こんにちは"},
        )
        response = client.post(
            "/api/reception/respond",
            json={
                "session_id": "s1",
                "reception_session_id": rid,
                "message": "館内を見学したいです",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["purpose"]["category"] == "tour"

    def test_respond_with_tour_purpose_classified_in_english(self):
        start = _start_session(session_id="s1", language="en")
        rid = start["reception_session_id"]

        client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "Hello"},
        )
        response = client.post(
            "/api/reception/respond",
            json={
                "session_id": "s1",
                "reception_session_id": rid,
                "message": "I would like a guided tour of the facility",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["purpose"]["category"] == "tour"

    def test_respond_unknown_purpose_stays_in_purpose_hearing(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "こんにちは"},
        )
        response = client.post(
            "/api/reception/respond",
            json={
                "session_id": "s1",
                "reception_session_id": rid,
                "message": "なんとなく",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "purpose_hearing"
        assert data["next_action"] == "clarify_purpose"

    def test_respond_404_for_nonexistent_session(self):
        response = client.post(
            "/api/reception/respond",
            json={
                "session_id": "s1",
                "reception_session_id": "does-not-exist",
                "message": "hello",
            },
        )
        assert response.status_code == 404

    def test_full_flow_greeting_to_routing(self):
        """Complete greeting -> purpose_hearing -> routing flow."""
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        def respond(msg: str) -> dict:
            r = client.post(
                "/api/reception/respond",
                json={"session_id": "s1", "reception_session_id": rid, "message": msg},
            )
            assert r.status_code == 200, r.text
            return r.json()

        d1 = respond("こんにちは")
        assert d1["stage"] == "purpose_hearing"

        d2 = respond("コワーキングスペースで作業したい")
        assert d2["stage"] == "routing"
        assert d2["purpose"]["category"] == "facility_use"

    def test_respond_english_routing_message(self):
        start = _start_session(session_id="s1", language="en")
        rid = start["reception_session_id"]

        def respond(msg: str) -> dict:
            r = client.post(
                "/api/reception/respond",
                json={"session_id": "s1", "reception_session_id": rid, "message": msg},
            )
            assert r.status_code == 200
            return r.json()

        respond("Hello")
        d = respond("I need to use the coworking space")
        assert d["stage"] == "routing"


# ===========================================================================
# GET /api/reception/status/{session_id}
# ===========================================================================


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

    def test_status_reflects_advanced_stage(self):
        start = _start_session(session_id="s1")
        rid = start["reception_session_id"]

        client.post(
            "/api/reception/respond",
            json={"session_id": "s1", "reception_session_id": rid, "message": "こんにちは"},
        )
        client.post(
            "/api/reception/respond",
            json={
                "session_id": "s1",
                "reception_session_id": rid,
                "message": "イベントに参加します",
            },
        )

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


# ===========================================================================
# POST /api/reception/complete
# ===========================================================================


def _advance_to_routing(session_id: str = "sess-001") -> str:
    """Start a session and advance it to the 'routing' stage.

    Returns the reception_session_id.
    """
    start = _start_session(session_id=session_id)
    rid = start["reception_session_id"]

    # greeting -> purpose_hearing
    client.post(
        "/api/reception/respond",
        json={"session_id": session_id, "reception_session_id": rid, "message": "hello"},
    )
    # purpose_hearing -> routing (facility keyword)
    client.post(
        "/api/reception/respond",
        json={
            "session_id": session_id,
            "reception_session_id": rid,
            "message": "I want to use the coworking space",
        },
    )
    return rid


@dataclass
class _FakePurposeFlow:
    response_text: str = "Welcome to the coworking area."
    action_type: str = "guide"
    action_data: Optional[dict[str, Any]] = None


@dataclass
class _FakeHandoffResult:
    workflow_state: dict[str, Any] = None  # type: ignore[assignment]
    target_agent: str = "facility_agent"
    purpose_flow: _FakePurposeFlow = None  # type: ignore[assignment]
    requires_staff: bool = False

    def __post_init__(self) -> None:
        if self.workflow_state is None:
            self.workflow_state = {"step": "routed"}
        if self.purpose_flow is None:
            self.purpose_flow = _FakePurposeFlow()


class TestCompleteReception:
    def test_complete_returns_404_for_unknown_session(self):
        response = client.post(
            "/api/reception/complete",
            json={
                "session_id": "sess-001",
                "reception_session_id": "does-not-exist",
            },
        )
        assert response.status_code == 404

    def test_complete_returns_403_on_session_id_mismatch(self):
        rid = _advance_to_routing(session_id="sess-001")

        response = client.post(
            "/api/reception/complete",
            json={
                "session_id": "wrong-session-id",
                "reception_session_id": rid,
            },
        )
        assert response.status_code == 403

    def test_complete_returns_409_when_not_in_routing_stage(self):
        start = _start_session(session_id="sess-001")
        rid = start["reception_session_id"]
        # Session is in 'greeting' stage, not 'routing'

        response = client.post(
            "/api/reception/complete",
            json={
                "session_id": "sess-001",
                "reception_session_id": rid,
            },
        )
        assert response.status_code == 409

    def test_complete_success_with_mocked_handoff(self):
        rid = _advance_to_routing(session_id="sess-001")

        fake_result = _FakeHandoffResult()
        mock_service = AsyncMock()
        mock_service.prepare_handoff.return_value = fake_result
        mock_workflow = AsyncMock()
        mock_workflow.ainvoke_from_reception = AsyncMock(
            return_value={"answer": "Welcome to the coworking area."}
        )

        with (
            patch(
                "backend.api.reception._get_handoff_service",
                return_value=mock_service,
            ),
            patch(
                "backend.workflows.main_workflow.get_workflow",
                new=AsyncMock(return_value=mock_workflow),
            ),
        ):
            response = client.post(
                "/api/reception/complete",
                json={
                    "session_id": "sess-001",
                    "reception_session_id": rid,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["target_agent"] == "facility_agent"
        assert data["requires_staff"] is False
        assert data["response_text"] == "Welcome to the coworking area."
        assert data["action_type"] == "guide"
        assert data["purpose_category"] == "facility_use"
        # workflow_state must NOT be in the response (PII leak fix)
        assert "workflow_state" not in data


class TestSensorTriggerEndpoint:
    """Tests for POST /api/reception/sensor-trigger (#353)"""

    def setup_method(self):
        reception_module._reset_session_storage()

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
        """Rapid duplicate requests from the same device should be rate-limited (#357)."""
        payload = {
            "sensor_type": "tof",
            "distance_mm": 500,
            "device_id": "m5stack-ratelimit-test",
        }

        # First request should succeed
        resp1 = client.post("/api/reception/sensor-trigger", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["success"] is True
        assert resp1.json()["action"] == "trigger_received"

        # Immediate second request from same device should be rate-limited
        resp2 = client.post("/api/reception/sensor-trigger", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["success"] is False
        assert resp2.json()["action"] == "rate_limited"

    def test_sensor_trigger_rate_limit_different_devices(self):
        """Different devices should NOT be rate-limited by each other (#357)."""
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

        # Different device should still succeed
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
