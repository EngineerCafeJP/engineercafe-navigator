# Backend Dockerfile for Engineer Cafe Navigator
# Python FastAPI + LangGraph backend

# Base image - Python 3.11
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies (curl/unzip for Vosk model download, ffmpeg for pydub audio conversion)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    unzip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Enable 'from backend.xxx' imports:
# Source lives at /app/ which has __init__.py, making it a Python package.
# Create /pypath/backend -> /app symlink so Python resolves 'backend' as a package.
RUN mkdir -p /pypath && ln -s /app /pypath/backend
ENV PYTHONPATH="/pypath"

# Create non-root user for security
RUN adduser --disabled-password --gecos "" --home /nonexistent --shell /sbin/nologin appuser

# Development stage
FROM base AS development

# Copy application code
COPY . .

# Download Vosk STT models (small versions: ~88MB total)
RUN bash scripts/download_vosk_models.sh models

# Download translation models (Helsinki-NLP/opus-mt, CTranslate2 int8: ~300MB total)
# Qwen3-ASR uses torch/transformers at runtime, so keep them installed.
RUN pip install --no-cache-dir torch transformers \
    && bash scripts/download_translation_models.sh models/translation \
    && pip cache purge

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Hot reload with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage (multi-stage build)
FROM base AS production

# Copy application code
COPY . .

# Set HuggingFace cache to writable path (avoids /nonexistent home dir issue)
ENV HF_HOME=/app/.hf_cache
ENV NUMBA_CACHE_DIR=/app/.numba_cache
RUN mkdir -p $HF_HOME
RUN mkdir -p $NUMBA_CACHE_DIR

# Download Vosk STT models (~88MB) — required for Cloud Run where
# volume mounts are not available.
RUN bash scripts/download_vosk_models.sh models

# Download Qwen3-ASR 0.6B model (~1.2GB) — primary STT provider (ADR-007)
RUN bash scripts/download_qwen_model.sh

# Download translation models for tRAG EN<->JA on Cloud Run. Without these
# assets, live alpha runs retry and fall back before answering EN queries.
# Qwen3-ASR uses torch/transformers at runtime, so keep them installed.
RUN pip install --no-cache-dir torch transformers \
    && bash scripts/download_translation_models.sh models/translation \
    && pip cache purge

# Fail Docker build before deploy if the production image loses Qwen runtime deps.
RUN python -c "import torch; from qwen_asr import Qwen3ASRModel; print('qwen runtime import ok')"

# Pre-warm numba JIT cache for librosa resample used by qwen-asr audio preprocessing.
RUN python -c "import librosa; import numpy as np; librosa.resample(np.zeros(16000, dtype=np.float32), orig_sr=16000, target_sr=8000); print('numba warm complete')" || echo 'numba warm failed (non-fatal)'

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Healthcheck for production (start-period=45s for Qwen model loading)
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python scripts/healthcheck.py || exit 1

# Run with production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
