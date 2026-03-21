#!/usr/bin/env bash
set -euo pipefail

# Backend deployment verification script
# Tests all backend endpoints with and without authentication.
#
# Usage:
#   ./scripts/verify-deployment.sh <API_SECRET_KEY>
#   API_SECRET_KEY=xxx ./scripts/verify-deployment.sh

BASE_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
API_KEY="${1:-${API_SECRET_KEY:-}}"

if [ -z "$API_KEY" ]; then
  echo "Error: API_SECRET_KEY is required."
  echo "Usage: $0 <API_SECRET_KEY>"
  echo "   or: API_SECRET_KEY=xxx $0"
  exit 1
fi

PASS_COUNT=0
FAIL_COUNT=0

check() {
  local label="$1"
  local expected="$2"
  local actual="$3"

  if [ "$actual" -eq "$expected" ]; then
    echo "[PASS] $label — $actual (expected: $expected)"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "[FAIL] $label — $actual (expected: $expected)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

echo "============================================"
echo "Backend Deployment Verification"
echo "URL: $BASE_URL"
echo "============================================"
echo ""

# -----------------------------------------------------------
# Public endpoints (no auth required)
# -----------------------------------------------------------
echo "--- Public endpoints ---"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
check "GET /health" 200 "$code"

echo ""

# -----------------------------------------------------------
# Protected endpoints (with X-API-Key)
# -----------------------------------------------------------
echo "--- Protected endpoints (with auth) ---"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"query":"こんにちは","session_id":"test","language":"ja"}')
check "POST /api/chat (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/voice?action=supported_languages" \
  -H "X-API-Key: $API_KEY")
check "GET /api/voice?action=supported_languages (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/voice" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"action":"text_to_speech","text":"テスト","language":"ja"}')
check "POST /api/voice (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/slides" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"action":"get_current","session_id":"test"}')
check "POST /api/slides (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/character" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"action":"get_status"}')
check "POST /api/character (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/knowledge/categories" \
  -H "X-API-Key: $API_KEY")
check "GET /api/knowledge/categories (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/monitoring/dashboard" \
  -H "X-API-Key: $API_KEY")
check "GET /api/monitoring/dashboard (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/monitoring/migration-success" \
  -H "X-API-Key: $API_KEY")
check "GET /api/monitoring/migration-success (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/alerts" \
  -H "X-API-Key: $API_KEY")
check "GET /api/alerts (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/reception/start" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"language":"ja"}')
check "POST /api/reception/start (with key)" 200 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/slides/content" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"slide_path":"test"}')
# Accept 200 or 404 as valid
if [ "$code" -eq 200 ] || [ "$code" -eq 404 ]; then
  echo "[PASS] POST /api/slides/content (with key) — $code (expected: 200 or 404)"
  PASS_COUNT=$((PASS_COUNT + 1))
else
  echo "[FAIL] POST /api/slides/content (with key) — $code (expected: 200 or 404)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo ""

# -----------------------------------------------------------
# Auth denial tests (without X-API-Key, expect 403)
# -----------------------------------------------------------
echo "--- Auth denial tests (without key, expect 403) ---"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"query":"こんにちは","session_id":"test","language":"ja"}')
check "POST /api/chat (no key)" 403 "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/knowledge/categories")
check "GET /api/knowledge/categories (no key)" 403 "$code"

echo ""

# -----------------------------------------------------------
# Summary
# -----------------------------------------------------------
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "============================================"
echo "Summary: $PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL tests)"
echo "============================================"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
