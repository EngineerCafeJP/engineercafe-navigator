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
# Requires build-time deps: pip install torch transformers
RUN pip install --no-cache-dir torch transformers \
    && bash scripts/download_translation_models.sh models/translation \
    && pip uninstall -y torch transformers \
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

# Download Vosk STT models (~88MB) — required for Cloud Run where
# volume mounts are not available.
RUN bash scripts/download_vosk_models.sh models

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Healthcheck for production
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python scripts/healthcheck.py || exit 1

# Run with production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
