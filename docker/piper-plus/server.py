"""piper-plus HTTP API server

piper-tts-plus Python SDK を使用した高速 TTS サーバー。
tsukuyomi-chan-6lang モデル（全言語共通）で日本語・英語等を合成。
モデルは初回起動時に HuggingFace Hub から自動ダウンロード。

環境変数:
    PIPER_MODEL_REPO  : HuggingFace モデルリポジトリ ID
    PIPER_MODEL_DIR   : モデルキャッシュディレクトリ (default: /models/piper)
    PIPER_SPEED       : 話速 (default: 0.65 ≒ ゆっくり・聞き取りやすい発話)
                        1.0=標準, <1.0=遅い, >1.0=速い
    PIPER_USE_CUDA    : GPU 使用 (default: false)
"""

from __future__ import annotations

import io
import logging
import os
import threading
import unicodedata
import wave
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from huggingface_hub import snapshot_download
from piper import PiperVoice
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="piper-plus TTS API")

MODEL_REPO = os.getenv("PIPER_MODEL_REPO", "ayousanz/piper-plus-tsukuyomi-chan")
MODEL_DIR = Path(os.getenv("PIPER_MODEL_DIR", "/models/piper"))
USE_CUDA = os.getenv("PIPER_USE_CUDA", "false").lower() == "true"

# 話速デフォルト: 0.65 ≒ length_scale=1.54（ゆっくり・聞き取りやすい発話）
# 1.0=標準, <1.0=遅い, >1.0=速い
DEFAULT_SPEED = float(os.getenv("PIPER_SPEED", "0.65"))

_voice: Optional[PiperVoice] = None
_voice_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_spoken_content(text: str) -> bool:
    """文字・数字を含む場合のみ True（記号・空白のみのテキストを弾く）"""
    return any(unicodedata.category(ch)[0] in {"L", "N"} for ch in text)


def _build_silence_wav(sample_rate: int, duration_ms: int = 180) -> bytes:
    """無音 WAV を生成する"""
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * frame_count)
    return buf.getvalue()


def _build_silence_pcm(sample_rate: int, duration_ms: int = 180) -> bytes:
    """無音 PCM を生成する（ストリーミング用）"""
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    return b"\x00\x00" * frame_count


def _normalize_speed(speed: float) -> float:
    return max(0.5, min(2.0, speed))


def _length_scale_for_speed(speed: float) -> float:
    """speed → length_scale 変換 (length_scale = 1 / speed)"""
    return 1.0 / _normalize_speed(speed)


def _ensure_model_files() -> Path:
    """HuggingFace Hub からモデルをダウンロード（キャッシュ済みなら即返却）"""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Checking model from HuggingFace: %s", MODEL_REPO)
    snapshot_download(
        repo_id=MODEL_REPO,
        local_dir=MODEL_DIR,
        local_dir_use_symlinks=False,
    )
    model_paths = sorted(MODEL_DIR.rglob("*.onnx"))
    if not model_paths:
        raise RuntimeError(f"No ONNX model found in {MODEL_DIR}")
    return model_paths[0]


def _ensure_voice() -> PiperVoice:
    """PiperVoice シングルトン（スレッドセーフ遅延初期化）"""
    global _voice
    if _voice is None:
        with _voice_lock:
            if _voice is None:
                model_path = _ensure_model_files()
                logger.info("Loading Piper model: %s", model_path)
                _voice = PiperVoice.load(str(model_path), use_cuda=USE_CUDA)
                logger.info("Piper model loaded successfully")
    return _voice


def _resolve_language_id(voice: PiperVoice, language: str) -> Optional[int]:
    """tsukuyomi 多言語モデルの language_id_map から言語 ID を解決する"""
    language_map = getattr(voice.config, "language_id_map", None) or {}
    if not language_map:
        return None
    if language in language_map:
        return language_map[language]
    logger.warning("Language '%s' not in language_id_map, using default", language)
    return None


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


@app.on_event("startup")
def startup_event():
    """サーバー起動時にモデルをプリロード"""
    logger.info("Pre-loading Piper model on startup...")
    _ensure_voice()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    loaded = _voice is not None
    return {"ok": True, "model_repo": MODEL_REPO, "model_loaded": loaded}


@app.get("/info")
def info() -> dict:
    voice = _ensure_voice()
    language_map = getattr(voice.config, "language_id_map", None) or {}
    return {
        "model_repo": MODEL_REPO,
        "model_dir": str(MODEL_DIR),
        "sample_rate": voice.config.sample_rate,
        "default_speed": DEFAULT_SPEED,
        "supported_languages": list(language_map.keys()),
        "use_cuda": USE_CUDA,
    }


class SynthRequest(BaseModel):
    text: str
    language: str = "ja"
    speaker_id: Optional[int] = None
    speed: Optional[float] = None  # 1.0=標準, <1.0=遅い, >1.0=速い
    length_scale: Optional[float] = None  # 後方互換: 設定時は speed に変換
    noise_scale: Optional[float] = 0.667


@app.post("/synthesize")
def synthesize(req: SynthRequest) -> Response:
    """テキストを WAV 音声に変換して返す（POST）"""
    voice = _ensure_voice()

    if not _has_spoken_content(req.text):
        return Response(
            content=_build_silence_wav(voice.config.sample_rate),
            media_type="audio/wav",
        )

    # speed 解決: speed > length_scale（後方互換）> デフォルト
    if req.speed is not None:
        length_scale = _length_scale_for_speed(req.speed)
    elif req.length_scale is not None:
        length_scale = req.length_scale
    else:
        length_scale = _length_scale_for_speed(DEFAULT_SPEED)

    language_id = _resolve_language_id(voice, req.language)

    logger.info(
        "synthesize: lang=%s length_scale=%.3f text_len=%d",
        req.language,
        length_scale,
        len(req.text),
    )

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize(
            req.text,
            wav_file,
            speaker_id=req.speaker_id,
            length_scale=length_scale,
            noise_scale=req.noise_scale,
            language_id=language_id,
        )

    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.get("/synthesize")
def synthesize_get(
    text: str = Query(..., min_length=1),
    language: str = Query(default="ja"),
    speaker_id: Optional[int] = Query(default=None, ge=0),
    speed: float = Query(default=None),
) -> Response:
    """テキストを WAV 音声に変換して返す（GET）"""
    req = SynthRequest(text=text, language=language, speaker_id=speaker_id, speed=speed)
    return synthesize(req)


@app.post("/v1/tts/stream")
def synthesize_stream(body: dict) -> StreamingResponse:
    """テキストをストリーミング PCM で返す（低レイテンシ用）"""
    text = str(body.get("text", "")).strip()
    language = str(body.get("language", "ja")).strip() or "ja"
    speaker_id = body.get("speaker_id")
    speed = float(body.get("speed", DEFAULT_SPEED))

    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    voice = _ensure_voice()

    if not _has_spoken_content(text):
        silence = _build_silence_pcm(voice.config.sample_rate)

        def _silence():
            yield silence

        return StreamingResponse(
            _silence(),
            media_type="application/octet-stream",
            headers={"X-Sample-Rate": str(voice.config.sample_rate)},
        )

    language_id = _resolve_language_id(voice, language)
    length_scale = _length_scale_for_speed(speed)
    sid = speaker_id if isinstance(speaker_id, int) and speaker_id >= 0 else None

    def _generate():
        for chunk in voice.synthesize_stream_raw(
            text,
            speaker_id=sid,
            length_scale=length_scale,
            language_id=language_id,
        ):
            if chunk:
                yield chunk

    return StreamingResponse(
        _generate(),
        media_type="application/octet-stream",
        headers={"X-Sample-Rate": str(voice.config.sample_rate)},
    )
