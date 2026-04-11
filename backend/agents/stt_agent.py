"""
STTAgent - Speech-to-Text エージェント

ローカルSTT（Vosk / Qwen3-ASR）をデフォルト候補に、Google Cloud STT を
フォールバックとして実装します。

仕様:
- 入力: WAV バイナリ（16kHz, 16bit, mono 推奨）
- 出力: dict {success, transcript, confidence, language, provider, error}

機能:
- 日英Voskモデル自動切換え（language=None 時に両モデル並列実行、confidence比較で選択）
- word-level confidence 取得
- ドメイン固有語彙のGrammarサポート（opt-in）

注意:
- Vosk モデルが存在しない場合は RuntimeError を投げ、ダウンロード案内を出します。
- Qwen3-ASR は qwen-asr パッケージを追加インストールした場合のみ利用できます。
- 本実装は軽量で依存を抑えています。必要なら音声のリサンプリング機能を追加できます。

"""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import json
import logging
import numpy as np
import os
import wave
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx as _stt_httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared httpx client for STT LLM post-processing (connection pooling)
# ---------------------------------------------------------------------------

_stt_postprocess_client: Optional["_stt_httpx.AsyncClient"] = None


def _get_stt_postprocess_client() -> "_stt_httpx.AsyncClient":
    global _stt_postprocess_client
    if _stt_postprocess_client is None or _stt_postprocess_client.is_closed:
        _stt_postprocess_client = _stt_httpx.AsyncClient(timeout=3.0)
    return _stt_postprocess_client


WAV_RIFF_HEADER = b"RIFF"
MIN_WAV_HEADER_BYTES = 44
MAX_AUDIO_UPLOAD_BYTES = 10 * 1024 * 1024
TRUNCATED_WAV_AUDIO_ERROR = (
    "Audio data must be in WAV format (RIFF) and include a complete WAV header "
    "(minimum 44 bytes). Received truncated data."
)
AUDIO_CONVERSION_ERROR_PREFIX = "Failed to convert WebM audio to WAV for STT transcription"
PYDUB_IMPORT_ERROR = (
    "WebM audio conversion requires pydub. Install backend dependencies with pydub included."
)


def convert_audio_to_wav_bytes(audio_data: bytes) -> bytes:
    """Convert WebM/Opus audio bytes to 16kHz/16-bit/mono WAV PCM."""
    if len(audio_data) > MAX_AUDIO_UPLOAD_BYTES:
        raise ValueError(
            f"Audio payload too large ({len(audio_data)} bytes). "
            f"Maximum: {MAX_AUDIO_UPLOAD_BYTES} bytes."
        )

    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise ValueError(PYDUB_IMPORT_ERROR) from exc

    try:
        segment = AudioSegment.from_file(io.BytesIO(audio_data), format=None)
        normalized = segment.set_frame_rate(16000).set_sample_width(2).set_channels(1)
        wav_buffer = io.BytesIO()
        normalized.export(wav_buffer, format="wav")
        wav_bytes = wav_buffer.getvalue()
    except Exception as exc:
        raise ValueError(f"{AUDIO_CONVERSION_ERROR_PREFIX}: {exc}") from exc

    if not wav_bytes.startswith(WAV_RIFF_HEADER) or len(wav_bytes) < MIN_WAV_HEADER_BYTES:
        raise ValueError(
            f"{AUDIO_CONVERSION_ERROR_PREFIX}: converted output is not a valid WAV file"
        )

    return wav_bytes


# -----------------------------------------------------------------------------
# TranscriptionResult
# -----------------------------------------------------------------------------


@dataclass
class TranscriptionResult:
    """Vosk 認識結果（confidence 付き）"""

    text: str
    confidence: Optional[float]  # 平均 word confidence (0.0-1.0)
    language: str
    word_confidences: List[Dict[str, Any]] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Domain-specific grammar for Engineer Cafe (opt-in)
# -----------------------------------------------------------------------------

ENGINEER_CAFE_GRAMMAR: Dict[str, List[str]] = {
    "ja": [
        "エンジニアカフェ",
        "エンジニアカフェラボ",
        "営業時間",
        "会議室",
        "ミーティング",
        "ミートアップ",
        "集中スペース",
        "メーカーズスペース",
        "地下",
        "赤煉瓦",
        "天神",
        "博多",
        "ハカタ",
        "福岡",
        "ワイファイ",
        "Wi-Fi",
        "イベント",
        "コワーキング",
        "コワーキングスペース",
        "予約",
        "受付",
        "料金",
        "無料",
        "駐車場",
        "駐輪場",
        "サイノ",
    ],
    "en": [
        "engineer cafe",
        "engineer cafe lab",
        "business hours",
        "meeting room",
        "focus space",
        "makers space",
        "basement",
        "red brick",
        "tenjin",
        "hakata",
        "fukuoka",
        "wifi",
        "event",
        "meetup",
        "coworking",
        "coworking space",
        "reservation",
        "reception",
        "price",
        "free",
        "parking",
        "saino",
    ],
}


# -----------------------------------------------------------------------------
# Stage-specific grammars (greeting -> service_selection -> confirmation)
# -----------------------------------------------------------------------------

STAGE_GRAMMARS: Dict[str, Dict[str, List[str]]] = {
    "greeting": {
        "ja": [
            "こんにちは",
            "おはようございます",
            "こんばんは",
            "すみません",
            "はじめまして",
            "エンジニアカフェ",
            "受付",
            "サイノ",
        ],
        "en": [
            "hello",
            "hi",
            "good morning",
            "good afternoon",
            "excuse me",
            "engineer cafe",
            "reception",
            "saino",
        ],
    },
    "service_selection": {
        "ja": [
            "会議室",
            "コワーキングスペース",
            "コワーキング",
            "集中スペース",
            "メーカーズスペース",
            "Wi-Fi",
            "ワイファイ",
            "イベント",
            "ミートアップ",
            "ミーティング",
            "予約",
            "料金",
            "営業時間",
            "駐車場",
            "駐輪場",
            "エンジニアカフェラボ",
            "サイノ",
        ],
        "en": [
            "meeting room",
            "coworking space",
            "coworking",
            "focus space",
            "makers space",
            "wifi",
            "event",
            "meetup",
            "reservation",
            "price",
            "business hours",
            "parking",
            "engineer cafe lab",
            "saino",
        ],
    },
    "confirmation": {
        "ja": [
            "はい",
            "いいえ",
            "そうです",
            "違います",
            "お願いします",
            "キャンセル",
            "ありがとう",
            "ありがとうございます",
            "了解",
            "わかりました",
        ],
        "en": [
            "yes",
            "no",
            "correct",
            "that's right",
            "cancel",
            "please",
            "thank you",
            "thanks",
            "okay",
            "understood",
        ],
    },
}

VALID_STAGES = tuple(STAGE_GRAMMARS.keys())


# -----------------------------------------------------------------------------
# Default model paths
# -----------------------------------------------------------------------------

DEFAULT_MODEL_PATHS: Dict[str, str] = {
    "ja": "models/vosk-model-ja",
    "en": "models/vosk-model-en-us",
}

SUPPORTED_LANGUAGES = ("ja", "en")


# -----------------------------------------------------------------------------
# Local Vosk STT Client
# -----------------------------------------------------------------------------


class LocalSTTClient:
    def __init__(self, model_paths: Optional[Dict[str, str]] = None):
        self.model_paths = {**DEFAULT_MODEL_PATHS, **(model_paths or {})}
        self._models: Dict[str, Any] = {}
        logger.info("LocalSTTClient initialized (models will be loaded on first use)")

    def _convert_audio_to_wav(self, audio_data: bytes) -> bytes:
        """Convert WebM/Opus audio bytes to WAV PCM for Vosk."""
        wav_bytes = convert_audio_to_wav_bytes(audio_data)
        logger.info("Converted non-WAV audio payload to 16kHz/16-bit/mono WAV for Vosk")
        return wav_bytes

    def _load_model(self, lang: str):
        if lang not in self.model_paths:
            raise ValueError(
                f"Unsupported language: {lang}. Supported: {list(self.model_paths.keys())}"
            )

        if lang in self._models:
            return self._models[lang]

        try:
            from vosk import Model
        except ImportError:
            logger.error("Vosk not installed. Install with: pip install vosk")
            raise RuntimeError("Vosk not installed. Install with: pip install vosk")

        model_path = os.path.expanduser(self.model_paths[lang])
        if not os.path.exists(model_path):
            logger.warning("Vosk model not found at %s", model_path)
            raise RuntimeError(
                f"Vosk model not found: {model_path}. "
                f"Download from https://alphacephei.com/vosk/models"
            )

        self._models[lang] = Model(model_path)
        logger.info("Loaded Vosk %s model from %s", lang, model_path)
        return self._models[lang]

    def _sync_transcribe(
        self,
        audio_data: bytes,
        language: str = "ja",
        grammar: Optional[List[str]] = None,
    ) -> TranscriptionResult:
        """Synchronous Vosk transcription (called via thread pool).

        注意: 入力は WAV (PCM) で、可能であれば 16kHz, 16bit, mono を推奨します。
        """
        import wave

        if audio_data[:4] == WAV_RIFF_HEADER:
            if len(audio_data) < MIN_WAV_HEADER_BYTES:
                raise ValueError(TRUNCATED_WAV_AUDIO_ERROR)
        else:
            audio_data = self._convert_audio_to_wav(audio_data)

        from vosk import KaldiRecognizer

        bio = io.BytesIO(audio_data)
        with wave.open(bio, "rb") as wf:
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        if sample_rate != 16000:
            logger.warning(
                "Received sample rate %dHz — Vosk expects 16000Hz. Provide 16kHz for best results.",
                sample_rate,
            )

        model = self._load_model(language)

        if grammar:
            grammar_json = json.dumps(grammar)
            rec = KaldiRecognizer(model, sample_rate, grammar_json)
        else:
            rec = KaldiRecognizer(model, sample_rate)

        rec.SetWords(True)
        rec.AcceptWaveform(frames)
        result_json = rec.FinalResult()

        try:
            result = json.loads(result_json)
        except Exception:
            logger.error("Failed to parse Vosk result: %s", result_json)
            raise RuntimeError("Failed to parse Vosk recognition result")

        text = result.get("text", "")

        # Extract word-level confidences
        word_results = result.get("result", [])
        word_confidences = [
            {"word": w.get("word", ""), "conf": w.get("conf", 0.0)} for w in word_results
        ]

        # Compute average confidence
        if word_confidences:
            avg_confidence = sum(w["conf"] for w in word_confidences) / len(word_confidences)
        else:
            avg_confidence = None

        # Fallback: assemble text from word results
        if not text and word_results:
            text = " ".join(w.get("word", "") for w in word_results).strip()

        text = (text or "").strip()
        if not text:
            logger.warning("Vosk returned empty transcript")
            raise RuntimeError("Vosk returned empty recognition result")

        logger.info("Vosk transcription success: %s", text[:100])
        return TranscriptionResult(
            text=text,
            confidence=avg_confidence,
            language=language,
            word_confidences=word_confidences,
        )

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "ja",
        grammar: Optional[List[str]] = None,
    ) -> TranscriptionResult:
        """WAVバイト列を受け取り、TranscriptionResult を返します (thread pool経由)。"""
        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return await loop.run_in_executor(
                    pool,
                    lambda: self._sync_transcribe(audio_data, language, grammar),
                )
        except ValueError as e:
            message = f"Invalid audio data for STT transcription: {e}"
            logger.warning(message)
            raise ValueError(message) from e
        except Exception as e:
            logger.exception("Vosk transcription error: %s", e)
            raise

    async def transcribe_auto_detect(
        self,
        audio_data: bytes,
        grammar: Optional[Dict[str, List[str]]] = None,
    ) -> TranscriptionResult:
        """日英両モデルで並列認識し、confidence が高い方の結果を返す。

        Args:
            audio_data: WAV bytes
            grammar: 言語別 grammar dict, e.g. {"ja": [...], "en": [...]}

        Returns:
            confidence が高い方の TranscriptionResult
        """

        async def _run_model(lang: str) -> Optional[TranscriptionResult]:
            lang_grammar = (grammar or {}).get(lang)
            try:
                return await self.transcribe(audio_data, lang, grammar=lang_grammar)
            except (RuntimeError, ValueError) as e:
                logger.debug("Auto-detect: %s model returned error: %s", lang, e)
                return None

        results = await asyncio.gather(
            _run_model("ja"),
            _run_model("en"),
        )

        valid_results = [r for r in results if r is not None]

        if not valid_results:
            raise RuntimeError(
                "Auto-detect failed: neither Japanese nor English model produced a result"
            )

        if len(valid_results) == 1:
            return valid_results[0]

        best = max(
            valid_results,
            key=lambda r: r.confidence if r.confidence is not None else 0.0,
        )
        other_langs = [r.language for r in valid_results if r is not best]
        logger.info(
            "Auto-detect: selected %s (confidence=%.3f) over %s",
            best.language,
            best.confidence if best.confidence is not None else 0.0,
            other_langs,
        )
        return best


# -----------------------------------------------------------------------------
# Google Cloud STT Client (fallback)
# -----------------------------------------------------------------------------


class GoogleSTTClient:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.credentials_source = os.getenv("GOOGLE_CLOUD_CREDENTIALS") or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        logger.info("GoogleSTTClient initialized (project=%s)", self.project_id)

    def is_available(self) -> bool:
        """Google Cloud STT の認証情報が設定されているか確認"""
        # On Cloud Run, the service account is attached via Workload Identity
        if os.getenv("ENVIRONMENT") == "production":
            return bool(self.project_id or os.getenv("GOOGLE_CLOUD_PROJECT"))
        return bool(self.credentials_source)

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
# Qwen3-ASR Client (optional local provider)
# -----------------------------------------------------------------------------


class QwenSTTClient:
    MODEL_VARIANTS: Dict[str, str] = {
        "1.7b": "Qwen/Qwen3-ASR-1.7B",
        "0.6b": "Qwen/Qwen3-ASR-0.6B",
    }

    LANGUAGE_NAMES: Dict[str, str] = {
        "ja": "Japanese",
        "en": "English",
        "zh": "Chinese",
        "ko": "Korean",
        "de": "German",
        "fr": "French",
        "es": "Spanish",
        "pt": "Portuguese",
        "it": "Italian",
        "ru": "Russian",
        "ar": "Arabic",
        "th": "Thai",
        "vi": "Vietnamese",
    }

    # Reverse map: Qwen display names → ISO 639-1 codes
    LANGUAGE_CODES: Dict[str, str] = {v.lower(): k for k, v in LANGUAGE_NAMES.items()}

    def _normalize_language_code(self, qwen_language: Optional[str]) -> Optional[str]:
        """Convert Qwen display name (e.g. 'Japanese') to ISO code ('ja')."""
        if qwen_language is None:
            return None
        lower = qwen_language.lower()
        return self.LANGUAGE_CODES.get(lower, qwen_language)

    def __init__(
        self,
        model_variant: str = "1.7b",
        device: str = "auto",
        default_language: str = "ja",
    ):
        if model_variant not in self.MODEL_VARIANTS:
            raise ValueError(
                f"Invalid Qwen model variant: {model_variant}. "
                f"Supported: {list(self.MODEL_VARIANTS.keys())}"
            )

        self.model_variant = model_variant
        self.model_name = self.MODEL_VARIANTS[model_variant]
        self.device = device
        self.default_language = default_language
        self._model: Optional[Any] = None
        logger.info(
            "QwenSTTClient initialized: model=%s, device=%s, default_language=%s",
            self.model_name,
            device,
            default_language,
        )

    def _load_model(self) -> None:
        if self._model is not None:
            return

        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise RuntimeError(
                "Qwen3-ASR requires the optional qwen-asr package. "
                "Install with: pip install qwen-asr"
            ) from exc

        resolved_device = self.device
        if resolved_device == "auto":
            resolved_device = "cuda:0" if torch.cuda.is_available() else "cpu"

        torch_dtype = torch.bfloat16 if str(resolved_device).startswith("cuda") else torch.float32
        self.device = resolved_device

        logger.info("Loading Qwen3-ASR model %s on %s", self.model_name, self.device)
        self._model = Qwen3ASRModel.from_pretrained(
            self.model_name,
            torch_dtype=torch_dtype,
            device_map=self.device,
            low_cpu_mem_usage=True,
            max_new_tokens=256,
        )

    def _sync_transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        self._load_model()

        if audio_data[:4] == WAV_RIFF_HEADER:
            if len(audio_data) < MIN_WAV_HEADER_BYTES:
                raise ValueError(TRUNCATED_WAV_AUDIO_ERROR)
        else:
            audio_data = convert_audio_to_wav_bytes(audio_data)

        lang_code = language  # preserve None for auto-detect
        qwen_language = self.LANGUAGE_NAMES.get(lang_code, lang_code) if lang_code else None

        try:
            with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                frames = wav_file.readframes(wav_file.getnframes())

            pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

            kwargs: Dict[str, Any] = {"audio": (pcm, sample_rate)}
            if qwen_language:
                kwargs["language"] = qwen_language

            results = self._model.transcribe(**kwargs)
            result = results[0] if results else None
            text = (getattr(result, "text", "") or "").strip() if result else ""
            detected_language = getattr(result, "language", None) if result else None
        except wave.Error as exc:
            raise ValueError(f"Invalid WAV audio for Qwen STT transcription: {exc}") from exc

        if not text:
            raise RuntimeError("Qwen3-ASR returned empty recognition result")

        normalized_lang = self._normalize_language_code(detected_language)
        logger.info("Qwen transcription success (%s): %s", self.model_variant, text[:100])
        return TranscriptionResult(
            text=text,
            confidence=None,
            language=normalized_lang or lang_code or self.default_language,
            word_confidences=[],
        )

    async def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(
                pool,
                lambda: self._sync_transcribe(audio_data, language),
            )


class Qwen06BCpuSTTClient(QwenSTTClient):
    """Qwen3-ASR 0.6B CPU固定の軽量クライアント。"""

    def __init__(self, default_language: str = "ja"):
        super().__init__(model_variant="0.6b", device="cpu", default_language=default_language)


# -----------------------------------------------------------------------------
# STTAgent - provider switching with auto-detection
# -----------------------------------------------------------------------------


class STTAgent:
    def __init__(
        self,
        stt_provider: Optional[str] = None,
        stt_client: Optional[Any] = None,
        use_grammar: bool = False,
        language_processor: Optional[Any] = None,
        confidence_threshold: float = 0.4,
        fallback_client: Optional[Any] = None,
    ):
        """Initialize STTAgent with provider selection and fallback.

        Args:
            stt_provider: STT provider name
                ('vosk', 'google', 'qwen', 'qwen0.6b-cpu',
                or 'qwen-primary').
                If None, uses ``STT_PROVIDER`` env var; if that is also unset,
                defaults to ``google`` when ``ENVIRONMENT=production``, else
                ``qwen0.6b-cpu``. Cloud Run でイメージ同梱の Vosk を使う場合は
                必ず ``STT_PROVIDER=vosk`` を設定すること。
            stt_client: Custom STT client instance.
                If None, creates default based on provider.
            use_grammar: Whether to use domain-specific grammar.
                Defaults to False.
            language_processor: LanguageProcessor for
                post-validation. If None, creates default.
            confidence_threshold: Min confidence for Vosk before
                Google fallback. Defaults to 0.4.
            fallback_client: Google STT client for fallback.
                If None and provider is 'vosk', creates one.
        """
        self.stt_provider = stt_provider or os.getenv(
            "STT_PROVIDER",
            "google" if os.getenv("ENVIRONMENT") == "production" else "qwen0.6b-cpu",
        )
        self.use_grammar = use_grammar
        self.confidence_threshold = confidence_threshold
        if stt_client:
            self.stt_client = stt_client
        elif self.stt_provider == "vosk":
            self.stt_client = LocalSTTClient()
        elif self.stt_provider == "google":
            self.stt_client = GoogleSTTClient()
        elif self.stt_provider == "qwen":
            self.stt_client = QwenSTTClient(
                model_variant=os.getenv("QWEN_STT_MODEL_VARIANT", "1.7b"),
                device=os.getenv("QWEN_STT_DEVICE", "auto"),
                default_language=os.getenv("QWEN_STT_LANGUAGE", "ja"),
            )
        elif self.stt_provider in ("qwen0.6b-cpu", "qwen-0.6b-cpu"):
            self.stt_client = Qwen06BCpuSTTClient(
                default_language=os.getenv("QWEN_STT_LANGUAGE", "ja"),
            )
        elif self.stt_provider == "qwen-primary":
            self.stt_client = Qwen06BCpuSTTClient(
                default_language=os.getenv("QWEN_STT_LANGUAGE", "ja"),
            )
            self._vosk_fallback_client = LocalSTTClient()
        else:
            raise ValueError(f"Unknown STT provider: {self.stt_provider}")

        # #9: Fallback client (Google STT) for low-confidence Vosk results
        if fallback_client is not None:
            self.fallback_client = fallback_client
        elif self.stt_provider == "vosk":
            self.fallback_client = GoogleSTTClient()
        else:
            self.fallback_client = None

        # #1: LanguageProcessor for post-validation of Vosk language detection
        if language_processor is not None:
            self.language_processor = language_processor
        else:
            try:
                from backend.utils.language_processor import LanguageProcessor

                self.language_processor = LanguageProcessor(default_language="ja")
            except ImportError:
                logger.warning("LanguageProcessor not available, skipping language validation")
                self.language_processor = None

    async def _validate_language(
        self,
        result: TranscriptionResult,
        audio_data: bytes,
    ) -> TranscriptionResult:
        """LanguageProcessor で Vosk の言語選択を後検証し、不一致なら再認識を試行する。"""
        if self.language_processor is None:
            return result
        if not isinstance(self.stt_client, LocalSTTClient):
            return result

        try:
            lp_result = self.language_processor.detect_language(result.text)
        except Exception as e:
            logger.debug("LanguageProcessor failed: %s", e)
            return result

        lp_lang = lp_result["detected"]
        lp_confidence = lp_result["confidence"]

        # 言語が一致、または LP の confidence が低ければそのまま返す
        if lp_lang == result.language or lp_confidence < 0.7:
            return result

        # LP が ja/en 以外を示す場合は Vosk 結果を信頼
        if lp_lang not in SUPPORTED_LANGUAGES:
            return result

        logger.info(
            "LanguageProcessor suggests '%s' (conf=%.2f) instead of Vosk '%s', re-transcribing...",
            lp_lang,
            lp_confidence,
            result.language,
        )

        try:
            grammar_list = ENGINEER_CAFE_GRAMMAR.get(lp_lang) if self.use_grammar else None
            alt_result = await self.stt_client.transcribe(audio_data, lp_lang, grammar=grammar_list)
            if alt_result.confidence is not None and (
                result.confidence is None or alt_result.confidence > result.confidence
            ):
                logger.info(
                    "Language corrected: %s -> %s (conf %s -> %s)",
                    result.language,
                    lp_lang,
                    result.confidence,
                    alt_result.confidence,
                )
                return alt_result
        except RuntimeError as e:
            logger.debug("Re-transcription with %s failed: %s", lp_lang, e)

        return result

    async def _try_fallback(
        self,
        audio_data: bytes,
        language: str,
        vosk_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """低信頼度の場合に Google STT でフォールバックを試行する。"""
        if self.fallback_client is None:
            return vosk_result

        if (
            hasattr(self.fallback_client, "is_available")
            and not self.fallback_client.is_available()
        ):
            logger.debug("Google STT credentials not configured, skipping fallback")
            return vosk_result

        vosk_confidence = vosk_result.get("confidence")
        if vosk_confidence is None or vosk_confidence >= self.confidence_threshold:
            return vosk_result

        logger.info(
            "Vosk confidence %.3f < threshold %s, attempting Google STT fallback...",
            vosk_confidence,
            self.confidence_threshold,
        )

        try:
            google_transcript = await self.fallback_client.transcribe(audio_data, language)
            if google_transcript and google_transcript.strip():
                logger.info("Google STT fallback succeeded: %s", google_transcript[:100])
                return {
                    "success": True,
                    "transcript": google_transcript,
                    "confidence": None,
                    "language": language,
                    "provider": "google-fallback",
                    "fallback_used": True,
                    "original_confidence": vosk_confidence,
                }
        except Exception as e:
            logger.warning("Google STT fallback failed: %s, using Vosk result", e)

        return vosk_result

    def _load_custom_vocabulary(self) -> List[str]:
        """JSONファイルからカスタム語彙の単語リストを同期的に読み込む。

        ファイルが存在しない場合やエラー時は空リストを返す。
        """
        try:
            from api.stt_vocabulary import _load_vocabulary_sync

            vocabulary = _load_vocabulary_sync()
            return [v["word"] for v in vocabulary]
        except Exception as e:
            logger.warning("Failed to load custom vocabulary from JSON: %s", e)
            return []

    async def _llm_post_process(
        self,
        transcript: str,
        language: str,
    ) -> str:
        """Post-process Vosk transcript with LLM for formatting.

        Uses Gemini Flash via OpenRouter for:
        - Punctuation insertion
        - Domain-specific term correction
        - Proper noun normalization

        Returns original transcript if LLM call fails or times out.
        """
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key or not transcript.strip():
            return transcript

        model = os.getenv(
            "STT_POSTPROCESS_MODEL",
            "google/gemini-2.0-flash-001",
        )

        try:
            client = _get_stt_postprocess_client()
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a speech recognition "
                                "post-processor for Engineer Cafe "
                                "(エンジニアカフェ) in Fukuoka. "
                                f"Input language: {language}. "
                                "Fix punctuation, correct proper "
                                "nouns (エンジニアカフェ, Wi-Fi, "
                                "etc.), and normalize formatting. "
                                "Return ONLY the corrected text, "
                                "nothing else."
                            ),
                        },
                        {"role": "user", "content": transcript},
                    ],
                    "max_tokens": 200,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                corrected = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                )
                # Guard: reject hallucinated/injected output
                if corrected and len(corrected) > len(transcript) * 3:
                    logger.warning(
                        "STT post-process too divergent: %d vs %d chars",
                        len(corrected),
                        len(transcript),
                    )
                    return transcript
                if corrected:
                    logger.info(
                        "STT post-process: '%s' -> '%s'",
                        transcript[:40],
                        corrected[:40],
                    )
                    return corrected
            else:
                logger.warning(
                    "STT post-process %d: %s",
                    resp.status_code,
                    resp.text[:100],
                )
        except Exception as e:
            logger.warning("STT LLM post-process failed: %s", e)

        return transcript

    async def _transcribe_qwen_primary(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Qwen primary + Vosk parallel fallback (ADR-007).

        ``asyncio.gather`` で Qwen と Vosk を同時実行し、Qwen が
        ``QWEN_STT_TIMEOUT`` 秒以内に成功すればその結果を返す。
        タイムアウトまたはエラー時は Vosk の結果にフォールバックする。
        """
        timeout = float(os.getenv("QWEN_STT_TIMEOUT", "10"))

        async def _run_qwen():
            return await asyncio.wait_for(
                self.stt_client.transcribe(audio_data, language=language),
                timeout=timeout,
            )

        async def _run_vosk():
            if language is None:
                return await self._vosk_fallback_client.transcribe_auto_detect(audio_data)
            return await self._vosk_fallback_client.transcribe(audio_data, language)

        qwen_result, vosk_result = await asyncio.gather(
            _run_qwen(), _run_vosk(), return_exceptions=True
        )

        # Qwen success
        if isinstance(qwen_result, TranscriptionResult):
            return {
                "success": True,
                "transcript": qwen_result.text,
                "confidence": qwen_result.confidence,
                "language": qwen_result.language,
                "provider": "qwen-primary",
            }

        # Qwen failed -> Vosk fallback
        logger.warning(
            "Qwen STT failed, using Vosk fallback: %s",
            qwen_result,
        )
        if isinstance(vosk_result, TranscriptionResult):
            transcript = vosk_result.text
            postprocessed = False
            if os.getenv("STT_LLM_POSTPROCESS", "false").lower() == "true":
                corrected = await self._llm_post_process(transcript, vosk_result.language)
                if corrected != transcript:
                    postprocessed = True
                    transcript = corrected
            return {
                "success": True,
                "transcript": transcript,
                "confidence": vosk_result.confidence,
                "language": vosk_result.language,
                "provider": "vosk-fallback",
                "postprocessed": postprocessed,
            }

        # Both failed
        raise RuntimeError(f"Both Qwen and Vosk STT failed: qwen={qwen_result}, vosk={vosk_result}")

    def _resolve_grammar(self, conversation_stage: Optional[str]) -> Optional[Dict[str, List[str]]]:
        """会話ステージに応じた Grammar 辞書を解決する。

        JSONファイルのカスタム語彙をベースに、ステージ固有ワードを合成する。

        優先順位:
        1. conversation_stage 指定あり → STAGE_GRAMMARS[stage] + カスタム語彙
        2. use_grammar=True → ENGINEER_CAFE_GRAMMAR + カスタム語彙
        3. それ以外 → None
        """
        custom_words = self._load_custom_vocabulary()

        def _merge(base: Dict[str, List[str]]) -> Dict[str, List[str]]:
            """ベースgrammarにカスタム語彙を重複なしでマージする。"""
            return {lang: list(dict.fromkeys(words + custom_words)) for lang, words in base.items()}

        if conversation_stage and conversation_stage in STAGE_GRAMMARS:
            return _merge(STAGE_GRAMMARS[conversation_stage])
        if conversation_stage and conversation_stage not in STAGE_GRAMMARS:
            logger.warning(
                "Unknown conversation_stage '%s', falling back to ENGINEER_CAFE_GRAMMAR",
                conversation_stage,
            )
            return _merge(ENGINEER_CAFE_GRAMMAR)
        if self.use_grammar:
            return _merge(ENGINEER_CAFE_GRAMMAR)
        return None

    async def speech_to_text(
        self,
        audio_data: bytes,
        language: Optional[str] = "ja",
        conversation_stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unified interface for speech-to-text recognition.

        Args:
            audio_data: WAV audio bytes
                (16kHz, 16bit, mono recommended).
            language: Language code
                ('ja', 'en', or None for auto-detection).
            conversation_stage: Conversation stage for grammar
                ('greeting', 'service_selection',
                'confirmation', or None).

        Returns:
            Recognition result dict with keys:
                - success (bool): Whether recognition succeeded.
                - transcript (str): Recognized text.
                - confidence (float): Recognition confidence (0.0-1.0). None for Google STT.
                - language (str): Detected language code.
                - provider (str): STT provider used ('vosk', 'google', or 'qwen').
                - error (str): Error message if failed. Optional.
                - fallback_used (bool): Whether Google fallback was used. Optional.
        """
        provider = self.stt_provider
        if provider == "qwen-primary":
            return await self._transcribe_qwen_primary(audio_data, language)
        grammar = self._resolve_grammar(conversation_stage)
        try:
            if language is None and isinstance(self.stt_client, LocalSTTClient):
                result = await self.stt_client.transcribe_auto_detect(audio_data, grammar=grammar)
            elif language is None and isinstance(self.stt_client, QwenSTTClient):
                # Qwen supports auto-detect: pass language=None
                result = await self.stt_client.transcribe(audio_data, language=None)
            else:
                lang = language or getattr(self.stt_client, "default_language", "ja")
                if isinstance(self.stt_client, LocalSTTClient):
                    grammar_list = (grammar or {}).get(lang) if grammar else None
                    result = await self.stt_client.transcribe(
                        audio_data, lang, grammar=grammar_list
                    )
                else:
                    result = await self.stt_client.transcribe(audio_data, lang)

            # Handle TranscriptionResult vs str (GoogleSTTClient returns str)
            if isinstance(result, TranscriptionResult):
                # #1: LanguageProcessor post-validation
                validated = await self._validate_language(result, audio_data)
                response = {
                    "success": True,
                    "transcript": validated.text,
                    "confidence": validated.confidence,
                    "language": validated.language,
                    "provider": provider,
                    "language_validated": validated is not result,
                }
                # #9: Low-confidence fallback to Google STT
                response = await self._try_fallback(audio_data, validated.language, response)

                # Vosk-only: LLM post-processing for accuracy
                if (
                    response.get("success")
                    and provider == "vosk"
                    and os.getenv("STT_LLM_POSTPROCESS", "false").lower() == "true"
                ):
                    original = response["transcript"]
                    response["transcript"] = await self._llm_post_process(
                        original, validated.language
                    )
                    if response["transcript"] != original:
                        response["original_transcript"] = original
                        response["postprocessed"] = True

                return response
            else:
                return {
                    "success": True,
                    "transcript": result,
                    "confidence": None,
                    "language": language or "ja",
                    "provider": provider,
                }
        except Exception as e:
            logger.error("STT failed (%s): %s", provider, e)
            return {
                "success": False,
                "transcript": "",
                "confidence": 0.0,
                "language": language or getattr(self.stt_client, "default_language", "unknown"),
                "provider": provider,
                "error": str(e),
            }
