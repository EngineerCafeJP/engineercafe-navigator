# Backend Dockerfile for Engineer Cafe Navigator
# Python FastAPI + LangGraph backend

# Base image - Python 3.11
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base AS development

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Hot reload with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage (multi-stage build)
FROM base AS production

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run with production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
