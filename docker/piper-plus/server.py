"""PiperPlus (piper-plus) バックエンド互換 /synthesize アダプタ.

backend/agents/voice/clients.py の ``PiperPlusTTSClient`` が期待する
``POST /synthesize`` (JSON: {text, language, speaker_id?}) -> WAV を提供する。
モデルは ``piper-plus`` パッケージの ``PiperVoice`` で起動時にロードする
（モデルファイルは Docker build 時に同梱されるため、実行時のネットワーク取得はない）。

言語は MultilingualPhonemizer が文単位で自動判定する（ja/en/zh/es/fr/pt）。
"""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

logger = logging.getLogger("piper-plus-adapter")

MODEL_DIR = Path("/app/models")
MODEL_ONNX = MODEL_DIR / "tsukuyomi-chan-6lang-fp16.onnx"
MODEL_CONFIG = MODEL_DIR / "config.json"

VOICES = ["tsukuyomi-chan-6lang"]
LANGUAGES = ["ja", "en", "zh", "es", "fr", "pt"]

app = FastAPI(title="piper-plus adapter (backend /synthesize)", version="1.0.0")

_voice = None


class SynthRequest(BaseModel):
    text: str
    language: str | None = None
    speaker_id: int | None = None


@app.on_event("startup")
def _load_model() -> None:
    global _voice
    if not MODEL_ONNX.exists():
        raise RuntimeError(f"Model not found: {MODEL_ONNX} (build image with models baked in)")
    from piper import PiperVoice

    _voice = PiperVoice.load(str(MODEL_ONNX), str(MODEL_CONFIG))
    logger.info("PiperVoice loaded: %s (sample_rate=%s)", MODEL_ONNX.name, _voice.config.sample_rate)


@app.get("/api/voices")
def get_voices() -> dict:
    """ヘルスチェック兼 voice 一覧（compose healthcheck で使用）。"""
    return {"voices": VOICES, "languages": LANGUAGES, "model": MODEL_ONNX.name}


@app.post("/synthesize")
def synthesize(req: SynthRequest) -> Response:
    """backend PiperPlusTTSClient 互換: {text, language} -> WAV bytes."""
    if _voice is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    if len(text.encode("utf-8")) > 1 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Text too large")

    logger.info("synthesize: lang=%s text_len=%d", req.language, len(text))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        _voice.synthesize(text, wav_file)
    return Response(content=buf.getvalue(), media_type="audio/wav")
