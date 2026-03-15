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


@pytest.fixture(autouse=True)
def clear_sessions():
    """Wipe the in-memory session store before every test."""
    reception_module._reset_session_storage()
    yield
    reception_module._reset_session_storage()


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

        with patch(
            "backend.api.reception._get_handoff_service",
            return_value=mock_service,
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
