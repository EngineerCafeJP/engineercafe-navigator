#!/usr/bin/env bash
set -euo pipefail

# Alpha quality gates for #571 GO decision.
#
# Suites:
#   q - LangGraph回答品質gate
#   m - STM/LTM memory品質gate
#   t - PiperPlus回答TTS品質gate
#
# Usage:
#   scripts/alpha-quality-gates.sh
#   scripts/alpha-quality-gates.sh --host https://... --key "$API_SECRET_KEY"
#   scripts/alpha-quality-gates.sh --suites q,m --dry-run
#
# Env:
#   API_SECRET_KEY                         Required unless --key is provided or gcloud can read it.
#   ALPHA_QUALITY_GATES_BASE_URL           Overrides default Cloud Run URL.
#   ALPHA_QUALITY_GATES_SECRET_PROJECT     Overrides Secret Manager project.
#   ALPHA_QUALITY_CHAT_INTERVAL            Seconds between /api/chat calls (default: 2.2).
#   ALPHA_QUALITY_VOICE_INTERVAL           Seconds between /api/voice calls (default: 3.1).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/backend/evaluation/live_quality_gates.py"
DEFAULT_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
BASE_URL="${ALPHA_QUALITY_GATES_BASE_URL:-$DEFAULT_URL}"
API_KEY="${API_SECRET_KEY:-}"
SECRET_PROJECT="${ALPHA_QUALITY_GATES_SECRET_PROJECT:-aipartner-426616}"
SECRET_NAME="API_SECRET_KEY"
OUTPUT_DIR="$ROOT_DIR/backend/tests/reports"
SUITES="q,m,t"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TIMEOUT=120
CHAT_INTERVAL="${ALPHA_QUALITY_CHAT_INTERVAL:-2.2}"
VOICE_INTERVAL="${ALPHA_QUALITY_VOICE_INTERVAL:-3.1}"
DRY_RUN=0

usage() {
  sed -n '3,17p' "$0"
  cat <<'EOF'

Options:
  --host URL             Backend base URL (default: Cloud Run live URL)
  --key VALUE            API key; skips Secret Manager lookup
  --secret-project ID    GCP project for Secret Manager (default: aipartner-426616)
  --secret-name NAME     Secret Manager secret name (default: API_SECRET_KEY)
  --output-dir DIR       Report directory (default: backend/tests/reports)
  --timestamp VALUE      Stable timestamp for report names
  --suites LIST          Comma-separated q,m,t or all (default: q,m,t)
  --timeout SECONDS      Per-request timeout (default: 120)
  --chat-interval SEC    Minimum seconds between /api/chat calls (default: 2.2)
  --voice-interval SEC   Minimum seconds between /api/voice calls (default: 3.1)
  --dry-run              Validate cases and print plan without network
  -h, --help             Show this usage

Output:
  backend/tests/reports/quality-gates-<timestamp>.md
  backend/tests/reports/quality-gates-<timestamp>.csv
EOF
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) BASE_URL="$2"; shift 2 ;;
    --key) API_KEY="$2"; shift 2 ;;
    --secret-project) SECRET_PROJECT="$2"; shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --timestamp) TIMESTAMP="$2"; shift 2 ;;
    --suites) SUITES="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --chat-interval) CHAT_INTERVAL="$2"; shift 2 ;;
    --voice-interval) VOICE_INTERVAL="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 2
  fi
}

fetch_api_key_from_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    gcloud secrets versions access latest \
      --secret="$SECRET_NAME" --project="$SECRET_PROJECT" 2>/dev/null || true
  fi
}

main() {
  require_cmd python3

  if [ ! -f "$RUNNER" ]; then
    echo "Error: quality gates runner not found: $RUNNER" >&2
    exit 2
  fi

  if [ "$DRY_RUN" = "1" ]; then
    echo "Dry run: no quality gate commands will be executed."
    echo "Timestamp: $TIMESTAMP"
    echo "Runner: $RUNNER"
    echo "Base URL: $BASE_URL"
    echo "Output dir: $OUTPUT_DIR"
    echo "Suites: $SUITES"
    echo "Timeout: $TIMEOUT"
    echo "Chat interval: $CHAT_INTERVAL"
    echo "Voice interval: $VOICE_INTERVAL"
    echo ""
    echo "Case file: backend/evaluation/datasets/quality_gate_cases.json"
    python3 "$RUNNER" --dry-run --suites "$SUITES" --chat-interval "$CHAT_INTERVAL" --voice-interval "$VOICE_INTERVAL"
    exit $?
  fi

  if [ -z "$API_KEY" ]; then
    API_KEY="$(fetch_api_key_from_gcloud)"
  fi
  if [ -z "$API_KEY" ]; then
    echo "Error: API_SECRET_KEY is required (pass --key, set env, or allow gcloud Secret Manager access)" >&2
    exit 2
  fi

  mkdir -p "$OUTPUT_DIR"
  echo "Running alpha quality gates"
  echo "Timestamp: $TIMESTAMP"
  echo "Base URL: $BASE_URL"
  echo "Suites: $SUITES"
  echo "Chat interval: $CHAT_INTERVAL"
  echo "Voice interval: $VOICE_INTERVAL"

  cmd=(python3 "$RUNNER" --base-url "$BASE_URL" --api-key "$API_KEY" --suites "$SUITES" --output-dir "$OUTPUT_DIR" --timestamp "$TIMESTAMP" --timeout "$TIMEOUT" --chat-interval "$CHAT_INTERVAL" --voice-interval "$VOICE_INTERVAL")
  "${cmd[@]}"
}

main "$@"
