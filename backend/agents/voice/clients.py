from __future__ import annotations

import asyncio
import base64
import importlib
import logging
from typing import Any, Optional

import httpx

from backend.observability.structured_logger import log_tts_event

from .text import get_piper_plus_max_attempts, get_piper_plus_retry_backoff_seconds

logger = logging.getLogger("backend.agents.voice_agent")


def _public_symbol(name: str, fallback: Any) -> Any:
    try:
        return getattr(importlib.import_module("backend.agents.voice_agent"), name)
    except Exception:
        return fallback


def _httpx():
    return _public_symbol("httpx", httpx)


def _log_tts_event(**kwargs: Any) -> None:
    _public_symbol("log_tts_event", log_tts_event)(**kwargs)


class VoiceVoxClient:
    """
    ローカルTTS: VoiceVox エンジン

    VoiceVox はオフライン対応の高品質日本語音声合成エンジン。
    Docker で起動した VoiceVox REST API を使用します。

    注意: VoiceVoxは日本語専用TTS。英語テキストはカタカナ読みになります。
    """

    DEFAULT_SPEAKER_JA = 3  # ずんだもん (ノーマル)
    DEFAULT_SPEAKER_EN = 3  # VoiceVoxに英語話者なし。日本語話者でカタカナ読み

    def __init__(self, api_url: str = "http://localhost:50021"):
        """
        Args:
            api_url: VoiceVox Engine API URL
        """
        self.api_url = api_url.rstrip("/")
        self._initialized_speakers: set[int] = set()
        self._client: Optional[httpx.AsyncClient] = None
        logger.info("VoiceVoxClient initialized: %s", self.api_url)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = _httpx().AsyncClient(timeout=30)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def aclose(self) -> None:
        await self.close()

    async def _ensure_speaker_initialized(self, client: httpx.AsyncClient, speaker_id: int) -> None:
        """初回遅延回避のためスピーカーを事前初期化 (公式推奨)"""
        if speaker_id in self._initialized_speakers:
            return
        try:
            resp = await client.post(
                f"{self.api_url}/initialize_speaker",
                params={"speaker": speaker_id},
            )
            if resp.status_code < 400:
                self._initialized_speakers.add(speaker_id)
                logger.info("VoiceVox speaker %s initialized", speaker_id)
        except Exception as e:
            logger.warning("VoiceVox speaker init failed (non-fatal): %s", e)

    async def synthesize_wav_base64(
        self, text: str, lang: str, speaker_id: Optional[int] = None
    ) -> str:
        """
        テキストを音声に合成し、base64エンコードされたWAVを返す
        """
        if speaker_id is None:
            speaker_id = self.DEFAULT_SPEAKER_JA if lang == "ja" else self.DEFAULT_SPEAKER_EN

        try:
            client = self._get_client()
            # Step 0: スピーカー初期化 (初回のみ、公式推奨)
            await self._ensure_speaker_initialized(client, speaker_id)

            # Step 1: Query 作成
            query_url = f"{self.api_url}/audio_query"
            query_response = await client.post(
                query_url,
                params={"text": text, "speaker": speaker_id},
            )

            if query_response.status_code >= 400:
                raise RuntimeError(f"VoiceVox audio_query failed: {query_response.status_code}")

            query_data = query_response.json()

            # Step 2: 音声合成
            synthesis_url = f"{self.api_url}/synthesis"
            synthesis_response = await client.post(
                synthesis_url,
                params={"speaker": speaker_id},
                json=query_data,
                headers={"Content-Type": "application/json"},
            )

            if synthesis_response.status_code >= 400:
                raise RuntimeError(f"VoiceVox synthesis failed: {synthesis_response.status_code}")

            wav_data = synthesis_response.content
            wav_b64 = base64.b64encode(wav_data).decode("utf-8")

            logger.info("VoiceVox synthesis success: text_len=%d", len(text))
            return wav_b64

        except _httpx().TimeoutException as e:
            logger.error("VoiceVox timeout: %s", e)
            raise RuntimeError(f"VoiceVox connection timeout: {e}")
        except Exception as e:
            logger.exception("VoiceVox synthesis error: %s", e)
            raise RuntimeError(f"VoiceVox synthesis error: {e}")


# =============================================================================
# Kokoro TTS Client (Local, WAV format)
# =============================================================================


class KokoroTTSClient:
    """
    英語TTS: Kokoro TTS エンジン

    Kokoro TTSは英語・日本語・中国語に対応した軽量TTSエンジン。
    Dockerで起動したKokoro FastAPI REST APIを使用します。
    """

    DEFAULT_VOICE_EN = "af_bella"  # 英語用デフォルトボイス

    def __init__(self, api_url: str = "http://localhost:8880"):
        """
        Args:
            api_url: Kokoro TTS Engine API URL
        """
        self.api_url = api_url.rstrip("/")
        logger.info("KokoroTTSClient initialized: %s", self.api_url)

    async def synthesize_wav_base64(self, text: str, lang: str, voice: Optional[str] = None) -> str:
        """
        テキストを音声に合成し、base64エンコードされたWAVを返す

        Args:
            text: 合成するテキスト
            lang: 言語コード（現在は使用されないが、将来の拡張のために保持）
            voice: ボイス名（未指定時はデフォルトボイスを使用）

        Returns:
            base64エンコードされたWAVデータ
        """
        if voice is None:
            voice = self.DEFAULT_VOICE_EN

        try:
            async with _httpx().AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.api_url}/v1/audio/speech",
                    json={
                        "model": "kokoro",
                        "input": text,
                        "voice": voice,
                        "response_format": "wav",
                    },
                )

                if response.status_code >= 400:
                    raise RuntimeError(
                        f"Kokoro TTS API Error {response.status_code}: {response.text}"
                    )

                wav_data = response.content
                wav_b64 = base64.b64encode(wav_data).decode("utf-8")

                logger.info("Kokoro TTS synthesis success: text_len=%d", len(text))
                return wav_b64

        except _httpx().TimeoutException as e:
            logger.error("Kokoro TTS timeout: %s", e)
            raise RuntimeError(f"Kokoro TTS connection timeout: {e}")
        except Exception as e:
            logger.exception("Kokoro TTS synthesis error: %s", e)
            raise RuntimeError(f"Kokoro TTS synthesis error: {e}")


# =============================================================================
# PiperPlus TTS Client (Local, WAV format, bilingual ja/en)
# =============================================================================


class PiperPlusTTSClient:
    """
    軽量・高速TTS: piper-plus エンジン (Python SDK ベース)

    piper-tts-plus Python SDK を使用した高速多言語TTSエンジン。
    tsukuyomi-chan-6lang モデルで日本語・英語等に対応。
    Docker で起動した piper-plus HTTP API (POST /synthesize) を使用します。

    話速は PIPER_SPEED 環境変数でサーバー側に設定済み (default: 0.65 ≒ ゆっくり)。
    """

    def __init__(self, api_url: str = "http://localhost:8090"):
        self.api_url = api_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        logger.info("PiperPlusTTSClient initialized: %s", self.api_url)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = _httpx().AsyncClient(timeout=30)
        return self._client

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = get_piper_plus_retry_backoff_seconds() * attempt
        if delay > 0:
            await asyncio.sleep(delay)

    def _log_retry(
        self,
        *,
        attempt: int,
        max_attempts: int,
        reason: str,
        status_code: Optional[int] = None,
        error_type: Optional[str] = None,
    ) -> None:
        delay_ms = int(get_piper_plus_retry_backoff_seconds() * attempt * 1000)
        logger.warning(
            "PiperPlus TTS attempt %d/%d failed (%s); retrying in %dms",
            attempt,
            max_attempts,
            reason,
            delay_ms,
        )
        _log_tts_event(
            event="tts_provider_retry",
            provider="piper",
            attempt=attempt,
            max_attempts=max_attempts,
            retry_delay_ms=delay_ms,
            retry_reason=reason,
            status_code=status_code,
            error_type=error_type,
        )

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def aclose(self) -> None:
        await self.close()

    async def synthesize_wav_base64(
        self, text: str, lang: str, speaker_id: Optional[int] = None
    ) -> str:
        """
        テキストを音声に合成し、base64エンコードされたWAVを返す

        Args:
            text: 合成するテキスト
            lang: 言語コード ("ja" / "en" 等、tsukuyomi 6言語対応)
            speaker_id: 話者ID（None でモデルデフォルト）

        Returns:
            base64エンコードされたWAVデータ
        """
        payload: dict = {"text": text, "language": lang}
        if speaker_id is not None:
            payload["speaker_id"] = speaker_id

        max_attempts = get_piper_plus_max_attempts()
        for attempt in range(1, max_attempts + 1):
            try:
                client = self._get_client()
                response = await client.post(
                    f"{self.api_url}/synthesize",
                    json=payload,
                )

                if response.status_code >= 400:
                    if self._is_retryable_status(response.status_code) and attempt < max_attempts:
                        self._log_retry(
                            attempt=attempt,
                            max_attempts=max_attempts,
                            reason="http_status",
                            status_code=response.status_code,
                        )
                        await self._sleep_before_retry(attempt)
                        continue
                    raise RuntimeError(
                        f"PiperPlus TTS API Error {response.status_code}: {response.text}"
                    )

                if not response.content:
                    if attempt < max_attempts:
                        self._log_retry(
                            attempt=attempt,
                            max_attempts=max_attempts,
                            reason="empty_audio",
                        )
                        await self._sleep_before_retry(attempt)
                        continue
                    raise RuntimeError("PiperPlus TTS returned empty audio response")

                wav_b64 = base64.b64encode(response.content).decode("utf-8")
                logger.info(
                    "PiperPlus TTS synthesis success: text_len=%d attempt=%d",
                    len(text),
                    attempt,
                )
                return wav_b64

            except _httpx().TimeoutException as e:
                if attempt < max_attempts:
                    self._log_retry(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        reason="timeout",
                        error_type=type(e).__name__,
                    )
                    await self._sleep_before_retry(attempt)
                    continue
                logger.error("PiperPlus TTS timeout: %s", e)
                raise RuntimeError(f"PiperPlus TTS connection timeout: {e}")
            except _httpx().RequestError as e:
                if attempt < max_attempts:
                    self._log_retry(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        reason="request_error",
                        error_type=type(e).__name__,
                    )
                    await self._sleep_before_retry(attempt)
                    continue
                logger.error("PiperPlus TTS request error: %s", e)
                raise RuntimeError(f"PiperPlus TTS connection error: {e}")
            except RuntimeError:
                raise
            except Exception as e:
                logger.exception("PiperPlus TTS synthesis error: %s", e)
                raise RuntimeError(f"PiperPlus TTS synthesis error: {e}")

        raise RuntimeError("PiperPlus TTS failed without a retryable result")
