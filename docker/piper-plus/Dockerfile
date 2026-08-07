# piper-plus TTS アダプタ（COSCUP 2026 デモ / 本番パリティ用）
#
# - モデル (tsukuyomi-chan-6lang-fp16.onnx + config.json) はビルド時に HF から
#   取得してイメージ内に焼き込む。実行時のネットワーク取得はゼロ。
# - g2p-en が import 時に nltk データ (averaged_perceptron_tagger / cmudict) を
#   必要とするため、ビルド時に nltk_data も同梱する。
# - ARM64 (Apple Silicon) / x86_64 両対応（onnxruntime・pyopenjtalk-plus とも
#   aarch64 wheel 提供あり）。

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    NLTK_DATA=/usr/share/nltk_data \
    PIPER_MODEL_DIR=/app/models

# ビルド時のみネットワーク使用（モデル・辞書データの取得）
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ENV PIP_DEFAULT_TIMEOUT=180
RUN pip install --no-cache-dir "piper-plus[http]==1.13.0"

# nltk データ（g2p-en 用）。nltk.download() は不安定なため curl で直接配置。
# 旧名 averaged_perceptron_tagger.zip も同梱（g2p-en は find() で旧名を参照）
RUN mkdir -p /usr/share/nltk_data/taggers /usr/share/nltk_data/corpora && \
    curl -fsSL --max-time 180 --retry 5 --retry-delay 2 -o /usr/share/nltk_data/taggers/averaged_perceptron_tagger_eng.zip \
      "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/taggers/averaged_perceptron_tagger_eng.zip" && \
    cp /usr/share/nltk_data/taggers/averaged_perceptron_tagger_eng.zip \
       /usr/share/nltk_data/taggers/averaged_perceptron_tagger.zip && \
    curl -fsSL --max-time 180 --retry 5 --retry-delay 2 -o /usr/share/nltk_data/corpora/cmudict.zip \
      "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/cmudict.zip"

# 音声モデル（tsukuyomi-chan-6lang: ja/en/zh/es/fr/pt）
RUN mkdir -p /app/models && \
    curl -fsSL --max-time 180 --retry 5 --retry-delay 2 -o /app/models/tsukuyomi-chan-6lang-fp16.onnx \
      "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx" && \
    curl -fsSL --max-time 180 --retry 5 --retry-delay 2 -o /app/models/config.json \
      "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json"

WORKDIR /app
COPY server.py /app/server.py

EXPOSE 8090

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
