from __future__ import annotations

import asyncio
import importlib
import io
import time
import wave
from typing import Any, Dict, Optional

import numpy as np

from backend.agents.stt_onnx import QwenOnnxRuntime, QwenOnnxRuntimeConfig

from .common import (
    MIN_WAV_HEADER_BYTES,
    TRUNCATED_WAV_AUDIO_ERROR,
    WAV_RIFF_HEADER,
    TranscriptionResult,
    _duration_ms,
    _get_qwen_stt_executor,
    convert_audio_to_wav_bytes,
    logger,
    log_stt_event,
)
from .postprocess import _post_process_qwen_transcription_result


def _public_symbol(name: str, fallback: Any) -> Any:
    try:
        return getattr(importlib.import_module("backend.agents.stt_agent"), name)
    except Exception:
        return fallback


def _convert_audio_to_wav_bytes(audio_data: bytes) -> bytes:
    return _public_symbol("convert_audio_to_wav_bytes", convert_audio_to_wav_bytes)(audio_data)


def _qwen_executor():
    return _public_symbol("_get_qwen_stt_executor", _get_qwen_stt_executor)()


def _log_stt_event(**kwargs: Any) -> None:
    _public_symbol("log_stt_event", log_stt_event)(**kwargs)


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

    def _load_model(self, *, stt_trace_id: Optional[str] = None) -> int:
        if self._model is not None:
            return 0

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
        load_started_at = time.perf_counter()
        self._model = Qwen3ASRModel.from_pretrained(
            self.model_name,
            torch_dtype=torch_dtype,
            device_map=self.device,
            low_cpu_mem_usage=True,
            max_new_tokens=256,
        )
        load_duration_ms = _duration_ms(load_started_at)
        _log_stt_event(
            event="stt_model_load_complete",
            stt_trace_id=stt_trace_id,
            stt_model_load_duration_ms=load_duration_ms,
            provider="qwen",
            model_name=self.model_name,
            model_variant=self.model_variant,
            device=self.device,
        )
        return load_duration_ms

    def _sync_transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        *,
        stt_trace_id: Optional[str] = None,
    ) -> TranscriptionResult:
        runtime_started_at = time.perf_counter()
        model_load_duration_ms = 0
        audio_conversion_duration_ms = 0
        wav_decode_duration_ms = 0
        pcm_prepare_duration_ms = 0
        inference_duration_ms = 0
        audio_metadata: dict[str, Any] = {}
        conversion_required = not audio_data.startswith(WAV_RIFF_HEADER)

        try:
            load_duration = self._load_model(stt_trace_id=stt_trace_id)
            model_load_duration_ms = load_duration if isinstance(load_duration, int) else 0

            if audio_data[:4] == WAV_RIFF_HEADER:
                if len(audio_data) < MIN_WAV_HEADER_BYTES:
                    raise ValueError(TRUNCATED_WAV_AUDIO_ERROR)
            else:
                conversion_started_at = time.perf_counter()
                audio_data = _convert_audio_to_wav_bytes(audio_data)
                audio_conversion_duration_ms = _duration_ms(conversion_started_at)

            lang_code = language  # preserve None for auto-detect
            qwen_language = self.LANGUAGE_NAMES.get(lang_code, lang_code) if lang_code else None

            wav_decode_started_at = time.perf_counter()
            with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                frame_count = wav_file.getnframes()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                frames = wav_file.readframes(frame_count)
            wav_decode_duration_ms = _duration_ms(wav_decode_started_at)
            audio_metadata = {
                "audio_sample_rate_hz": sample_rate,
                "audio_channels": channels,
                "audio_sample_width_bytes": sample_width,
                "audio_frame_count": frame_count,
                "audio_duration_ms": (
                    int((frame_count / sample_rate) * 1000) if sample_rate else None
                ),
            }

            pcm_prepare_started_at = time.perf_counter()
            pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            pcm_prepare_duration_ms = _duration_ms(pcm_prepare_started_at)

            kwargs: Dict[str, Any] = {"audio": (pcm, sample_rate)}
            if qwen_language:
                kwargs["language"] = qwen_language

            inference_started_at = time.perf_counter()
            results = self._model.transcribe(**kwargs)
            inference_duration_ms = _duration_ms(inference_started_at)
            result = results[0] if results else None
            text = (getattr(result, "text", "") or "").strip() if result else ""
            detected_language = getattr(result, "language", None) if result else None
        except wave.Error as exc:
            _log_stt_event(
                event="stt_qwen_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                model_name=self.model_name,
                model_variant=self.model_variant,
                device=self.device,
                language=language,
                success=False,
                error_type="WaveError",
                conversion_required=conversion_required,
                stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_qwen_model_load_duration_ms=model_load_duration_ms,
                stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
                stt_qwen_model_inference_duration_ms=inference_duration_ms,
                **audio_metadata,
            )
            raise ValueError(f"Invalid WAV audio for Qwen STT transcription: {exc}") from exc
        except Exception as exc:
            _log_stt_event(
                event="stt_qwen_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                model_name=self.model_name,
                model_variant=self.model_variant,
                device=self.device,
                language=language,
                success=False,
                error_type=type(exc).__name__,
                conversion_required=conversion_required,
                stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_qwen_model_load_duration_ms=model_load_duration_ms,
                stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
                stt_qwen_model_inference_duration_ms=inference_duration_ms,
                **audio_metadata,
            )
            raise

        if not text:
            _log_stt_event(
                event="stt_qwen_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                model_name=self.model_name,
                model_variant=self.model_variant,
                device=self.device,
                language=language,
                success=False,
                error_type="EmptyRecognitionResult",
                conversion_required=conversion_required,
                stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_qwen_model_load_duration_ms=model_load_duration_ms,
                stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
                stt_qwen_model_inference_duration_ms=inference_duration_ms,
                **audio_metadata,
            )
            raise RuntimeError("Qwen3-ASR returned empty recognition result")

        normalized_lang = self._normalize_language_code(detected_language)
        logger.info("Qwen transcription success (%s): %s", self.model_variant, text[:100])
        _log_stt_event(
            event="stt_qwen_runtime_complete",
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            model_name=self.model_name,
            model_variant=self.model_variant,
            device=self.device,
            language=normalized_lang or lang_code or self.default_language,
            success=True,
            transcript_chars=len(text),
            conversion_required=conversion_required,
            stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
            stt_qwen_model_load_duration_ms=model_load_duration_ms,
            stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
            stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
            stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
            stt_qwen_model_inference_duration_ms=inference_duration_ms,
            **audio_metadata,
        )
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
        *,
        stt_trace_id: Optional[str] = None,
    ) -> TranscriptionResult:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _qwen_executor(),
            lambda: self._sync_transcribe(audio_data, language, stt_trace_id=stt_trace_id),
        )

        return await _post_process_qwen_transcription_result(result, stt_trace_id=stt_trace_id)

    async def preload_model(self) -> None:
        """Load the Qwen model in the shared executor before serving traffic."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_qwen_executor(), self._load_model)


class Qwen06BCpuSTTClient(QwenSTTClient):
    """Qwen3-ASR 0.6B CPU固定の軽量クライアント。"""

    def __init__(self, default_language: str = "ja"):
        super().__init__(model_variant="0.6b", device="cpu", default_language=default_language)


class QwenOnnxSTTClient:
    """Experimental Qwen3-ASR ONNX Runtime client.

    This is opt-in via STT_QWEN_RUNTIME=onnx and intentionally lazy-loads the
    ONNX session so normal backend imports do not require artifacts.
    """

    def __init__(
        self,
        default_language: str = "ja",
        model_variant: str = "0.6b",
        runtime: Optional[QwenOnnxRuntime] = None,
    ):
        if model_variant not in QwenSTTClient.MODEL_VARIANTS:
            raise ValueError(
                f"Invalid Qwen ONNX model variant: {model_variant}. "
                f"Supported: {list(QwenSTTClient.MODEL_VARIANTS.keys())}"
            )

        self.default_language = default_language
        self.model_variant = model_variant
        self.model_name = QwenSTTClient.MODEL_VARIANTS[model_variant]
        self.device = "onnxruntime"
        self._runtime = runtime or QwenOnnxRuntime(QwenOnnxRuntimeConfig.from_env())
        logger.info(
            "QwenOnnxSTTClient initialized: model=%s, default_language=%s",
            self.model_name,
            default_language,
        )

    def _sync_transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        *,
        stt_trace_id: Optional[str] = None,
    ) -> TranscriptionResult:
        runtime_started_at = time.perf_counter()
        audio_conversion_duration_ms = 0
        wav_decode_duration_ms = 0
        pcm_prepare_duration_ms = 0
        inference_duration_ms = 0
        audio_metadata: dict[str, Any] = {}
        conversion_required = not audio_data.startswith(WAV_RIFF_HEADER)
        lang_code = language or self.default_language

        try:
            if audio_data[:4] == WAV_RIFF_HEADER:
                if len(audio_data) < MIN_WAV_HEADER_BYTES:
                    raise ValueError(TRUNCATED_WAV_AUDIO_ERROR)
            else:
                conversion_started_at = time.perf_counter()
                audio_data = _convert_audio_to_wav_bytes(audio_data)
                audio_conversion_duration_ms = _duration_ms(conversion_started_at)

            wav_decode_started_at = time.perf_counter()
            with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                frame_count = wav_file.getnframes()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                frames = wav_file.readframes(frame_count)
            wav_decode_duration_ms = _duration_ms(wav_decode_started_at)
            audio_metadata = {
                "audio_sample_rate_hz": sample_rate,
                "audio_channels": channels,
                "audio_sample_width_bytes": sample_width,
                "audio_frame_count": frame_count,
                "audio_duration_ms": (
                    int((frame_count / sample_rate) * 1000) if sample_rate else None
                ),
            }

            if sample_width != 2:
                raise ValueError(
                    "Qwen3-ASR ONNX currently expects 16-bit PCM WAV audio; "
                    f"received sample width {sample_width} bytes."
                )

            pcm_prepare_started_at = time.perf_counter()
            pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                pcm = pcm.reshape(-1, channels).mean(axis=1)
            pcm_prepare_duration_ms = _duration_ms(pcm_prepare_started_at)

            inference_started_at = time.perf_counter()
            result = self._runtime.transcribe(pcm, sample_rate, language=language)
            inference_duration_ms = _duration_ms(inference_started_at)
        except wave.Error as exc:
            _log_stt_event(
                event="stt_qwen_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                model_name=self.model_name,
                model_variant=self.model_variant,
                language=language,
                device=self.device,
                success=False,
                error_type="WaveError",
                conversion_required=conversion_required,
                stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
                stt_qwen_model_inference_duration_ms=inference_duration_ms,
                **audio_metadata,
            )
            raise ValueError(f"Invalid WAV audio for Qwen ONNX STT transcription: {exc}") from exc
        except Exception as exc:
            _log_stt_event(
                event="stt_qwen_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                model_name=self.model_name,
                model_variant=self.model_variant,
                language=language,
                device=self.device,
                success=False,
                error_type=type(exc).__name__,
                conversion_required=conversion_required,
                stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
                stt_qwen_model_inference_duration_ms=inference_duration_ms,
                **audio_metadata,
            )
            raise

        text = result.text.strip()
        if not text:
            _log_stt_event(
                event="stt_qwen_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="qwen-primary",
                model_name=self.model_name,
                model_variant=self.model_variant,
                language=language,
                device=self.device,
                success=False,
                error_type="EmptyRecognitionResult",
                conversion_required=conversion_required,
                stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
                stt_qwen_model_inference_duration_ms=inference_duration_ms,
                **audio_metadata,
            )
            raise RuntimeError("Qwen3-ASR ONNX returned empty recognition result")

        detected_language = result.language or lang_code
        logger.info("Qwen ONNX transcription success (%s): %s", self.model_variant, text[:100])
        _log_stt_event(
            event="stt_qwen_runtime_complete",
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            model_name=self.model_name,
            model_variant=self.model_variant,
            device=self.device,
            language=detected_language,
            success=True,
            transcript_chars=len(text),
            conversion_required=conversion_required,
            stt_qwen_runtime_duration_ms=_duration_ms(runtime_started_at),
            stt_qwen_audio_conversion_duration_ms=audio_conversion_duration_ms,
            stt_qwen_wav_decode_duration_ms=wav_decode_duration_ms,
            stt_qwen_pcm_prepare_duration_ms=pcm_prepare_duration_ms,
            stt_qwen_model_inference_duration_ms=inference_duration_ms,
            **audio_metadata,
        )
        return TranscriptionResult(
            text=text,
            confidence=result.confidence,
            language=detected_language,
            word_confidences=[],
        )

    async def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        *,
        stt_trace_id: Optional[str] = None,
    ) -> TranscriptionResult:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _qwen_executor(),
            lambda: self._sync_transcribe(audio_data, language, stt_trace_id=stt_trace_id),
        )
        return await _post_process_qwen_transcription_result(result, stt_trace_id=stt_trace_id)

    async def preload_model(self) -> None:
        """Load the ONNX session in the shared executor before serving traffic."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_qwen_executor(), self._runtime.ensure_ready)
