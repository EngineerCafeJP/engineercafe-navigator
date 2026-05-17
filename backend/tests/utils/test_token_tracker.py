"""
TokenTracker ユーティリティのユニットテスト

record()、total_tokens、total_cost_usd、summary、reset、
ContextVar ヘルパー（get_token_tracker / reset_token_tracker）を検証する。
"""

import logging
from unittest.mock import patch

import pytest

from backend.utils.token_tracker import (
    LLMCallMetadata,
    TokenTracker,
    TokenUsage,
    _token_tracker_var,
    get_token_tracker,
    get_latest_llm_metadata,
    record_llm_call_metadata,
    reset_token_tracker,
)

# ============================================
# record()
# ============================================


def test_record_basic():
    """record() がトークン使用量を記録して TokenUsage を返す"""
    tracker = TokenTracker()

    usage = tracker.record(
        model="test-model",
        prompt_tokens=100,
        completion_tokens=50,
    )

    assert isinstance(usage, TokenUsage)
    assert usage.model == "test-model"
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50
    assert usage.total_tokens == 150
    assert len(tracker.usages) == 1


def test_record_negative_tokens():
    """負のトークン数は 0 に補正される"""
    tracker = TokenTracker()

    usage = tracker.record(
        model="test-model",
        prompt_tokens=-10,
        completion_tokens=-5,
    )

    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0


def test_cerebras_fast_model_cost_is_env_configurable_without_unknown_warning(
    monkeypatch,
    caplog,
):
    """Cerebras direct-hop models should not pollute production logs as unknown."""

    monkeypatch.setenv("CEREBRAS_FAST_MODEL", "gpt-oss-120b")
    monkeypatch.setenv("CEREBRAS_INPUT_COST_PER_1K", "0.25")
    monkeypatch.setenv("CEREBRAS_OUTPUT_COST_PER_1K", "0.75")
    tracker = TokenTracker()

    with caplog.at_level(logging.WARNING):
        usage = tracker.record(
            model="gpt-oss-120b",
            prompt_tokens=1000,
            completion_tokens=2000,
        )

    assert usage.estimated_cost_usd == 1.75
    assert "No cost data for model" not in caplog.text


# ============================================
# total_tokens / total_cost_usd
# ============================================


def test_total_tokens():
    """total_tokens が全記録のトークン合計を返す"""
    tracker = TokenTracker()

    tracker.record(model="m1", prompt_tokens=100, completion_tokens=50)
    tracker.record(model="m2", prompt_tokens=200, completion_tokens=100)

    assert tracker.total_tokens == 450  # (100+50) + (200+100)


def test_total_cost():
    """total_cost_usd がコストの合計を返す"""
    tracker = TokenTracker()

    # _estimate_cost をモックして確定的なコストを返す
    with patch.object(tracker, "_estimate_cost", return_value=0.001):
        tracker.record(model="m1", prompt_tokens=100, completion_tokens=50)
        tracker.record(model="m2", prompt_tokens=200, completion_tokens=100)

    assert tracker.total_cost_usd == pytest.approx(0.002, abs=1e-6)


# ============================================
# summary()
# ============================================


def test_summary_empty():
    """使用量がない場合、total_calls=0 のサマリーを返す"""
    tracker = TokenTracker()
    s = tracker.summary()

    assert s["total_calls"] == 0
    assert s["total_tokens"] == 0
    assert s["total_cost_usd"] == 0.0


def test_summary_with_entries():
    """使用量ありの場合、model_breakdown を含むサマリーを返す"""
    tracker = TokenTracker()

    with patch.object(tracker, "_estimate_cost", return_value=0.0):
        tracker.record(model="model-a", prompt_tokens=10, completion_tokens=5)
        tracker.record(model="model-a", prompt_tokens=20, completion_tokens=10)
        tracker.record(model="model-b", prompt_tokens=30, completion_tokens=15)

    s = tracker.summary()

    assert s["total_calls"] == 3
    assert s["total_tokens"] == 90  # (10+5) + (20+10) + (30+15)
    assert "model_breakdown" in s

    assert "model-a" in s["model_breakdown"]
    assert s["model_breakdown"]["model-a"]["calls"] == 2
    assert s["model_breakdown"]["model-a"]["prompt_tokens"] == 30
    assert s["model_breakdown"]["model-a"]["completion_tokens"] == 15

    assert "model-b" in s["model_breakdown"]
    assert s["model_breakdown"]["model-b"]["calls"] == 1


# ============================================
# reset()
# ============================================


def test_reset():
    """reset() が使用量をクリアする"""
    tracker = TokenTracker()

    with patch.object(tracker, "_estimate_cost", return_value=0.0):
        tracker.record(model="m", prompt_tokens=100, completion_tokens=50)

    assert len(tracker.usages) == 1

    tracker.reset()

    assert len(tracker.usages) == 0
    assert tracker.total_tokens == 0


def test_record_llm_call_metadata_tracks_latest_successful_call():
    """LLM provider/model metadata is request-scoped and returns the latest call."""
    tracker = TokenTracker()

    first = tracker.record_llm_call(
        provider="openrouter",
        model="google/gemini-3.1-flash-lite-preview",
        llm_latency_ms=12,
    )
    latest = tracker.record_llm_call(
        provider="cerebras",
        model="gpt-oss-120b",
        llm_latency_ms=7,
    )

    assert isinstance(first, LLMCallMetadata)
    assert tracker.llm_calls == [first, latest]
    assert tracker.latest_llm_call is latest
    assert latest.as_log_metadata() == {
        "provider": "cerebras",
        "model": "gpt-oss-120b",
        "llm_latency_ms": 7,
    }


def test_reset_clears_llm_call_metadata():
    tracker = TokenTracker()
    tracker.record_llm_call(provider="openrouter", model="m", llm_latency_ms=1)

    tracker.reset()

    assert tracker.llm_calls == []
    assert tracker.latest_llm_call is None


# ============================================
# ContextVar helpers
# ============================================


def test_get_token_tracker():
    """get_token_tracker() が新しいトラッカーを作成して返す"""
    # Reset to clean state
    _token_tracker_var.set(None)

    tracker = get_token_tracker()

    assert isinstance(tracker, TokenTracker)
    # 同一コンテキストで再度取得すると同じインスタンス
    assert get_token_tracker() is tracker

    # Cleanup
    _token_tracker_var.set(None)


def test_reset_token_tracker():
    """reset_token_tracker() が ContextVar を None にリセットする"""
    # Setup
    _token_tracker_var.set(None)
    _ = get_token_tracker()
    assert _token_tracker_var.get() is not None

    reset_token_tracker()

    assert _token_tracker_var.get() is None


def test_request_scoped_llm_metadata_helpers():
    reset_token_tracker()

    record_llm_call_metadata(provider="openrouter", model="model-a", llm_latency_ms=3)

    assert get_latest_llm_metadata() == {
        "provider": "openrouter",
        "model": "model-a",
        "llm_latency_ms": 3,
    }
    reset_token_tracker()
