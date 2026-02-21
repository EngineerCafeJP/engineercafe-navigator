"""
STTAgent - Speech-to-Text エージェント

ローカルSTT（Vosk）をデフォルトに、Google Cloud STT をフォールバックとして実装します。

仕様:
- 入力: WAV バイナリ（16kHz, 16bit, mono 推奨）
- 出力: dict {success, transcript, confidence, provider, error}

注意:
- Vosk モデルが存在しない場合は RuntimeError を投げ、ダウンロード案内を出します。
- 本実装は軽量で依存を抑えています。必要なら音声のリサンプリング機能を追加できます。

"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from typing import Any, Dict, Optional
import concurrent.futures

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Local Vosk STT Client
# -----------------------------------------------------------------------------


class LocalSTTClient:
    DEFAULT_MODEL_PATH_JA = "models/vosk-model-ja"
    DEFAULT_MODEL_PATH_EN = "models/vosk-model-en-us"

    def __init__(
        self, model_path_ja: str = DEFAULT_MODEL_PATH_JA, model_path_en: str = DEFAULT_MODEL_PATH_EN
    ):
        self.model_path_ja = model_path_ja
        self.model_path_en = model_path_en
        self._model_ja = None
        self._model_en = None
        logger.info("LocalSTTClient initialized (models will be loaded on first use)")

    def _load_model(self, lang: str):
        try:
            from vosk import Model
        except ImportError:
            logger.error("Vosk not installed. Install with: pip install vosk")
            raise RuntimeError("Vosk not installed. Install with: pip install vosk")

        if lang == "ja":
            if self._model_ja is None:
                model_path = os.path.expanduser(self.model_path_ja)
                if not os.path.exists(model_path):
                    logger.warning(f"Vosk model not found at {model_path}")
                    raise RuntimeError(
                        f"Vosk model not found: {model_path}. Download from https://alphacephei.com/vosk/models"
                    )
                self._model_ja = Model(model_path)
                logger.info(f"Loaded Vosk Japanese model from {model_path}")
            return self._model_ja

        else:
            if self._model_en is None:
                model_path = os.path.expanduser(self.model_path_en)
                if not os.path.exists(model_path):
                    logger.warning(f"Vosk model not found at {model_path}")
                    raise RuntimeError(
                        f"Vosk model not found: {model_path}. Download from https://alphacephei.com/vosk/models"
                    )
                self._model_en = Model(model_path)
                logger.info(f"Loaded Vosk English model from {model_path}")
            return self._model_en

    def _sync_transcribe(self, audio_data: bytes, language: str = "ja") -> str:
        """Synchronous Vosk transcription (called via thread pool).

        注意: 入力は WAV (PCM) で、可能であれば 16kHz, 16bit, mono を推奨します。
        """
        import wave
        from vosk import KaldiRecognizer

        bio = io.BytesIO(audio_data)
        with wave.open(bio, "rb") as wf:
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        if sample_rate != 16000:
            logger.warning(
                f"Received sample rate {sample_rate}Hz — Vosk expects 16000Hz."
                " Provide 16kHz for best results."
            )

        model = self._load_model(language)
        rec = KaldiRecognizer(model, sample_rate)
        rec.AcceptWaveform(frames)
        result_json = rec.FinalResult()

        try:
            result = json.loads(result_json)
        except Exception:
            logger.error(f"Failed to parse Vosk result: {result_json}")
            raise RuntimeError("Failed to parse Vosk recognition result")

        text = result.get("text", "")
        if not text and isinstance(result.get("result"), list):
            parts = [p.get("word", "") for p in result.get("result", [])]
            text = " ".join([p for p in parts if p])

        text = (text or "").strip()
        if not text:
            logger.warning("Vosk returned empty transcript")
            raise RuntimeError("Vosk returned empty recognition result")

        logger.info(f"Vosk transcription success: {text[:100]}")
        return text

    async def transcribe(self, audio_data: bytes, language: str = "ja") -> str:
        """WAVバイト列を受け取り、テキストを返します (thread pool経由)。"""
        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return await loop.run_in_executor(pool, self._sync_transcribe, audio_data, language)
        except Exception as e:
            logger.exception("Vosk transcription error: %s", e)
            raise


# -----------------------------------------------------------------------------
# Google Cloud STT Client (fallback)
# -----------------------------------------------------------------------------


class GoogleSTTClient:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        self.credentials_source = os.getenv("GOOGLE_CLOUD_CREDENTIALS") or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        logger.info("GoogleSTTClient initialized (credentials must be configured for use)")

    def _sync_transcribe(self, audio_data: bytes, language: str = "ja") -> str:
        # Synchronous blocking call to Google Cloud Speech API
        from google.cloud import speech

        client = speech.SpeechClient()
        lang_code = "ja-JP" if language.startswith("ja") else "en-US"

        audio = speech.RecognitionAudio(content=audio_data)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=lang_code,
            enable_automatic_punctuation=True,
        )

        response = client.recognize(config=config, audio=audio)
        transcripts = []
        for result in response.results:
            if result.alternatives:
                transcripts.append(result.alternatives[0].transcript)

        return " ".join(transcripts).strip()

    async def transcribe(self, audio_data: bytes, language: str = "ja") -> str:
        loop = None
        try:
            import asyncio

            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return await loop.run_in_executor(pool, self._sync_transcribe, audio_data, language)
        else:
            # Fallback synchronous
            return self._sync_transcribe(audio_data, language)


# -----------------------------------------------------------------------------
# STTAgent - provider switching
# -----------------------------------------------------------------------------


class STTAgent:
    def __init__(self, stt_provider: Optional[str] = None, stt_client: Optional[Any] = None):
        self.stt_provider = stt_provider or os.getenv("STT_PROVIDER", "vosk")
        if stt_client:
            self.stt_client = stt_client
        elif self.stt_provider == "vosk":
            self.stt_client = LocalSTTClient()
        elif self.stt_provider == "google":
            self.stt_client = GoogleSTTClient()
        else:
            raise ValueError(f"Unknown STT provider: {self.stt_provider}")

    async def speech_to_text(self, audio_data: bytes, language: str = "ja") -> Dict[str, Any]:
        """Unified interface for speech-to-text

        Returns:
            {success: bool, transcript: str, confidence: Optional[float], provider: str, error: Optional[str]}
        """
        provider = self.stt_provider
        try:
            transcript = await self.stt_client.transcribe(audio_data, language)
            return {
                "success": True,
                "transcript": transcript,
                "confidence": None,
                "provider": provider,
            }
        except Exception as e:
            logger.error(f"STT failed ({provider}): {e}")
            return {
                "success": False,
                "transcript": "",
                "confidence": 0.0,
                "provider": provider,
                "error": str(e),
            }
