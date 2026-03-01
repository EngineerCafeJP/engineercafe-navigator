#!/usr/bin/env bash
# ===========================================
# Production Model Setup Script
# ===========================================
# Downloads all required models for the backend:
#   - Vosk STT models (Japanese + English, ~88 MB)
#   - Helsinki-NLP translation models (CTranslate2 int8, ~300 MB)
#
# Usage (recommended — runs inside Docker with all dependencies):
#   docker compose -f docker-compose.production.yml --profile setup run --rm model-setup
#
# Or run directly on host (requires curl, unzip, python3 with torch/transformers):
#   bash backend/scripts/setup_production_models.sh
# ===========================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="${1:-/app/models}"

echo "=== Engineer Cafe Navigator: Model Setup ==="
echo "Model directory: ${MODEL_DIR}"
echo ""

# --- 1. Vosk STT Models ---
echo "--- [1/2] Downloading Vosk STT models ---"
if [ -f "${SCRIPT_DIR}/download_vosk_models.sh" ]; then
    bash "${SCRIPT_DIR}/download_vosk_models.sh" "${MODEL_DIR}"
    echo "Vosk models: OK"
else
    echo "WARNING: download_vosk_models.sh not found at ${SCRIPT_DIR}. Skipping."
fi

echo ""

# --- 2. Translation Models ---
echo "--- [2/2] Downloading translation models ---"
TRANSLATION_DIR="${MODEL_DIR}/translation"
if [ -f "${SCRIPT_DIR}/download_translation_models.sh" ]; then
    bash "${SCRIPT_DIR}/download_translation_models.sh" "${TRANSLATION_DIR}"
    echo "Translation models: OK"
else
    echo "WARNING: download_translation_models.sh not found at ${SCRIPT_DIR}. Skipping."
fi

echo ""
echo "=== Model setup complete ==="
echo "Models are stored in: ${MODEL_DIR}"
ls -lh "${MODEL_DIR}" 2>/dev/null || true
