#!/usr/bin/env bash
# COSCUP 2026 デモ用: STT モデルのプリロード + LLM の 1 往復 + デモ回答 2 件の TTS キャッシュ生成
#
# 1. POST /api/voice action=warmup          -> STT（Qwen ONNX）モデルを非同期プリロード
# 2. ステータスが ready になるまでポーリング
# 3. POST /api/chat（固定セッション demo-warmup）-> Ollama モデルを Metal にロード
# 4. POST /api/voice action=text_to_speech x2（piper -> kokoro 英語フォールバック）-> TTS キャッシュを温める
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"
SESSION_ID="${DEMO_WARMUP_SESSION:-demo-warmup}"
WARMUP_TIMEOUT_SECONDS="${DEMO_WARMUP_TIMEOUT_SECONDS:-300}"
POLL_INTERVAL_SECONDS=3

started_at=$(date +%s)
fail() {
  echo "[demo] ERROR: $*" >&2
  exit 1
}

post_json() {
  # $1=json body, $2=description; stdout にレスポンスを出力（http code は CODE に）
  local body="$1" desc="$2"
  local response
  response=$(curl -fsS -X POST "${BACKEND_URL}/api/voice" \
    -H "Content-Type: application/json" \
    -d "$body" 2>/dev/null) || fail "POST /api/voice ($desc) failed - is the backend up?"
  printf '%s' "$response"
}

extract_field() {
  # $1=json, $2=field name -> 値（無ければ空文字）
  local json="$1" field="$2"
  printf '%s' "$json" | grep -oE "\"${field}\"[[:space:]]*:[[:space:]]*\"?[^\",}]+" | head -1 \
    | sed -E "s/\"${field}\"[[:space:]]*:[[:space:]]*\"?//"
}

echo "[demo] 1/4  Starting STT warmup (provider=qwen-primary)"
response=$(post_json "{\"action\":\"warmup\",\"sessionId\":\"${SESSION_ID}\"}" "warmup")
echo "[demo]      warmup response status: $(extract_field "$response" sttWarmupStatus)"

echo "[demo] 2/4  Polling STT warmup status (timeout ${WARMUP_TIMEOUT_SECONDS}s)"
deadline=$((SECONDS + WARMUP_TIMEOUT_SECONDS))
status="warming"
while [[ "${status}" != "ready" && "${status}" != "failed" && "${status}" != "skipped" ]]; do
  if ((SECONDS >= deadline)); then
    fail "STT warmup did not finish within ${WARMUP_TIMEOUT_SECONDS}s (last status=${status})"
  fi
  sleep "${POLL_INTERVAL_SECONDS}"
  response=$(post_json "{\"action\":\"warmup\",\"sessionId\":\"${SESSION_ID}\"}" "warmup status")
  status=$(extract_field "$response" sttWarmupStatus)
  echo "[demo]      status: ${status:-unknown}"
done
if [[ "${status}" == "failed" ]]; then
  error=$(extract_field "$response" sttWarmupError)
  fail "STT warmup failed: ${error:-unknown error} (check STT_QWEN_ONNX_MODEL_DIR / ONNX artifact)"
fi

echo "[demo] 3/4  One dummy LLM round trip (loads Ollama model into Metal)"
curl -fsS -X POST "${BACKEND_URL}/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Where is the toilet?\",\"session_id\":\"${SESSION_ID}\",\"language\":\"en\"}" \
  >/dev/null 2>&1 || fail "POST /api/chat failed - is Ollama running on the host?"

echo "[demo] 4/4  Pre-synthesizing the 2 demo answers via piper (falls back to kokoro)"
for text in \
  "You can use our free Wi-Fi, power outlets, meeting rooms, and the makerspace. The cafe on the first floor serves drinks and snacks." \
  "The toilets are on the basement floor, next to the meeting rooms."; do
  response=$(post_json "{\"action\":\"text_to_speech\",\"text\":$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$text"),\"language\":\"en\",\"sessionId\":\"${SESSION_ID}\",\"ttsProvider\":\"piper\"}" "text_to_speech")
  if ! printf '%s' "$response" | grep -q '"success":true'; then
    fail "TTS pre-synthesis failed: $(printf '%s' "$response" | grep -oE '\"error\"[^,}]*' | head -1)"
  fi
done

elapsed=$(( $(date +%s) - started_at ))
echo "[demo] Warm-up done in ${elapsed}s"
echo "[demo] STT model, Ollama model, and 2 TTS cache entries are ready."
echo "[demo] 注意: モデルは Ollama サーバー既定 keep_alive（通常 5 分）でアンロードされます。"
echo "[demo] デモ中は  bash scripts/demo/heartbeat.sh  （バックグラウンド実行推奨）で保持してください。"
echo "[demo] 30 分以上間が空きそうな場合は、直前にもう一度 warmup.sh を実行してください。"
