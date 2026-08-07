#!/usr/bin/env bash
# S2: LLM コールドリロード（keep_alive 切れ）時の応答遅延・タイムアウト検証
#
# 背景: REPORT.md に「LLM コールドリロード（~20s）は keep_alive=1h が切れた後に発生」
#       と記載。実機で「2 問目の質問がタイムオーバー」はこのコールドリロードと
#       重なった可能性がある。
#
# 検証方法:
#   1. Ollama のモデルロード状態を確認（ollama ps）
#   2. 同一セッションで Q を 1 往復（ウォーム状態の応答時間を記録）
#   3. keep_alive を待つ（デフォルト 1h では待てないため、テスト用に
#       OLLAMA_KEEP_ALIVE を短くした backend 再起動を指示 or 環境変数で指定）
#   4. 再度 Q を実行し、コールドリロード時の応答時間・タイムアウト有無を記録
#
# 使い方:
#   通常（現在の keep_alive で簡易確認）:
#     bash scripts/demo/scenarios/keepalive-expiry.sh
#   コールドリロードを意図的に再現（推奨）:
#     docker compose -f docker-compose.yml -f docker-compose.demo.yml \
#       up -d backend   # OLLAMA_KEEP_ALIVE=1m など短い値を .env で設定して再起動
#     bash scripts/demo/scenarios/keepalive-expiry.sh
#
# 結果: docs/demo/coscup2026/evidence/scenario/keepalive-expiry/ に保存
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "${REPO_ROOT}"

BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"
SESSION_ID="${DEMO_KEEPALIVE_SESSION:-scenario-keepalive}"
EVIDENCE_DIR="${DEMO_EVIDENCE_DIR:-docs/demo/coscup2026/evidence/scenario/keepalive-expiry}"
WAIT_SECONDS="${DEMO_KEEPALIVE_WAIT_SECONDS:-45}"
mkdir -p "${EVIDENCE_DIR}"

WAV="${SCRIPT_DIR}/../audio/q1_what_can_i_do.wav"
if [ ! -f "${WAV}" ]; then
  echo "ERROR: WAV fixture not found: ${WAV}" >&2
  exit 1
fi

result_file="${EVIDENCE_DIR}/result.txt"
: > "${result_file}"

echo "[keepalive] Backend: ${BACKEND_URL}, session: ${SESSION_ID}"
echo "[keepalive] OLLAMA keep_alive 設定を確認..."
if command -v ollama >/dev/null 2>&1; then
  ollama ps | tee -a "${result_file}"
else
  echo "(ollama CLI not on PATH; skip model state check)" | tee -a "${result_file}"
fi

# 1 往復（STT -> Chat -> TTS）を実行して JSON 出力
run_turn() {
  # $1=ラベル
  python3 - "${BACKEND_URL}" "${WAV}" "$1" "${SESSION_ID}" <<'PY'
import base64, json, sys, time
import httpx

base, wav, label, sid = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
b64 = base64.b64encode(open(wav, "rb").read()).decode()

async def main():
    result = {"label": label}
    async with httpx.AsyncClient(timeout=150) as c:
        t0 = time.perf_counter()
        r = await c.post(f"{base}/api/voice", json={
            "action": "speech_to_text", "audioData": b64, "language": "en", "sessionId": sid,
        })
        body = r.json()
        transcript = body.get("transcript") or "Where is the toilet?"
        t1 = time.perf_counter()
        try:
            r = await c.post(f"{base}/api/chat", json={
                "query": transcript, "session_id": sid, "language": "en",
            })
            cbody = r.json()
            result["chat_ok"] = cbody.get("success")
            result["answer"] = cbody.get("answer")
            result["chat_error"] = cbody.get("error")
        except Exception as e:
            result["chat_ok"] = False
            result["chat_error"] = str(e)
        t2 = time.perf_counter()
        result["stt_ms"] = int((t1 - t0) * 1000)
        result["chat_ms"] = int((t2 - t1) * 1000)
        result["total_ms"] = int((t2 - t0) * 1000)
        result["transcript"] = transcript
        print(json.dumps(result, ensure_ascii=False))

import asyncio; asyncio.run(main())
PY
}

echo "[keepalive] --- Turn 1 (warm) ---"
turn1=$(run_turn "warm") || {
  echo "[keepalive] Turn 1 FAILED: ${turn1}" | tee -a "${result_file}"
  exit 1
}
echo "${turn1}" | python3 -m json.tool
echo "${turn1}" > "${EVIDENCE_DIR}/turn1.json"
chat1_ms=$(printf '%s' "${turn1}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["chat_ms"])')

echo "[keepalive] Waiting ${WAIT_SECONDS}s for keep_alive expiry (モデルがアンロードされるのを待つ)..."
sleep "${WAIT_SECONDS}"

if command -v ollama >/dev/null 2>&1; then
  echo "[keepalive] ollama ps after wait:"
  ollama ps | tee -a "${result_file}"
fi

echo "[keepalive] --- Turn 2 (after keep_alive expiry) ---"
turn2=$(run_turn "cold") || {
  echo "[keepalive] Turn 2 FAILED (timeout?)" | tee -a "${result_file}"
  echo "RESULT: FAIL" | tee -a "${result_file}"
  exit 1
}
echo "${turn2}" | python3 -m json.tool
echo "${turn2}" > "${EVIDENCE_DIR}/turn2.json"
chat2_ms=$(printf '%s' "${turn2}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["chat_ms"])')

{
  echo "=== S2 keepalive-expiry: $(date) ==="
  echo "wait_seconds=${WAIT_SECONDS}"
  echo "Turn1_chat_ms=${chat1_ms}"
  echo "Turn2_chat_ms=${chat2_ms}"
  echo "Turn2_ok=$(printf '%s' "${turn2}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["chat_ok"])')"
} | tee -a "${result_file}"

echo ""
echo "[keepalive] RESULT: recorded (cold reload latency visible in Turn2_chat_ms)"
