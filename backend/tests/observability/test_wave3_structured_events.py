from __future__ import annotations

import json

from backend.observability import structured_logger as structured_logger_module


def _remove_marked_handlers(logger, marker: str) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, marker, False):
            logger.removeHandler(handler)
            handler.close()


def test_stt_qwen_complete_payload_matches_wave3_schema(monkeypatch):
    monkeypatch.setattr(structured_logger_module, "_current_request_id", lambda: "req-stt-21")

    payload = structured_logger_module.build_stt_qwen_complete_payload(
        provider="qwen-primary",
        language="ja",
        audio_duration_ms=2340,
        latency_ms=1820,
        confidence="0.94",
        transcript_length=18,
        winner=True,
        session_id="session-1",
    )

    assert payload == {
        "event": "stt_qwen_complete",
        "request_id": "req-stt-21",
        "provider": "qwen-primary",
        "language": "ja",
        "audio_duration_ms": 2340,
        "latency_ms": 1820,
        "confidence": 0.94,
        "transcript_length": 18,
        "winner": True,
        "session_id": "session-1",
    }


def test_stt_winner_normalizes_alternatives():
    payload = structured_logger_module.build_stt_winner_payload(
        request_id="req-winner-22",
        winner_provider="qwen-primary",
        language="ja",
        confidence=0.91,
        alternatives=[
            ("qwen-primary", 0.91),
            {"name": "vosk-fallback", "score": "0.44"},
        ],
        session_id="session-2",
    )

    assert payload["event"] == "stt_winner"
    assert payload["winner_provider"] == "qwen-primary"
    assert payload["alternatives"] == [
        {"name": "qwen-primary", "score": 0.91},
        {"name": "vosk-fallback", "score": 0.44},
    ]


def test_tts_synthesis_complete_payload_shape_and_json_output(capsys, monkeypatch):
    logger = structured_logger_module._get_tts_logger()
    marker = structured_logger_module._TTS_LOG_HANDLER_MARKER
    _remove_marked_handlers(logger, marker)
    monkeypatch.setattr(structured_logger_module, "_current_request_id", lambda: "req-tts-21")

    payload = structured_logger_module.log_tts_synthesis_complete(
        provider="piper-plus",
        language="ja",
        voice="neutral",
        text_length=42,
        latency_ms=315,
        audio_duration_ms=1200,
        fallback_used=False,
        session_id="session-3",
    )

    captured_payload = json.loads(capsys.readouterr().out.strip())

    assert payload["event"] == "tts_synthesis_complete"
    assert payload["request_id"] == "req-tts-21"
    assert payload["provider"] == "piper-plus"
    assert payload["success"] is True
    assert payload["latency_ms"] == 315
    assert payload == captured_payload


def test_agent_routing_and_voice_round_trip_payloads():
    routing = structured_logger_module.build_agent_routing_payload(
        request_id="req-route-22",
        routed_to="facility",
        intent="facility_hours",
        confidence=1.4,
        fallback_used=False,
        alternatives={"facility": 1.4, "fallback_general": 0.2},
        latency_ms="17",
        session_id="session-4",
    )
    round_trip = structured_logger_module.build_voice_round_trip_payload(
        request_id="req-voice-22",
        stt_ms=100,
        chat_ms=250,
        tts_ms=300,
        success=True,
        session_id="session-4",
    )

    assert routing["event"] == "agent_routing"
    assert routing["confidence"] == 1.0
    assert routing["latency_ms"] == 17
    assert routing["alternatives"] == [
        {"name": "facility", "score": 1.4},
        {"name": "fallback_general", "score": 0.2},
    ]
    assert round_trip["event"] == "voice_round_trip"
    assert round_trip["total_ms"] == 650
    assert round_trip["error_type"] is None


def test_frontend_telemetry_event_preserves_browser_message_field(capsys):
    logger = structured_logger_module._get_frontend_telemetry_logger()
    marker = structured_logger_module._FRONTEND_TELEMETRY_LOG_HANDLER_MARKER
    _remove_marked_handlers(logger, marker)

    payload = structured_logger_module.log_frontend_telemetry_event(
        event="audio_playback_failed",
        request_id="req-fe-23",
        session_id="session-5",
        from_state="thinking",
        to_state="error",
        message="NotAllowedError",
    )

    captured_payload = json.loads(capsys.readouterr().out.strip())

    assert payload["event"] == "audio_playback_failed"
    assert payload["telemetry_event"] == "audio_playback_failed"
    assert payload["source"] == "frontend"
    assert payload["message"] == "NotAllowedError"
    assert payload == captured_payload


def test_chat_response_adds_wave3_routing_fields():
    payload = structured_logger_module.build_chat_response_payload(
        request_id="req-chat-22",
        language="ja",
        metadata={
            "route": "facility",
            "agent_route": "facility_agent",
            "intent": "facility_hours",
            "confidence": "0.82",
        },
        latency_ms=123,
    )

    assert payload["agent_route"] == "facility_agent"
    assert payload["intent"] == "facility_hours"
    assert payload["confidence"] == 0.82
