#!/usr/bin/env bash
# COSCUP 2026 デモ用: 起動したデモサービスを停止する
# データボリューム（postgres 等）は維持する。全削除したい場合は -v を付ける。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice down

echo "[demo] Demo services stopped (data volumes kept)."
echo "[demo] To also delete data volumes, run:"
echo "[demo]   docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile voice down -v"
