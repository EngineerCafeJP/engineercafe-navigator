#!/usr/bin/env bash
set -euo pipefail

# Alpha deployment smoke test — verifies the P0 scenarios that broke in rev 00093-gz5.
#
# Scenarios:
#   1. Health check                            (fast)
#   2. LTM cross-session recall                (15s wait default, 300s with --full)
#   3. EventAgent hallucination check (JA/EN)  (fast)
#   4. EN RAG registration / parking / hours   (fast)
#
# Usage:
#   scripts/alpha-smoke.sh                                    # all scenarios, 15s LTM wait
#   scripts/alpha-smoke.sh --full                             # +5min LTM idle acceptance
#   scripts/alpha-smoke.sh --ltm-only                         # LTM only
#   scripts/alpha-smoke.sh --host https://... --key $API_KEY  # override target
#
# Env:
#   API_SECRET_KEY            Required unless --key provided or gcloud available
#   ALPHA_SMOKE_BASE_URL      Overrides default Cloud Run URL
#
# Exit: 0 if every scenario passed, 1 otherwise.

DEFAULT_URL="https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"
BASE_URL="${ALPHA_SMOKE_BASE_URL:-$DEFAULT_URL}"
API_KEY="${API_SECRET_KEY:-}"
MODE_FULL=0
ONLY_LTM=0
ONLY_EVENT=0
ONLY_EN_RAG=0
LTM_WAIT_DEFAULT=15
LTM_WAIT_FULL=300

PASS_COUNT=0
FAIL_COUNT=0
FAILED_CASES=()

usage() {
  sed -n '3,22p' "$0"
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)       MODE_FULL=1; shift ;;
    --ltm-only)   ONLY_LTM=1; shift ;;
    --event-only) ONLY_EVENT=1; shift ;;
    --en-only)    ONLY_EN_RAG=1; shift ;;
    --host)       BASE_URL="$2"; shift 2 ;;
    --key)        API_KEY="$2"; shift 2 ;;
    -h|--help)    usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

fetch_api_key_from_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    gcloud secrets versions access latest \
      --secret=API_SECRET_KEY --project=aipartner-426616 2>/dev/null || true
  fi
}

if [ -z "$API_KEY" ]; then
  API_KEY="$(fetch_api_key_from_gcloud)"
fi

if [ -z "$API_KEY" ]; then
  echo "Error: API_SECRET_KEY is required (pass --key, set env, or gcloud login)" >&2
  exit 2
fi

record_pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "[PASS] $1"
}

record_fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILED_CASES+=("$1")
  echo "[FAIL] $1 — $2"
}

chat_post() {
  local body="$1" tmp status
  tmp=$(mktemp)
  status=$(curl -sS -m 45 -o "$tmp" -w "%{http_code}" \
    -X POST "$BASE_URL/api/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "$body" || true)
  if [ "$status" != "200" ]; then
    echo "HTTP_$status"
    rm -f "$tmp"
    return 1
  fi
  cat "$tmp"
  rm -f "$tmp"
}

json_pick() {
  python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception as exc:
    print(f'ERR:{exc}')
    sys.exit(0)
path = sys.argv[1].split('.')
node = data
for key in path:
    if isinstance(node, dict):
        node = node.get(key, '')
    else:
        node = ''
        break
print(node if isinstance(node, str) else json.dumps(node, ensure_ascii=False))
" "$1"
}

contains_any() {
  local haystack="$1"; shift
  for needle in "$@"; do
    [[ "$haystack" == *"$needle"* ]] && return 0
  done
  return 1
}

test_health() {
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
  if [ "$code" = "200" ]; then
    record_pass "health endpoint returns 200"
  else
    record_fail "health endpoint" "got $code"
  fi
}

test_ltm_cross_session() {
  local wait_seconds="$1"
  local vid
  vid="alpha-ltm-$(date +%s)-$$"
  local write_body read_body write_out read_out answer
  write_body=$(python3 -c "import json,sys;print(json.dumps({'query':'私の名前は山本太郎です。覚えてください。','language':'ja','session_id':'alpha-ltm-w','visitor_id':sys.argv[1]}))" "$vid")
  write_out=$(chat_post "$write_body") || { record_fail "LTM write request" "$write_out"; return; }

  echo "  ... sleeping ${wait_seconds}s to simulate idle before cross-session recall"
  sleep "$wait_seconds"

  read_body=$(python3 -c "import json,sys;print(json.dumps({'query':'私の名前を覚えていますか？','language':'ja','session_id':'alpha-ltm-r','visitor_id':sys.argv[1]}))" "$vid")
  read_out=$(chat_post "$read_body") || { record_fail "LTM recall request" "$read_out"; return; }

  answer=$(printf '%s' "$read_out" | json_pick answer)
  if contains_any "$answer" "山本" "太郎"; then
    record_pass "LTM cross-session recall (idle=${wait_seconds}s) vid=$vid"
  else
    record_fail "LTM cross-session recall (idle=${wait_seconds}s)" "answer='$answer' vid=$vid"
  fi
}

test_event_agent_ja() {
  local body out answer
  body='{"query":"今日のイベントを教えて","language":"ja","session_id":"alpha-evt-ja"}'
  out=$(chat_post "$body") || { record_fail "EventAgent JA request" "$out"; return; }
  answer=$(printf '%s' "$out" | json_pick answer)
  if contains_any "$answer" "ビジー" "your calendar" "ランチ交流会"; then
    record_fail "EventAgent JA hallucination" "suspicious tokens in '$answer'"
  else
    record_pass "EventAgent JA responds without hallucination tokens"
  fi
}

test_event_agent_en() {
  local body out answer
  body='{"query":"Any events today?","language":"en","session_id":"alpha-evt-en"}'
  out=$(chat_post "$body") || { record_fail "EventAgent EN request" "$out"; return; }
  answer=$(printf '%s' "$out" | json_pick answer)
  if contains_any "$answer" "lunch exchange" "your calendar"; then
    record_fail "EventAgent EN hallucination" "suspicious tokens in '$answer'"
  else
    record_pass "EventAgent EN responds without hallucination tokens"
  fi
}

test_en_rag_query() {
  local question="$1"
  local expect_source="$2"
  local body out sources ans
  body=$(python3 -c "import json,sys;print(json.dumps({'query':sys.argv[1],'language':'en','session_id':'alpha-en-rag'}))" "$question")
  out=$(chat_post "$body") || { record_fail "EN RAG request ($question)" "$out"; return; }
  sources=$(printf '%s' "$out" | json_pick metadata.sources)
  ans=$(printf '%s' "$out" | json_pick answer)
  if [[ "$sources" == *"$expect_source"* ]]; then
    record_pass "EN RAG '$question' -> sources contain $expect_source"
  else
    record_fail "EN RAG '$question'" "sources=$sources answer='${ans:0:80}'"
  fi
}

run_ltm_scenarios() {
  echo "--- LTM cross-session recall ---"
  test_ltm_cross_session "$LTM_WAIT_DEFAULT"
  if [ "$MODE_FULL" = "1" ]; then
    test_ltm_cross_session "$LTM_WAIT_FULL"
  fi
  echo ""
}

run_event_scenarios() {
  echo "--- EventAgent hallucination ---"
  test_event_agent_ja
  test_event_agent_en
  echo ""
}

run_en_rag_scenarios() {
  echo "--- EN RAG (membership / parking / hours) ---"
  test_en_rag_query "How do I register as a member?" "enhanced_rag"
  test_en_rag_query "Tell me about membership"        "enhanced_rag"
  test_en_rag_query "Is there parking available?"     "enhanced_rag"
  test_en_rag_query "What are the business hours?"    "enhanced_rag"
  echo ""
}

print_header() {
  echo "============================================"
  echo "Alpha smoke test"
  echo "URL : $BASE_URL"
  echo "Mode: full=$MODE_FULL ltm_only=$ONLY_LTM event_only=$ONLY_EVENT en_only=$ONLY_EN_RAG"
  echo "============================================"
  echo ""
}

print_summary() {
  local total=$((PASS_COUNT + FAIL_COUNT))
  echo "============================================"
  echo "Summary: $PASS_COUNT passed, $FAIL_COUNT failed (out of $total)"
  if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "Failed cases:"
    for c in "${FAILED_CASES[@]}"; do
      echo "  - $c"
    done
  fi
  echo "============================================"
}

main() {
  print_header

  if [ "$ONLY_LTM" = "0" ] && [ "$ONLY_EVENT" = "0" ] && [ "$ONLY_EN_RAG" = "0" ]; then
    test_health
    echo ""
    run_ltm_scenarios
    run_event_scenarios
    run_en_rag_scenarios
  else
    [ "$ONLY_LTM" = "1" ]    && run_ltm_scenarios
    [ "$ONLY_EVENT" = "1" ]  && run_event_scenarios
    [ "$ONLY_EN_RAG" = "1" ] && run_en_rag_scenarios
  fi

  print_summary
  [ "$FAIL_COUNT" -eq 0 ] || exit 1
}

main "$@"
