"""
リクエストレイテンシ追跡ユーティリティ

オペレーション別のレイテンシを収集・集計するための軽量トラッカー。
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List


@dataclass
class TimingResult:
    """個別オペレーションの計測結果"""

    operation: str
    duration_ms: float
    timestamp: str


class LatencyTracker:
    """リクエストあたりのオペレーション別レイテンシ収集"""

    def __init__(self):
        self._entries: List[TimingResult] = []

    @contextmanager
    def track(self, operation: str):
        """オペレーションの所要時間を計測するコンテキストマネージャー"""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self._entries.append(
                TimingResult(
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

    @property
    def entries(self) -> List[TimingResult]:
        """記録済みエントリ一覧"""
        return list(self._entries)

    def percentile(self, p: int) -> float:
        """記録済みエントリのパーセンタイルを計算

        Args:
            p: パーセンタイル値 (0-100)

        Returns:
            指定パーセンタイルのduration_ms値
        """
        if not 0 <= p <= 100:
            raise ValueError(f"Percentile must be between 0 and 100, got {p}")
        if not self._entries:
            return 0.0
        durations = sorted(e.duration_ms for e in self._entries)
        k = (len(durations) - 1) * (p / 100)
        f = int(k)
        c = f + 1
        if c >= len(durations):
            return durations[-1]
        return durations[f] + (k - f) * (durations[c] - durations[f])

    def summary(self) -> dict:
        """全エントリのサマリーを生成"""
        if not self._entries:
            return {"total_operations": 0, "total_ms": 0.0}
        durations = [e.duration_ms for e in self._entries]

        # Aggregate by operation name
        ops: dict[str, list[float]] = {}
        for e in self._entries:
            ops.setdefault(e.operation, []).append(e.duration_ms)

        return {
            "total_operations": len(self._entries),
            "total_ms": round(sum(durations), 2),
            "p50_ms": round(self.percentile(50), 2),
            "p95_ms": round(self.percentile(95), 2),
            "p99_ms": round(self.percentile(99), 2),
            "min_ms": round(min(durations), 2),
            "max_ms": round(max(durations), 2),
            "operations": {
                name: {
                    "count": len(durs),
                    "total_ms": round(sum(durs), 2),
                    "avg_ms": round(sum(durs) / len(durs), 2),
                }
                for name, durs in ops.items()
            },
        }

    def reset(self):
        """エントリをクリア"""
        self._entries.clear()
