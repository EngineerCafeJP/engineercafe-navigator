"""
STTAgent - Speech-to-Text エージェント

Compatibility facade for STT public imports. Implementation details live under
backend.agents.stt.* so this module remains small while preserving the existing
backend.agents.stt_agent import surface used by tests and application code.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from backend.agents.stt.common import (
    AUDIO_CONVERSION_ERROR_PREFIX,
    MAX_AUDIO_UPLOAD_BYTES,
    MIN_WAV_HEADER_BYTES,
    PYDUB_IMPORT_ERROR,
    TRUNCATED_WAV_AUDIO_ERROR,
    WAV_RIFF_HEADER,
    HedgedFallback,
    RejectedQwenPrimary,
    RejectedVoskFallback,
    TranscriptionResult,
    _MEDIA_CONTAINER_SIGNATURES as _MEDIA_CONTAINER_SIGNATURES,
    _duration_ms,
    _env_flag as _env_flag,
    _get_qwen_stt_executor as _get_qwen_stt_executor,
    _get_stt_postprocess_client,
    _get_vosk_stt_executor as _get_vosk_stt_executor,
    _is_real_openrouter_key as _is_real_openrouter_key,
    _looks_like_non_wav_media,
    _parse_qwen_stt_hedge_delay,
    _parse_qwen_stt_hedge_grace,
    _parse_qwen_stt_latency_budget,
    _parse_qwen_stt_timeout,
    _qwen_postprocess_enabled as _qwen_postprocess_enabled,
    _stt_preload_qwen_primary_enabled,
    _stt_preload_vosk_fallback_enabled,
    _wav_metadata,
    convert_audio_to_wav_bytes,
    logger,
    log_stt_event,
    log_stt_qwen_complete,
    log_stt_winner,
)
from backend.agents.stt.grammar import (
    DEFAULT_MODEL_PATHS,
    ENGINEER_CAFE_GRAMMAR,
    STAGE_GRAMMARS,
    SUPPORTED_LANGUAGES,
    VALID_STAGES,
)
from backend.agents.stt.heuristics import (
    _QWEN_SHORT_COMMANDS as _QWEN_SHORT_COMMANDS,
    _QWEN_SHORT_NOISE as _QWEN_SHORT_NOISE,
    _normalize_vosk_route_transcript as _normalize_vosk_route_transcript,
    _qwen_primary_transcript_suspicious as _qwen_primary_transcript_suspicious,
    _vosk_fallback_transcript_suspicious as _vosk_fallback_transcript_suspicious,
    _vosk_japanese_fragmented_request_suspicious as _vosk_japanese_fragmented_request_suspicious,
    _vosk_transcript_trusted_for_early_return as _vosk_transcript_trusted_for_early_return,
)
from backend.agents.stt.local_client import LocalSTTClient
from backend.agents.stt.postprocess import (
    _JAPANESE_LANGUAGE_LABELS as _JAPANESE_LANGUAGE_LABELS,
    _QWEN_BOUNDARY as _QWEN_BOUNDARY,
    _QWEN_DETERMINISTIC_CORRECTIONS as _QWEN_DETERMINISTIC_CORRECTIONS,
    _SAINO_NAME_VARIANT as _SAINO_NAME_VARIANT,
    _is_japanese_qwen_language as _is_japanese_qwen_language,
    _load_qwen_vocab as _load_qwen_vocab,
    _normalize_qwen_language_label as _normalize_qwen_language_label,
    _post_process_qwen_transcription_result as _post_process_qwen_transcription_result,
    _qwen_deterministic_post_process as _qwen_deterministic_post_process,
    _qwen_llm_post_process as _qwen_llm_post_process,
)
from backend.agents.stt.qwen_client import Qwen06BCpuSTTClient, QwenOnnxSTTClient, QwenSTTClient
from backend.agents.stt.qwen_primary import transcribe_qwen_primary


def _qwen_stt_runtime() -> str:
    return os.getenv("STT_QWEN_RUNTIME", "torch").strip().lower()


def _build_qwen_06b_cpu_client(*, default_language: str) -> Any:
    runtime = _qwen_stt_runtime()
    if runtime in ("", "torch", "pytorch"):
        return Qwen06BCpuSTTClient(default_language=default_language)
    if runtime == "onnx":
        return QwenOnnxSTTClient(default_language=default_language, model_variant="0.6b")
    raise ValueError(
        f"Unsupported STT_QWEN_RUNTIME={runtime!r}. Use 'onnx' for the experimental "
        "ONNX path, or unset it to use the PyTorch Qwen CPU path."
    )


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
                ('vosk', 'qwen', 'qwen0.6b-cpu', or 'qwen-primary').
                If None, uses ``STT_PROVIDER`` env var; if that is also unset,
                defaults to ``qwen-primary`` when ``ENVIRONMENT=production``, else
                ``qwen0.6b-cpu``.
            stt_client: Custom STT client instance.
                If None, creates default based on provider.
            use_grammar: Whether to use domain-specific grammar.
                Defaults to False.
            language_processor: LanguageProcessor for
                post-validation. If None, creates default.
            confidence_threshold: Min confidence for Vosk before
                Google fallback. Defaults to 0.4.
            fallback_client: Optional local/custom STT fallback.
        """
        self.stt_provider = stt_provider or os.getenv(
            "STT_PROVIDER",
            ("qwen-primary" if os.getenv("ENVIRONMENT") == "production" else "qwen0.6b-cpu"),
        )
        allowed_providers = {
            "vosk",
            "qwen",
            "qwen0.6b-cpu",
            "qwen-0.6b-cpu",
            "qwen-primary",
        }
        if self.stt_provider not in allowed_providers:
            allowed = ", ".join(sorted(allowed_providers))
            raise ValueError(f"Unknown STT provider: {self.stt_provider}. Allowed: {allowed}")
        self.use_grammar = use_grammar
        self.confidence_threshold = confidence_threshold
        self._vosk_fallback_client = None
        self._qwen_timeout = None
        self._qwen_hedge_delay = None
        self._qwen_hedge_grace = 0.0
        self._qwen_latency_budget = None
        if stt_client:
            self.stt_client = stt_client
        elif self.stt_provider == "vosk":
            self.stt_client = LocalSTTClient()
        elif self.stt_provider == "qwen":
            self.stt_client = QwenSTTClient(
                model_variant=os.getenv("QWEN_STT_MODEL_VARIANT", "1.7b"),
                device=os.getenv("QWEN_STT_DEVICE", "auto"),
                default_language=os.getenv("QWEN_STT_LANGUAGE", "ja"),
            )
        elif self.stt_provider in ("qwen0.6b-cpu", "qwen-0.6b-cpu"):
            self.stt_client = _build_qwen_06b_cpu_client(
                default_language=os.getenv("QWEN_STT_LANGUAGE", "ja")
            )
        elif self.stt_provider == "qwen-primary":
            self.stt_client = _build_qwen_06b_cpu_client(
                default_language=os.getenv("QWEN_STT_LANGUAGE", "ja")
            )
            self._vosk_fallback_client = LocalSTTClient()
            self._qwen_timeout = _parse_qwen_stt_timeout(os.getenv("QWEN_STT_TIMEOUT"))
            self._qwen_hedge_delay = _parse_qwen_stt_hedge_delay(
                os.getenv("QWEN_STT_HEDGE_DELAY_SECONDS"),
                hard_timeout=self._qwen_timeout,
            )
            self._qwen_hedge_grace = _parse_qwen_stt_hedge_grace(
                os.getenv("QWEN_STT_HEDGE_GRACE_SECONDS"),
                hard_timeout=self._qwen_timeout,
                hedge_delay=self._qwen_hedge_delay,
            )
            self._qwen_latency_budget = _parse_qwen_stt_latency_budget(
                os.getenv("QWEN_STT_LATENCY_BUDGET_SECONDS"),
                hard_timeout=self._qwen_timeout,
            )
            if _stt_preload_vosk_fallback_enabled():
                self._vosk_fallback_client.preload_models()
        else:
            raise ValueError(f"Unknown STT provider: {self.stt_provider}")

        # Optional custom fallback for low-confidence Vosk results. Wave 3 removes
        # the built-in Google Cloud fallback so application code stays portable.
        self.fallback_client = fallback_client

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

    async def warmup(self) -> None:
        """Warm STT models that must not load on the first user request."""
        if (
            self.stt_provider == "qwen-primary"
            and callable(getattr(self.stt_client, "preload_model", None))
            and _stt_preload_qwen_primary_enabled()
        ):
            logger.info("Preloading Qwen primary STT model before serving traffic")
            await self.stt_client.preload_model()

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
        """低信頼度の場合に設定済みの STT フォールバックを試行する。"""
        if self.fallback_client is None:
            return vosk_result

        if (
            hasattr(self.fallback_client, "is_available")
            and not self.fallback_client.is_available()
        ):
            logger.debug("STT fallback client not available, skipping fallback")
            return vosk_result

        vosk_confidence = vosk_result.get("confidence")
        if vosk_confidence is None or vosk_confidence >= self.confidence_threshold:
            return vosk_result

        logger.info(
            "Vosk confidence %.3f < threshold %s, attempting STT fallback...",
            vosk_confidence,
            self.confidence_threshold,
        )

        try:
            fallback_transcript = await self.fallback_client.transcribe(audio_data, language)
            if fallback_transcript and fallback_transcript.strip():
                logger.info("STT fallback succeeded: %s", fallback_transcript[:100])
                return {
                    "success": True,
                    "transcript": fallback_transcript,
                    "confidence": None,
                    "language": language,
                    "provider": "fallback",
                    "fallback_used": True,
                    "original_confidence": vosk_confidence,
                }
        except Exception as e:
            logger.warning("STT fallback failed: %s, using Vosk result", e)

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
            "google/gemini-3.1-flash-lite-preview",
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

    async def _prepare_qwen_primary_audio(
        self,
        audio_data: bytes,
        *,
        stt_trace_id: str,
        language: Optional[str],
    ) -> bytes:
        """Prepare shared audio once before the Qwen/Vosk hedge race."""

        prepare_started_at = time.perf_counter()
        conversion_duration_ms = 0
        conversion_attempted = False
        conversion_required = not audio_data.startswith(WAV_RIFF_HEADER)
        output_audio = audio_data
        success = True
        error_type: str | None = None

        try:
            if audio_data.startswith(WAV_RIFF_HEADER):
                if len(audio_data) < MIN_WAV_HEADER_BYTES:
                    raise ValueError(TRUNCATED_WAV_AUDIO_ERROR)
            elif _looks_like_non_wav_media(audio_data):
                conversion_attempted = True
                conversion_started_at = time.perf_counter()
                output_audio = await asyncio.to_thread(convert_audio_to_wav_bytes, audio_data)
                conversion_duration_ms = _duration_ms(conversion_started_at)
        except Exception as exc:
            success = False
            error_type = type(exc).__name__
            output_audio = audio_data
            logger.warning("qwen-primary shared audio preparation failed: %s", exc)

        log_stt_event(
            event="stt_audio_prepare_complete",
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            language=language,
            success=success,
            error_type=error_type,
            conversion_required=conversion_required,
            conversion_attempted=conversion_attempted,
            input_audio_bytes=len(audio_data),
            prepared_audio_bytes=len(output_audio),
            stt_audio_prepare_duration_ms=_duration_ms(prepare_started_at),
            stt_audio_conversion_duration_ms=conversion_duration_ms,
            **_wav_metadata(output_audio),
        )
        return output_audio

    async def _transcribe_qwen_primary(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await transcribe_qwen_primary(self, audio_data, language)

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
                - confidence (float): Recognition confidence (0.0-1.0). None for provider-specific
                  clients that do not report confidence.
                - language (str): Detected language code.
                - provider (str): STT provider used ('vosk', 'qwen', or 'qwen-primary').
                - error (str): Error message if failed. Optional.
                - fallback_used (bool): Whether custom fallback was used. Optional.
        """
        provider = self.stt_provider
        if provider == "qwen-primary":
            return await self._transcribe_qwen_primary(audio_data, language)
        grammar = self._resolve_grammar(conversation_stage)
        stt_started_at = time.perf_counter()
        audio_metadata = _wav_metadata(audio_data)
        try:
            if language is None and isinstance(self.stt_client, LocalSTTClient):
                result = await self.stt_client.transcribe_auto_detect(audio_data, grammar=grammar)
            elif language is None and isinstance(
                self.stt_client, (QwenSTTClient, QwenOnnxSTTClient)
            ):
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

            # Handle TranscriptionResult vs provider-specific string results.
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
                # #9: Low-confidence fallback when explicitly configured.
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

                if provider == "vosk":
                    log_stt_winner(
                        winner_provider=response.get("provider", "vosk"),
                        stt_winner=response.get("provider", "vosk"),
                        provider=response.get("provider", "vosk"),
                        language=response.get("language"),
                        confidence=response.get("confidence"),
                        latency_ms=_duration_ms(stt_started_at),
                        alternatives=[
                            (
                                response.get("provider", "vosk"),
                                response.get("confidence"),
                            )
                        ],
                        success=True,
                    )
                elif provider in {"qwen", "qwen0.6b-cpu", "qwen-0.6b-cpu"}:
                    log_stt_qwen_complete(
                        provider=provider,
                        language=response.get("language"),
                        audio_duration_ms=audio_metadata.get("audio_duration_ms"),
                        latency_ms=_duration_ms(stt_started_at),
                        confidence=response.get("confidence"),
                        transcript_length=len(str(response.get("transcript") or "")),
                        winner=True,
                        success=True,
                    )

                return response
            else:
                if provider in {"qwen", "qwen0.6b-cpu", "qwen-0.6b-cpu"}:
                    transcript = str(result or "")
                    log_stt_qwen_complete(
                        provider=provider,
                        language=language or "ja",
                        audio_duration_ms=audio_metadata.get("audio_duration_ms"),
                        latency_ms=_duration_ms(stt_started_at),
                        confidence=None,
                        transcript_length=len(transcript),
                        winner=True,
                        success=True,
                    )
                return {
                    "success": True,
                    "transcript": result,
                    "confidence": None,
                    "language": language or "ja",
                    "provider": provider,
                }
        except Exception as e:
            logger.error("STT failed (%s): %s", provider, e)
            if provider == "vosk":
                log_stt_winner(
                    winner_provider="none",
                    stt_winner="none",
                    provider="vosk",
                    language=language,
                    latency_ms=_duration_ms(stt_started_at),
                    success=False,
                    error_type=type(e).__name__,
                )
            elif provider in {"qwen", "qwen0.6b-cpu", "qwen-0.6b-cpu"}:
                log_stt_qwen_complete(
                    provider=provider,
                    language=language,
                    audio_duration_ms=audio_metadata.get("audio_duration_ms"),
                    latency_ms=_duration_ms(stt_started_at),
                    confidence=None,
                    transcript_length=0,
                    winner=False,
                    success=False,
                    error_type=type(e).__name__,
                )
            return {
                "success": False,
                "transcript": "",
                "confidence": 0.0,
                "language": language or getattr(self.stt_client, "default_language", "unknown"),
                "provider": provider,
                "error": str(e),
            }


__all__ = [
    "AUDIO_CONVERSION_ERROR_PREFIX",
    "DEFAULT_MODEL_PATHS",
    "ENGINEER_CAFE_GRAMMAR",
    "HedgedFallback",
    "LocalSTTClient",
    "MAX_AUDIO_UPLOAD_BYTES",
    "MIN_WAV_HEADER_BYTES",
    "PYDUB_IMPORT_ERROR",
    "Qwen06BCpuSTTClient",
    "QwenOnnxSTTClient",
    "QwenSTTClient",
    "RejectedQwenPrimary",
    "RejectedVoskFallback",
    "STAGE_GRAMMARS",
    "STTAgent",
    "SUPPORTED_LANGUAGES",
    "TRUNCATED_WAV_AUDIO_ERROR",
    "TranscriptionResult",
    "VALID_STAGES",
    "WAV_RIFF_HEADER",
    "convert_audio_to_wav_bytes",
]
