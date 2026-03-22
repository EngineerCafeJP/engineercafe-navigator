#!/bin/bash
# Smoke test: Reception → Agent flow
# Tests the full reception lifecycle via Live API
# Usage: bash test_reception_flow.sh [BASE_URL] [API_KEY]
#
# Compatible with both the current deployed backend and Wave 2 updates.
# Steps 1-4 test the reception lifecycle (/api/reception/*).
# Steps 5-6 test chat integration (/api/chat) and are non-fatal
# since Wave 2 may not be deployed yet.

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
API_KEY="${2:-${API_SECRET_KEY:-test-api-key}}"

PASS=0
FAIL=0
WARN=0

pass() { PASS=$((PASS + 1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }
warn() { WARN=$((WARN + 1)); echo "WARN: $1 (non-fatal)"; }

echo "=== Reception Flow Smoke Test ==="
echo "Target: $BASE_URL"
echo ""

# Generate unique session ID
SESSION_ID="smoke-test-$(date +%s)"

# --------------------------------------------------------------------------
# Step 1: Start reception
# --------------------------------------------------------------------------
echo "--- Step 1: Start Reception ---"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/reception/start" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"language\": \"ja\",
    \"trigger_type\": \"button_press\"
  }")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP: $HTTP_CODE"
echo "Body: $BODY"

if [ "$HTTP_CODE" != "200" ]; then
  fail "Start reception: expected 200, got $HTTP_CODE"
  echo ""
  echo "=== Smoke Test Aborted (cannot continue without session) ==="
  exit 1
fi

RECEPTION_SESSION_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['reception_session_id'])" 2>/dev/null)
STAGE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['stage'])" 2>/dev/null)
GREETING=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('greeting','')[:80])" 2>/dev/null)

if [ -z "$RECEPTION_SESSION_ID" ]; then
  fail "Start reception: reception_session_id missing from response"
  echo ""
  echo "=== Smoke Test Aborted ==="
  exit 1
fi

pass "Start reception (stage=$STAGE, greeting=${GREETING}...)"
echo "Reception Session ID: $RECEPTION_SESSION_ID"
echo ""

# --------------------------------------------------------------------------
# Step 2: Respond — advance from greeting to purpose_hearing
# --------------------------------------------------------------------------
echo "--- Step 2: Respond (greeting → purpose_hearing) ---"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/reception/respond" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"reception_session_id\": \"$RECEPTION_SESSION_ID\",
    \"message\": \"はい\"
  }")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP: $HTTP_CODE"
echo "Body: $BODY"

if [ "$HTTP_CODE" != "200" ]; then
  fail "Respond (greeting): expected 200, got $HTTP_CODE"
  echo ""
  echo "=== Smoke Test Aborted ==="
  exit 1
fi

STAGE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['stage'])" 2>/dev/null)
pass "Respond greeting (stage=$STAGE)"
echo ""

# --------------------------------------------------------------------------
# Step 3: Respond — provide purpose to advance to routing
# --------------------------------------------------------------------------
echo "--- Step 3: Respond with Purpose (purpose_hearing → routing) ---"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/reception/respond" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"reception_session_id\": \"$RECEPTION_SESSION_ID\",
    \"message\": \"コワーキングスペースを利用したいです\"
  }")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP: $HTTP_CODE"
echo "Body: $BODY"

if [ "$HTTP_CODE" != "200" ]; then
  fail "Respond (purpose): expected 200, got $HTTP_CODE"
  echo ""
  echo "=== Smoke Test Aborted ==="
  exit 1
fi

STAGE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['stage'])" 2>/dev/null)
PURPOSE=$(echo "$BODY" | python3 -c "import sys,json; p=json.load(sys.stdin).get('purpose'); print(p.get('category','?') if p else 'None')" 2>/dev/null)
echo "Stage: $STAGE, Purpose: $PURPOSE"

# If still in purpose_hearing (classifier didn't match), try again with simpler input
if [ "$STAGE" = "purpose_hearing" ]; then
  echo ""
  echo "--- Step 3b: Retry purpose (classifier didn't match) ---"
  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/reception/respond" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{
      \"session_id\": \"$SESSION_ID\",
      \"reception_session_id\": \"$RECEPTION_SESSION_ID\",
      \"message\": \"施設を利用したい\"
    }")

  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | sed '$d')
  echo "HTTP: $HTTP_CODE"
  echo "Body: $BODY"
  STAGE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['stage'])" 2>/dev/null)
  PURPOSE=$(echo "$BODY" | python3 -c "import sys,json; p=json.load(sys.stdin).get('purpose'); print(p.get('category','?') if p else 'None')" 2>/dev/null)
  echo "Stage: $STAGE, Purpose: $PURPOSE"
fi

if [ "$STAGE" = "routing" ]; then
  pass "Purpose classified (category=$PURPOSE, stage=routing)"
else
  fail "Purpose classification: expected routing stage, got $STAGE"
fi
echo ""

# --------------------------------------------------------------------------
# Step 4: Complete reception (handoff to MainWorkflow)
# --------------------------------------------------------------------------
if [ "$STAGE" = "routing" ]; then
  echo "--- Step 4: Complete Reception ---"
  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/reception/complete" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{
      \"session_id\": \"$SESSION_ID\",
      \"reception_session_id\": \"$RECEPTION_SESSION_ID\"
    }")

  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  echo "HTTP: $HTTP_CODE"
  echo "Body: $BODY"

  if [ "$HTTP_CODE" = "200" ]; then
    TARGET=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('target_agent','?'))" 2>/dev/null)
    ACTION=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('action_type','?'))" 2>/dev/null)
    pass "Complete reception (target_agent=$TARGET, action_type=$ACTION)"
  else
    fail "Complete reception: expected 200, got $HTTP_CODE"
  fi
  echo ""
fi

# --------------------------------------------------------------------------
# Step 5: Check status
# --------------------------------------------------------------------------
echo "--- Step 5: Check Status ---"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "$BASE_URL/api/reception/status/$RECEPTION_SESSION_ID?session_id=$SESSION_ID" \
  -H "X-API-Key: $API_KEY")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP: $HTTP_CODE"
echo "Body: $BODY"

if [ "$HTTP_CODE" = "200" ]; then
  STATUS_STAGE=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stage','?'))" 2>/dev/null)
  pass "Status check (stage=$STATUS_STAGE)"
else
  fail "Status check: expected 200, got $HTTP_CODE"
fi
echo ""

# --------------------------------------------------------------------------
# Step 6: Test /api/chat with the same session (Wave 2 feature)
# Non-fatal — Wave 2 may not be deployed yet.
# --------------------------------------------------------------------------
echo "--- Step 6: Chat with same session (Wave 2 test, non-fatal) ---"
RESPONSE=$(curl -s -w "\n%{http_code}" --max-time 30 -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"query\": \"エンジニアカフェの営業時間を教えてください\",
    \"session_id\": \"$SESSION_ID\",
    \"language\": \"ja\"
  }")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP: $HTTP_CODE"
if [ "$HTTP_CODE" = "200" ]; then
  ANSWER=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'answer={d.get(\"answer\",\"N/A\")[:100]}... agent={d.get(\"metadata\",{}).get(\"agent\",\"N/A\")}')" 2>/dev/null || echo "$BODY" | head -c 200)
  echo "Body: $ANSWER"
  pass "Chat with existing session"
else
  echo "Body: $(echo "$BODY" | head -c 200)"
  warn "Chat with existing session: HTTP $HTTP_CODE (Wave 2 may not be deployed)"
fi
echo ""

# --------------------------------------------------------------------------
# Step 7: Test /api/chat with a NEW session (should trigger reception in Wave 2)
# Non-fatal — Wave 2 may not be deployed yet.
# --------------------------------------------------------------------------
echo "--- Step 7: New session chat (Wave 2 reception trigger, non-fatal) ---"
NEW_SESSION="smoke-new-$(date +%s)"
RESPONSE=$(curl -s -w "\n%{http_code}" --max-time 30 -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"query\": \"こんにちは\",
    \"session_id\": \"$NEW_SESSION\",
    \"language\": \"ja\"
  }")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP: $HTTP_CODE"
if [ "$HTTP_CODE" = "200" ]; then
  ANSWER=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'answer={d.get(\"answer\",\"N/A\")[:100]}... agent={d.get(\"metadata\",{}).get(\"agent\",\"N/A\")}')" 2>/dev/null || echo "$BODY" | head -c 200)
  echo "Body: $ANSWER"
  pass "Chat with new session"
else
  echo "Body: $(echo "$BODY" | head -c 200)"
  warn "Chat with new session: HTTP $HTTP_CODE (Wave 2 may not be deployed)"
fi
echo ""

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo "=== Smoke Test Summary ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
echo "WARN: $WARN (non-fatal)"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: FAILED ($FAIL failures)"
  exit 1
else
  echo "RESULT: PASSED"
  exit 0
fi
