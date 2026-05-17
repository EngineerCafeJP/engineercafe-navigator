"""Benchmark SimplifiedMemoryHelper recent-message loading latency.

This script is intentionally read-only. It measures the current live or local
Supabase-backed `agent_memory` query path for an existing session.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

from backend.utils.memory_helper import SimplifiedMemoryHelper


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark memory loader p95 latency.")
    parser.add_argument("--session-id", required=True, help="Existing session_id to read.")
    parser.add_argument("--iterations", type=int, default=50, help="Number of read iterations.")
    return parser.parse_args()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percentile / 100) * (len(ordered) - 1)))))
    return ordered[index]


async def _run() -> None:
    args = _parse_args()
    helper = SimplifiedMemoryHelper()
    if helper.supabase is None:
        raise SystemExit("SUPABASE_URL and SUPABASE_KEY are required")

    timings_ms: list[float] = []
    row_counts: list[int] = []
    for _ in range(max(1, args.iterations)):
        started_at = time.perf_counter()
        messages = await helper._get_recent_messages(args.session_id)
        timings_ms.append((time.perf_counter() - started_at) * 1000)
        row_counts.append(len(messages))

    result = {
        "session_id": args.session_id,
        "iterations": len(timings_ms),
        "row_count_min": min(row_counts) if row_counts else 0,
        "row_count_max": max(row_counts) if row_counts else 0,
        "latency_ms_min": round(min(timings_ms), 2),
        "latency_ms_p50": round(statistics.median(timings_ms), 2),
        "latency_ms_p95": round(_percentile(timings_ms, 95), 2),
        "latency_ms_max": round(max(timings_ms), 2),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_run())
