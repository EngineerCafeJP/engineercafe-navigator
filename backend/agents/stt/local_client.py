from __future__ import annotations

import asyncio
import importlib
import io
import json
import os
import time
import wave
from typing import Any, Dict, List, Optional

import numpy as np

from .common import (
    MIN_WAV_HEADER_BYTES,
    TRUNCATED_WAV_AUDIO_ERROR,
    WAV_RIFF_HEADER,
    TranscriptionResult,
    _duration_ms,
    _get_vosk_stt_executor,
    convert_audio_to_wav_bytes,
    logger,
    log_stt_event,
)
from .grammar import DEFAULT_MODEL_PATHS, SUPPORTED_LANGUAGES


def _public_symbol(name: str, fallback: Any) -> Any:
    try:
        return getattr(importlib.import_module("backend.agents.stt_agent"), name)
    except Exception:
        return fallback


def _convert_audio_to_wav_bytes(audio_data: bytes) -> bytes:
    return _public_symbol("convert_audio_to_wav_bytes", convert_audio_to_wav_bytes)(audio_data)


def _vosk_executor():
    return _public_symbol("_get_vosk_stt_executor", _get_vosk_stt_executor)()


def _log_stt_event(**kwargs: Any) -> None:
    _public_symbol("log_stt_event", log_stt_event)(**kwargs)


class LocalSTTClient:
    def __init__(self, model_paths: Optional[Dict[str, str]] = None):
        self.model_paths = {**DEFAULT_MODEL_PATHS, **(model_paths or {})}
        self._models: Dict[str, Any] = {}
        logger.info("LocalSTTClient initialized (models will be loaded on first use)")

    def preload_models(self, languages: Optional[List[str]] = None) -> None:
        """Load configured Vosk models before the first user-facing fallback."""

        for lang in languages or list(SUPPORTED_LANGUAGES):
            try:
                self._load_model(lang)
            except Exception as exc:
                logger.warning("Vosk preload failed for %s: %s", lang, exc)

    def _convert_audio_to_wav(self, audio_data: bytes) -> bytes:
        """Convert WebM/Opus audio bytes to WAV PCM for Vosk."""
        wav_bytes = _convert_audio_to_wav_bytes(audio_data)
        logger.info("Converted non-WAV audio payload to 16kHz/16-bit/mono WAV for Vosk")
        return wav_bytes

    def _load_model(self, lang: str, *, stt_trace_id: Optional[str] = None):
        if lang not in self.model_paths:
            raise ValueError(
                f"Unsupported language: {lang}. Supported: {list(self.model_paths.keys())}"
            )

        if lang in self._models:
            return self._models[lang], 0

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

        load_started_at = time.perf_counter()
        self._models[lang] = Model(model_path)
        load_duration_ms = _duration_ms(load_started_at)
        logger.info("Loaded Vosk %s model from %s", lang, model_path)
        _log_stt_event(
            event="stt_model_load_complete",
            stt_trace_id=stt_trace_id,
            provider="vosk",
            language=lang,
            model_path=model_path,
            stt_model_load_duration_ms=load_duration_ms,
        )
        return self._models[lang], load_duration_ms

    @staticmethod
    def _resample_to_16khz(frames: bytes, orig_rate: int) -> tuple[bytes, int]:
        """Resample PCM 16-bit mono audio to 16kHz using scipy.

        Args:
            frames: Raw PCM bytes (16-bit signed integers).
            orig_rate: Original sample rate in Hz.

        Returns:
            Tuple of (resampled_frames_bytes, 16000).
        """
        assert len(frames) % 2 == 0, "Expected 16-bit aligned PCM data"

        if orig_rate == 16000:
            return frames, 16000

        from scipy.signal import resample_poly
        from math import gcd

        g = gcd(16000, orig_rate)
        up = 16000 // g
        down = orig_rate // g

        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
        resampled = resample_poly(audio, up, down)
        resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
        logger.info(
            "Resampled audio from %dHz to 16000Hz (%d -> %d samples)",
            orig_rate,
            len(audio),
            len(resampled),
        )
        return resampled.tobytes(), 16000

    def _sync_transcribe(
        self,
        audio_data: bytes,
        language: str = "ja",
        grammar: Optional[List[str]] = None,
        *,
        stt_trace_id: Optional[str] = None,
    ) -> TranscriptionResult:
        """Synchronous Vosk transcription (called via thread pool).

        注意: 入力は WAV (PCM) で、可能であれば 16kHz, 16bit, mono を推奨します。
        非16kHz音声は自動的に16kHzにリサンプルされます。
        """
        runtime_started_at = time.perf_counter()
        audio_conversion_duration_ms = 0
        wav_decode_duration_ms = 0
        downmix_duration_ms = 0
        resample_duration_ms = 0
        model_load_duration_ms = 0
        recognition_duration_ms = 0
        audio_metadata: dict[str, Any] = {}
        conversion_required = not audio_data.startswith(WAV_RIFF_HEADER)

        try:
            if audio_data[:4] == WAV_RIFF_HEADER:
                if len(audio_data) < MIN_WAV_HEADER_BYTES:
                    raise ValueError(TRUNCATED_WAV_AUDIO_ERROR)
            else:
                conversion_started_at = time.perf_counter()
                audio_data = self._convert_audio_to_wav(audio_data)
                audio_conversion_duration_ms = _duration_ms(conversion_started_at)

            from vosk import KaldiRecognizer

            wav_decode_started_at = time.perf_counter()
            bio = io.BytesIO(audio_data)
            with wave.open(bio, "rb") as wf:
                sample_rate = wf.getframerate()
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                frame_count = wf.getnframes()
                frames = wf.readframes(frame_count)
            wav_decode_duration_ms = _duration_ms(wav_decode_started_at)
            audio_metadata = {
                "audio_sample_rate_hz": sample_rate,
                "audio_channels": nchannels,
                "audio_sample_width_bytes": sampwidth,
                "audio_frame_count": frame_count,
                "audio_duration_ms": (
                    int((frame_count / sample_rate) * 1000) if sample_rate else None
                ),
            }

            if sampwidth != 2:
                raise ValueError(
                    f"Unsupported sample width: {sampwidth} bytes (only 16-bit PCM supported)"
                )

            if nchannels > 1:
                downmix_started_at = time.perf_counter()
                audio_np = np.frombuffer(frames, dtype=np.int16).reshape(-1, nchannels)
                frames = audio_np.mean(axis=1).astype(np.int16).tobytes()
                downmix_duration_ms = _duration_ms(downmix_started_at)
                logger.info("Downmixed %d-channel audio to mono", nchannels)

            if sample_rate != 16000:
                logger.info(
                    "Received sample rate %dHz — resampling to 16000Hz for Vosk.",
                    sample_rate,
                )
                resample_started_at = time.perf_counter()
                frames, sample_rate = self._resample_to_16khz(frames, sample_rate)
                resample_duration_ms = _duration_ms(resample_started_at)

            load_result = self._load_model(
                language,
                stt_trace_id=stt_trace_id,
            )
            if isinstance(load_result, tuple) and len(load_result) == 2:
                model, model_load_duration_ms = load_result
            else:
                model = load_result
                model_load_duration_ms = 0

            if grammar:
                grammar_json = json.dumps(grammar)
                rec = KaldiRecognizer(model, sample_rate, grammar_json)
            else:
                rec = KaldiRecognizer(model, sample_rate)

            recognition_started_at = time.perf_counter()
            rec.SetWords(True)
            rec.AcceptWaveform(frames)
            result_json = rec.FinalResult()
            recognition_duration_ms = _duration_ms(recognition_started_at)

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
            _log_stt_event(
                event="stt_vosk_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="vosk-fallback",
                language=language,
                success=True,
                conversion_required=conversion_required,
                stt_vosk_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_vosk_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_vosk_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_vosk_downmix_duration_ms=downmix_duration_ms,
                stt_vosk_resample_duration_ms=resample_duration_ms,
                stt_vosk_model_load_duration_ms=model_load_duration_ms,
                stt_vosk_recognition_duration_ms=recognition_duration_ms,
                transcript_chars=len(text),
                confidence=avg_confidence,
                grammar_enabled=bool(grammar),
                **audio_metadata,
            )
            return TranscriptionResult(
                text=text,
                confidence=avg_confidence,
                language=language,
                word_confidences=word_confidences,
            )
        except Exception as exc:
            _log_stt_event(
                event="stt_vosk_runtime_complete",
                stt_trace_id=stt_trace_id,
                provider="vosk-fallback",
                language=language,
                success=False,
                error_type=type(exc).__name__,
                conversion_required=conversion_required,
                stt_vosk_runtime_duration_ms=_duration_ms(runtime_started_at),
                stt_vosk_audio_conversion_duration_ms=audio_conversion_duration_ms,
                stt_vosk_wav_decode_duration_ms=wav_decode_duration_ms,
                stt_vosk_downmix_duration_ms=downmix_duration_ms,
                stt_vosk_resample_duration_ms=resample_duration_ms,
                stt_vosk_model_load_duration_ms=model_load_duration_ms,
                stt_vosk_recognition_duration_ms=recognition_duration_ms,
                grammar_enabled=bool(grammar),
                **audio_metadata,
            )
            raise

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "ja",
        grammar: Optional[List[str]] = None,
        *,
        stt_trace_id: Optional[str] = None,
    ) -> TranscriptionResult:
        """WAVバイト列を受け取り、TranscriptionResult を返します (thread pool経由)。"""
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                _vosk_executor(),
                lambda: self._sync_transcribe(
                    audio_data,
                    language,
                    grammar,
                    stt_trace_id=stt_trace_id,
                ),
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
        *,
        stt_trace_id: Optional[str] = None,
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
                return await self.transcribe(
                    audio_data,
                    lang,
                    grammar=lang_grammar,
                    stt_trace_id=stt_trace_id,
                )
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
