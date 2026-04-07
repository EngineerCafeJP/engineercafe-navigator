#!/bin/bash
# piper-plus HTTP server entrypoint
# モデルは Python SDK が起動時に HuggingFace Hub から自動ダウンロードする

set -e

echo "=== piper-plus TTS Server ==="
echo "model repo   : ${PIPER_MODEL_REPO:-ayousanz/piper-plus-tsukuyomi-chan}"
echo "model dir    : ${PIPER_MODEL_DIR:-/models/piper}"
echo "speed        : ${PIPER_SPEED:-0.65}"
echo "use_cuda     : ${PIPER_USE_CUDA:-false}"
echo ""
echo "Starting piper-plus HTTP API server on :8090 ..."

exec uvicorn server:app --host 0.0.0.0 --port 8090
