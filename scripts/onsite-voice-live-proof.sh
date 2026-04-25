#!/usr/bin/env bash
set -euo pipefail

# On-site voice live proof for #571.
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
)

if [ "$DRY_RUN" = "1" ]; then
  cmd+=(--dry-run)
else
  cmd+=(--api-key "$API_KEY")
fi

"${cmd[@]}"
