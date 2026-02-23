"""
LatencyTracker ユーティリティのユニットテスト

track() コンテキストマネージャー、percentile 計算、summary 生成、
reset 動作を検証する。
"""

import time

import pytest

from backend.utils.timing import LatencyTracker, TimingResult

# ============================================
# track() context manager
# ============================================


def test_track_records_entry():
    """track() がコンテキストマネージャー終了後に TimingResult を記録する"""
    tracker = LatencyTracker()

    with tracker.track("test_op"):
        time.sleep(0.01)  # 10 ms

    assert len(tracker.entries) == 1
    entry = tracker.entries[0]
    assert isinstance(entry, TimingResult)
    assert entry.operation == "test_op"
    assert entry.duration_ms > 0
    assert entry.timestamp  # ISO format string


# ============================================
# percentile()
# ============================================


def test_percentile_empty():
    """エントリがない場合、percentile は 0.0 を返す"""
    tracker = LatencyTracker()
    assert tracker.percentile(50) == 0.0
    assert tracker.percentile(99) == 0.0


def test_percentile_single():
    """エントリが 1 件の場合、任意のパーセンタイルでその値を返す"""
    tracker = LatencyTracker()

    with tracker.track("single"):
        pass

    value = tracker.entries[0].duration_ms
    assert tracker.percentile(0) == value
    assert tracker.percentile(50) == value
    assert tracker.percentile(100) == value


def test_percentile_validation():
    """p < 0 または p > 100 で ValueError を送出する"""
    tracker = LatencyTracker()

    with pytest.raises(ValueError, match="Percentile must be between 0 and 100"):
        tracker.percentile(-1)

    with pytest.raises(ValueError, match="Percentile must be between 0 and 100"):
        tracker.percentile(101)


# ============================================
# summary()
# ============================================


def test_summary_empty():
    """エントリがない場合、total_operations=0 のサマリーを返す"""
    tracker = LatencyTracker()
    s = tracker.summary()

    assert s["total_operations"] == 0
    assert s["total_ms"] == 0.0


def test_summary_with_entries():
    """エントリありの場合、全フィールドが存在する"""
    tracker = LatencyTracker()

    with tracker.track("op_a"):
        pass
    with tracker.track("op_b"):
        pass

    s = tracker.summary()

    assert s["total_operations"] == 2
    assert "total_ms" in s
    assert "p50_ms" in s
    assert "p95_ms" in s
    assert "p99_ms" in s
    assert "min_ms" in s
    assert "max_ms" in s
    assert "operations" in s
    assert "op_a" in s["operations"]
    assert "op_b" in s["operations"]

    # Each operation breakdown has count, total_ms, avg_ms
    for op_data in s["operations"].values():
        assert "count" in op_data
        assert "total_ms" in op_data
        assert "avg_ms" in op_data


# ============================================
# reset()
# ============================================


def test_reset():
    """reset() がエントリをクリアする"""
    tracker = LatencyTracker()

    with tracker.track("to_be_cleared"):
        pass

    assert len(tracker.entries) == 1

    tracker.reset()

    assert len(tracker.entries) == 0
    assert tracker.summary()["total_operations"] == 0
