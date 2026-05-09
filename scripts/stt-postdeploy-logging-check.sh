#!/usr/bin/env bash
set -euo pipefail

# Summarize post-deploy STT structured logs from Cloud Logging.
#
# Usage:
#   scripts/stt-postdeploy-logging-check.sh --since 2026-05-08T10:00:00+09:00
#   scripts/stt-postdeploy-logging-check.sh --since 2026-05-08T01:00:00Z --revision engineer-cafe-backend-00099-abc --dry-run

PROJECT_ID="${STT_LOG_CHECK_PROJECT:-aipartner-426616}"
SERVICE_NAME="${STT_LOG_CHECK_SERVICE:-engineer-cafe-backend}"
REGION="${STT_LOG_CHECK_REGION:-asia-northeast1}"
LIMIT=1000
SINCE=""
UNTIL=""
REVISION=""
DRY_RUN=0

usage() {
  sed -n '4,9p' "$0"
  cat <<'EOF'

Options:
  --since RFC3339      Required start timestamp. Accepts UTC (Z), offsets, or JST suffix.
  --until RFC3339      Optional end timestamp. Accepts UTC (Z), offsets, or JST suffix.
  --project ID         GCP project (default: aipartner-426616)
  --service NAME       Cloud Run service (default: engineer-cafe-backend)
  --region REGION      Cloud Run region (default: asia-northeast1)
  --revision NAME      Optional Cloud Run revision filter
  --limit N            Max log rows to read (default: 1000)
  --dry-run            Print the Cloud Logging filter without reading logs
  -h, --help           Show this usage

Reports:
  - stt_winner counts
  - stt_overall_duration_ms p50/p90/max
  - qwen/vosk runtime breakdown where available
  - stt_qwen_rejected count
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

normalize_timestamp() {
  python3 - "$1" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import re
import sys

raw = sys.argv[1].strip()
if not raw or '"' in raw or "\n" in raw or "\r" in raw:
    raise SystemExit(2)

value = re.sub(r"\s+JST$", "+09:00", raw, flags=re.IGNORECASE)
value = value.replace(" ", "T")
if value.endswith("Z"):
    value = value[:-1] + "+00:00"

try:
    parsed = datetime.fromisoformat(value)
except ValueError as exc:
    raise SystemExit(f"invalid timestamp {raw!r}: {exc}")

if parsed.tzinfo is None:
    raise SystemExit(f"timestamp must include timezone, Z, offset, or JST suffix: {raw!r}")

print(parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
PY
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --since) [ "$#" -ge 2 ] || die "--since requires a value"; SINCE="$2"; shift 2 ;;
    --until) [ "$#" -ge 2 ] || die "--until requires a value"; UNTIL="$2"; shift 2 ;;
    --project) [ "$#" -ge 2 ] || die "--project requires a value"; PROJECT_ID="$2"; shift 2 ;;
    --service) [ "$#" -ge 2 ] || die "--service requires a value"; SERVICE_NAME="$2"; shift 2 ;;
    --region) [ "$#" -ge 2 ] || die "--region requires a value"; REGION="$2"; shift 2 ;;
    --revision) [ "$#" -ge 2 ] || die "--revision requires a value"; REVISION="$2"; shift 2 ;;
    --limit) [ "$#" -ge 2 ] || die "--limit requires a value"; LIMIT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

[[ -n "$PROJECT_ID" ]] || die "project must not be empty"
[[ -n "$SERVICE_NAME" ]] || die "service must not be empty"
[[ -n "$REGION" ]] || die "region must not be empty"
[[ -n "$SINCE" ]] || die "--since is required"
is_positive_int "$LIMIT" || die "--limit must be a positive integer"
require_cmd python3

SINCE_UTC="$(normalize_timestamp "$SINCE")"
UNTIL_UTC=""
if [ -n "$UNTIL" ]; then
  UNTIL_UTC="$(normalize_timestamp "$UNTIL")"
fi

FILTER='resource.type="cloud_run_revision"'
FILTER="$FILTER AND resource.labels.service_name=\"$SERVICE_NAME\""
FILTER="$FILTER AND resource.labels.location=\"$REGION\""
if [ -n "$REVISION" ]; then
  [[ "$REVISION" != *'"'* && "$REVISION" != *$'\n'* && "$REVISION" != *$'\r'* ]] || die "--revision must not contain quotes or newlines"
  FILTER="$FILTER AND resource.labels.revision_name=\"$REVISION\""
fi
FILTER="$FILTER AND timestamp >= \"$SINCE_UTC\""
if [ -n "$UNTIL_UTC" ]; then
  FILTER="$FILTER AND timestamp <= \"$UNTIL_UTC\""
fi
FILTER="$FILTER AND (jsonPayload.event=\"stt_winner\""
FILTER="$FILTER OR jsonPayload.event=\"stt_request_complete\""
FILTER="$FILTER OR jsonPayload.event=\"stt_audio_prepare_complete\""
FILTER="$FILTER OR jsonPayload.event=\"stt_qwen_runtime_complete\""
FILTER="$FILTER OR jsonPayload.event=\"stt_qwen_postprocess_complete\""
FILTER="$FILTER OR jsonPayload.event=\"stt_vosk_runtime_complete\""
FILTER="$FILTER OR jsonPayload.event=\"stt_qwen_hedge_start\""
FILTER="$FILTER OR jsonPayload.event=\"stt_qwen_hedge_grace_complete\""
FILTER="$FILTER OR jsonPayload.event=\"stt_qwen_rejected\")"

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: no gcloud logging read calls will be executed."
  echo "Project: $PROJECT_ID"
  echo "Service: $SERVICE_NAME"
  echo "Region: $REGION"
  echo "Revision: ${REVISION:-all revisions}"
  echo "Since UTC: $SINCE_UTC"
  echo "Until UTC: ${UNTIL_UTC:-none}"
  echo "Limit: $LIMIT"
  echo "Filter: $FILTER"
  exit 0
fi

require_cmd gcloud
LOG_JSON="$(mktemp)"
trap 'rm -f "$LOG_JSON"' EXIT

gcloud logging read "$FILTER" \
  --project "$PROJECT_ID" \
  --limit "$LIMIT" \
  --format=json > "$LOG_JSON"

python3 - "$LOG_JSON" "$PROJECT_ID" "$SERVICE_NAME" "$REGION" "$REVISION" "$SINCE_UTC" "${UNTIL_UTC:-}" "$LIMIT" <<'PY'
from __future__ import annotations

from collections import Counter
import json
import math
import sys
from typing import Any

log_json, project, service, region, revision, since_utc, until_utc, limit_raw = sys.argv[1:9]
limit = int(limit_raw)

with open(log_json, encoding="utf-8") as fh:
    entries = json.load(fh)
if not isinstance(entries, list):
    entries = []


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * ratio
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}"


winner_counts: Counter[str] = Counter()
latencies: list[float] = []
request_latencies: list[float] = []
audio_prepare_latencies: list[float] = []
audio_conversion_latencies: list[float] = []
qwen_runtime_latencies: list[float] = []
qwen_model_inference_latencies: list[float] = []
qwen_postprocess_latencies: list[float] = []
vosk_runtime_latencies: list[float] = []
vosk_recognition_latencies: list[float] = []
hedge_wait_latencies: list[float] = []
qwen_grace_wait_latencies: list[float] = []
qwen_rejected_count = 0
event_counts: Counter[str] = Counter()

def append_float(values: list[float], value: Any) -> None:
    try:
        values.append(float(value))
    except (TypeError, ValueError):
        pass

for entry in entries:
    payload = entry.get("jsonPayload")
    if not isinstance(payload, dict):
        continue
    event = payload.get("event")
    if not isinstance(event, str):
        continue
    event_counts[event] += 1
    if event == "stt_qwen_rejected":
        qwen_rejected_count += 1
        continue
    if event == "stt_request_complete":
        append_float(request_latencies, payload.get("stt_request_duration_ms"))
        continue
    if event == "stt_audio_prepare_complete":
        append_float(audio_prepare_latencies, payload.get("stt_audio_prepare_duration_ms"))
        append_float(audio_conversion_latencies, payload.get("stt_audio_conversion_duration_ms"))
        continue
    if event == "stt_qwen_runtime_complete":
        append_float(qwen_runtime_latencies, payload.get("stt_qwen_runtime_duration_ms"))
        append_float(
            qwen_model_inference_latencies,
            payload.get("stt_qwen_model_inference_duration_ms"),
        )
        continue
    if event == "stt_qwen_postprocess_complete":
        append_float(qwen_postprocess_latencies, payload.get("stt_qwen_postprocess_duration_ms"))
        continue
    if event == "stt_vosk_runtime_complete":
        append_float(vosk_runtime_latencies, payload.get("stt_vosk_runtime_duration_ms"))
        append_float(vosk_recognition_latencies, payload.get("stt_vosk_recognition_duration_ms"))
        continue
    if event == "stt_qwen_hedge_start":
        append_float(hedge_wait_latencies, payload.get("stt_hedge_wait_duration_ms"))
        continue
    if event == "stt_qwen_hedge_grace_complete":
        continue
    if event != "stt_winner":
        continue

    winner = payload.get("stt_winner") or payload.get("provider") or "unknown"
    winner_counts[str(winner)] += 1
    append_float(latencies, payload.get("stt_overall_duration_ms"))
    append_float(qwen_grace_wait_latencies, payload.get("stt_qwen_grace_wait_duration_ms"))

print("# STT Post-Deploy Logging Check")
print()
print(f"- Project: `{project}`")
print(f"- Service: `{service}` / `{region}`")
print(f"- Revision: `{revision or 'all revisions'}`")
print(f"- Window UTC: `{since_utc}` to `{until_utc or 'now'}`")
print(f"- Rows read: `{len(entries)}`")
if len(entries) >= limit:
    print(f"- Limit warning: read hit the configured limit `{limit}`; rerun with a larger --limit if needed.")
print()
print("## Events")
print()
print("| Event | Count |")
print("| --- | ---: |")
for event in (
    "stt_winner",
    "stt_request_complete",
    "stt_audio_prepare_complete",
    "stt_qwen_runtime_complete",
    "stt_qwen_postprocess_complete",
    "stt_vosk_runtime_complete",
    "stt_qwen_hedge_start",
    "stt_qwen_hedge_grace_complete",
    "stt_qwen_rejected",
):
    print(f"| {event} | {event_counts.get(event, 0)} |")
print()
print("## Winners")
print()
print("| stt_winner | Count |")
print("| --- | ---: |")
if winner_counts:
    for winner, count in sorted(winner_counts.items()):
        print(f"| {winner} | {count} |")
else:
    print("| n/a | 0 |")
print()
print("## Latency")
print()
print("| Metric | Value ms |")
print("| --- | ---: |")
latency_rows = {
    "stt_overall p50": percentile(latencies, 0.50),
    "stt_overall p90": percentile(latencies, 0.90),
    "stt_overall max": max(latencies) if latencies else None,
    "backend_stt_request p50": percentile(request_latencies, 0.50),
    "audio_prepare p50": percentile(audio_prepare_latencies, 0.50),
    "audio_conversion p50": percentile(audio_conversion_latencies, 0.50),
    "qwen_runtime p50": percentile(qwen_runtime_latencies, 0.50),
    "qwen_model_inference p50": percentile(qwen_model_inference_latencies, 0.50),
    "qwen_postprocess p50": percentile(qwen_postprocess_latencies, 0.50),
    "vosk_runtime p50": percentile(vosk_runtime_latencies, 0.50),
    "vosk_recognition p50": percentile(vosk_recognition_latencies, 0.50),
    "hedge_wait p50": percentile(hedge_wait_latencies, 0.50),
    "qwen_grace_wait p50": percentile(qwen_grace_wait_latencies, 0.50),
}
for metric, value in latency_rows.items():
    print(f"| {metric} | {fmt_ms(value)} |")
print()
print(f"stt_qwen_rejected count: `{qwen_rejected_count}`")
PY
