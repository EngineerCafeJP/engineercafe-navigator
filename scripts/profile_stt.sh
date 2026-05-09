#!/usr/bin/env bash
set -euo pipefail

# Profile live Cloud Run STT via /api/voice and collect structured stt_* logs.
#
# Usage:
#   scripts/profile_stt.sh --key "$API_SECRET_KEY"
#   scripts/profile_stt.sh --host https://... --audio-file sample.wav --iterations 20 --sleep 4
#
# Env:
#   API_SECRET_KEY              Required unless --key provided or gcloud secrets access works
#   STT_PROFILE_BASE_URL        Overrides the default Cloud Run URL
#   STT_PROFILE_PROJECT         Defaults to aipartner-426616
#   STT_PROFILE_SERVICE         Defaults to engineer-cafe-backend
#   STT_PROFILE_REGION          Defaults to asia-northeast1

DEFAULT_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
BASE_URL="${STT_PROFILE_BASE_URL:-$DEFAULT_URL}"
PROJECT="${STT_PROFILE_PROJECT:-aipartner-426616}"
SERVICE="${STT_PROFILE_SERVICE:-engineer-cafe-backend}"
REGION="${STT_PROFILE_REGION:-asia-northeast1}"
ITERATIONS=20
SLEEP_SECONDS=4
LANGUAGE="ja"
PROFILE_TEXT="テストです"
API_KEY="${API_SECRET_KEY:-}"
AUDIO_FILE=""
OUT_DIR="backend/tests/reports"

usage() {
  sed -n '3,16p' "$0"
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) BASE_URL="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --iterations) ITERATIONS="$2"; shift 2 ;;
    --sleep) SLEEP_SECONDS="$2"; shift 2 ;;
    --language) LANGUAGE="$2"; shift 2 ;;
    --text) PROFILE_TEXT="$2"; shift 2 ;;
    --key) API_KEY="$2"; shift 2 ;;
    --audio-file) AUDIO_FILE="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

fetch_api_key_from_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    gcloud secrets versions access latest \
      --secret=API_SECRET_KEY --project="$PROJECT" 2>/dev/null || true
  fi
}

json_get() {
  python3 -c '
import json, sys
data = json.load(sys.stdin)
node = data
for part in sys.argv[1].split("."):
    if isinstance(node, dict):
        node = node.get(part, "")
    else:
        node = ""
        break
print(node if node is not None else "")
' "$1"
}

if [[ -z "$API_KEY" ]]; then
  API_KEY="$(fetch_api_key_from_gcloud)"
fi

if [[ -z "$API_KEY" ]]; then
  echo "Error: API_SECRET_KEY is required (pass --key, set env, or gcloud login)" >&2
  exit 2
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "Error: gcloud is required to collect Cloud Logging events" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REQUEST_CSV="$OUT_DIR/stt-profile-$STAMP-requests.csv"
EVENT_CSV="$OUT_DIR/stt-profile-$STAMP-events.csv"
LOG_JSON="$OUT_DIR/stt-profile-$STAMP-logs.json"
REPORT_MD="$OUT_DIR/stt-profile-$STAMP.md"

if [[ -n "$AUDIO_FILE" ]]; then
  AUDIO_B64="$(base64 < "$AUDIO_FILE" | tr -d '\n')"
else
  echo "Generating reusable TTS sample audio via /api/voice..."
  TTS_BODY="$(PROFILE_TEXT="$PROFILE_TEXT" LANGUAGE="$LANGUAGE" python3 -c '
import json, os
print(json.dumps({
    "action": "text_to_speech",
    "text": os.environ["PROFILE_TEXT"],
    "language": os.environ["LANGUAGE"],
    "sessionId": "stt-profile-tts",
}, ensure_ascii=False))
')"
  TTS_RESPONSE="$(curl -sS -m 60 \
    -X POST "$BASE_URL/api/voice" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "$TTS_BODY")"
  AUDIO_B64="$(printf '%s' "$TTS_RESPONSE" | json_get audioResponse)"
  if [[ -z "$AUDIO_B64" ]]; then
    echo "Error: failed to generate TTS audio sample: $TTS_RESPONSE" >&2
    exit 1
  fi
fi

LOG_START="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "request_index,http_status,total_ms,transcript_chars,success" > "$REQUEST_CSV"

for i in $(seq 1 "$ITERATIONS"); do
  SESSION_ID="stt-profile-$STAMP-$i"
  BODY="$(AUDIO_B64="$AUDIO_B64" SESSION_ID="$SESSION_ID" LANGUAGE="$LANGUAGE" python3 -c '
import json, os
print(json.dumps({
    "action": "speech_to_text",
    "audioData": os.environ["AUDIO_B64"],
    "language": os.environ["LANGUAGE"],
    "sessionId": os.environ["SESSION_ID"],
}, ensure_ascii=False))
')"
  TMP_BODY="$(mktemp)"
  TOTAL_SECONDS="$(curl -sS -m 90 -o "$TMP_BODY" -w "%{time_total}" \
    -X POST "$BASE_URL/api/voice" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "$BODY" || true)"
  HTTP_STATUS="$(python3 - "$TMP_BODY" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print("parse_error")
else:
    print("200" if data.get("success") is True else "error")
PY
)"
  TRANSCRIPT_CHARS="$(python3 - "$TMP_BODY" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(len(data.get("transcript") or ""))
except Exception:
    print(0)
PY
)"
  SUCCESS="$(python3 - "$TMP_BODY" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(str(data.get("success") is True).lower())
except Exception:
    print("false")
PY
)"
  TOTAL_MS="$(TOTAL_SECONDS="$TOTAL_SECONDS" python3 -c 'import os; print(int(float(os.environ["TOTAL_SECONDS"]) * 1000))')"
  echo "$i,$HTTP_STATUS,$TOTAL_MS,$TRANSCRIPT_CHARS,$SUCCESS" >> "$REQUEST_CSV"
  rm -f "$TMP_BODY"
  echo "[$i/$ITERATIONS] total=${TOTAL_MS}ms success=$SUCCESS"
  if [[ "$i" != "$ITERATIONS" ]]; then
    sleep "$SLEEP_SECONDS"
  fi
done

LOG_END="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\" AND resource.labels.location=\"$REGION\" AND jsonPayload.event=~\"stt_.*\" AND timestamp>=\"$LOG_START\" AND timestamp<=\"$LOG_END\""

gcloud logging read "$FILTER" \
  --project="$PROJECT" \
  --format=json \
  --limit=1000 \
  > "$LOG_JSON"

python3 - "$REQUEST_CSV" "$LOG_JSON" "$EVENT_CSV" "$REPORT_MD" "$BASE_URL" "$SERVICE" "$REGION" "$LOG_START" "$LOG_END" <<'PY'
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

request_csv, log_json, event_csv, report_md, base_url, service, region, start, end = sys.argv[1:]

requests = []
with open(request_csv, newline="", encoding="utf-8") as fh:
    requests = list(csv.DictReader(fh))

logs = json.loads(Path(log_json).read_text(encoding="utf-8") or "[]")
events = []
for entry in logs:
    payload = entry.get("jsonPayload") or {}
    payload["timestamp"] = entry.get("timestamp")
    if payload.get("event", "").startswith("stt_"):
        events.append(payload)

fieldnames = [
    "timestamp",
    "stt_trace_id",
    "request_id",
    "event",
    "provider",
    "stt_winner",
    "success",
    "stt_request_duration_ms",
    "stt_base64_decode_duration_ms",
    "stt_audio_prepare_duration_ms",
    "stt_audio_conversion_duration_ms",
    "stt_qwen_duration_ms",
    "stt_qwen_runtime_duration_ms",
    "stt_qwen_model_load_duration_ms",
    "stt_qwen_audio_conversion_duration_ms",
    "stt_qwen_wav_decode_duration_ms",
    "stt_qwen_pcm_prepare_duration_ms",
    "stt_qwen_model_inference_duration_ms",
    "stt_qwen_postprocess_duration_ms",
    "stt_vosk_duration_ms",
    "stt_vosk_runtime_duration_ms",
    "stt_vosk_audio_conversion_duration_ms",
    "stt_vosk_wav_decode_duration_ms",
    "stt_vosk_downmix_duration_ms",
    "stt_vosk_resample_duration_ms",
    "stt_vosk_model_load_duration_ms",
    "stt_vosk_recognition_duration_ms",
    "stt_overall_duration_ms",
    "stt_hedge_wait_duration_ms",
    "stt_qwen_grace_wait_duration_ms",
    "stt_model_load_duration_ms",
    "language",
    "error_type",
]
with open(event_csv, "w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(events)

def percentile(values, ratio):
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

def stats(values):
    nums = [float(v) for v in values if v not in (None, "")]
    if not nums:
        return {"count": 0, "p50": None, "p90": None, "p95": None, "max": None}
    return {
        "count": len(nums),
        "p50": percentile(nums, 0.50),
        "p90": percentile(nums, 0.90),
        "p95": percentile(nums, 0.95),
        "max": max(nums),
    }

winner_events = [event for event in events if event.get("event") == "stt_winner"]
request_events = [event for event in events if event.get("event") == "stt_request_complete"]
audio_prepare_events = [
    event for event in events if event.get("event") == "stt_audio_prepare_complete"
]
qwen_events = [event for event in events if event.get("event") == "stt_qwen_complete"]
qwen_runtime_events = [
    event for event in events if event.get("event") == "stt_qwen_runtime_complete"
]
qwen_postprocess_events = [
    event for event in events if event.get("event") == "stt_qwen_postprocess_complete"
]
vosk_events = [event for event in events if event.get("event") == "stt_vosk_complete"]
vosk_runtime_events = [
    event for event in events if event.get("event") == "stt_vosk_runtime_complete"
]
model_events = [event for event in events if event.get("event") == "stt_model_load_complete"]
hedge_events = [event for event in events if event.get("event") == "stt_qwen_hedge_start"]
grace_events = winner_events

request_totals = [row["total_ms"] for row in requests]
overall = stats(event.get("stt_overall_duration_ms") for event in winner_events)
backend_request = stats(event.get("stt_request_duration_ms") for event in request_events)
base64_decode = stats(event.get("stt_base64_decode_duration_ms") for event in request_events)
audio_prepare = stats(event.get("stt_audio_prepare_duration_ms") for event in audio_prepare_events)
audio_conversion = stats(
    event.get("stt_audio_conversion_duration_ms") for event in audio_prepare_events
)
qwen = stats(event.get("stt_qwen_duration_ms") for event in qwen_events)
qwen_runtime = stats(event.get("stt_qwen_runtime_duration_ms") for event in qwen_runtime_events)
qwen_model_inference = stats(
    event.get("stt_qwen_model_inference_duration_ms") for event in qwen_runtime_events
)
qwen_postprocess = stats(
    event.get("stt_qwen_postprocess_duration_ms") for event in qwen_postprocess_events
)
vosk = stats(event.get("stt_vosk_duration_ms") for event in vosk_events)
vosk_runtime = stats(event.get("stt_vosk_runtime_duration_ms") for event in vosk_runtime_events)
vosk_recognition = stats(
    event.get("stt_vosk_recognition_duration_ms") for event in vosk_runtime_events
)
network = stats(request_totals)
model = stats(event.get("stt_model_load_duration_ms") for event in model_events)
hedge_wait = stats(event.get("stt_hedge_wait_duration_ms") for event in hedge_events)
grace_wait = stats(event.get("stt_qwen_grace_wait_duration_ms") for event in grace_events)

winners = defaultdict(int)
for event in winner_events:
    winners[event.get("stt_winner") or "unknown"] += 1

def fmt(value):
    return "n/a" if value is None else f"{value:.0f}"

lines = [
    f"# STT Phase 2 Profile {Path(report_md).stem.removeprefix('stt-profile-')}",
    "",
    f"- Target: `{base_url}`",
    f"- Cloud Run service: `{service}` / `{region}`",
    f"- Window UTC: `{start}` to `{end}`",
    f"- Requests: `{len(requests)}`",
    f"- Structured STT events: `{len(events)}`",
    f"- Event CSV: `{Path(event_csv).name}`",
    f"- Request CSV: `{Path(request_csv).name}`",
    "",
    "## Summary",
    "",
    "| Metric | count | p50 ms | p90 ms | p95 ms | max ms |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
    f"| request_total | {network['count']} | {fmt(network['p50'])} | {fmt(network['p90'])} | {fmt(network['p95'])} | {fmt(network['max'])} |",
    f"| backend_stt_request | {backend_request['count']} | {fmt(backend_request['p50'])} | {fmt(backend_request['p90'])} | {fmt(backend_request['p95'])} | {fmt(backend_request['max'])} |",
    f"| base64_decode | {base64_decode['count']} | {fmt(base64_decode['p50'])} | {fmt(base64_decode['p90'])} | {fmt(base64_decode['p95'])} | {fmt(base64_decode['max'])} |",
    f"| audio_prepare | {audio_prepare['count']} | {fmt(audio_prepare['p50'])} | {fmt(audio_prepare['p90'])} | {fmt(audio_prepare['p95'])} | {fmt(audio_prepare['max'])} |",
    f"| audio_conversion | {audio_conversion['count']} | {fmt(audio_conversion['p50'])} | {fmt(audio_conversion['p90'])} | {fmt(audio_conversion['p95'])} | {fmt(audio_conversion['max'])} |",
    f"| stt_overall | {overall['count']} | {fmt(overall['p50'])} | {fmt(overall['p90'])} | {fmt(overall['p95'])} | {fmt(overall['max'])} |",
    f"| qwen_inference | {qwen['count']} | {fmt(qwen['p50'])} | {fmt(qwen['p90'])} | {fmt(qwen['p95'])} | {fmt(qwen['max'])} |",
    f"| qwen_runtime | {qwen_runtime['count']} | {fmt(qwen_runtime['p50'])} | {fmt(qwen_runtime['p90'])} | {fmt(qwen_runtime['p95'])} | {fmt(qwen_runtime['max'])} |",
    f"| qwen_model_inference | {qwen_model_inference['count']} | {fmt(qwen_model_inference['p50'])} | {fmt(qwen_model_inference['p90'])} | {fmt(qwen_model_inference['p95'])} | {fmt(qwen_model_inference['max'])} |",
    f"| qwen_postprocess | {qwen_postprocess['count']} | {fmt(qwen_postprocess['p50'])} | {fmt(qwen_postprocess['p90'])} | {fmt(qwen_postprocess['p95'])} | {fmt(qwen_postprocess['max'])} |",
    f"| vosk_inference | {vosk['count']} | {fmt(vosk['p50'])} | {fmt(vosk['p90'])} | {fmt(vosk['p95'])} | {fmt(vosk['max'])} |",
    f"| vosk_runtime | {vosk_runtime['count']} | {fmt(vosk_runtime['p50'])} | {fmt(vosk_runtime['p90'])} | {fmt(vosk_runtime['p95'])} | {fmt(vosk_runtime['max'])} |",
    f"| vosk_recognition | {vosk_recognition['count']} | {fmt(vosk_recognition['p50'])} | {fmt(vosk_recognition['p90'])} | {fmt(vosk_recognition['p95'])} | {fmt(vosk_recognition['max'])} |",
    f"| hedge_wait | {hedge_wait['count']} | {fmt(hedge_wait['p50'])} | {fmt(hedge_wait['p90'])} | {fmt(hedge_wait['p95'])} | {fmt(hedge_wait['max'])} |",
    f"| qwen_grace_wait | {grace_wait['count']} | {fmt(grace_wait['p50'])} | {fmt(grace_wait['p90'])} | {fmt(grace_wait['p95'])} | {fmt(grace_wait['max'])} |",
    f"| model_load | {model['count']} | {fmt(model['p50'])} | {fmt(model['p90'])} | {fmt(model['p95'])} | {fmt(model['max'])} |",
    "",
    "## Winners",
    "",
]
for winner, count in sorted(winners.items()):
    lines.append(f"- `{winner}`: {count}")
lines.extend([
    "",
    "## Notes",
    "",
    "- `request_total` includes network and JSON serialization overhead.",
    "- `stt_overall` is emitted inside `STTAgent._transcribe_qwen_primary`.",
    "- Event grouping uses `stt_trace_id`; request rows are ordered separately.",
])

Path(report_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "Wrote $REPORT_MD"
echo "Wrote $REQUEST_CSV"
echo "Wrote $EVENT_CSV"
