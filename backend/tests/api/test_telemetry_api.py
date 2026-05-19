from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_post_voice_telemetry_logs_frontend_event(monkeypatch):
    import backend.main as main_mod

    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)

    with (
        patch(
            "backend.api.telemetry.log_frontend_telemetry_event",
            return_value={
                "event": "audio_playback_failed",
                "telemetry_event": "audio_playback_failed",
            },
        ) as log_frontend,
        patch("backend.api.telemetry.log_voice_round_trip") as log_round_trip,
    ):
        response = TestClient(main_mod.app).post(
            "/api/telemetry/voice",
            headers={"X-Request-ID": "req-telemetry-1"},
            json={
                "event": "audio_playback_failed",
                "sessionId": "session-voice-1",
                "method": "web-audio",
                "errorType": "playback_failed",
                "errorMessage": "decode failed",
                "userAgent": "pytest",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "event": "audio_playback_failed",
        "telemetryEvent": "audio_playback_failed",
        "voiceRoundTrip": False,
        "requestId": "req-telemetry-1",
    }
    log_frontend.assert_called_once()
    fields = log_frontend.call_args.kwargs
    assert fields["event"] == "audio_playback_failed"
    assert fields["request_id"] == "req-telemetry-1"
    assert fields["session_id"] == "session-voice-1"
    assert fields["method"] == "web-audio"
    assert fields["errorType"] == "playback_failed"
    assert fields["userAgent"] == "pytest"
    log_round_trip.assert_not_called()


def test_post_voice_telemetry_logs_voice_round_trip_when_timings_present(monkeypatch):
    import backend.main as main_mod

    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)

    with (
        patch(
            "backend.api.telemetry.log_frontend_telemetry_event",
            return_value={
                "event": "frontend_telemetry",
                "telemetry_event": "voice_round_trip",
            },
        ) as log_frontend,
        patch(
            "backend.api.telemetry.log_voice_round_trip",
            return_value={"event": "voice_round_trip"},
        ) as log_round_trip,
    ):
        response = TestClient(main_mod.app).post(
            "/api/telemetry/voice",
            headers={"X-Request-ID": "req-telemetry-2"},
            json={
                "event": "voice_round_trip",
                "sessionId": "session-voice-2",
                "sttMs": 101,
                "qaMs": "202",
                "ttsMs": 303,
                "turnTotalMs": 707,
                "success": False,
                "errorType": "PlaybackTimeout",
            },
        )

    assert response.status_code == 200
    assert response.json()["voiceRoundTrip"] is True
    log_frontend.assert_called_once()
    log_round_trip.assert_called_once()
    fields = log_round_trip.call_args.kwargs
    assert fields["request_id"] == "req-telemetry-2"
    assert fields["session_id"] == "session-voice-2"
    assert fields["stt_ms"] == 101
    assert fields["chat_ms"] == 202
    assert fields["tts_ms"] == 303
    assert fields["total_ms"] == 707
    assert fields["success"] is False
    assert fields["error_type"] == "PlaybackTimeout"
    assert fields["source"] == "frontend"


def test_post_voice_telemetry_ignores_reserved_extra_fields(monkeypatch):
    import backend.main as main_mod

    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", None)

    with (
        patch(
            "backend.api.telemetry.log_frontend_telemetry_event",
            return_value={
                "event": "frontend_telemetry",
                "telemetry_event": "voice_round_trip",
            },
        ) as log_frontend,
        patch(
            "backend.api.telemetry.log_voice_round_trip",
            return_value={"event": "voice_round_trip"},
        ) as log_round_trip,
    ):
        response = TestClient(main_mod.app).post(
            "/api/telemetry/voice",
            headers={"X-Request-ID": "req-telemetry-reserved"},
            json={
                "event": "voice_round_trip",
                "sessionId": "session-voice-reserved",
                "source": "browser",
                "telemetry_event": "client_override",
                "sttMs": 100,
                "qaMs": 200,
                "ttsMs": 300,
                "turnTotalMs": 650,
                "success": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["voiceRoundTrip"] is True
    frontend_fields = log_frontend.call_args.kwargs
    round_trip_fields = log_round_trip.call_args.kwargs
    assert frontend_fields["event"] == "voice_round_trip"
    assert "source" not in frontend_fields
    assert "telemetry_event" not in frontend_fields
    assert round_trip_fields["source"] == "frontend"
    assert round_trip_fields["telemetry_event"] == "voice_round_trip"
