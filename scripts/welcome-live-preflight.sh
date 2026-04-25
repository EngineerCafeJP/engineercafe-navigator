#!/usr/bin/env bash
set -euo pipefail

# Browser-level Welcome live preflight for alpha H scenarios.
#
# Usage:
#   scripts/welcome-live-preflight.sh
#   scripts/welcome-live-preflight.sh --host https://... --key "$API_SECRET_KEY"
#   scripts/welcome-live-preflight.sh --delays 0,5,10
#   scripts/welcome-live-preflight.sh --dry-run

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
BASE_URL="${WELCOME_LIVE_BASE_URL:-${BACKEND_API_URL:-$DEFAULT_URL}}"
API_KEY="${API_SECRET_KEY:-${BACKEND_API_KEY:-}}"
SECRET_PROJECT="${WELCOME_LIVE_SECRET_PROJECT:-aipartner-426616}"
SECRET_NAME="API_SECRET_KEY"
OUTPUT_DIR="$ROOT_DIR/backend/tests/reports"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DELAYS="${PLAYWRIGHT_WELCOME_VOICE_DELAYS:-0,5,10}"
DRY_RUN=0

usage() {
  sed -n '3,10p' "$0"
  cat <<'EOF'

Options:
  --host URL             Backend base URL (default: Cloud Run live URL)
  --key VALUE            API key; skips Secret Manager lookup
  --secret-project ID    GCP project for Secret Manager (default: aipartner-426616)
  --secret-name NAME     Secret Manager secret name (default: API_SECRET_KEY)
  --output-dir DIR       Report directory (default: backend/tests/reports)
  --timestamp VALUE      Stable timestamp marker for logs
  --delays LIST          Seconds after Welcome before first voice turn (default: 0,5,10)
  --dry-run              Print planned command without network/browser execution
  -h, --help             Show this usage
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
    --delays) DELAYS="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

fetch_api_key_from_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    gcloud secrets versions access latest \
      --secret="$SECRET_NAME" --project="$SECRET_PROJECT" 2>/dev/null || true
  fi
}

if [ -z "$API_KEY" ]; then
  API_KEY="$(fetch_api_key_from_gcloud)"
fi

if [ -z "$API_KEY" ] && [ "$DRY_RUN" != "1" ]; then
  echo "Error: API_SECRET_KEY/BACKEND_API_KEY is required (pass --key, set env, or allow gcloud Secret Manager access)" >&2
  exit 2
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run: no browser or network calls will be executed."
  echo "Backend: $BASE_URL"
  echo "Timestamp: $TIMESTAMP"
  echo "Delays: $DELAYS"
  echo "Output: $OUTPUT_DIR/welcome-live-preflight-$TIMESTAMP.md"
  echo "Command: PLAYWRIGHT_WELCOME_LIVE=1 BACKEND_API_URL=$BASE_URL BACKEND_API_KEY=<redacted> PLAYWRIGHT_WELCOME_VOICE_DELAYS=$DELAYS pnpm --dir frontend exec playwright test --config=playwright.config.ts e2e/welcome-live.spec.ts --project=chromium-voice-live --workers=1"
  exit 0
fi

mkdir -p "$OUTPUT_DIR"
REPORT="$OUTPUT_DIR/welcome-live-preflight-$TIMESTAMP.md"
LOG="$OUTPUT_DIR/welcome-live-preflight-$TIMESTAMP.log"

set +e
BACKEND_API_URL="$BASE_URL" \
BACKEND_API_KEY="$API_KEY" \
PLAYWRIGHT_WELCOME_LIVE=1 \
PLAYWRIGHT_WELCOME_TIMESTAMP="$TIMESTAMP" \
PLAYWRIGHT_WELCOME_VOICE_DELAYS="$DELAYS" \
pnpm --dir "$ROOT_DIR/frontend" exec playwright test \
  --config=playwright.config.ts \
  e2e/welcome-live.spec.ts \
  --project=chromium-voice-live \
  --workers=1 \
  --reporter=line,html 2>&1 | tee "$LOG"
STATUS="${PIPESTATUS[0]}"
set -e

{
  echo "# Welcome Live Preflight"
  echo
  echo "- Timestamp: $TIMESTAMP"
  echo "- Backend: $BASE_URL"
  echo "- Delays: $DELAYS"
  echo "- Status: $([ "$STATUS" = "0" ] && echo PASS || echo FAIL)"
  echo "- Playwright log: $(basename "$LOG")"
  echo
  echo "## Scope"
  echo
  echo "- H-1: Welcome 起動 → greeting TTS → OCR sidecar → STT warmup"
  echo "- H-2/H-3: Welcome 後 0秒/5秒/10秒の初回発話"
  echo "- H-6/H-7: frontend cleanup / stale warmup の回帰は mocked E2E と合わせて確認"
} > "$REPORT"

echo "$REPORT"
exit "$STATUS"
