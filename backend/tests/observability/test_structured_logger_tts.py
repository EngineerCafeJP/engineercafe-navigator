from __future__ import annotations

import json
import logging

from backend.observability import structured_logger as structured_logger_module


def _remove_marked_handlers(logger, marker: str) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, marker, False):
            logger.removeHandler(handler)
            handler.close()


def test_log_tts_cache_event_outputs_json_with_tts_cache_hit(capsys):
    logger = structured_logger_module._get_tts_cache_logger()
    marker = structured_logger_module._TTS_CACHE_LOG_HANDLER_MARKER

    _remove_marked_handlers(logger, marker)

    structured_logger_module.log_tts_cache_event(
        hit=True,
        cache_key="ja:neutral:こんにちは",
        language="ja",
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert payload["event"] == "tts_cache"
    assert payload["tts_cache_hit"] is True
    assert payload["cache_key"] == "ja:neutral:こんにちは"
    assert payload["language"] == "ja"


def test_log_tts_event_includes_request_id(capsys):
    logger = structured_logger_module._get_tts_logger()
    marker = structured_logger_module._TTS_LOG_HANDLER_MARKER

    _remove_marked_handlers(logger, marker)

    token = structured_logger_module._current_request_id
    structured_logger_module._current_request_id = lambda: "req-tts-613"
    try:
        structured_logger_module.log_tts_event(
            event="tts_complete",
            provider="piper",
            language="ja",
            success=True,
            tts_overall_duration_ms=42,
            fallback_used=True,
            fallback_provider="voicevox",
            error_type="RuntimeError",
        )
    finally:
        structured_logger_module._current_request_id = token

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert payload["event"] == "tts_complete"
    assert payload["request_id"] == "req-tts-613"
    assert payload["tts_overall_duration_ms"] == 42
    assert payload["fallback_used"] is True
    assert payload["fallback_provider"] == "voicevox"
    assert payload["error_type"] == "RuntimeError"


def test_log_memory_event_outputs_json_and_request_id(capsys, monkeypatch):
    logger = structured_logger_module._get_memory_logger()
    marker = structured_logger_module._MEMORY_LOG_HANDLER_MARKER
    _remove_marked_handlers(logger, marker)
    monkeypatch.setattr(structured_logger_module, "_current_request_id", lambda: "req-memory-834")

    structured_logger_module.log_memory_event(
        event="memory_store_message",
        session_id="session-1",
        role="assistant",
        success=True,
        latency_ms=12,
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert payload["event"] == "memory_store_message"
    assert payload["request_id"] == "req-memory-834"
    assert payload["session_id"] == "session-1"
    assert payload["role"] == "assistant"
    assert payload["success"] is True
    assert payload["latency_ms"] == 12


def test_reception_transition_and_ltm_promote_are_caplog_compatible(
    caplog,
    monkeypatch,
):
    monkeypatch.setenv("OBSERVABILITY_LOG_PROPAGATE", "true")
    caplog.set_level(logging.INFO, logger=structured_logger_module.MEMORY_LOGGER_NAME)

    reception_payload = structured_logger_module.log_reception_transition(
        request_id="req-reception-834",
        session_id="session-2",
        reception_session_id="reception-1",
        from_stage="purpose_hearing",
        to_stage="completed",
        action="complete_reception",
        status="completed",
        target_agent="facility",
    )
    promote_payload = structured_logger_module.log_ltm_promote(
        request_id="req-promote-834",
        status="success",
        user_id="visitor-1",
        candidates=3,
        promoted=1,
        duplicates_skipped=0,
    )

    assert reception_payload["event"] == "reception_transition"
    assert promote_payload["event"] == "ltm_promote"

    reception_record = next(
        record
        for record in caplog.records
        if record.name == structured_logger_module.MEMORY_LOGGER_NAME
        and getattr(record, "request_id", None) == "req-reception-834"
    )
    promote_record = next(
        record
        for record in caplog.records
        if record.name == structured_logger_module.MEMORY_LOGGER_NAME
        and getattr(record, "request_id", None) == "req-promote-834"
    )

    assert reception_record.event == "reception_transition"
    assert reception_record.from_stage == "purpose_hearing"
    assert reception_record.to_stage == "completed"
    assert reception_record.action == "complete_reception"
    assert reception_record.target_agent == "facility"
    assert promote_record.event == "ltm_promote"
    assert promote_record.status == "success"
    assert promote_record.user_id == "visitor-1"
    assert promote_record.promoted == 1


def test_chat_response_route_does_not_fall_back_to_agent_class():
    payload = structured_logger_module.build_chat_response_payload(
        request_id="req-route-834",
        language="ja",
        metadata={
            "agent": "BusinessInfoAgent",
            "request_type": "facility",
            "provider": "openrouter",
            "model": "google/gemini-2.5-flash-lite",
            "llm_latency_ms": "87",
        },
        latency_ms=100,
    )

    assert payload["route"] == "facility"
    assert payload["agent_class"] == "BusinessInfoAgent"
    assert payload["provider"] == "openrouter"
    assert payload["model"] == "google/gemini-2.5-flash-lite"
    assert payload["llm_latency_ms"] == 87


def test_chat_response_route_priority_and_unknown_llm_fields():
    payload = structured_logger_module.build_chat_response_payload(
        request_id="req-route-priority-834",
        language=None,
        metadata={
            "category": "business_info",
            "request_type": "facility",
            "reception_target_agent": "facility_agent",
            "agent": "orchestrator_inline",
        },
        latency_ms=12,
    )

    assert payload["language"] == "unknown"
    assert payload["route"] == "business_info"
    assert payload["agent_class"] is None
    assert payload["provider"] == "unknown"
    assert payload["model"] == "unknown"
    assert payload["llm_latency_ms"] is None


def test_chat_response_hallucination_flag_coerces_string_values():
    false_payload = structured_logger_module.build_chat_response_payload(
        request_id="req-hallucination-false-834",
        language="ja",
        metadata={"hallucination_flag": "false"},
        latency_ms=12,
    )
    true_payload = structured_logger_module.build_chat_response_payload(
        request_id="req-hallucination-true-834",
        language="ja",
        metadata={"hallucination_flag": "true"},
        latency_ms=12,
    )

    assert false_payload["hallucination_flag"] is False
    assert true_payload["hallucination_flag"] is True


def test_observability_loggers_do_not_propagate_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("OBSERVABILITY_LOG_PROPAGATE", raising=False)

    chat_logger = structured_logger_module._get_chat_response_logger()
    stt_logger = structured_logger_module._get_stt_logger()
    tts_logger = structured_logger_module._get_tts_logger()
    memory_logger = structured_logger_module._get_memory_logger()

    assert chat_logger.propagate is False
    assert stt_logger.propagate is False
    assert tts_logger.propagate is False
    assert memory_logger.propagate is False


def test_observability_log_propagation_can_be_enabled_for_tests(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OBSERVABILITY_LOG_PROPAGATE", "true")

    stt_logger = structured_logger_module._get_stt_logger()

    assert stt_logger.propagate is True
