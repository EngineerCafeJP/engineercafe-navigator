#!/usr/bin/env bash
set -euo pipefail

# Verify alpha final structured log coverage in Cloud Logging.
#
# Usage:
#   scripts/cloud-logging-verify.sh
#   scripts/cloud-logging-verify.sh --minutes 120 --project aipartner-426616
#   scripts/cloud-logging-verify.sh --dry-run

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ID="aipartner-426616"
SERVICE_NAME="engineer-cafe-backend"
REGION="asia-northeast1"
MINUTES=120
THRESHOLD=99
OUTPUT_DIR="$ROOT_DIR/backend/tests/reports"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DRY_RUN=0
LIMIT=1000

usage() {
  sed -n '4,9p' "$0"
  cat <<'EOF'

Options:
  --project ID           GCP project (default: aipartner-426616)
  --service NAME         Cloud Run service (default: engineer-cafe-backend)
  --region REGION        Cloud Run region (default: asia-northeast1)
  --minutes N            Lookback window in minutes (default: 120)
  --threshold FLOAT      STT event generation threshold percent (default: 99; 0.99 also accepted)
  --limit N              Max log rows per query (default: 1000)
  --output-dir DIR       Report directory (default: backend/tests/reports)
  --timestamp VALUE      Stable timestamp for output names
  --dry-run              Validate local checks and print gcloud filters only
  -h, --help             Show this usage

Output:
  backend/tests/reports/cloud-logging-check-<timestamp>.md
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

is_positive_int() {
  [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]
}

is_number() {
  [[ "${1:-}" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project) [ "$#" -ge 2 ] || die "--project requires a value"; PROJECT_ID="$2"; shift 2 ;;
    --service) [ "$#" -ge 2 ] || die "--service requires a value"; SERVICE_NAME="$2"; shift 2 ;;
    --region) [ "$#" -ge 2 ] || die "--region requires a value"; REGION="$2"; shift 2 ;;
    --minutes) [ "$#" -ge 2 ] || die "--minutes requires a value"; MINUTES="$2"; shift 2 ;;
    --threshold) [ "$#" -ge 2 ] || die "--threshold requires a value"; THRESHOLD="$2"; shift 2 ;;
    --limit) [ "$#" -ge 2 ] || die "--limit requires a value"; LIMIT="$2"; shift 2 ;;
    --output-dir) [ "$#" -ge 2 ] || die "--output-dir requires a value"; OUTPUT_DIR="$2"; shift 2 ;;
    --timestamp) [ "$#" -ge 2 ] || die "--timestamp requires a value"; TIMESTAMP="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$PROJECT_ID" ]] || die "project must not be empty"
[[ -n "$SERVICE_NAME" ]] || die "service must not be empty"
[[ -n "$REGION" ]] || die "region must not be empty"
is_positive_int "$MINUTES" || die "--minutes must be a positive integer"
is_positive_int "$LIMIT" || die "--limit must be a positive integer"
is_number "$THRESHOLD" || die "--threshold must be numeric"
require_cmd python3

REPORT="$OUTPUT_DIR/cloud-logging-check-$TIMESTAMP.md"
BASE_FILTER='resource.type="cloud_run_revision"'
BASE_FILTER="$BASE_FILTER AND resource.labels.service_name=\"$SERVICE_NAME\""
BASE_FILTER="$BASE_FILTER AND resource.labels.location=\"$REGION\""
BASE_FILTER="$BASE_FILTER AND timestamp >= \"$(python3 - "$MINUTES" <<'PY'
from datetime import datetime, timedelta, timezone
import sys
minutes = int(sys.argv[1])
print((datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"))
PY
)\""

event_filter() {
  printf '%s AND (jsonPayload.event="%s" OR labels.event="%s" OR textPayload:"%s")' \
    "$BASE_FILTER" "$1" "$1" "$1"
}

chat_filter="$BASE_FILTER AND (jsonPayload.event=\"chat_response\" OR labels.event=\"chat_response\" OR textPayload:\"chat_response\")"
memory_filter="$BASE_FILTER AND ((jsonPayload.logger=\"backend.utils.memory_helper\" AND jsonPayload.level=\"ERROR\") OR jsonPayload.event=\"memory_helper_error\" OR (jsonPayload.logger:\"memory_helper\" AND severity>=ERROR) OR (textPayload:\"memory_helper\" AND severity>=ERROR))"
uuid_hygiene_filter="$BASE_FILTER AND (textPayload:\"invalid input syntax for type uuid\" OR jsonPayload.message:\"invalid input syntax for type uuid\" OR jsonPayload.exception.message:\"invalid input syntax for type uuid\")"
reception_hygiene_filter="$BASE_FILTER AND (textPayload:\"Reception session persistence failed\" OR jsonPayload.message:\"Reception session persistence failed\")"

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: no gcloud logging read calls will be executed."
  echo "Project: $PROJECT_ID"
  echo "Output: $REPORT"
  for event in stt_qwen_start stt_qwen_complete stt_winner; do
    echo "Filter[$event]: $(event_filter "$event")"
  done
  echo "Filter[chat_response]: $chat_filter"
  echo "Filter[memory_helper_error]: $memory_filter"
  echo "Filter[uuid_hygiene]: $uuid_hygiene_filter"
  echo "Filter[reception_hygiene]: $reception_hygiene_filter"
  exit 0
fi

require_cmd gcloud
mkdir -p "$OUTPUT_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

read_logs() {
  local filter="$1"
  local out="$2"
  gcloud logging read "$filter" \
    --project "$PROJECT_ID" \
    --limit "$LIMIT" \
    --format=json > "$out"
}

for event in stt_qwen_start stt_qwen_complete stt_winner; do
  read_logs "$(event_filter "$event")" "$TMP_DIR/$event.json"
done
read_logs "$chat_filter" "$TMP_DIR/chat_response.json"
read_logs "$memory_filter" "$TMP_DIR/memory_helper_errors.json"
read_logs "$uuid_hygiene_filter" "$TMP_DIR/uuid_hygiene.json"
read_logs "$reception_hygiene_filter" "$TMP_DIR/reception_hygiene.json"

python3 - "$TIMESTAMP" "$PROJECT_ID" "$SERVICE_NAME" "$REGION" "$MINUTES" "$THRESHOLD" "$REPORT" "$TMP_DIR" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict
from typing import Any

timestamp, project, service, region, minutes, threshold_raw, report, tmp = sys.argv[1:9]
threshold = float(threshold_raw)
if threshold <= 1:
    threshold *= 100
tmp_path = pathlib.Path(tmp)
required_stt_events = ("stt_qwen_start", "stt_qwen_complete", "stt_winner")
required_chat_fields = ("latency_ms", "route", "language", "rag_fallback", "ltm_store_write")


def load(name: str) -> list[dict[str, Any]]:
    path = tmp_path / f"{name}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def payload(entry: dict[str, Any]) -> dict[str, Any]:
    data = entry.get("jsonPayload")
    return data if isinstance(data, dict) else {}


def field_present(data: dict[str, Any], field: str) -> bool:
    if field in data and data[field] is not None:
        return True
    obs = data.get("observability_payload")
    return isinstance(obs, dict) and field in obs and obs[field] is not None


def field_value(data: dict[str, Any], field: str) -> Any:
    if field in data:
        return data.get(field)
    obs = data.get("observability_payload")
    if isinstance(obs, dict):
        return obs.get(field)
    return None


def md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


stt_entries: list[dict[str, Any]] = []
for name in required_stt_events:
    for entry in load(name):
        data = payload(entry)
        if data.get("event") == name:
            stt_entries.append({**data, "_timestamp": entry.get("timestamp")})

event_counts = Counter(str(item.get("event")) for item in stt_entries)
trace_events: dict[str, set[str]] = defaultdict(set)
missing_trace_count = 0
for index, item in enumerate(stt_entries):
    trace_id = item.get("stt_trace_id")
    if not trace_id:
        missing_trace_count += 1
        trace_id = f"__missing_stt_trace_id_{index}"
    trace_events[str(trace_id)].add(str(item.get("event")))

trace_count = len(trace_events)
rates: dict[str, float] = {}
missing_by_event: dict[str, int] = {}
for name in required_stt_events:
    present = sum(1 for events in trace_events.values() if name in events)
    rates[name] = (present / trace_count * 100) if trace_count else 0.0
    missing_by_event[name] = trace_count - present

chat_entries = [
    {**payload(entry), "_timestamp": entry.get("timestamp")}
    for entry in load("chat_response")
    if payload(entry).get("event") == "chat_response"
    or (
        isinstance(payload(entry).get("observability_payload"), dict)
        and payload(entry)["observability_payload"].get("event") == "chat_response"
    )
]
chat_missing: list[dict[str, Any]] = []
for index, data in enumerate(chat_entries):
    missing = [field for field in required_chat_fields if not field_present(data, field)]
    if missing:
        chat_missing.append({"index": index, "missing": missing, "data": data})

memory_errors = []
for entry in load("memory_helper_errors"):
    data = payload(entry)
    if (
        data.get("logger") == "backend.utils.memory_helper"
        or data.get("event") == "memory_helper_error"
        or "memory_helper" in str(entry.get("textPayload", ""))
    ):
        memory_errors.append({**data, "_timestamp": entry.get("timestamp"), "_severity": entry.get("severity")})

uuid_hygiene_entries = load("uuid_hygiene")
reception_hygiene_entries = load("reception_hygiene")

failures: list[str] = []
if trace_count == 0:
    failures.append("No structured STT trace events found.")
if missing_trace_count:
    failures.append(f"{missing_trace_count} structured STT event(s) are missing stt_trace_id.")
for name in required_stt_events:
    if rates[name] < threshold:
        failures.append(f"{name} generation rate {rates[name]:.2f}% is below threshold {threshold:.2f}%.")
if not chat_entries:
    failures.append("No structured chat_response logs found.")
if chat_missing:
    failures.append(f"{len(chat_missing)} chat_response log(s) are missing required fields.")
if uuid_hygiene_entries:
    failures.append(
        f"{len(uuid_hygiene_entries)} invalid UUID syntax log(s) found; synthetic alpha IDs are still leaking into UUID queries."
    )
if reception_hygiene_entries:
    failures.append(
        f"{len(reception_hygiene_entries)} reception persistence failure log(s) found."
    )

passed = not failures
lines = [
    "# Cloud Logging Structured Event Check",
    "",
    f"- Timestamp: {timestamp}",
    f"- Project: {project}",
    f"- Service: {service}",
    f"- Region: {region}",
    f"- Lookback minutes: {minutes}",
    f"- STT generation threshold: {threshold:.2f}%",
    f"- Overall passed: {'yes' if passed else 'no'}",
    "",
    "## Summary",
    "",
    "| Check | Result | Detail |",
    "| --- | --- | --- |",
]
for name in required_stt_events:
    result = "PASS" if trace_count and rates[name] >= threshold else "FAIL"
    lines.append(
        f"| `{name}` generation | {result} | {rates[name]:.2f}% across {trace_count} STT trace(s); "
        f"raw structured events: {event_counts[name]}; missing traces: {missing_by_event[name]} |"
    )
chat_passed = bool(chat_entries) and not chat_missing
lines.append(
    f"| `chat_response` required fields | {'PASS' if chat_passed else 'FAIL'} | "
    f"{len(chat_entries)} structured log(s); required: {', '.join(required_chat_fields)} |"
)
lines.append(
    f"| `memory_helper` ERROR samples | {'WARN' if memory_errors else 'PASS'} | "
    f"{len(memory_errors)} error log(s) found; samples listed below if present |"
)
lines.append(
    f"| `invalid input syntax for type uuid` hygiene | {'FAIL' if uuid_hygiene_entries else 'PASS'} | "
    f"{len(uuid_hygiene_entries)} matching log row(s) |"
)
lines.append(
    f"| `Reception session persistence failed` hygiene | {'FAIL' if reception_hygiene_entries else 'PASS'} | "
    f"{len(reception_hygiene_entries)} matching log row(s) |"
)

if failures:
    lines.extend(["", "## Failures", ""])
    for failure in failures:
        lines.append(f"- {failure}")

lines.extend([
    "",
    "## STT Events",
    "",
    "| Event | Structured count | Trace generation rate | Missing trace count |",
    "| --- | ---: | ---: | ---: |",
])
for name in required_stt_events:
    lines.append(f"| `{name}` | {event_counts[name]} | {rates[name]:.2f}% | {missing_by_event[name]} |")

lines.extend([
    "",
    "## chat_response Schema",
    "",
    f"- Rows checked: {len(chat_entries)}",
    f"- Required fields: {', '.join(required_chat_fields)}",
])
if chat_missing:
    lines.extend(["", "| Row | Missing fields | Timestamp | Request ID | Route | Language |", "| ---: | --- | --- | --- | --- | --- |"])
    for item in chat_missing[:20]:
        data = item["data"]
        lines.append(
            f"| {item['index']} | {md(', '.join(item['missing']))} | {md(data.get('_timestamp'))} | "
            f"{md(field_value(data, 'request_id'))} | {md(field_value(data, 'route'))} | {md(field_value(data, 'language'))} |"
        )

lines.extend([
    "",
    "## memory_helper Error Samples",
    "",
    f"- Error rows found: {len(memory_errors)}",
])
if memory_errors:
    lines.extend(["", "| Timestamp | Severity | Message |", "| --- | --- | --- |"])
    for item in memory_errors[:5]:
        message = item.get("message") or item.get("msg") or item.get("error") or item.get("event") or ""
        lines.append(f"| {md(item.get('_timestamp'))} | {md(item.get('_severity') or item.get('level'))} | {md(message)[:500]} |")
else:
    lines.append("- No memory_helper error samples in the lookback window.")

lines.extend([
    "",
    "## Alpha Log Hygiene",
    "",
    f"- `invalid input syntax for type uuid` rows: {len(uuid_hygiene_entries)}",
    f"- `Reception session persistence failed` rows: {len(reception_hygiene_entries)}",
])
if uuid_hygiene_entries or reception_hygiene_entries:
    lines.extend(["", "| Check | Timestamp | Severity | Message |", "| --- | --- | --- | --- |"])
    for name, entries in (
        ("uuid", uuid_hygiene_entries[:5]),
        ("reception", reception_hygiene_entries[:5]),
    ):
        for entry in entries:
            data = payload(entry)
            message = (
                data.get("message")
                or data.get("error")
                or entry.get("textPayload")
                or data.get("event")
                or ""
            )
            lines.append(
                f"| {name} | {md(entry.get('timestamp'))} | {md(entry.get('severity'))} | {md(message)[:500]} |"
            )
else:
    lines.append("- No alpha log hygiene matches in the lookback window.")

pathlib.Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(report)
sys.exit(0 if passed else 1)
PY
