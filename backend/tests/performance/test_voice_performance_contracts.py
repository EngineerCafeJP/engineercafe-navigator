from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.stt_agent import LocalSTTClient, STTAgent, TranscriptionResult
from backend.scripts.stt_profile_summary import (
    STT_EVENT_FIELDS,
    extract_stt_events,
    summarize_stt_events,
)
from backend.utils.intent_classifier import filler_intent_for_query


def _make_qwen_primary_agent(mock_qwen: MagicMock, mock_vosk: MagicMock) -> STTAgent:
    agent = STTAgent(
        stt_provider="vosk",
        stt_client=mock_qwen,
        fallback_client=None,
        language_processor=None,
    )
    agent.stt_provider = "qwen-primary"
    agent._vosk_fallback_client = mock_vosk
    agent._qwen_timeout = 10.0
    agent._qwen_hedge_delay = 0.01
    agent._qwen_hedge_grace = 0.20
    agent._qwen_latency_budget = 1.0
    return agent


def _stt_records(caplog: pytest.LogCaptureFixture) -> list[object]:
    return [record for record in caplog.records if record.name == "backend.observability.stt"]


@pytest.mark.asyncio
async def test_stt_trace_events_expose_qwen_vosk_hedge_and_overall_timings(caplog):
    """#529 needs one trace to separate model duration, hedge delay/grace, and total latency."""

    caplog.set_level("INFO", logger="backend.observability.stt")

    async def slow_qwen(*args, **kwargs):
        await asyncio.sleep(0.04)
        return TranscriptionResult(
            text="エンジニアカフェの営業時間を教えてください",
            confidence=0.95,
            language="ja",
        )

    async def fast_vosk(*args, **kwargs):
        await asyncio.sleep(0.01)
        return TranscriptionResult(text="fast fallback", confidence=0.80, language="ja")

    mock_qwen = MagicMock()
    mock_qwen.transcribe = slow_qwen
    mock_vosk = MagicMock(spec=LocalSTTClient)
    mock_vosk.transcribe = AsyncMock(side_effect=fast_vosk)

    result = await _make_qwen_primary_agent(mock_qwen, mock_vosk).speech_to_text(
        b"audio",
        language="ja",
    )

    assert result["provider"] == "qwen-primary"

    records = _stt_records(caplog)
    winner = next(record for record in records if getattr(record, "event", None) == "stt_winner")
    trace_records = [
        record for record in records if getattr(record, "stt_trace_id", None) == winner.stt_trace_id
    ]
    by_event = {getattr(record, "event", None): record for record in trace_records}

    assert set(by_event) >= {
        "stt_qwen_complete",
        "stt_vosk_complete",
        "stt_qwen_hedge_start",
        "stt_qwen_hedge_grace_start",
        "stt_winner",
    }
    assert by_event["stt_winner"].stt_winner == "qwen"
    assert isinstance(by_event["stt_winner"].stt_overall_duration_ms, int)
    assert isinstance(by_event["stt_qwen_complete"].stt_qwen_duration_ms, int)
    assert isinstance(by_event["stt_vosk_complete"].stt_vosk_duration_ms, int)
    assert by_event["stt_qwen_hedge_start"].hedge_delay_s == pytest.approx(0.01)
    assert by_event["stt_qwen_hedge_start"].hedge_grace_s == pytest.approx(0.20)
    assert by_event["stt_qwen_hedge_grace_start"].hedge_grace_s == pytest.approx(0.20)
    assert by_event["stt_winner"].hedge_grace_s == pytest.approx(0.20)


def test_stt_profile_summary_preserves_timing_columns_for_issue_529():
    entries = [
        {
            "timestamp": "2026-05-09T00:00:00Z",
            "jsonPayload": {
                "event": "stt_qwen_hedge_start",
                "stt_trace_id": "stt-local",
                "provider": "qwen-primary",
                "stt_qwen_duration_ms": 10,
                "hedge_delay_s": 0.01,
                "hedge_grace_s": 0.2,
            },
        },
        {
            "timestamp": "2026-05-09T00:00:00.020Z",
            "jsonPayload": {
                "event": "stt_vosk_complete",
                "stt_trace_id": "stt-local",
                "provider": "vosk-fallback",
                "success": True,
                "stt_vosk_duration_ms": 9,
            },
        },
        {
            "timestamp": "2026-05-09T00:00:00.040Z",
            "jsonPayload": {
                "event": "stt_qwen_complete",
                "stt_trace_id": "stt-local",
                "provider": "qwen-primary",
                "success": True,
                "stt_qwen_duration_ms": 40,
            },
        },
        {
            "timestamp": "2026-05-09T00:00:00.041Z",
            "jsonPayload": {
                "event": "stt_winner",
                "stt_trace_id": "stt-local",
                "stt_winner": "qwen",
                "provider": "qwen-primary",
                "success": True,
                "stt_overall_duration_ms": 41,
                "hedge_grace_s": 0.2,
            },
        },
    ]

    events = extract_stt_events(entries)
    summary = summarize_stt_events(events)

    assert "hedge_delay_s" in STT_EVENT_FIELDS
    assert "hedge_grace_s" in STT_EVENT_FIELDS
    assert "effective_hedge_grace_s" in STT_EVENT_FIELDS
    assert events[0]["hedge_delay_s"] == 0.01
    assert events[0]["hedge_grace_s"] == 0.2
    assert summary["trace_count"] == 1
    assert summary["hedged_count"] == 1
    assert summary["winner_counts"] == {"qwen": 1}
    assert summary["qwen"]["p50"] == 40
    assert summary["vosk"]["p50"] == 9
    assert summary["overall"]["p50"] == 41


def test_static_filler_lookup_stays_under_local_budget_for_issue_611():
    queries = [
        "WiFiのパスワードは？",
        "明日のイベントは？",
        "スライドを見せて",
        "営業時間を教えて",
        "Where is the restroom?",
    ]

    started_at = time.perf_counter()
    results = [filler_intent_for_query(query) for query in queries for _ in range(100)]
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert set(results) >= {"wifi", "event", "slide", "business_info", "facility"}
    assert elapsed_ms / len(results) < 0.5
