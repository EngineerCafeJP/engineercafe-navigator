# Backend Dockerfile for Engineer Cafe Navigator
# Python FastAPI + LangGraph backend

# Base image - Python 3.11
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies (curl/unzip for Vosk model download)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base AS development

# Copy application code
COPY . .

# Download Vosk STT models (small versions: ~88MB total)
RUN bash scripts/download_vosk_models.sh models

# Expose port
EXPOSE 8000

# Hot reload with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage (multi-stage build)
FROM base AS production

# Copy application code
COPY . .

# Note: In production, mount Vosk models via volume:
#   volumes:
#     - ./models:/app/models

# Expose port
EXPOSE 8000

# Run with production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
