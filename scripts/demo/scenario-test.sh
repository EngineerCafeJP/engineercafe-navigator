#!/usr/bin/env bash
# COSCUP 2026 デモ検証: シナリオテストスイートのエントリポイント
#
# 既知のデモ不具合シナリオを自動化し、Docker デモスタック上で再現・検証する。
# 実機でのタイミング狙いの手動再現に依存せず、回帰テストとして固定する。
#
# シナリオ:
#   followup     S1: 同一セッションで Q1->Q2 連続。2 問目の応答時間と
#                    会話履歴継承（コンテキストが Q2 に反映されるか）を検証
#   tts-speed    S3: piper-plus の PIPER_SPEED(length_scale) が合成 WAV の
#                    長さに効いているかを検証（話速制御の機械的証明）
#   keepalive    S2: LLM コールドリロード（keep_alive 切れ）時のタイムアウト
#                    発生有無とリカバリを検証（要テスト用 override 再起動）
#
# 使い方:
#   bash scripts/demo/scenario-test.sh [all|followup|tts-speed|keepalive]
#
# 前提: scripts/demo/up.sh でデモスタックが起動済みであること。
# 各シナリオの結果は docs/demo/coscup2026/evidence/scenario/<name>/ に保存される。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

TARGET="${1:-all}"

# 実行前にヘルスチェック（backend と piper-plus が生きていること）
BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"
curl -fsS --max-time 10 "${BACKEND_URL}/health" >/dev/null 2>&1 \
  || { echo "[scenario] ERROR: backend not reachable. Run scripts/demo/up.sh first." >&2; exit 1; }
curl -fsS --max-time 10 "http://localhost:8090/api/voices" >/dev/null 2>&1 \
  || { echo "[scenario] ERROR: piper-plus not reachable." >&2; exit 1; }

run_scenario() {
  # $1=名前, $2=スクリプト
  local name="$1" script="$2"
  echo ""
  echo "=================================================="
  echo "[scenario] RUN: ${name}"
  echo "=================================================="
  bash "${script}"
}

case "${TARGET}" in
  followup)  run_scenario "followup-turn" "${SCRIPT_DIR}/scenarios/followup-turn.sh" ;;
  tts-speed) run_scenario "tts-speed"     "${SCRIPT_DIR}/scenarios/tts-speed.sh" ;;
  keepalive) run_scenario "keepalive-expiry" "${SCRIPT_DIR}/scenarios/keepalive-expiry.sh" ;;
  all)
    run_scenario "tts-speed"     "${SCRIPT_DIR}/scenarios/tts-speed.sh"
    run_scenario "followup-turn" "${SCRIPT_DIR}/scenarios/followup-turn.sh"
    run_scenario "keepalive-expiry" "${SCRIPT_DIR}/scenarios/keepalive-expiry.sh"
    ;;
  *)
    echo "Usage: bash scripts/demo/scenario-test.sh [all|followup|tts-speed|keepalive]" >&2
    exit 1
    ;;
esac

echo ""
echo "[scenario] DONE (evidence under docs/demo/coscup2026/evidence/scenario/)"
