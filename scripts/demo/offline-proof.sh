#!/usr/bin/env bash
# COSCUP 2026 デモ用: オフライン完走の証跡取得スクリプト
#
# 1. Wi-Fi を切断する（sudo 必要）
# 2. en0 の外向きパケットを tcpdump でキャプチャ（sudo 必要）
# 3. デモ 2 項目（英語 Q&A 1往復 + 割り込み）を API 経由で実行
# 4. pcap を解析して外向き通信ゼロを確認し、証跡一式を保存
# 5. Wi-Fi を復元する
#
# 使い方:  sudo を求められるため、ターミナルで直接実行する
#   bash scripts/demo/offline-proof.sh
#
# 前提: scripts/demo/up.sh で起動済み、scripts/demo/warmup.sh 済み、
#       モデル類は事前ダウンロード済み（このスクリプト実行中はネット不要）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"
WIFI_IFACE="${DEMO_WIFI_IFACE:-en0}"
EVIDENCE_DIR="${DEMO_EVIDENCE_DIR:-docs/demo/coscup2026/evidence/offline2}"
STT_WAV1="${SCRIPT_DIR}/audio/q1_what_can_i_do.wav"
STT_WAV2="${SCRIPT_DIR}/audio/q2_where_is_toilet.wav"
PCAP="${EVIDENCE_DIR}/offline-capture.pcap"
LOG="${EVIDENCE_DIR}/offline-run.log"

if [ ! -f "${STT_WAV1}" ] || [ ! -f "${STT_WAV2}" ]; then
  echo "ERROR: demo WAV fixtures not found. Generate them first:" >&2
  echo "  say -v Samantha -o scripts/demo/audio/q1_what_can_i_do.wav --data-format=LEI16@16000 \"What can I do at Engineer Cafe?\"" >&2
  echo "  say -v Samantha -o scripts/demo/audio/q2_where_is_toilet.wav --data-format=LEI16@16000 \"Where is the toilet?\"" >&2
  exit 1
fi

mkdir -p "${EVIDENCE_DIR}"
: > "${LOG}"

echo "[offline] 1/5 Checking backend is up..."
curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1 || {
  echo "ERROR: backend not reachable. Run scripts/demo/up.sh first." >&2
  exit 1
}
echo "[offline] Backend OK. Ensure Ollama models are loaded: ollama ps"

echo "[offline] 2/5 Turning OFF Wi-Fi (${WIFI_IFACE})..."
networksetup -setairportpower "${WIFI_IFACE}" off || {
  echo "ERROR: failed to disable Wi-Fi (needs admin)." >&2
  exit 1
}
echo "[offline] Wi-Fi is OFF."

cleanup() {
  echo "[offline] 5/5 Restoring Wi-Fi..."
  networksetup -setairportpower "${WIFI_IFACE}" on || true
}
trap cleanup EXIT

echo "[offline] 3/5 Capturing outbound traffic on ${WIFI_IFACE}..."
sudo tcpdump -i "${WIFI_IFACE}" -w "${PCAP}" 'not port 53' >/dev/null 2>&1 &
TCPDUMP_PID=$!
sleep 2

echo "[offline] 4/5 Running demo round trips (2 x English Q&A + 1 x interrupt)..."
{
  echo "=== demo round trip 1: What can I do at Engineer Cafe? ==="
  date
  python3 - "${BACKEND_URL}" "${STT_WAV1}" <<'PY'
import base64, json, sys, time
import httpx
base, wav = sys.argv[1], sys.argv[2]
b64 = base64.b64encode(open(wav, "rb").read()).decode()
async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        t0 = time.perf_counter()
        r = await c.post(f"{base}/api/voice", json={"action":"speech_to_text","audioData":b64,"language":"en","sessionId":"offline-1"})
        transcript = r.json().get("transcript")
        t1 = time.perf_counter()
        r = await c.post(f"{base}/api/chat", json={"query": transcript, "session_id":"offline-1", "language":"en"})
        answer = r.json().get("answer")
        t2 = time.perf_counter()
        r = await c.post(f"{base}/api/voice", json={"action":"text_to_speech","text":answer,"language":"en","sessionId":"offline-1","ttsProvider":"piper"})
        ok = r.json().get("success")
        t3 = time.perf_counter()
        print(json.dumps({"transcript": transcript, "answer": answer, "stt_ms": int((t1-t0)*1000), "llm_ms": int((t2-t1)*1000), "tts_ms": int((t3-t2)*1000), "e2e_ms": int((t3-t0)*1000), "tts_ok": ok}))
import asyncio; asyncio.run(main())
PY
  echo "=== demo round trip 2: Where is the toilet? ==="
  date
  python3 - "${BACKEND_URL}" "${STT_WAV2}" <<'PY'
import base64, json, sys, time
import httpx
base, wav = sys.argv[1], sys.argv[2]
b64 = base64.b64encode(open(wav, "rb").read()).decode()
async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        t0 = time.perf_counter()
        r = await c.post(f"{base}/api/voice", json={"action":"speech_to_text","audioData":b64,"language":"en","sessionId":"offline-2"})
        transcript = r.json().get("transcript")
        t1 = time.perf_counter()
        r = await c.post(f"{base}/api/chat", json={"query": transcript, "session_id":"offline-2", "language":"en"})
        answer = r.json().get("answer")
        t2 = time.perf_counter()
        r = await c.post(f"{base}/api/voice", json={"action":"text_to_speech","text":answer,"language":"en","sessionId":"offline-2","ttsProvider":"piper"})
        ok = r.json().get("success")
        t3 = time.perf_counter()
        print(json.dumps({"transcript": transcript, "answer": answer, "stt_ms": int((t1-t0)*1000), "llm_ms": int((t2-t1)*1000), "tts_ms": int((t3-t2)*1000), "e2e_ms": int((t3-t0)*1000), "tts_ok": ok}))
import asyncio; asyncio.run(main())
PY
  echo "=== interrupt round ==="
  date
  python3 - "${BACKEND_URL}" <<'PY'
import asyncio, json, sys
import httpx
base = sys.argv[1]
async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        sid = "offline-interrupt"
        text = "This is a long answer that keeps playing. " * 20
        task = asyncio.create_task(c.post(f"{base}/api/voice", json={"action":"text_to_speech","text":text,"language":"en","sessionId":sid,"ttsProvider":"piper"}, timeout=120))
        await asyncio.sleep(0.8)
        r = await c.post(f"{base}/api/voice", json={"action":"interrupt","sessionId":sid})
        print(json.dumps({"interrupt": r.json().get("interruptStatus")}))
        try:
            await task
        except Exception:
            pass
import asyncio; asyncio.run(main())
PY
} 2>&1 | tee -a "${LOG}"

sleep 2
sudo kill "${TCPDUMP_PID}" 2>/dev/null || true
wait "${TCPDUMP_PID}" 2>/dev/null || true

echo "[offline] pcap summary (should contain NO external IPs):"
sudo tcpdump -r "${PCAP}" 2>/dev/null | head -30 | tee -a "${LOG}"
COUNT=$(sudo tcpdump -r "${PCAP}" 2>/dev/null | wc -l | tr -d ' ')
echo "[offline] total packets captured on ${WIFI_IFACE}: ${COUNT}" | tee -a "${LOG}"
if [ "${COUNT:-0}" -gt 0 ]; then
  echo "WARNING: outbound packets captured while Wi-Fi was OFF. Inspect ${PCAP}." | tee -a "${LOG}"
fi
echo "[offline] Evidence saved to ${EVIDENCE_DIR}/"
echo "[offline] DONE (Wi-Fi restored by trap)."
