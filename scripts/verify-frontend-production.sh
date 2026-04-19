#!/usr/bin/env bash
set -euo pipefail

# Frontend production smoke verification.
#
# This probes the real Vercel -> Cloud Run path so deploy-time auth drift
# between BACKEND_API_KEY and API_SECRET_KEY shows up immediately.
#
# Usage:
#   ./scripts/verify-frontend-production.sh <frontend_base_url>
#   FRONTEND_BASE_URL=https://example.vercel.app ./scripts/verify-frontend-production.sh

FRONTEND_BASE_URL="${1:-${FRONTEND_BASE_URL:-${FRONTEND_PRODUCTION_ORIGIN:-}}}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-12}"
SLEEP_SECONDS="${SLEEP_SECONDS:-15}"

if [[ -z "$FRONTEND_BASE_URL" ]]; then
  echo "error: frontend base URL is required." >&2
  echo "usage: $0 <frontend_base_url>" >&2
  echo "   or: FRONTEND_BASE_URL=https://example.vercel.app $0" >&2
  exit 1
fi

BASE_URL="${FRONTEND_BASE_URL%/}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PASS_COUNT=0
FAIL_COUNT=0

check_status() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  local body_file="$4"

  if [[ "$actual" == "$expected" ]]; then
    echo "[PASS] $label — $actual"
    PASS_COUNT=$((PASS_COUNT + 1))
    return 0
  fi

  echo "[FAIL] $label — $actual (expected: $expected)" >&2
  echo "Body:" >&2
  sed -n '1,40p' "$body_file" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
  return 1
}

request_with_retries() {
  local label="$1"
  local expected="$2"
  local method="$3"
  local path="$4"
  local body="${5:-}"
  local body_file="$TMP_DIR/$(echo "$label" | tr ' /?:' '_').json"

  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    local code
    : > "$body_file"

    if [[ "$method" == "GET" ]]; then
      code="$(curl -sS -o "$body_file" -w "%{http_code}" "$BASE_URL$path" || true)"
    else
      code="$(curl -sS -o "$body_file" -w "%{http_code}" \
        -X "$method" \
        -H "Content-Type: application/json" \
        -d "$body" \
        "$BASE_URL$path" || true)"
    fi

    if [[ "$code" == "$expected" ]]; then
      check_status "$label" "$expected" "$code" "$body_file"
      return 0
    fi

    echo "[retry $attempt/$MAX_ATTEMPTS] $label returned $code" >&2
    if [[ -s "$body_file" ]]; then
      sed -n '1,20p' "$body_file" >&2
    fi

    if [[ "$attempt" -lt "$MAX_ATTEMPTS" ]]; then
      sleep "$SLEEP_SECONDS"
    fi
  done

  check_status "$label" "$expected" "$code" "$body_file"
  return 1
}

echo "============================================"
echo "Frontend Production Smoke Verification"
echo "URL: $BASE_URL"
echo "Attempts: $MAX_ATTEMPTS"
echo "Sleep seconds: $SLEEP_SECONDS"
echo "============================================"
echo

request_with_retries \
  "GET /api/voice?action=supported_languages" \
  "200" \
  "GET" \
  "/api/voice?action=supported_languages"

request_with_retries \
  "POST /api/character" \
  "200" \
  "POST" \
  "/api/character" \
  '{"action":"get_status"}'

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo
echo "============================================"
echo "Summary: $PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL checks)"
echo "============================================"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
