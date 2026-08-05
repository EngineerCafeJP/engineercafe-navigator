#!/usr/bin/env bash
# COSCUP 2026 デモ用: 録音済み WAV で STT -> Chat -> TTS の 1 往復を実行し、
# バックエンドの構造化ログから各ステージのレイテンシを表形式で表示する
#
# 事前準備: scripts/demo/audio/README.md の手順で WAV を生成しておく
#   say -v Samantha -o scripts/demo/audio/question1.wav --data-format=LEI16@22050 "What can I do at Engineer Cafe?"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"
SESSION_ID="${DEMO_LATENCY_SESSION:-demo-latency}"
WAV_FILE="${1:-scripts/demo/audio/question1.wav}"
LOG_SINCE_SECONDS="${DEMO_LOG_SINCE_SECONDS:-90}"

fail() {
  echo "[demo] ERROR: $*" >&2
  exit 1
}

[[ -f "${WAV_FILE}" ]] || fail "WAV not found: ${WAV_FILE} (see scripts/demo/audio/README.md)"

# macOS と GNU の両方で動く base64 エンコード
audio_b64=$(base64 -i "${WAV_FILE}" 2>/dev/null || base64 "${WAV_FILE}")
[[ -n "${audio_b64}" ]] || fail "Failed to base64-encode ${WAV_FILE}"

echo "[demo] 1/3  STT: speech_to_text (${WAV_FILE}, $(wc -c < "${WAV_FILE}" | tr -d ' ') bytes)"
stt_response=$(curl -fsS -X POST "${BACKEND_URL}/api/voice" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"speech_to_text\",\"audioData\":\"${audio_b64}\",\"language\":\"en\",\"sessionId\":\"${SESSION_ID}\"}" \
  --max-time 90) || fail "POST /api/voice (speech_to_text) failed"
printf '%s' "${stt_response}" | grep -q '"success":true' \
  || fail "STT failed: $(printf '%s' "${stt_response}" | grep -oE '\"error\"[^,}]*' | head -1)"
transcript=$(printf '%s' "${stt_response}" | grep -oE '"transcript":"[^"]*"' | head -1 | sed -E 's/"transcript":"(.*)"/\1/')
echo "[demo]      transcript: ${transcript:-<empty>}"

query="${transcript:-Where is the toilet?}"
echo "[demo] 2/3  Chat: /api/chat (query: ${query})"
chat_response=$(curl -fsS -X POST "${BACKEND_URL}/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"query\":$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$query"),\"session_id\":\"${SESSION_ID}\",\"language\":\"en\"}" \
  --max-time 120) || fail "POST /api/chat failed"
answer=$(printf '%s' "${chat_response}" | grep -oE '"answer":"[^"]*"' | head -1 | sed -E 's/"answer":"(.*)"/\1/')
echo "[demo]      answer: ${answer:-<empty>}"

echo "[demo] 3/3  TTS: text_to_speech (piper -> kokoro fallback)"
tts_text="${answer:-The toilets are on the basement floor, next to the meeting rooms.}"
curl -fsS -X POST "${BACKEND_URL}/api/voice" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"text_to_speech\",\"text\":$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$tts_text"),\"language\":\"en\",\"sessionId\":\"${SESSION_ID}\",\"ttsProvider\":\"piper\"}" \
  -o /dev/null --max-time 90 || fail "POST /api/voice (text_to_speech) failed"

echo "[demo] Extracting structured timing events from backend logs (--since ${LOG_SINCE_SECONDS}s)"
logs=$(docker compose -f docker-compose.yml -f docker-compose.demo.yml logs --since "${LOG_SINCE_SECONDS}s" backend 2>/dev/null) \
  || fail "docker compose logs failed - is the demo stack up?"

# 各イベントの JSON ログ行から最新の latency 値を抽出（jq 非依存）
last_int_after() {
  # $1=イベント名, $2=フィールド名 -> 最後の数値
  printf '%s' "${logs}" \
    | grep "\"message\": \"$1\"" \
    | grep -oE "\"$2\": ?[0-9]+" \
    | grep -oE "[0-9]+" | tail -1
}

stt_ms=$(last_int_after "stt_qwen_complete" "latency_ms")
llm_ms=$(printf '%s' "${logs}" | grep '"llm_latency_ms"' | grep -oE '"llm_latency_ms": ?[0-9]+' | grep -oE '[0-9]+' | tail -1)
tts_ms=$(last_int_after "tts_synthesis_complete" "latency_ms")
tts_total_ms=$(last_int_after "tts_complete" "tts_overall_duration_ms")
chat_ms=$(last_int_after "chat_response" "latency_ms")

printf '\n[demo] Per-stage latency (latest request):\n'
printf '[demo] %-28s %10s\n' "stage" "latency_ms"
printf '[demo] %-28s %10s\n' "--------------------------" "----------"
printf '[demo] %-28s %10s\n' "stt_qwen_complete" "${stt_ms:-n/a}"
printf '[demo] %-28s %10s\n' "llm (llm_latency_ms)" "${llm_ms:-n/a}"
printf '[demo] %-28s %10s\n' "chat_response (total)" "${chat_ms:-n/a}"
printf '[demo] %-28s %10s\n' "tts_synthesis_complete" "${tts_ms:-n/a}"
printf '[demo] %-28s %10s\n' "tts_overall_duration_ms" "${tts_total_ms:-n/a}"
printf '\n[demo] Tip: TTS shows two tts_synthesis_complete lines when piper fails and kokoro takes over (fallback).\n'
