#!/usr/bin/env bash
# COSCUP 2026 デモ用: フロントエンド・バックエンド・DB・TTS をオフライン構成で起動
#
# 明示的なサービスリストにより observability 系（otel-collector / loki /
# prometheus / grafana / alertmanager / mailhog）と voicevox を起動しない。
# backend の depends_on は docker-compose.demo.yml の `!override` で
# postgres のみに絞られているため、依存コンテナも増えない。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

COMPOSE_CMD=(docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice)
BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"
HEALTH_TIMEOUT_SECONDS="${DEMO_HEALTH_TIMEOUT_SECONDS:-120}"

echo "[demo] Starting services: frontend backend postgres kokoro-tts"
"${COMPOSE_CMD[@]}" up -d frontend backend postgres kokoro-tts

echo "[demo] Waiting for backend /health (timeout ${HEALTH_TIMEOUT_SECONDS}s)"
deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
until curl -fsS "${BACKEND_URL}/health" >/dev/null 2>&1; do
  if ((SECONDS >= deadline)); then
    echo "[demo] ERROR: backend did not become healthy within ${HEALTH_TIMEOUT_SECONDS}s" >&2
    echo "[demo] Hint: run scripts/demo/health.sh or inspect: docker compose -f docker-compose.yml -f docker-compose.demo.yml logs backend" >&2
    exit 1
  fi
  sleep 2
done

echo "[demo] DEMO READY"
echo "[demo]   Frontend : http://localhost:3000"
echo "[demo]   Backend  : ${BACKEND_URL}"
echo "[demo]   Next     : scripts/demo/warmup.sh  (STT model + TTS cache warm-up)"
