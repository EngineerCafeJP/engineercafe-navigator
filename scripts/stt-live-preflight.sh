#!/usr/bin/env bash
set -euo pipefail

# Log-based STT latency preflight for alpha final voice testing.
#
# Usage:
#   scripts/stt-live-preflight.sh
#   scripts/stt-live-preflight.sh --minutes 1440 --dry-run

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ID="aipartner-426616"
SERVICE_NAME="engineer-cafe-backend"
REGION="asia-northeast1"
MINUTES=1440
LIMIT=500
OUTPUT_DIR="$ROOT_DIR/backend/tests/reports"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
GATE_REVISION="${ALPHA_SMOKE_CLOUD_RUN_REVISION:-}"
DRY_RUN=0

usage() {
  sed -n '3,8p' "$0"
  cat <<'EOF'

Options:
  --project ID        GCP project (default: aipartner-426616)
  --service NAME      Cloud Run service (default: engineer-cafe-backend)
  --region REGION     Cloud Run region (default: asia-northeast1)
  --revision NAME     Gate only this Cloud Run revision (default: ALPHA_SMOKE_CLOUD_RUN_REVISION)
  --minutes N         Lookback window in minutes (default: 1440)
  --limit N           Max log rows to read (default: 500)
  --output-dir DIR    Report directory (default: backend/tests/reports)
  --timestamp VALUE   Stable timestamp for output names
  --dry-run           Print the Cloud Logging filter without reading logs
  -h, --help          Show this usage

Output:
  backend/tests/reports/stt-live-preflight-<timestamp>.md
EOF
  exit "${1:-0}"
}

die() {
  echo "Error: $*" >&2
  exit 2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    die "required command not found: $1"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project) [ "$#" -ge 2 ] || die "--project requires a value"; PROJECT_ID="$2"; shift 2 ;;
    --service) [ "$#" -ge 2 ] || die "--service requires a value"; SERVICE_NAME="$2"; shift 2 ;;
    --region) [ "$#" -ge 2 ] || die "--region requires a value"; REGION="$2"; shift 2 ;;
    --revision) [ "$#" -ge 2 ] || die "--revision requires a value"; GATE_REVISION="$2"; shift 2 ;;
    --minutes) [ "$#" -ge 2 ] || die "--minutes requires a value"; MINUTES="$2"; shift 2 ;;
    --limit) [ "$#" -ge 2 ] || die "--limit requires a value"; LIMIT="$2"; shift 2 ;;
    --output-dir) [ "$#" -ge 2 ] || die "--output-dir requires a value"; OUTPUT_DIR="$2"; shift 2 ;;
    --timestamp) [ "$#" -ge 2 ] || die "--timestamp requires a value"; TIMESTAMP="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

[[ "$MINUTES" =~ ^[1-9][0-9]*$ ]] || die "--minutes must be a positive integer"
[[ "$LIMIT" =~ ^[1-9][0-9]*$ ]] || die "--limit must be a positive integer"
require_cmd python3

SINCE="$(python3 - "$MINUTES" <<'PY'
from datetime import datetime, timedelta, timezone
import sys
minutes = int(sys.argv[1])
print((datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"))
PY
)"
BASE_FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND resource.labels.location=\"$REGION\" AND jsonPayload.event=\"stt_winner\" AND timestamp >= \"$SINCE\""
GATE_FILTER="$BASE_FILTER"
if [ -n "$GATE_REVISION" ]; then
  GATE_FILTER="$GATE_FILTER AND resource.labels.revision_name=\"$GATE_REVISION\""
fi
REPORT="$OUTPUT_DIR/stt-live-preflight-$TIMESTAMP.md"

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: no gcloud logging read calls will be executed."
  echo "Project: $PROJECT_ID"
  echo "Gate revision: ${GATE_REVISION:-all revisions}"
  echo "Gate filter: $GATE_FILTER"
  echo "History filter: $BASE_FILTER"
  echo "Output: $REPORT"
  exit 0
fi

require_cmd gcloud
mkdir -p "$OUTPUT_DIR"
GATE_JSON="$(mktemp)"
HISTORY_JSON="$(mktemp)"
trap 'rm -f "$GATE_JSON" "$HISTORY_JSON"' EXIT

gcloud logging read "$GATE_FILTER" \
  --project "$PROJECT_ID" \
  --limit "$LIMIT" \
  --format=json > "$GATE_JSON"

if [ -n "$GATE_REVISION" ]; then
  gcloud logging read "$BASE_FILTER" \
    --project "$PROJECT_ID" \
    --limit "$LIMIT" \
    --format=json > "$HISTORY_JSON"
else
  cp "$GATE_JSON" "$HISTORY_JSON"
fi

python3 - "$GATE_JSON" "$HISTORY_JSON" "$REPORT" "$TIMESTAMP" "$PROJECT_ID" "$SERVICE_NAME" "$REGION" "$MINUTES" "$LIMIT" "${GATE_REVISION:-}" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter
from typing import Any

gate_path, history_path, report_path, timestamp, project, service, region, minutes, limit, gate_revision = sys.argv[1:11]


def load_rows(raw_path: str) -> list[dict[str, Any]]:
    entries = json.load(open(raw_path, encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for entry in entries if isinstance(entries, list) else []:
        payload = entry.get("jsonPayload") or {}
        if payload.get("event") != "stt_winner":
            continue
        duration = payload.get("stt_overall_duration_ms")
        try:
            duration_ms = int(duration)
        except Exception:
            continue
        rows.append(
            {
                "timestamp": entry.get("timestamp"),
                "revision": (entry.get("resource") or {}).get("labels", {}).get("revision_name"),
                "trace_id": payload.get("stt_trace_id") or "",
                "winner": payload.get("stt_winner") or payload.get("provider") or "unknown",
                "provider": payload.get("provider") or "unknown",
                "duration_ms": duration_ms,
                "success": payload.get("success"),
                "qwen_error_type": payload.get("qwen_error_type") or "",
            }
        )
    return rows


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    index = int(round((len(values) - 1) * pct))
    return values[index]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [row["duration_ms"] for row in rows]
    timeout_rows = [row for row in rows if row["qwen_error_type"] == "TimeoutError"]
    over_10s = [row for row in rows if row["duration_ms"] > 10_000]
    p95 = percentile(durations, 0.95) or 0
    over_10s_ratio = (len(over_10s) / len(rows)) if rows else 1.0
    passed = bool(rows) and not timeout_rows and (
        p95 <= 10_000 or (p95 <= 12_000 and over_10s_ratio <= 0.10)
    )
    return {
        "durations": durations,
        "winner_counts": Counter(str(row["winner"]) for row in rows),
        "provider_counts": Counter(str(row["provider"]) for row in rows),
        "revision_counts": Counter(str(row["revision"]) for row in rows),
        "timeout_rows": timeout_rows,
        "over_10s": over_10s,
        "over_30s": [row for row in rows if row["duration_ms"] > 30_000],
        "p95": p95,
        "over_10s_ratio": over_10s_ratio,
        "passed": passed,
    }


gate_rows = load_rows(gate_path)
history_rows = load_rows(history_path)
gate = summarize(gate_rows)
history = summarize(history_rows)
durations = gate["durations"]
passed = bool(gate["passed"])
timeout_rows = gate["timeout_rows"]
over_10s = gate["over_10s"]
p95 = percentile(durations, 0.95) or 0
over_10s_ratio = gate["over_10s_ratio"]

lines = [
    "# STT Live Preflight",
    "",
    f"- Timestamp: {timestamp}",
    f"- Project: {project}",
    f"- Service: {service}",
    f"- Region: {region}",
    f"- Gate revision: {gate_revision or 'all revisions'}",
    f"- Lookback minutes: {minutes}",
    f"- Log limit: {limit}",
    f"- Gate samples: {len(gate_rows)}",
    f"- Historical samples: {len(history_rows)}",
    f"- Overall passed: {'yes' if passed else 'no'}",
    "",
    "## Gate Latency",
    "",
    "| Metric | Value ms |",
    "| --- | ---: |",
    f"| min | {min(durations) if durations else 'n/a'} |",
    f"| p50 | {percentile(durations, 0.50) if durations else 'n/a'} |",
    f"| p95 | {percentile(durations, 0.95) if durations else 'n/a'} |",
    f"| max | {max(durations) if durations else 'n/a'} |",
    "",
    "## Winner Distribution",
    "",
    "| Winner | Count |",
    "| --- | ---: |",
]
for key, value in gate["winner_counts"].most_common():
    lines.append(f"| {key} | {value} |")
lines.extend(["", "## Provider Distribution", "", "| Provider | Count |", "| --- | ---: |"])
for key, value in gate["provider_counts"].most_common():
    lines.append(f"| {key} | {value} |")
lines.extend(["", "## Revision Distribution", "", "| Revision | Count |", "| --- | ---: |"])
for key, value in gate["revision_counts"].most_common():
    lines.append(f"| {key} | {value} |")

lines.extend(
    [
        "",
    "## Risk Signals",
    "",
    f"- Qwen TimeoutError samples: {len(timeout_rows)}",
    f"- Samples over 10s: {len(over_10s)}",
    f"- Samples over 30s: {len(gate['over_30s'])}",
    f"- Samples over 10s ratio: {over_10s_ratio:.1%}",
    "- Pass rule: p95 <= 10s, or p95 <= 12s with <= 10% samples over 10s and no TimeoutError",
    ]
)
if gate_revision:
    lines.extend(
        [
            "",
            "## Historical Risk Report",
            "",
            "Historical rows are reported for operator awareness only; they do not decide the release gate when a gate revision is set.",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| samples | {len(history_rows)} |",
            f"| p95 ms | {percentile(history['durations'], 0.95) if history['durations'] else 'n/a'} |",
            f"| max ms | {max(history['durations']) if history['durations'] else 'n/a'} |",
            f"| TimeoutError samples | {len(history['timeout_rows'])} |",
            f"| samples over 10s | {len(history['over_10s'])} |",
            f"| samples over 30s | {len(history['over_30s'])} |",
            f"| samples over 10s ratio | {history['over_10s_ratio']:.1%} |",
            "",
            "| Revision | Count |",
            "| --- | ---: |",
        ]
    )
    for key, value in history["revision_counts"].most_common():
        lines.append(f"| {key} | {value} |")
if timeout_rows or over_10s:
    lines.extend(
        [
            "",
            "| Timestamp | Revision | Trace | Winner | Provider | Duration ms | Error |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    risk_rows = {
        (
            row["timestamp"],
            row["revision"],
            row["trace_id"],
            row["winner"],
            row["provider"],
            row["duration_ms"],
            row["qwen_error_type"],
        ): row
        for row in timeout_rows + over_10s
    }.values()
    for row in sorted(risk_rows, key=lambda x: x["duration_ms"], reverse=True)[:20]:
        lines.append(
            f"| {row['timestamp']} | {row['revision']} | {row['trace_id']} | {row['winner']} | "
            f"{row['provider']} | {row['duration_ms']} | {row['qwen_error_type']} |"
        )

pathlib.Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(report_path)
sys.exit(0 if passed else 1)
PY
