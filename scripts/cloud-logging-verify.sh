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
SINCE=""
UNTIL=""
ERROR_GATE_ONLY=0
INPUT_DIR=""

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
  --since RFC3339        Override lookback start timestamp
  --until RFC3339        Optional inclusive end timestamp
  --error-gate-only      Only fail on critical API, LTM, or persistence error rows
  --input-dir DIR        Read pre-fetched JSON logs from DIR instead of gcloud (tests)
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

is_filter_safe_timestamp() {
  [[ -n "${1:-}" && "$1" != *'"'* && "$1" != *$'\n'* && "$1" != *$'\r'* ]]
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
    --since) [ "$#" -ge 2 ] || die "--since requires a value"; SINCE="$2"; shift 2 ;;
    --until) [ "$#" -ge 2 ] || die "--until requires a value"; UNTIL="$2"; shift 2 ;;
    --error-gate-only) ERROR_GATE_ONLY=1; shift ;;
    --input-dir) [ "$#" -ge 2 ] || die "--input-dir requires a value"; INPUT_DIR="$2"; shift 2 ;;
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
[ -z "$SINCE" ] || is_filter_safe_timestamp "$SINCE" || die "--since must be a non-empty timestamp without quotes or newlines"
[ -z "$UNTIL" ] || is_filter_safe_timestamp "$UNTIL" || die "--until must be a non-empty timestamp without quotes or newlines"
[ -z "$INPUT_DIR" ] || [ -d "$INPUT_DIR" ] || die "--input-dir must be an existing directory"
require_cmd python3

REPORT="$OUTPUT_DIR/cloud-logging-check-$TIMESTAMP.md"
WINDOW_START="$SINCE"
if [ -z "$WINDOW_START" ]; then
  WINDOW_START="$(python3 - "$MINUTES" <<'PY'
from datetime import datetime, timedelta, timezone
import sys
minutes = int(sys.argv[1])
print((datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"))
PY
)"
fi
BASE_FILTER='resource.type="cloud_run_revision"'
BASE_FILTER="$BASE_FILTER AND resource.labels.service_name=\"$SERVICE_NAME\""
BASE_FILTER="$BASE_FILTER AND resource.labels.location=\"$REGION\""
BASE_FILTER="$BASE_FILTER AND timestamp >= \"$WINDOW_START\""
if [ -n "$UNTIL" ]; then
  BASE_FILTER="$BASE_FILTER AND timestamp <= \"$UNTIL\""
fi

event_filter() {
  printf '%s AND (jsonPayload.event="%s" OR labels.event="%s" OR textPayload:"%s")' \
    "$BASE_FILTER" "$1" "$1" "$1"
}

chat_filter="$BASE_FILTER AND (jsonPayload.event=\"chat_response\" OR labels.event=\"chat_response\" OR textPayload:\"chat_response\")"
chat_5xx_filter="$BASE_FILTER AND ((httpRequest.requestMethod=\"POST\" AND httpRequest.requestUrl:\"/api/chat\" AND httpRequest.status>=500) OR (jsonPayload.path=\"/api/chat\" AND jsonPayload.status_code>=500) OR (jsonPayload.extra.path=\"/api/chat\" AND jsonPayload.extra.status_code>=500) OR (jsonPayload.event=\"request_failed\" AND jsonPayload.path=\"/api/chat\") OR (jsonPayload.event=\"request_completed_slow\" AND jsonPayload.path=\"/api/chat\" AND jsonPayload.status_code>=500) OR (textPayload:\"/api/chat\" AND severity>=ERROR))"
api_error_filter="$BASE_FILTER AND (((httpRequest.requestUrl:\"/api/voice\" OR httpRequest.requestUrl:\"/api/chat\" OR httpRequest.requestUrl:\"/api/slides\" OR httpRequest.requestUrl:\"/api/error\") AND httpRequest.status>=500) OR ((jsonPayload.path=\"/api/voice\" OR jsonPayload.path=\"/api/chat\" OR jsonPayload.path=\"/api/slides\" OR jsonPayload.path=\"/api/error\" OR jsonPayload.extra.path=\"/api/voice\" OR jsonPayload.extra.path=\"/api/chat\" OR jsonPayload.extra.path=\"/api/slides\" OR jsonPayload.extra.path=\"/api/error\") AND (jsonPayload.status_code>=500 OR jsonPayload.extra.status_code>=500 OR severity>=ERROR)) OR ((textPayload:\"/api/voice\" OR textPayload:\"/api/chat\" OR textPayload:\"/api/slides\" OR textPayload:\"/api/error\") AND severity>=ERROR))"
memory_filter="$BASE_FILTER AND ((jsonPayload.logger=\"backend.utils.memory_helper\" AND jsonPayload.level=\"ERROR\") OR jsonPayload.event=\"memory_helper_error\" OR (jsonPayload.logger:\"memory_helper\" AND severity>=ERROR) OR (textPayload:\"memory_helper\" AND severity>=ERROR))"
ltm_connection_filter="$BASE_FILTER AND (jsonPayload.event=\"ltm_connection_error\" OR jsonPayload.event=\"memory_helper_connection_error\" OR ((jsonPayload.logger=\"backend.utils.memory_helper\" OR jsonPayload.logger:\"memory_helper\" OR jsonPayload.message:\"LTM\" OR jsonPayload.message:\"long-term memory\" OR textPayload:\"memory_helper\" OR textPayload:\"LTM\" OR textPayload:\"long-term memory\") AND (jsonPayload.message:\"connection\" OR jsonPayload.message:\"ConnectionError\" OR jsonPayload.message:\"connection refused\" OR jsonPayload.message:\"timeout\" OR jsonPayload.exception.message:\"connection\" OR jsonPayload.exception.message:\"ConnectionError\" OR jsonPayload.exception.message:\"connection refused\" OR jsonPayload.exception.message:\"timeout\" OR textPayload:\"connection\" OR textPayload:\"ConnectionError\" OR textPayload:\"connection refused\" OR textPayload:\"timeout\") AND severity>=ERROR))"
uuid_hygiene_filter="$BASE_FILTER AND (textPayload:\"invalid input syntax for type uuid\" OR jsonPayload.message:\"invalid input syntax for type uuid\" OR jsonPayload.exception.message:\"invalid input syntax for type uuid\")"
reception_hygiene_filter="$BASE_FILTER AND (textPayload:\"Reception session persistence failed\" OR jsonPayload.message:\"Reception session persistence failed\")"

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: no gcloud logging read calls will be executed."
  echo "Project: $PROJECT_ID"
  echo "Output: $REPORT"
  echo "Window start: $WINDOW_START"
  echo "Window end: ${UNTIL:-none}"
  echo "Error gate only: $ERROR_GATE_ONLY"
  if [ "$ERROR_GATE_ONLY" != "1" ]; then
    for event in stt_qwen_start stt_qwen_complete stt_winner; do
      echo "Filter[$event]: $(event_filter "$event")"
    done
  fi
  echo "Filter[chat_response]: $chat_filter"
  echo "Filter[chat_api_5xx]: $chat_5xx_filter"
  echo "Filter[critical_api_errors]: $api_error_filter"
  echo "Filter[memory_helper_error]: $memory_filter"
  echo "Filter[ltm_connection_error]: $ltm_connection_filter"
  echo "Filter[uuid_hygiene]: $uuid_hygiene_filter"
  echo "Filter[reception_hygiene]: $reception_hygiene_filter"
  exit 0
fi

mkdir -p "$OUTPUT_DIR"
if [ -n "$INPUT_DIR" ]; then
  TMP_DIR="$INPUT_DIR"
else
  require_cmd gcloud
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
fi

read_logs() {
  local filter="$1"
  local out="$2"
  gcloud logging read "$filter" \
    --project "$PROJECT_ID" \
    --limit "$LIMIT" \
    --format=json > "$out"
}

if [ -z "$INPUT_DIR" ]; then
  if [ "$ERROR_GATE_ONLY" != "1" ]; then
    for event in stt_qwen_start stt_qwen_complete stt_winner; do
      read_logs "$(event_filter "$event")" "$TMP_DIR/$event.json"
    done
  fi
  read_logs "$chat_filter" "$TMP_DIR/chat_response.json"
  read_logs "$chat_5xx_filter" "$TMP_DIR/chat_api_5xx.json"
  read_logs "$api_error_filter" "$TMP_DIR/critical_api_errors.json"
  read_logs "$memory_filter" "$TMP_DIR/memory_helper_errors.json"
  read_logs "$ltm_connection_filter" "$TMP_DIR/ltm_connection_errors.json"
  read_logs "$uuid_hygiene_filter" "$TMP_DIR/uuid_hygiene.json"
  read_logs "$reception_hygiene_filter" "$TMP_DIR/reception_hygiene.json"
fi

python3 - "$TIMESTAMP" "$PROJECT_ID" "$SERVICE_NAME" "$REGION" "$MINUTES" "$THRESHOLD" "$REPORT" "$TMP_DIR" "$WINDOW_START" "${UNTIL:-}" "$ERROR_GATE_ONLY" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict
from typing import Any

(
    timestamp,
    project,
    service,
    region,
    minutes,
    threshold_raw,
    report,
    tmp,
    window_start,
    window_end,
    error_gate_only_raw,
) = sys.argv[1:12]
error_gate_only = error_gate_only_raw == "1"
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


def entry_message(entry: dict[str, Any]) -> str:
    data = payload(entry)
    value = (
        data.get("message")
        or data.get("msg")
        or data.get("error")
        or entry.get("textPayload")
        or data.get("event")
        or ""
    )
    return str(value)


def entry_http_status(entry: dict[str, Any]) -> Any:
    http_request = entry.get("httpRequest")
    if isinstance(http_request, dict) and http_request.get("status") is not None:
        return http_request.get("status")
    data = payload(entry)
    if data.get("status_code") is not None:
        return data.get("status_code")
    extra = data.get("extra")
    if isinstance(extra, dict):
        return extra.get("status_code")
    return None


def entry_path(entry: dict[str, Any]) -> str:
    http_request = entry.get("httpRequest")
    if isinstance(http_request, dict) and http_request.get("requestUrl") is not None:
        return str(http_request.get("requestUrl"))
    data = payload(entry)
    if data.get("path") is not None:
        return str(data.get("path"))
    extra = data.get("extra")
    if isinstance(extra, dict) and extra.get("path") is not None:
        return str(extra.get("path"))
    return ""


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

chat_api_5xx_entries = load("chat_api_5xx")
critical_api_error_entries = load("critical_api_errors")
ltm_store_failed = [
    data for data in chat_entries if str(field_value(data, "ltm_store_write")).lower() == "failed"
]

memory_errors = []
for entry in load("memory_helper_errors"):
    data = payload(entry)
    if (
        data.get("logger") == "backend.utils.memory_helper"
        or data.get("event") == "memory_helper_error"
        or "memory_helper" in str(entry.get("textPayload", ""))
    ):
        memory_errors.append({**data, "_timestamp": entry.get("timestamp"), "_severity": entry.get("severity")})

ltm_connection_errors = []
for entry in load("ltm_connection_errors"):
    data = payload(entry)
    ltm_connection_errors.append({**data, "_timestamp": entry.get("timestamp"), "_severity": entry.get("severity")})

uuid_hygiene_entries = load("uuid_hygiene")
reception_hygiene_entries = load("reception_hygiene")

failures: list[str] = []
if not error_gate_only:
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
if chat_api_5xx_entries:
    failures.append(f"{len(chat_api_5xx_entries)} /api/chat 5xx log row(s) found.")
if critical_api_error_entries:
    failures.append(f"{len(critical_api_error_entries)} critical API ERROR/5xx log row(s) found.")
if ltm_store_failed:
    failures.append(f"{len(ltm_store_failed)} chat_response log(s) reported ltm_store_write=failed.")
if memory_errors:
    failures.append(f"{len(memory_errors)} memory_helper error log(s) found.")
if ltm_connection_errors:
    failures.append(f"{len(ltm_connection_errors)} LTM connection/timeout error log row(s) found.")
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
    "# Cloud Logging Error Gate" if error_gate_only else "# Cloud Logging Structured Event Check",
    "",
    f"- Timestamp: {timestamp}",
    f"- Project: {project}",
    f"- Service: {service}",
    f"- Region: {region}",
    f"- Window start: {window_start}",
    f"- Window end: {window_end or 'now'}",
    f"- Lookback minutes: {minutes}",
    f"- Error gate only: {'yes' if error_gate_only else 'no'}",
    f"- STT generation threshold: {threshold:.2f}%",
    f"- Overall passed: {'yes' if passed else 'no'}",
    "",
    "## Summary",
    "",
    "| Check | Result | Detail |",
    "| --- | --- | --- |",
]
if not error_gate_only:
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
    f"| `/api/chat` 5xx rows | {'FAIL' if chat_api_5xx_entries else 'PASS'} | "
    f"{len(chat_api_5xx_entries)} matching log row(s) |"
)
lines.append(
    f"| critical API ERROR/5xx rows | {'FAIL' if critical_api_error_entries else 'PASS'} | "
    f"{len(critical_api_error_entries)} matching /api/voice, /api/chat, /api/slides, or /api/error log row(s) |"
)
lines.append(
    f"| `ltm_store_write=failed` rows | {'FAIL' if ltm_store_failed else 'PASS'} | "
    f"{len(ltm_store_failed)} matching chat_response log row(s) |"
)
lines.append(
    f"| `memory_helper` ERROR samples | {'FAIL' if memory_errors else 'PASS'} | "
    f"{len(memory_errors)} error log(s) found; samples listed below if present |"
)
lines.append(
    f"| LTM connection/timeout errors | {'FAIL' if ltm_connection_errors else 'PASS'} | "
    f"{len(ltm_connection_errors)} matching log row(s) |"
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

if not error_gate_only:
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
    "## Cloud Run Error Rows",
    "",
    f"- `/api/chat` 5xx rows: {len(chat_api_5xx_entries)}",
    f"- Critical API ERROR/5xx rows: {len(critical_api_error_entries)}",
    f"- `ltm_store_write=failed` rows: {len(ltm_store_failed)}",
])
if chat_api_5xx_entries:
    lines.extend(["", "| Timestamp | Severity | Status | Path | Message |", "| --- | --- | ---: | --- | --- |"])
    for entry in chat_api_5xx_entries[:10]:
        lines.append(
            f"| {md(entry.get('timestamp'))} | {md(entry.get('severity'))} | "
            f"{md(entry_http_status(entry))} | {md(entry_path(entry))[:160]} | {md(entry_message(entry))[:500]} |"
        )
if critical_api_error_entries:
    lines.extend(["", "| Timestamp | Severity | Status | Path | Message |", "| --- | --- | ---: | --- | --- |"])
    for entry in critical_api_error_entries[:10]:
        lines.append(
            f"| {md(entry.get('timestamp'))} | {md(entry.get('severity'))} | "
            f"{md(entry_http_status(entry))} | {md(entry_path(entry))[:160]} | {md(entry_message(entry))[:500]} |"
        )
if ltm_store_failed:
    lines.extend(["", "| Timestamp | Request ID | Route | Language |", "| --- | --- | --- | --- |"])
    for item in ltm_store_failed[:10]:
        lines.append(
            f"| {md(item.get('_timestamp'))} | {md(field_value(item, 'request_id'))} | "
            f"{md(field_value(item, 'route'))} | {md(field_value(item, 'language'))} |"
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
    "## LTM Connection Error Samples",
    "",
    f"- Error rows found: {len(ltm_connection_errors)}",
])
if ltm_connection_errors:
    lines.extend(["", "| Timestamp | Severity | Event | Logger | Message |", "| --- | --- | --- | --- | --- |"])
    for item in ltm_connection_errors[:5]:
        message = item.get("message") or item.get("msg") or item.get("error") or item.get("event") or ""
        lines.append(
            f"| {md(item.get('_timestamp'))} | {md(item.get('_severity') or item.get('level'))} | "
            f"{md(item.get('event'))} | {md(item.get('logger'))} | {md(message)[:500]} |"
        )
else:
    lines.append("- No LTM connection error samples in the lookback window.")

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
