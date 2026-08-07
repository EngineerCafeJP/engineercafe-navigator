#!/usr/bin/env bash
# COSCUP 2026 デモ用: STT モデルのプリロード + LLM の 1 往復 + デモ回答 2 件の TTS キャッシュ生成
#
# 1. POST /api/voice action=warmup          -> STT（Qwen ONNX）モデルを非同期プリロード
# 2. ステータスが ready になるまでポーリング
# 3. POST /api/chat（固定セッション demo-warmup）-> Ollama モデルを Metal にロード
# 4. POST /api/voice action=text_to_speech x2（piper -> kokoro 英語フォールバック）-> TTS キャッシュを温める
# 5. Ollama native API に keep_alive=1h を送信 + heartbeat.sh をバックグラウンド自動起動
#    -> 起動後 1 時間はモデルがメモリ上に保持される（コールドリロード回避）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"
SESSION_ID="${DEMO_WARMUP_SESSION:-demo-warmup}"
WARMUP_TIMEOUT_SECONDS="${DEMO_WARMUP_TIMEOUT_SECONDS:-300}"
POLL_INTERVAL_SECONDS=3
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.6:35b}"

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

echo "[demo] 1/5  Starting STT warmup (provider=qwen-primary)"
response=$(post_json "{\"action\":\"warmup\",\"sessionId\":\"${SESSION_ID}\"}" "warmup")
echo "[demo]      warmup response status: $(extract_field "$response" sttWarmupStatus)"

echo "[demo] 2/5  Polling STT warmup status (timeout ${WARMUP_TIMEOUT_SECONDS}s)"
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

echo "[demo] 3/5  One dummy LLM round trip (loads Ollama model into Metal)"
curl -fsS -X POST "${BACKEND_URL}/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Where is the toilet?\",\"session_id\":\"${SESSION_ID}\",\"language\":\"en\"}" \
  >/dev/null 2>&1 || fail "POST /api/chat failed - is Ollama running on the host?"

echo "[demo] 4/5  Pre-synthesizing the 2 demo answers via piper (falls back to kokoro)"
for text in \
  "You can use our free Wi-Fi, power outlets, meeting rooms, and the makerspace. The cafe on the first floor serves drinks and snacks." \
  "The toilets are on the basement floor, next to the meeting rooms."; do
  response=$(post_json "{\"action\":\"text_to_speech\",\"text\":$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$text"),\"language\":\"en\",\"sessionId\":\"${SESSION_ID}\",\"ttsProvider\":\"piper\"}" "text_to_speech")
  if ! printf '%s' "$response" | grep -q '"success":true'; then
    fail "TTS pre-synthesis failed: $(printf '%s' "$response" | grep -oE '\"error\"[^,}]*' | head -1)"
  fi
done

echo "[demo] 5/5  Pinning Ollama model (keep_alive=1h) + starting heartbeat"
# backend は OpenAI 互換 API のため keep_alive が無視される → native API で明示送信
if ! curl -fsS --max-time 60 "${OLLAMA_URL}/api/chat" \
    -d "{\"model\":\"${OLLAMA_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"stream\":false,\"keep_alive\":\"1h\"}" \
    >/dev/null 2>&1; then
  echo "[demo] WARNING: keep_alive pin failed (Ollama 未起動?) — コールドリロードの可能性" >&2
fi

# heartbeat.sh が未起動ならバックグラウンドで自動起動（1 時間 warm を維持）
if ! pgrep -f "scripts/demo/heartbeat.sh" >/dev/null 2>&1; then
  nohup bash scripts/demo/heartbeat.sh >/dev/null 2>&1 &
  echo "[demo] heartbeat.sh started (PID $!) — keep_alive=1h を 3 分間隔で更新します"
else
  echo "[demo] heartbeat.sh already running (PID $(pgrep -f 'scripts/demo/heartbeat.sh' | head -1))"
fi

elapsed=$(( $(date +%s) - started_at ))
echo "[demo] Warm-up done in ${elapsed}s"
echo "[demo] STT model, Ollama model, and 2 TTS cache entries are ready."
echo "[demo] Ollama model pinned: keep_alive=1h + heartbeat 常駐 → 1 時間は warm を保証"
echo "[demo] 確認: ollama ps で UNTIL が '59 minutes from now' になっていれば OK"
