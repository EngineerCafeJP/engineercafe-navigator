"""Summarize structured STT Cloud Logging exports for local profiling.

This module intentionally has no GCP dependency. Feed it the JSON produced by
``gcloud logging read --format=json`` or a saved fixture and it will emit the
same timing columns used to triage #529.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

STT_EVENT_FIELDS = [
    "timestamp",
    "stt_trace_id",
    "event",
    "provider",
    "stt_winner",
    "success",
    "stt_qwen_duration_ms",
    "stt_vosk_duration_ms",
    "stt_overall_duration_ms",
    "hedge_delay_s",
    "hedge_grace_s",
    "effective_hedge_grace_s",
    "latency_budget_s",
    "qwen_error_type",
    "vosk_error_type",
    "language",
    "error_type",
]


def extract_stt_events(log_entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract structured ``stt_*`` payloads from Cloud Logging JSON entries."""

    events: list[dict[str, Any]] = []
    for entry in log_entries:
        payload = entry.get("jsonPayload")
        if not isinstance(payload, dict):
            continue
        event_name = payload.get("event")
        if not isinstance(event_name, str) or not event_name.startswith("stt_"):
            continue
        row = {field: payload.get(field) for field in STT_EVENT_FIELDS}
        row["timestamp"] = entry.get("timestamp") or payload.get("timestamp")
        events.append(row)
    return events


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * ratio
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def timing_stats(events: Iterable[dict[str, Any]], field: str) -> dict[str, float | int | None]:
    nums = [float(value) for event in events if (value := event.get(field)) not in (None, "")]
    if not nums:
        return {"count": 0, "p50": None, "p90": None, "p95": None, "max": None}
    return {
        "count": len(nums),
        "p50": percentile(nums, 0.50),
        "p90": percentile(nums, 0.90),
        "p95": percentile(nums, 0.95),
        "max": max(nums),
    }


def summarize_stt_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    winner_events = [event for event in events if event.get("event") == "stt_winner"]
    qwen_events = [event for event in events if event.get("event") == "stt_qwen_complete"]
    vosk_events = [event for event in events if event.get("event") == "stt_vosk_complete"]

    return {
        "event_count": len(events),
        "trace_count": len(
            {event.get("stt_trace_id") for event in events if event.get("stt_trace_id")}
        ),
        "winner_counts": dict(
            Counter(event.get("stt_winner") or "unknown" for event in winner_events)
        ),
        "overall": timing_stats(winner_events, "stt_overall_duration_ms"),
        "qwen": timing_stats(qwen_events, "stt_qwen_duration_ms"),
        "vosk": timing_stats(vosk_events, "stt_vosk_duration_ms"),
        "hedged_count": sum(1 for event in events if event.get("event") == "stt_qwen_hedge_start"),
        "grace_count": sum(
            1 for event in events if event.get("event") == "stt_qwen_hedge_grace_start"
        ),
    }


def write_event_csv(events: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=STT_EVENT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events)


def _fmt_ms(value: float | int | None) -> str:
    return "n/a" if value is None else f"{value:.0f}"


def write_markdown_summary(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# STT Profile Summary",
        "",
        f"- Structured STT events: `{summary['event_count']}`",
        f"- STT traces: `{summary['trace_count']}`",
        f"- Hedged traces: `{summary['hedged_count']}`",
        f"- Grace waits: `{summary['grace_count']}`",
        "",
        "| Metric | count | p50 ms | p90 ms | p95 ms | max ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, key in (
        ("stt_overall", "overall"),
        ("qwen_inference", "qwen"),
        ("vosk_inference", "vosk"),
    ):
        stats = summary[key]
        lines.append(
            f"| {label} | {stats['count']} | {_fmt_ms(stats['p50'])} | "
            f"{_fmt_ms(stats['p90'])} | {_fmt_ms(stats['p95'])} | {_fmt_ms(stats['max'])} |"
        )
    lines.extend(["", "## Winners", ""])
    for winner, count in sorted(summary["winner_counts"].items()):
        lines.append(f"- `{winner}`: {count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_json", type=Path, help="Cloud Logging JSON export")
    parser.add_argument("--event-csv", type=Path, help="Optional normalized STT event CSV")
    parser.add_argument("--report", type=Path, help="Optional Markdown summary path")
    args = parser.parse_args()

    entries = json.loads(args.log_json.read_text(encoding="utf-8") or "[]")
    events = extract_stt_events(entries)
    summary = summarize_stt_events(events)

    if args.event_csv:
        write_event_csv(events, args.event_csv)
    if args.report:
        write_markdown_summary(summary, args.report)
    if not args.event_csv and not args.report:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
