# piper-plus TTS HTTP API Server
#
# piper-tts-plus Python SDK + FastAPI による軽量 TTS サーバー。
# モデルは初回起動時に HuggingFace Hub から自動ダウンロード。
#
# Build:
#   docker build --platform linux/amd64 -t engineer-cafe-piper-plus ./docker/piper-plus/
#
# Run:
#   docker run -p 8090:8090 -v piper-models:/models engineer-cafe-piper-plus

FROM python:3.11-slim

WORKDIR /app

# piper-tts-plus のビルドに必要なシステム依存ライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cargo \
    libgomp1 \
    rustc \
    && rm -rf /var/lib/apt/lists/*

# Python 依存関係
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイル
COPY server.py .

# モデルキャッシュ用ボリューム
VOLUME ["/models"]

EXPOSE 8090

ENV PIPER_MODEL_REPO=ayousanz/piper-plus-tsukuyomi-chan \
    PIPER_MODEL_DIR=/models/piper \
    HF_HOME=/models/hf \
    PIPER_SPEED=0.65 \
    PIPER_USE_CUDA=false

RUN useradd --create-home --shell /bin/bash piper && \
    chown -R piper:piper /models
USER piper

HEALTHCHECK --interval=15s --timeout=10s --retries=5 --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/health')"

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
