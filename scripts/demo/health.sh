#!/usr/bin/env bash
# COSCUP 2026 デモ用: バックエンドのヘルスチェックと音声 API の状態を確認
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

BACKEND_URL="${DEMO_BACKEND_URL:-http://localhost:8000}"

echo "[demo] GET ${BACKEND_URL}/health"
if response=$(curl -fsS --max-time 10 "${BACKEND_URL}/health"); then
  echo "[demo]   OK: $(printf '%s' "$response" | head -c 300)"
else
  echo "[demo]   ERROR: /health unreachable (is scripts/demo/up.sh done?)" >&2
  exit 1
fi

echo "[demo] GET ${BACKEND_URL}/api/voice?action=supported_languages"
if response=$(curl -fsS --max-time 10 "${BACKEND_URL}/api/voice?action=supported_languages"); then
  echo "[demo]   OK: $(printf '%s' "$response" | head -c 200)"
else
  echo "[demo]   ERROR: /api/voice unreachable" >&2
  exit 1
fi

echo "[demo] GET ${BACKEND_URL}/api/voice (action list)"
if response=$(curl -fsS --max-time 10 "${BACKEND_URL}/api/voice"); then
  echo "[demo]   OK: $(printf '%s' "$response" | head -c 300)"
else
  echo "[demo]   ERROR: /api/voice GET failed" >&2
  exit 1
fi

echo "[demo] All health checks passed."
