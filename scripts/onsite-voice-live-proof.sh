#!/usr/bin/env bash
set -euo pipefail

# On-site voice live proof for #774/#483/#489/#140.
#
# This script is for real kiosk/device audio, not CI fixtures. Record WAV files
# from the target microphone, describe them in a manifest, then run the same
# live API path used by the product:
#
#   /api/voice speech_to_text -> /api/chat -> /api/voice text_to_speech
#
# Usage:
#   scripts/onsite-voice-live-proof.sh --manifest path/to/manifest.json
#   scripts/onsite-voice-live-proof.sh --manifest path/to/manifest.json --host https://... --key "$API_SECRET_KEY"
#   scripts/onsite-voice-live-proof.sh --manifest path/to/manifest.json --dry-run

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/backend/evaluation/onsite_voice_live_proof.py"
DEFAULT_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
BASE_URL="${ONSITE_VOICE_LIVE_BASE_URL:-$DEFAULT_URL}"
API_KEY="${API_SECRET_KEY:-${BACKEND_API_KEY:-}}"
SECRET_PROJECT="${ONSITE_VOICE_LIVE_SECRET_PROJECT:-aipartner-426616}"
SECRET_NAME="API_SECRET_KEY"
OUTPUT_DIR="$ROOT_DIR/backend/tests/reports"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
MANIFEST=""
DRY_RUN=0
SLEEP="${ONSITE_VOICE_LIVE_SLEEP:-2.2}"
TIMEOUT="${ONSITE_VOICE_LIVE_TIMEOUT:-120}"
RETRIES="${ONSITE_VOICE_LIVE_RETRIES:-3}"
STT_PASS_MS="${ONSITE_STT_PASS_MS:-5000}"
STT_FAIL_MS="${ONSITE_STT_FAIL_MS:-10000}"
CHAT_PASS_MS="${ONSITE_CHAT_PASS_MS:-5000}"
CHAT_FAIL_MS="${ONSITE_CHAT_FAIL_MS:-10000}"
TTS_PASS_MS="${ONSITE_TTS_PASS_MS:-5000}"
TTS_FAIL_MS="${ONSITE_TTS_FAIL_MS:-10000}"
FULL_TURN_PASS_MS="${ONSITE_FULL_TURN_PASS_MS:-12000}"
FULL_TURN_FAIL_MS="${ONSITE_FULL_TURN_FAIL_MS:-15000}"
TRANSCRIPT_SIMILARITY="${ONSITE_TRANSCRIPT_SIMILARITY:-0.50}"
FACT_SIMILARITY="${ONSITE_FACT_SIMILARITY:-0.60}"
TTS_PROVIDER="${ONSITE_TTS_PROVIDER:-piper}"
MIN_TTS_AUDIO_CHARS="${ONSITE_MIN_TTS_AUDIO_CHARS:-64}"
ALLOW_VOSK_FALLBACK=0

usage() {
  sed -n '3,14p' "$0"
  cat <<'EOF'

Options:
  --manifest FILE        Required JSON manifest for on-site audio cases
  --host URL             Backend base URL (default: Cloud Run live URL)
  --key VALUE            API key; skips Secret Manager lookup
  --secret-project ID    GCP project for Secret Manager (default: aipartner-426616)
  --secret-name NAME     Secret Manager secret name (default: API_SECRET_KEY)
  --output-dir DIR       Report directory (default: backend/tests/reports)
  --timestamp VALUE      Stable timestamp for report names
  --sleep SEC            Seconds between live calls (default: 2.2)
  --timeout SECONDS      Per-request timeout (default: 120)
  --retries N            Retries for 429/transient live calls (default: 3)
  --stt-pass-ms N        STT green window upper bound (default: 5000)
  --stt-fail-ms N        STT failure window lower bound (default: 10000)
  --chat-pass-ms N       Chat green window upper bound (default: 5000)
  --chat-fail-ms N       Chat failure window lower bound (default: 10000)
  --tts-pass-ms N        TTS green window upper bound (default: 5000)
  --tts-fail-ms N        TTS failure window lower bound (default: 10000)
  --full-turn-pass-ms N  STT+chat+TTS green window upper bound (default: 12000)
  --full-turn-fail-ms N  STT+chat+TTS failure window lower bound (default: 15000)
  --tts-provider NAME    TTS provider override for answer synthesis (default: piper)
  --allow-vosk-fallback  Permit Vosk fallback in the underlying STT proof
  --dry-run              Validate manifest and print plan without network
  -h, --help             Show this usage

Manifest example:
  {
    "cases": [
      {
        "id": "ONSITE-JA-BIZ-001",
        "audio_path": "audio/onsite-ja-biz-001.wav",
        "language": "ja",
        "expected_transcript": "エンジニアカフェの営業時間を教えてください。",
        "expected_route": "business_info",
        "required_sources": ["enhanced_rag"],
        "expected_facts": ["10", "20|8"]
      }
    ]
  }
EOF
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --host) BASE_URL="$2"; shift 2 ;;
    --key) API_KEY="$2"; shift 2 ;;
    --secret-project) SECRET_PROJECT="$2"; shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --timestamp) TIMESTAMP="$2"; shift 2 ;;
    --sleep) SLEEP="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --retries) RETRIES="$2"; shift 2 ;;
    --stt-pass-ms) STT_PASS_MS="$2"; shift 2 ;;
    --stt-fail-ms) STT_FAIL_MS="$2"; shift 2 ;;
    --chat-pass-ms) CHAT_PASS_MS="$2"; shift 2 ;;
    --chat-fail-ms) CHAT_FAIL_MS="$2"; shift 2 ;;
    --tts-pass-ms) TTS_PASS_MS="$2"; shift 2 ;;
    --tts-fail-ms) TTS_FAIL_MS="$2"; shift 2 ;;
    --full-turn-pass-ms) FULL_TURN_PASS_MS="$2"; shift 2 ;;
    --full-turn-fail-ms) FULL_TURN_FAIL_MS="$2"; shift 2 ;;
    --tts-provider) TTS_PROVIDER="$2"; shift 2 ;;
    --allow-vosk-fallback) ALLOW_VOSK_FALLBACK=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

if [ -z "$MANIFEST" ]; then
  echo "Error: --manifest is required" >&2
  usage 2
fi

fetch_api_key_from_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    gcloud secrets versions access latest \
      --secret="$SECRET_NAME" --project="$SECRET_PROJECT" 2>/dev/null || true
  fi
}

require_positive_number() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "Error: $name must be a positive number: $value" >&2
    exit 2
  fi
}

require_threshold_order() {
  local pass_name="$1"
  local pass_value="$2"
  local fail_name="$3"
  local fail_value="$4"
  python3 - "$pass_name" "$pass_value" "$fail_name" "$fail_value" <<'PY'
import sys
pass_name, pass_value, fail_name, fail_value = sys.argv[1:5]
if float(pass_value) > float(fail_value):
    raise SystemExit(f"Error: {pass_name} must be <= {fail_name}: {pass_value} > {fail_value}")
PY
}

for pair in \
  "sleep:$SLEEP" \
  "timeout:$TIMEOUT" \
  "retries:$RETRIES" \
  "stt-pass-ms:$STT_PASS_MS" \
  "stt-fail-ms:$STT_FAIL_MS" \
  "chat-pass-ms:$CHAT_PASS_MS" \
  "chat-fail-ms:$CHAT_FAIL_MS" \
  "tts-pass-ms:$TTS_PASS_MS" \
  "tts-fail-ms:$TTS_FAIL_MS" \
  "full-turn-pass-ms:$FULL_TURN_PASS_MS" \
  "full-turn-fail-ms:$FULL_TURN_FAIL_MS" \
  "transcript-similarity:$TRANSCRIPT_SIMILARITY" \
  "fact-similarity:$FACT_SIMILARITY" \
  "min-tts-audio-chars:$MIN_TTS_AUDIO_CHARS"; do
  require_positive_number "${pair%%:*}" "${pair#*:}"
done
require_threshold_order "--stt-pass-ms" "$STT_PASS_MS" "--stt-fail-ms" "$STT_FAIL_MS"
require_threshold_order "--chat-pass-ms" "$CHAT_PASS_MS" "--chat-fail-ms" "$CHAT_FAIL_MS"
require_threshold_order "--tts-pass-ms" "$TTS_PASS_MS" "--tts-fail-ms" "$TTS_FAIL_MS"
require_threshold_order "--full-turn-pass-ms" "$FULL_TURN_PASS_MS" "--full-turn-fail-ms" "$FULL_TURN_FAIL_MS"

if [ -z "$API_KEY" ] && [ "$DRY_RUN" != "1" ]; then
  API_KEY="$(fetch_api_key_from_gcloud)"
fi

if [ -z "$API_KEY" ] && [ "$DRY_RUN" != "1" ]; then
  echo "Error: API_SECRET_KEY/BACKEND_API_KEY is required (pass --key, set env, or allow gcloud Secret Manager access)" >&2
  exit 2
fi

cmd=(
  python3 "$RUNNER"
  --manifest "$MANIFEST"
  --host "$BASE_URL"
  --output-dir "$OUTPUT_DIR"
  --timestamp "$TIMESTAMP"
  --sleep "$SLEEP"
  --timeout "$TIMEOUT"
  --retries "$RETRIES"
  --stt-warn-ms "$STT_PASS_MS"
  --stt-max-ms "$STT_FAIL_MS"
  --chat-warn-ms "$CHAT_PASS_MS"
  --tts-max-ms "$TTS_FAIL_MS"
  --transcript-similarity "$TRANSCRIPT_SIMILARITY"
  --fact-similarity "$FACT_SIMILARITY"
  --tts-provider "$TTS_PROVIDER"
  --min-tts-audio-chars "$MIN_TTS_AUDIO_CHARS"
)

if [ "$ALLOW_VOSK_FALLBACK" = "1" ]; then
  cmd+=(--allow-vosk-fallback)
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "Operational gate windows:"
  echo "  STT: pass<=${STT_PASS_MS}ms warn<=${STT_FAIL_MS}ms fail>${STT_FAIL_MS}ms"
  echo "  Chat: pass<=${CHAT_PASS_MS}ms warn<=${CHAT_FAIL_MS}ms fail>${CHAT_FAIL_MS}ms"
  echo "  TTS: pass<=${TTS_PASS_MS}ms warn<=${TTS_FAIL_MS}ms fail>${TTS_FAIL_MS}ms"
  echo "  Full turn: pass<=${FULL_TURN_PASS_MS}ms warn<=${FULL_TURN_FAIL_MS}ms fail>${FULL_TURN_FAIL_MS}ms"
  echo ""
  cmd+=(--dry-run)
else
  cmd+=(--api-key "$API_KEY")
fi

runner_rc=0
"${cmd[@]}" || runner_rc=$?

if [ "$DRY_RUN" = "1" ]; then
  exit "$runner_rc"
fi

CSV="$OUTPUT_DIR/onsite-voice-live-proof-$TIMESTAMP.csv"
OPS_REPORT="$OUTPUT_DIR/onsite-voice-ops-gate-$TIMESTAMP.md"
if [ ! -f "$CSV" ]; then
  echo "Error: expected runner CSV not found: $CSV" >&2
  exit "${runner_rc:-1}"
fi

ops_rc=0
python3 - "$CSV" "$OPS_REPORT" "$TIMESTAMP" "$BASE_URL" "$MANIFEST" \
  "$STT_PASS_MS" "$STT_FAIL_MS" "$CHAT_PASS_MS" "$CHAT_FAIL_MS" \
  "$TTS_PASS_MS" "$TTS_FAIL_MS" "$FULL_TURN_PASS_MS" "$FULL_TURN_FAIL_MS" \
  "$runner_rc" <<'PY' || ops_rc=$?
from __future__ import annotations

import csv
import pathlib
import sys
from collections import defaultdict
from typing import Any

(
    csv_path,
    report_path,
    timestamp,
    base_url,
    manifest,
    stt_pass,
    stt_fail,
    chat_pass,
    chat_fail,
    tts_pass,
    tts_fail,
    full_pass,
    full_fail,
    runner_rc,
) = sys.argv[1:15]

thresholds = {
    "onsite_qwen_stt": ("STT", float(stt_pass), float(stt_fail)),
    "live_langgraph_answer": ("Chat", float(chat_pass), float(chat_fail)),
    "live_answer_tts": ("TTS", float(tts_pass), float(tts_fail)),
}
full_pass_f = float(full_pass)
full_fail_f = float(full_fail)


def md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def classify(duration_ms: float, pass_ms: float, fail_ms: float) -> str:
    if duration_ms > fail_ms:
        return "FAIL"
    if duration_ms > pass_ms:
        return "WARN"
    return "PASS"


def worse(left: str, right: str) -> str:
    order = {"PASS": 0, "WARN": 1, "FAIL": 2}
    return left if order[left] >= order[right] else right


rows: list[dict[str, str]] = []
with pathlib.Path(csv_path).open("r", encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh))

by_case: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
latency_rows: list[tuple[str, str, str, int, str, str]] = []
gate_status = "PASS"

for row in rows:
    case_id = row.get("case_id", "")
    step = row.get("step", "")
    by_case[case_id][step] = row
    if row.get("status") == "FAIL":
        gate_status = "FAIL"
    if step not in thresholds:
        continue
    label, pass_ms, fail_ms = thresholds[step]
    duration = int(float(row.get("duration_ms") or 0))
    latency_status = classify(duration, pass_ms, fail_ms)
    gate_status = worse(gate_status, latency_status)
    latency_rows.append(
        (
            case_id,
            label,
            latency_status,
            duration,
            f"pass<={int(pass_ms)}ms warn<={int(fail_ms)}ms fail>{int(fail_ms)}ms",
            row.get("status", ""),
        )
    )

full_rows: list[tuple[str, str, int, str]] = []
for case_id, steps in sorted(by_case.items()):
    missing = [step for step in thresholds if step not in steps]
    if missing:
        full_rows.append((case_id, "FAIL", 0, f"missing steps: {', '.join(missing)}"))
        gate_status = "FAIL"
        continue
    total = sum(int(float(steps[step].get("duration_ms") or 0)) for step in thresholds)
    status = classify(total, full_pass_f, full_fail_f)
    gate_status = worse(gate_status, status)
    full_rows.append(
        (
            case_id,
            status,
            total,
            f"pass<={int(full_pass_f)}ms warn<={int(full_fail_f)}ms fail>{int(full_fail_f)}ms",
        )
    )

if int(runner_rc) != 0:
    gate_status = "FAIL"

lines = [
    "# On-site Voice Ops Gate",
    "",
    f"- Timestamp: {timestamp}",
    f"- Backend: {base_url}",
    f"- Manifest: {manifest}",
    f"- Source CSV: {pathlib.Path(csv_path).name}",
    f"- Runner exit code: {runner_rc}",
    f"- Overall gate: {gate_status}",
    "",
    "## Pass/Fail Windows",
    "",
    "| Hop | PASS | WARN | FAIL |",
    "| --- | ---: | ---: | ---: |",
    f"| STT | <= {int(float(stt_pass))}ms | <= {int(float(stt_fail))}ms | > {int(float(stt_fail))}ms |",
    f"| Chat | <= {int(float(chat_pass))}ms | <= {int(float(chat_fail))}ms | > {int(float(chat_fail))}ms |",
    f"| TTS | <= {int(float(tts_pass))}ms | <= {int(float(tts_fail))}ms | > {int(float(tts_fail))}ms |",
    f"| Full turn | <= {int(full_pass_f)}ms | <= {int(full_fail_f)}ms | > {int(full_fail_f)}ms |",
    "",
    "## Hop Results",
    "",
    "| Case | Hop | Gate | Duration | Window | Runner status |",
    "| --- | --- | --- | ---: | --- | --- |",
]
for case_id, label, status, duration, window, runner_status in latency_rows:
    lines.append(
        f"| {md(case_id)} | {label} | {status} | {duration}ms | {md(window)} | {md(runner_status)} |"
    )

lines.extend(
    [
        "",
        "## Full-Turn Results",
        "",
        "| Case | Gate | STT+chat+TTS | Window |",
        "| --- | --- | ---: | --- |",
    ]
)
for case_id, status, total, window in full_rows:
    lines.append(f"| {md(case_id)} | {status} | {total}ms | {md(window)} |")

lines.extend(
    [
        "",
        "## On-site Checklist",
        "",
        "- Capture WAV files on the target kiosk/M5Stack microphone path, not laptop fixtures.",
        "- Keep Cloud Run revision, backend SHA, device, network, and room/noise notes with this report.",
        "- Run Cloud Logging checks for the same timestamp window before marking onsite proof complete.",
        "- Treat any TTS fallback, empty audio, chat 5xx, memory helper error, UUID hygiene hit, or reception persistence error as a blocker until triaged.",
        "- Do not run Terraform apply from this proof script; monitoring changes remain plan/review/apply only.",
        "",
        "## Cloud Logging Queries",
        "",
        "```text",
        'resource.type="cloud_run_revision"',
        'resource.labels.service_name="engineer-cafe-backend"',
        'jsonPayload.event="stt_winner"',
        "```",
        "",
        "```text",
        'resource.type="cloud_run_revision"',
        'resource.labels.service_name="engineer-cafe-backend"',
        'jsonPayload.event="chat_response"',
        "```",
        "",
        "```text",
        'resource.type="cloud_run_revision"',
        'resource.labels.service_name="engineer-cafe-backend"',
        'jsonPayload.event="tts_complete"',
        "```",
    ]
)

pathlib.Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(report_path)
raise SystemExit(0 if gate_status != "FAIL" else 1)
PY

if [ "$runner_rc" -ne 0 ]; then
  exit "$runner_rc"
fi
exit "$ops_rc"
