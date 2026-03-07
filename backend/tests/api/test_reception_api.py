"""Tests for the Reception API endpoints.

All external calls (Supabase, LLM) are mocked. The in-memory session
store is cleared between tests to ensure isolation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
import backend.api.reception as reception_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    """Wipe the in-memory session store before every test."""
    reception_module._active_sessions.clear()
    yield
    reception_module._active_sessions.clear()


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
            kw in data["greeting"]
            for kw in ["ようこそ", "エンジニアカフェ", "こんにちは"]
        ), f"Unexpected greeting: {data['greeting']}"

    def test_start_english_greeting(self):
        data = _start_session(language="en")
        assert any(
            kw in data["greeting"]
            for kw in ["Welcome", "Engineer Cafe", "visit"]
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

        response = client.get(f"/api/reception/status/{rid}")
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

        response = client.get(f"/api/reception/status/{rid}")
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "routing"
        assert data["purpose"] == "event_participation"

    def test_status_404_for_nonexistent_session(self):
        response = client.get("/api/reception/status/no-such-id")
        assert response.status_code == 404

    def test_status_with_different_languages(self):
        for lang in ("ja", "en"):
            reception_module._active_sessions.clear()
            start = _start_session(session_id="s1", language=lang)
            rid = start["reception_session_id"]

            response = client.get(f"/api/reception/status/{rid}")
            assert response.status_code == 200
            assert response.json()["stage"] == "greeting"
