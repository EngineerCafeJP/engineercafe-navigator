"""PiperPlus (piper-plus) バックエンド互換 /synthesize アダプタ.

backend/agents/voice/clients.py の ``PiperPlusTTSClient`` が期待する
``POST /synthesize`` (JSON: {text, language, speaker_id?}) -> WAV を提供する。
モデルは ``piper-plus`` パッケージの ``PiperVoice`` で起動時にロードする
（モデルファイルは Docker build 時に同梱されるため、実行時のネットワーク取得はない）。

言語は MultilingualPhonemizer が文単位で自動判定する（ja/en/zh/es/fr/pt）。

話速: 環境変数 ``PIPER_SPEED``（速度倍率、1.0=標準・小さいほど遅い）を
Piper の ``length_scale``（= 1 / PIPER_SPEED）に変換して合成に渡す。
リクエストに ``speed`` フィールドがあれば環境変数より優先する。
"""

from __future__ import annotations

import io
import logging
import os
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
    speed: float | None = None


def _default_speed() -> float:
    """PIPER_SPEED 環境変数（速度倍率、1.0=標準・小さいほど遅い）。未設定は 1.0。"""
    raw = os.getenv("PIPER_SPEED", "").strip()
    if not raw:
        return 1.0
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid PIPER_SPEED=%r; using 1.0", raw)
        return 1.0
    if value <= 0:
        logger.warning("PIPER_SPEED=%r must be > 0; using 1.0", raw)
        return 1.0
    return value


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
    """backend PiperPlusTTSClient 互換: {text, language, speed?} -> WAV bytes."""
    if _voice is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    if len(text.encode("utf-8")) > 1 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Text too large")

    # 話速: リクエストの speed を優先、無ければ PIPER_SPEED env、無ければ 1.0
    speed = req.speed if req.speed is not None else _default_speed()
    if speed <= 0:
        speed = 1.0
    # Piper は length_scale（長さ倍率、1.0=標準・大きいほど遅い）で話速を制御する
    length_scale = 1.0 / speed

    logger.info("synthesize: lang=%s text_len=%d speed=%s length_scale=%.3f",
                req.language, len(text), speed, length_scale)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        _voice.synthesize(text, wav_file, length_scale=length_scale)
    return Response(content=buf.getvalue(), media_type="audio/wav")
