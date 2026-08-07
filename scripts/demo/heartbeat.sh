#!/usr/bin/env bash
# COSCUP 2026 デモ用: Ollama モデル常駐ハートビート
#
# 背景: backend は Ollama の OpenAI 互換 API (/v1/chat/completions) 経由で
#       通信するため、リクエストの keep_alive パラメータは無視される
#       （実測: /v1 では UNTIL が更新されず、Ollama サーバー既定の
#       keep_alive（通常 5 分）でモデルがアンロードされる）。
#       アンロード後の次ターンはコールドリロード（~12.5s）が発生し、
#       実機検証で「2 問目がタイムオーバー」の原因となった。
#
# 対策: Ollama の native API (/api/chat) には keep_alive が効く（実測済み）ため、
#       本スクリプトで keep_alive=1h 付きの軽量リクエストを定期的に送り、
#       モデルをメモリ上に保持する。デモ中はこのスクリプトをバックグラウンドで
#       実行しておく。
#
# 使い方:
#   デモ開始前: bash scripts/demo/warmup.sh
#   デモ中:     bash scripts/demo/heartbeat.sh   （Ctrl+C までループ）
#   バックグラウンド実行: nohup bash scripts/demo/heartbeat.sh &
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
MODEL="${OLLAMA_MODEL:-qwen3.6:35b}"
KEEP_ALIVE="${OLLAMA_HEARTBEAT_KEEP_ALIVE:-1h}"
INTERVAL_SECONDS="${OLLAMA_HEARTBEAT_INTERVAL_SECONDS:-180}"

fail() {
  echo "[heartbeat] ERROR: $*" >&2
  exit 1
}

echo "[heartbeat] Ollama: ${OLLAMA_URL}, model: ${MODEL}, keep_alive: ${KEEP_ALIVE}, interval: ${INTERVAL_SECONDS}s"
echo "[heartbeat] Press Ctrl+C to stop."

# 初回にモデルが存在するか確認
if ! curl -fsS --max-time 10 "${OLLAMA_URL}/api/tags" | grep -q "\"${MODEL}\""; then
  echo "[heartbeat] WARNING: model '${MODEL}' not found in 'ollama list'. Run: ollama pull ${MODEL}"
fi

last_ok_at=""
while true; do
  started_at=$(date +%s)
  if response=$(curl -fsS --max-time 120 "${OLLAMA_URL}/api/chat" \
      -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"stream\":false,\"keep_alive\":\"${KEEP_ALIVE}\"}" 2>/dev/null); then
    echo "[heartbeat] $(date '+%H:%M:%S') keep_alive=${KEEP_ALIVE} sent (ok)"
    last_ok_at=$(date '+%H:%M:%S')
  else
    echo "[heartbeat] $(date '+%H:%M:%S') WARNING: request failed (Ollama 停止中?)" >&2
  fi

  # 次の送信までの待機（経過時間を考慮し、sleep は差分のみ）
  elapsed=$(( $(date +%s) - started_at ))
  remaining=$(( INTERVAL_SECONDS - elapsed ))
  if (( remaining > 0 )); then
    sleep "${remaining}"
  fi
done
