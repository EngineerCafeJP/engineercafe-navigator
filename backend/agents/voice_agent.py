"""Compatibility facade for voice/TTS public imports."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Any, Awaitable, Dict, Optional

import httpx as httpx
from cachetools import TTLCache

from backend.observability.structured_logger import (
    log_tts_cache_event,
    log_tts_event,
    log_tts_synthesis_complete,
    log_tts_synthesis_error,
    log_tts_synthesis_start,
)
from backend.utils.clarification_templates import ClarificationCategory
from backend.utils.language_processor import LanguageProcessor
from backend.agents.voice.clients import KokoroTTSClient, PiperPlusTTSClient, VoiceVoxClient
from backend.agents.voice.emotion import (
    EMOTION_TAG_REGEX as EMOTION_TAG_REGEX,
    EmotionTag as EmotionTag,
    ParsedResponse as ParsedResponse,
    VRM_EMOTION_MAP as VRM_EMOTION_MAP,
    is_supported_emotion_alias as is_supported_emotion_alias,
    map_to_vrm_emotion,
    map_vrm_to_tts_emotion as map_vrm_to_tts_emotion,
    parse_emotion_tags,
)
from backend.agents.voice.text import (
    DEFAULT_PIPER_FAILURE_COOLDOWN_SECONDS as DEFAULT_PIPER_FAILURE_COOLDOWN_SECONDS,
    DEFAULT_PIPER_PLUS_MAX_ATTEMPTS as DEFAULT_PIPER_PLUS_MAX_ATTEMPTS,
    DEFAULT_PIPER_PLUS_RETRY_BACKOFF_SECONDS as DEFAULT_PIPER_PLUS_RETRY_BACKOFF_SECONDS,
    DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES as DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES,
    DEFAULT_TTS_CACHE_MAX_ENTRIES,
    DEFAULT_TTS_MAX_BYTES as DEFAULT_TTS_MAX_BYTES,
    MIN_CACHEABLE_TTS_AUDIO_BASE64_CHARS,
    _DEFAULT_TTS_TIMEOUTS as _DEFAULT_TTS_TIMEOUTS,
    clean_text_for_tts,
    fallback_error_message as fallback_error_message,
    get_piper_plus_max_attempts as get_piper_plus_max_attempts,
    get_piper_plus_retry_backoff_seconds as get_piper_plus_retry_backoff_seconds,
    get_tts_cache_max_audio_bytes,
    get_tts_max_bytes,
    get_tts_provider_failure_cooldown_seconds,
    get_tts_timeout_seconds,
    preprocess_tts,
    truncate_by_bytes,
    tts_require_primary_provider,
)

logger = logging.getLogger(__name__)


class VoiceAgent:
    def __init__(
        self,
        tts_provider: str = "voicevox",
        tts_client: Optional[Any] = None,
        language_processor: Optional[LanguageProcessor] = None,
        clarification_agent: Optional[Any] = None,
    ):
        """Initialize VoiceAgent with TTS provider switching.

        Args:
            tts_provider: TTS provider name. Defaults to 'voicevox'.
            tts_client: Custom TTS client instance.
                If None, creates default client based on provider.
            language_processor: LanguageProcessor for language
                detection. If None, creates default instance.
            clarification_agent: Deprecated. Clarification is handled by the
                chat workflow; TTS speaks the supplied text without rewriting it.
        """
        self.tts_provider = tts_provider
        self.require_primary_tts_provider = tts_require_primary_provider()

        if tts_client:
            self.tts_client = tts_client
        elif tts_provider == "voicevox":
            voicevox_api_url = os.getenv("VOICEVOX_API_URL", "http://localhost:50021")
            self.tts_client = VoiceVoxClient(api_url=voicevox_api_url)
            logger.info("Using VoiceVox TTS: %s", voicevox_api_url)
        elif tts_provider == "piper":
            piper_api_url = os.getenv("PIPER_PLUS_API_URL", "http://localhost:8090")
            self.tts_client = PiperPlusTTSClient(api_url=piper_api_url)
            logger.info("Using PiperPlus TTS: %s", piper_api_url)
        elif tts_provider == "kokoro":
            kokoro_api_url = os.getenv("KOKORO_API_URL", "http://localhost:8880")
            self.tts_client = KokoroTTSClient(api_url=kokoro_api_url)
            logger.info("Using Kokoro TTS: %s", kokoro_api_url)
        else:
            raise ValueError(f"Unknown TTS provider: {tts_provider}")

        self.language_processor = language_processor or LanguageProcessor(default_language="ja")
        logger.info("LanguageProcessor initialized for voice_agent")

        self.clarification_agent = clarification_agent

        # Kokoro TTSクライアント（英語TTS用 / piper障害時の英語フォールバック）
        # Cloud Run環境でKOKORO_API_URL未設定の場合は初期化しない
        kokoro_api_url = (
            os.getenv("KOKORO_API_URL")
            if not (self.require_primary_tts_provider and tts_provider == "piper")
            else None
        )
        if kokoro_api_url:
            self.kokoro_client = KokoroTTSClient(api_url=kokoro_api_url)
            logger.info("Kokoro TTS client initialized: %s", kokoro_api_url)
        else:
            self.kokoro_client = None
            logger.info("Kokoro TTS client not configured (KOKORO_API_URL not set)")

        # piper障害時の日本語フォールバック用 VoiceVox クライアント
        if tts_provider == "piper" and not self.require_primary_tts_provider:
            voicevox_fallback_url = os.getenv("VOICEVOX_API_URL")
            if voicevox_fallback_url or not os.getenv("K_SERVICE"):
                voicevox_fallback_url = voicevox_fallback_url or "http://localhost:50021"
                self.voicevox_fallback_client = VoiceVoxClient(api_url=voicevox_fallback_url)
                logger.info(
                    "VoiceVox fallback client initialized for piper: %s",
                    voicevox_fallback_url,
                )
            else:
                self.voicevox_fallback_client = None
                logger.info(
                    "VoiceVox fallback client disabled for piper "
                    "(Cloud Run without VOICEVOX_API_URL)"
                )
        else:
            self.voicevox_fallback_client = None

        self._tts_cache_max_audio_bytes = get_tts_cache_max_audio_bytes()
        self._tts_cache: TTLCache = TTLCache(maxsize=DEFAULT_TTS_CACHE_MAX_ENTRIES, ttl=3600)
        self._tts_provider_cooldown_until: dict[str, float] = {}

    async def close(self) -> None:
        """Close reusable TTS clients owned by this agent."""
        clients = [
            getattr(self, "tts_client", None),
            getattr(self, "kokoro_client", None),
            getattr(self, "voicevox_fallback_client", None),
        ]
        seen: set[int] = set()
        for client in clients:
            if client is None:
                continue
            client_id = id(client)
            if client_id in seen:
                continue
            seen.add(client_id)
            close = getattr(client, "close", None)
            if callable(close):
                result = close()
                if asyncio.iscoroutine(result):
                    await result
                continue
            aclose = getattr(client, "aclose", None)
            if callable(aclose):
                result = aclose()
                if asyncio.iscoroutine(result):
                    await result

    async def aclose(self) -> None:
        await self.close()

    @staticmethod
    def _tts_cache_key(text: str, language: str, provider: str, emotion: str,
                       speed: Optional[float] = None) -> str:
        raw = f"{text}|{language}|{provider}|{emotion or 'neutral'}|speed={speed or 'default'}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _ensure_tts_cache(self) -> TTLCache:
        cache_store = getattr(self, "_tts_cache", None)
        if cache_store is None:
            cache_store = TTLCache(maxsize=DEFAULT_TTS_CACHE_MAX_ENTRIES, ttl=3600)
            self._tts_cache = cache_store
        return cache_store

    @staticmethod
    def _is_cacheable_audio(audio_b64: Any) -> bool:
        return isinstance(audio_b64, str) and len(audio_b64) > MIN_CACHEABLE_TTS_AUDIO_BASE64_CHARS

    @staticmethod
    def _cached_audio_from_entry(cache_entry: Any) -> Optional[str]:
        if isinstance(cache_entry, str):
            return cache_entry
        if isinstance(cache_entry, dict):
            audio = cache_entry.get("audioResponse")
            return audio if isinstance(audio, str) else None
        return None

    @classmethod
    def _tts_cache_entry_audio_bytes(cls, cache_entry: Any) -> int:
        audio = cls._cached_audio_from_entry(cache_entry)
        if not isinstance(audio, str):
            return 0
        return len(audio.encode("utf-8"))

    @classmethod
    def _tts_cache_audio_bytes(cls, cache_store: TTLCache) -> int:
        return sum(cls._tts_cache_entry_audio_bytes(entry) for entry in cache_store.values())

    def _tts_cache_byte_budget(self) -> int:
        budget = getattr(self, "_tts_cache_max_audio_bytes", None)
        if isinstance(budget, int) and budget > 0:
            return budget
        budget = get_tts_cache_max_audio_bytes()
        self._tts_cache_max_audio_bytes = budget
        return budget

    def _evict_tts_cache_over_byte_budget(self, cache_store: TTLCache) -> None:
        expire = getattr(cache_store, "expire", None)
        if callable(expire):
            expire()

        budget = self._tts_cache_byte_budget()
        current_bytes = self._tts_cache_audio_bytes(cache_store)
        while current_bytes > budget and cache_store:
            key = next(iter(cache_store))
            evicted_entry = cache_store.pop(key, None)
            current_bytes -= self._tts_cache_entry_audio_bytes(evicted_entry)

    def _store_tts_cache_entry(
        self, cache_store: TTLCache, cache_key: str, entry: dict[str, Any]
    ) -> None:
        cache_store[cache_key] = entry
        self._evict_tts_cache_over_byte_budget(cache_store)

    def _tts_provider_cooldowns(self) -> dict[str, float]:
        cooldowns = getattr(self, "_tts_provider_cooldown_until", None)
        if cooldowns is None:
            cooldowns = {}
            self._tts_provider_cooldown_until = cooldowns
        return cooldowns

    def _tts_provider_cooldown_remaining(self, provider: str) -> float:
        until = self._tts_provider_cooldowns().get(provider, 0.0)
        return max(0.0, until - time.monotonic())

    def _clear_tts_provider_failure(self, provider: str) -> None:
        self._tts_provider_cooldowns().pop(provider, None)

    def _mark_tts_provider_failure(self, provider: str, error: Exception) -> None:
        cooldown_s = get_tts_provider_failure_cooldown_seconds(provider)
        if cooldown_s <= 0:
            return
        self._tts_provider_cooldowns()[provider] = time.monotonic() + cooldown_s
        log_tts_event(
            event="tts_provider_failure_cooldown",
            provider=provider,
            cooldown_seconds=cooldown_s,
            error_type=type(error).__name__,
        )

    @staticmethod
    def _require_audio_response(audio_b64: Any, provider: str) -> str:
        if isinstance(audio_b64, str) and audio_b64.strip():
            return audio_b64
        raise RuntimeError(f"{provider} TTS returned empty audio response")

    def _tts_audio_format(self, language: str) -> str:
        if self.tts_provider == "piper" or language == "en" or self.tts_provider == "voicevox":
            return "audio/wav"
        return "audio/mpeg"

    async def _await_tts_attempt(
        self,
        awaitable: Awaitable[str],
        *,
        provider: str,
        role: str,
        language: str,
        text_length: int,
    ) -> str:
        timeout_s = get_tts_timeout_seconds(provider, role)
        attempt_started_at = time.perf_counter()
        fallback_used = role == "fallback"
        log_tts_synthesis_start(
            provider=provider,
            language=language,
            text_length=text_length,
            fallback_used=fallback_used,
            fallback_provider=provider if fallback_used else None,
            role=role,
        )
        try:
            audio_b64 = await asyncio.wait_for(awaitable, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            error = RuntimeError(f"{provider} TTS {role} timed out after {timeout_s:.2f}s")
            log_tts_synthesis_error(
                provider=provider,
                language=language,
                text_length=text_length,
                latency_ms=int((time.perf_counter() - attempt_started_at) * 1000),
                fallback_used=fallback_used,
                fallback_provider=provider if fallback_used else None,
                error_type=type(exc).__name__,
                role=role,
            )
            raise error from exc
        except Exception as exc:
            log_tts_synthesis_error(
                provider=provider,
                language=language,
                text_length=text_length,
                latency_ms=int((time.perf_counter() - attempt_started_at) * 1000),
                fallback_used=fallback_used,
                fallback_provider=provider if fallback_used else None,
                error_type=type(exc).__name__,
                role=role,
            )
            raise

        if not isinstance(audio_b64, str) or not audio_b64.strip():
            error = RuntimeError(f"{provider} TTS returned empty audio response")
            log_tts_synthesis_error(
                provider=provider,
                language=language,
                text_length=text_length,
                latency_ms=int((time.perf_counter() - attempt_started_at) * 1000),
                fallback_used=fallback_used,
                fallback_provider=provider if fallback_used else None,
                error_type=type(error).__name__,
                role=role,
            )
            raise error

        log_tts_synthesis_complete(
            provider=provider,
            language=language,
            text_length=text_length,
            latency_ms=int((time.perf_counter() - attempt_started_at) * 1000),
            fallback_used=fallback_used,
            fallback_provider=provider if fallback_used else None,
            role=role,
        )
        return audio_b64

    def _requires_primary_tts_provider(self) -> bool:
        return bool(getattr(self, "require_primary_tts_provider", tts_require_primary_provider()))

    def _detect_category(self, text: str, language: str) -> Optional[ClarificationCategory]:
        """
        テキストから曖昧性カテゴリを検出
        """
        text_lower = text.lower()

        # カフェ関連キーワード
        cafe_keywords = ["カフェ", "cafe"] if language == "ja" else ["cafe"]

        # 会議室関連キーワード
        meeting_keywords = (
            ["会議室", "mtg", "ミーティング"] if language == "ja" else ["meeting", "room"]
        )

        # カフェの曖昧性チェック
        if any(kw in text_lower for kw in cafe_keywords):
            if any(
                word in text_lower
                for word in (["どこ", "どちら"] if language == "ja" else ["which", "where"])
            ):
                return "cafe-clarification-needed"

        # 会議室の曖昧性チェック
        if any(kw in text_lower for kw in meeting_keywords):
            if any(
                word in text_lower
                for word in (["どこ", "どちら"] if language == "ja" else ["which", "what"])
            ):
                return "meeting-room-clarification-needed"

        return None

    async def text_to_speech(
        self,
        text: str,
        language: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Convert text to speech.

        Supports language auto-detection, provider switching (voicevox/piper/
        kokoro), and speech speed override (speed 倍率 1.0=標準・小さいほど遅い).

        Args:
            text: Text to convert to speech. May include emotion tags like [happy].
            language: Language code ('ja' or 'en'). If None, auto-detects from text.
            emotion: Emotion tag to override detected emotion. Optional.

        Returns:
            TTS result dict with keys:
                - success (bool): Whether synthesis succeeded.
                - audioResponse (str): Base64-encoded audio data.
                - emotion (str): VRM emotion tag used.
                - cleanText (str): Processed text after cleaning and emotion tag removal.
                - format (str): Audio format ('audio/wav' or 'audio/mpeg').
                - language (str): Language used for synthesis.
                - error (str): Error message if failed. Optional.
        """
        tts_started_at = time.perf_counter()

        # ステップ1: 言語自動検出（未指定時）
        if language is None:
            try:
                language = await self.language_processor.detect(text)
                logger.info("Language auto-detected: %s", language)
            except Exception as e:
                logger.warning("Language detection failed: %s, using default 'ja'", e)
                language = "ja"

        # ステップ2: 感情タグパースとテキスト前処理
        parsed = parse_emotion_tags(text)
        cleaned = clean_text_for_tts(parsed.clean_text)
        processed = preprocess_tts(cleaned, language)

        vrm_emotion = (
            map_to_vrm_emotion(emotion) if emotion else (parsed.primary_emotion or "neutral")
        )

        # ステップ4: テキスト長チェック
        max_tts_bytes = get_tts_max_bytes()
        if len(processed.encode("utf-8")) > max_tts_bytes:
            processed = truncate_by_bytes(processed, max_tts_bytes)
            logger.warning("Text truncated to %d bytes for TTS", max_tts_bytes)

        cache_store = self._ensure_tts_cache()
        cache_key = self._tts_cache_key(processed, language, self.tts_provider, vrm_emotion,
                                        speed=speed)
        cached_entry = cache_store.get(cache_key)
        if cached_entry is not None:
            cached_audio = self._cached_audio_from_entry(cached_entry)
            if not self._is_cacheable_audio(cached_audio):
                cache_store.pop(cache_key, None)
                logger.warning("Ignored invalid TTS cache entry: cache_key=%s", cache_key)
            else:
                cached_format = (
                    cached_entry.get("format")
                    if isinstance(cached_entry, dict)
                    else self._tts_audio_format(language)
                )
                cached_fallback_used = (
                    bool(cached_entry.get("fallback_used"))
                    if isinstance(cached_entry, dict)
                    else False
                )
                cached_fallback_provider = (
                    cached_entry.get("fallback_provider")
                    if isinstance(cached_entry, dict)
                    else None
                )
                cached_actual_provider = (
                    cached_entry.get("actual_provider")
                    if isinstance(cached_entry, dict)
                    else self.tts_provider
                )
                log_tts_cache_event(hit=True, cache_key=cache_key, language=language)
                log_tts_synthesis_complete(
                    provider=cached_actual_provider or self.tts_provider,
                    language=language,
                    text_length=len(processed),
                    latency_ms=int((time.perf_counter() - tts_started_at) * 1000),
                    fallback_used=cached_fallback_used,
                    fallback_provider=cached_fallback_provider,
                    tts_cache_hit=True,
                )
                log_tts_event(
                    event="tts_complete",
                    provider=self.tts_provider,
                    language=language,
                    success=True,
                    tts_cache_hit=True,
                    tts_overall_duration_ms=int((time.perf_counter() - tts_started_at) * 1000),
                )
                return {
                    "success": True,
                    "audioResponse": cached_audio,
                    "emotion": vrm_emotion,
                    "cleanText": processed,
                    "format": cached_format or self._tts_audio_format(language),
                    "language": language,
                    "ambiguity_resolved": False,
                    "tts_cache_hit": True,
                    "tts_duration_ms": int((time.perf_counter() - tts_started_at) * 1000),
                    "fallback_used": cached_fallback_used,
                    "fallback_provider": cached_fallback_provider,
                    "actual_provider": cached_actual_provider,
                }

        log_tts_cache_event(hit=False, cache_key=cache_key, language=language)

        primary_attempt_provider: Optional[str] = None
        try:
            # ステップ5: 言語に基づいてTTSエンジンを選択
            if self.tts_provider == "piper":
                # piper-plus: 日本語・英語両対応（単一エンジン）
                primary_attempt_provider = "piper"
                if not self._requires_primary_tts_provider():
                    cooldown_remaining = self._tts_provider_cooldown_remaining("piper")
                    if cooldown_remaining > 0:
                        log_tts_event(
                            event="tts_provider_circuit_open",
                            provider="piper",
                            cooldown_remaining_ms=int(cooldown_remaining * 1000),
                        )
                        raise RuntimeError(
                            "piper TTS skipped during failure cooldown "
                            f"({cooldown_remaining:.2f}s remaining)"
                        )
                try:
                    audio_b64 = await self._await_tts_attempt(
                        self.tts_client.synthesize_wav_base64(processed, language, speed=speed),
                        provider="piper",
                        role="primary",
                        language=language,
                        text_length=len(processed),
                    )
                    self._clear_tts_provider_failure("piper")
                except Exception as piper_error:
                    if not self._requires_primary_tts_provider():
                        self._mark_tts_provider_failure("piper", piper_error)
                    raise
                audio_format = "audio/wav"
            elif language == "en" and self.kokoro_client:
                # 英語 → Kokoro TTS
                primary_attempt_provider = "kokoro"
                audio_b64 = await self._await_tts_attempt(
                    self.kokoro_client.synthesize_wav_base64(processed, language, speed=speed),
                    provider="kokoro",
                    role="primary",
                    language=language,
                    text_length=len(processed),
                )
                audio_format = "audio/wav"
            elif self.tts_provider == "kokoro":
                # プライマリ指定が kokoro の場合（COSCUP デモ等のローカル構成）
                primary_attempt_provider = "kokoro"
                audio_b64 = await self._await_tts_attempt(
                    self.tts_client.synthesize_wav_base64(processed, language, speed=speed),
                    provider="kokoro",
                    role="primary",
                    language=language,
                    text_length=len(processed),
                )
                audio_format = "audio/wav"
            elif self.tts_provider == "voicevox":
                # 日本語 → VoiceVox（英語は最後のローカルWAV fallbackとしても使う）
                primary_attempt_provider = "voicevox"
                audio_b64 = await self._await_tts_attempt(
                    self.tts_client.synthesize_wav_base64(processed, language),
                    provider="voicevox",
                    role="primary",
                    language=language,
                    text_length=len(processed),
                )
                audio_format = "audio/wav"
            else:
                raise RuntimeError(f"No TTS route for provider={self.tts_provider}")

            audio_b64 = self._require_audio_response(
                audio_b64,
                primary_attempt_provider or self.tts_provider,
            )
            if self._is_cacheable_audio(audio_b64):
                self._store_tts_cache_entry(
                    cache_store,
                    cache_key,
                    {
                        "audioResponse": audio_b64,
                        "format": audio_format,
                        "fallback_used": False,
                        "fallback_provider": None,
                        "actual_provider": primary_attempt_provider or self.tts_provider,
                    },
                )

            log_tts_event(
                event="tts_complete",
                provider=self.tts_provider,
                language=language,
                success=True,
                tts_cache_hit=False,
                tts_overall_duration_ms=int((time.perf_counter() - tts_started_at) * 1000),
            )
            return {
                "success": True,
                "audioResponse": audio_b64,
                "emotion": vrm_emotion,
                "cleanText": processed,
                "format": audio_format,
                "language": language,
                "ambiguity_resolved": False,
                "tts_cache_hit": False,
                "tts_duration_ms": int((time.perf_counter() - tts_started_at) * 1000),
                "fallback_used": False,
                "fallback_provider": None,
                "actual_provider": primary_attempt_provider or self.tts_provider,
            }
        except Exception as e:
            if self._requires_primary_tts_provider():
                logger.error("TTS failed and fallback is disabled: %s", e)
                log_tts_event(
                    event="tts_complete",
                    provider=self.tts_provider,
                    language=language,
                    success=False,
                    tts_cache_hit=False,
                    tts_overall_duration_ms=int((time.perf_counter() - tts_started_at) * 1000),
                    fallback_used=False,
                    fallback_provider=None,
                    error_type=type(e).__name__,
                )
                return {
                    "success": False,
                    "error": (
                        f"Failed to generate speech with primary "
                        f"{self.tts_provider} provider: {str(e)}"
                    ),
                    "emotion": "confused",
                    "cleanText": processed,
                    "format": self._tts_audio_format(language),
                    "language": language,
                    "tts_cache_hit": False,
                    "tts_duration_ms": int((time.perf_counter() - tts_started_at) * 1000),
                    "fallback_used": False,
                    "fallback_provider": None,
                    "actual_provider": None,
                }

            logger.exception("TTS failed, trying fallback: %s", e)
            fallback_provider: Optional[str] = None

            try:
                if self.tts_provider == "piper":
                    # piper障害時: ローカルfallbackのみを使う。
                    try:
                        if language == "en":
                            logger.warning("piper failed, falling back to Kokoro for en")
                            kokoro_client = getattr(self, "kokoro_client", None)
                            if not kokoro_client:
                                raise RuntimeError(
                                    "Piper unavailable and Kokoro not configured for English TTS"
                                )
                            fallback_provider = "kokoro"
                            audio_b64 = await self._await_tts_attempt(
                                kokoro_client.synthesize_wav_base64(processed, language,
                                                                    speed=speed),
                                provider="kokoro",
                                role="fallback",
                                language=language,
                                text_length=len(processed),
                            )
                            audio_format = "audio/wav"
                        else:
                            if language not in ("ja",):
                                logger.warning(
                                    "piper fallback to VoiceVox for unsupported language: %s",
                                    language,
                                )
                            logger.warning(
                                "piper failed, falling back to VoiceVox for %s",
                                language,
                            )
                            voicevox_fallback_client = getattr(
                                self, "voicevox_fallback_client", None
                            )
                            if not voicevox_fallback_client:
                                raise RuntimeError(
                                    "No VoiceVox fallback client available for piper TTS fallback"
                                )
                            fallback_provider = "voicevox"
                            audio_b64 = await self._await_tts_attempt(
                                voicevox_fallback_client.synthesize_wav_base64(processed, language),
                                provider="voicevox",
                                role="fallback",
                                language=language,
                                text_length=len(processed),
                            )
                            audio_format = "audio/wav"
                    except Exception as local_fallback_error:
                        raise local_fallback_error
                elif language == "en":
                    # 英語フォールバック: 同じ失敗 provider の即時再試行は避ける。
                    if (
                        getattr(self, "kokoro_client", None)
                        and primary_attempt_provider != "kokoro"
                    ):
                        fallback_provider = "kokoro"
                        audio_b64 = await self._await_tts_attempt(
                            self.kokoro_client.synthesize_wav_base64(processed, language,
                                                                     speed=speed),
                            provider="kokoro",
                            role="fallback",
                            language=language,
                            text_length=len(processed),
                        )
                        audio_format = "audio/wav"
                    elif self.tts_provider == "voicevox" and primary_attempt_provider != "voicevox":
                        fallback_provider = "voicevox"
                        audio_b64 = await self._await_tts_attempt(
                            self.tts_client.synthesize_wav_base64(processed, language),
                            provider="voicevox",
                            role="fallback",
                            language=language,
                            text_length=len(processed),
                        )
                        audio_format = "audio/wav"
                    else:
                        raise RuntimeError(
                            "English TTS failed and no alternate fallback provider is configured"
                        )
                elif self.tts_provider == "voicevox":
                    fallback_provider = "voicevox"
                    audio_b64 = await self._await_tts_attempt(
                        self.tts_client.synthesize_wav_base64(processed, language),
                        provider="voicevox",
                        role="fallback",
                        language=language,
                        text_length=len(processed),
                    )
                    audio_format = "audio/wav"
                else:
                    raise RuntimeError(
                        f"TTS failed and no portable fallback route is configured for "
                        f"provider={self.tts_provider}"
                    )

                audio_b64 = self._require_audio_response(
                    audio_b64,
                    fallback_provider or "fallback",
                )
                if self._is_cacheable_audio(audio_b64):
                    self._store_tts_cache_entry(
                        cache_store,
                        cache_key,
                        {
                            "audioResponse": audio_b64,
                            "format": audio_format,
                            "fallback_used": True,
                            "fallback_provider": fallback_provider,
                            "actual_provider": fallback_provider,
                        },
                    )

                log_tts_event(
                    event="tts_complete",
                    provider=self.tts_provider,
                    language=language,
                    success=True,
                    tts_cache_hit=False,
                    tts_overall_duration_ms=int((time.perf_counter() - tts_started_at) * 1000),
                    fallback_used=True,
                    fallback_provider=fallback_provider,
                    error_type=type(e).__name__,
                )
                return {
                    "success": True,
                    "audioResponse": audio_b64,
                    "emotion": "sad",
                    "cleanText": processed,
                    "error": str(e),
                    "format": audio_format,
                    "language": language,
                    "fallback_used": True,
                    "fallback_provider": fallback_provider,
                    "tts_cache_hit": False,
                    "tts_duration_ms": int((time.perf_counter() - tts_started_at) * 1000),
                    "actual_provider": fallback_provider,
                }
            except Exception as fallback_error:
                logger.error("Fallback TTS also failed: %s", fallback_error)
                fallback_attempted = fallback_provider is not None
                log_tts_event(
                    event="tts_complete",
                    provider=self.tts_provider,
                    language=language,
                    success=False,
                    tts_cache_hit=False,
                    tts_overall_duration_ms=int((time.perf_counter() - tts_started_at) * 1000),
                    fallback_used=fallback_attempted,
                    fallback_provider=None,
                    error_type=type(fallback_error).__name__,
                )
                return {
                    "success": False,
                    "error": f"Failed to generate speech: {str(fallback_error)}",
                    "emotion": "confused",
                    "language": language,
                    "tts_cache_hit": False,
                    "tts_duration_ms": int((time.perf_counter() - tts_started_at) * 1000),
                    "fallback_used": fallback_attempted,
                    "fallback_provider": None,
                    "actual_provider": None,
                }
