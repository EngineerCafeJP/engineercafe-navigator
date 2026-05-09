"""backend/agents/voice_agent.py

Phase 1 (TTS only):
- Emotion tag parsing + alias normalization (TS EmotionTagParser / EmotionMapping compatible)
- Text cleaning for TTS (TS VoiceOutputAgent.cleanTextForTTS compatible)
- preprocessTTS (currently MTG -> ミーティング/meeting)
- Configurable byte truncation for practical spoken responses
- Fallback handling
- Google TTS REST client (service account -> bearer token)
  for integration (can be monkeypatched in unit tests)

Note: Unit tests can monkeypatch
`VoiceAgent.tts_client.synthesize_mp3_base64` to avoid external calls.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Dict, List, Optional

import httpx
from cachetools import TTLCache

from backend.observability.structured_logger import log_tts_cache_event, log_tts_event
from backend.utils.clarification_templates import ClarificationCategory
from backend.utils.language_processor import LanguageProcessor

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Emotion mapping (TS emotion-mapping.ts compatible)
# -----------------------------------------------------------------------------

# TS: EmotionMapping.VRM_EMOTION_MAP (alias -> normalized VRM emotion)
VRM_EMOTION_MAP: Dict[str, str] = {
    # neutral
    "neutral": "neutral",
    "calm": "neutral",
    "normal": "neutral",
    "explaining": "neutral",
    "teaching": "neutral",
    "describing": "neutral",
    # happy
    "happy": "happy",
    "joy": "happy",
    "excited": "happy",
    "cheerful": "happy",
    "pleased": "happy",
    "greeting": "happy",
    "welcoming": "happy",
    "confident": "happy",
    "proud": "happy",
    "grateful": "happy",
    "warm": "happy",
    "helpful": "happy",
    # sad
    "sad": "sad",
    "disappointed": "sad",
    "melancholy": "sad",
    "down": "sad",
    "worried": "sad",
    "embarrassed": "sad",
    "apologetic": "sad",
    # angry
    "angry": "angry",
    "mad": "angry",
    "frustrated": "angry",
    "annoyed": "angry",
    # relaxed
    "relaxed": "relaxed",
    "thinking": "relaxed",
    "pondering": "relaxed",
    "wondering": "relaxed",
    "listening": "relaxed",
    "attentive": "relaxed",
    "concerned": "relaxed",
    "shy": "relaxed",
    "confused": "relaxed",
    "thoughtful": "relaxed",
    "supportive": "relaxed",
    "gentle": "relaxed",
    # surprised
    "curious": "surprised",
    "surprised": "surprised",
    "shocked": "surprised",
    "amazed": "surprised",
    "astonished": "surprised",
    "questioning": "surprised",
    "inquisitive": "surprised",
}


def is_supported_emotion_alias(emotion: str) -> bool:
    return isinstance(emotion, str) and emotion.lower().strip() in VRM_EMOTION_MAP


def map_to_vrm_emotion(emotion: Any) -> str:
    if not isinstance(emotion, str):
        return "neutral"
    return VRM_EMOTION_MAP.get(emotion.lower().strip(), "neutral")


def map_vrm_to_tts_emotion(vrm_emotion: str) -> str:
    """Map VRM emotion (6 kinds) to TTS emotion keys (TS GoogleCloudVoiceSimple).

    VRM: neutral/happy/sad/angry/surprised/relaxed
    TTS: happy/sad/angry/excited/calm
    """

    mapping = {
        "happy": "happy",
        "sad": "sad",
        "angry": "angry",
        "relaxed": "calm",
        "surprised": "excited",
        "neutral": "calm",
    }
    return mapping.get(vrm_emotion, "calm")


# -----------------------------------------------------------------------------
# Emotion tag parser (TS emotion-tag-parser.ts compatible)
# -----------------------------------------------------------------------------

# Matches: [happy], [/happy], [happy:0.8], [/happy:0.8]
EMOTION_TAG_REGEX = re.compile(r"\[/?([a-zA-Z_]+)(?::(\d*\.?\d+))?\]")


@dataclass
class EmotionTag:
    emotion: str
    position: int
    intensity: float = 1.0


@dataclass
class ParsedResponse:
    clean_text: str
    emotions: List[EmotionTag]
    primary_emotion: Optional[str]


def parse_emotion_tags(text: str) -> ParsedResponse:
    emotions: List[EmotionTag] = []
    if not text:
        return ParsedResponse(clean_text="", emotions=[], primary_emotion=None)

    for m in EMOTION_TAG_REGEX.finditer(text):
        raw = (m.group(1) or "").lower()
        intensity_str = m.group(2)
        intensity = float(intensity_str) if intensity_str else 1.0
        intensity = max(0.0, min(1.0, intensity))
        pos = m.start()

        if is_supported_emotion_alias(raw):
            vrm_emotion = map_to_vrm_emotion(raw)
            emotions.append(EmotionTag(emotion=vrm_emotion, position=pos, intensity=intensity))
        else:
            logger.warning("Unknown emotion tag: [%s]", raw)

    clean = EMOTION_TAG_REGEX.sub("", text).strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    primary = None
    if emotions:
        primary = sorted(emotions, key=lambda e: e.intensity, reverse=True)[0].emotion

    return ParsedResponse(clean_text=clean, emotions=emotions, primary_emotion=primary)


# -----------------------------------------------------------------------------
# preprocessTTS (TS tts-preprocess.ts compatible: MTG replacement)
# -----------------------------------------------------------------------------


def preprocess_tts(text: str, lang: str) -> str:
    replacement = "ミーティング" if lang == "ja" else "meeting"
    # Keep it simple and robust (tests expect MTG to be replaced)
    return re.sub(r"MTG", replacement, text, flags=re.IGNORECASE)


# -----------------------------------------------------------------------------
# Text cleaning for TTS (TS voice-output-agent.ts cleanTextForTTS compatible)
# -----------------------------------------------------------------------------


def clean_text_for_tts(text: str) -> str:
    t = text

    # Remove fenced code blocks ```...``` (non-greedy, before inline markers)
    t = re.sub(r"```[\s\S]*?```", "", t)

    # Remove markdown emphasis markers
    t = re.sub(r"\*\*", "", t)
    t = re.sub(r"\*", "", t)

    # Numbered list prefixes
    t = re.sub(r"^\d+\.\s*", "", t, flags=re.M)

    # Bullet points: - item or * item at start of line
    t = re.sub(r"^[-\*]\s+", "", t, flags=re.M)

    # Headers (requires # at start of line)
    t = re.sub(r"^#+\s+", "", t, flags=re.M)

    # Blockquotes: > text at start of line
    t = re.sub(r"^>\s*", "", t, flags=re.M)

    # Horizontal rules: ---, ***, ___ (3+ chars on their own line)
    t = re.sub(r"^[-\*_]{3,}\s*$", "", t, flags=re.M)

    # HTML tags: replace with space to prevent word concatenation
    # (preserves non-HTML angle brackets like vector<int>, 1 < 2)
    t = re.sub(
        r"</?(?:br|p|div|span|strong|em|b|i|u|a|h[1-6]"
        r"|ul|ol|li|table|tr|td|th|hr|img|pre|code|blockquote)(?=[\s>/])[^>]*>",
        " ",
        t,
        flags=re.I,
    )

    # Table syntax: remove separator rows, convert data rows to plain text
    t = re.sub(r"^\|?[-:]+\|[-:|]+\|?\s*$", "", t, flags=re.M)
    t = re.sub(
        r"^\s*\|(.+\|.+)\s*$",
        lambda m: m.group(1).replace("|", " ").strip(),
        t,
        flags=re.M,
    )

    # Convert markdown links [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)

    # Inline code `code` -> code
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Normalize multiple newlines to single space
    t = re.sub(r"\n{2,}", " ", t)

    # Normalize whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


# -----------------------------------------------------------------------------
# Truncate by UTF-8 bytes
# -----------------------------------------------------------------------------

DEFAULT_TTS_MAX_BYTES = 900
MIN_CACHEABLE_TTS_AUDIO_BASE64_CHARS = 100
DEFAULT_TTS_CACHE_MAX_ENTRIES = 200
DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES = 5 * 1024 * 1024
_DEFAULT_TTS_TIMEOUTS: Dict[str, float] = {
    "piper": 4.0,
    "kokoro": 3.0,
    "voicevox": 4.0,
    "google": 6.0,
}


def tts_require_primary_provider() -> bool:
    raw = os.getenv("TTS_REQUIRE_PRIMARY_PROVIDER", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_tts_max_bytes() -> int:
    raw = os.getenv("TTS_MAX_BYTES", "").strip()
    if not raw:
        return DEFAULT_TTS_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid TTS_MAX_BYTES=%r; using %d", raw, DEFAULT_TTS_MAX_BYTES)
        return DEFAULT_TTS_MAX_BYTES
    return max(200, value)


def get_tts_cache_max_audio_bytes() -> int:
    raw = os.getenv("TTS_CACHE_MAX_AUDIO_BYTES", "").strip()
    if not raw:
        return DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid TTS_CACHE_MAX_AUDIO_BYTES=%r; using default", raw)
        return DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES
    if value <= 0:
        logger.warning("TTS_CACHE_MAX_AUDIO_BYTES must be positive; using default")
        return DEFAULT_TTS_CACHE_MAX_AUDIO_BYTES
    return value


def get_tts_timeout_seconds(provider: str, role: str = "primary") -> float:
    """Soft timeout for one TTS provider attempt.

    HTTP clients keep their larger socket timeouts, but the voice turn should
    move to the next recovery path quickly when a local TTS server is wedged.
    """

    provider_key = (provider or "").strip().lower()
    role_key = (role or "primary").strip().upper()
    env_names = [
        f"TTS_{provider_key.upper()}_{role_key}_TIMEOUT_SECONDS",
        f"TTS_{role_key}_TIMEOUT_SECONDS",
        f"TTS_{provider_key.upper()}_TIMEOUT_SECONDS",
    ]
    default = _DEFAULT_TTS_TIMEOUTS.get(provider_key, 4.0)

    for name in env_names:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            logger.warning("Invalid %s=%r; using %.1fs", name, raw, default)
            return default
        if value <= 0:
            logger.warning("Invalid %s=%r; using %.1fs", name, raw, default)
            return default
        return max(0.05, value)
    return default


def truncate_by_bytes(text: str, max_bytes: int = 5000) -> str:
    def byte_len(s: str) -> int:
        return len(s.encode("utf-8"))

    truncated = text
    while truncated and byte_len(truncated) > max_bytes:
        if "。" in truncated:
            parts = [part for part in truncated.split("。") if part.strip()]
            if len(parts) > 1:
                parts.pop()
                truncated = "。".join(parts).strip()
                if truncated and not truncated.endswith("。"):
                    truncated += "。"
            else:
                truncated = truncated[:-10]
        else:
            # Generic fallback
            truncated = truncated[:-10]

    return truncated.strip()


def fallback_error_message(lang: str) -> str:
    return (
        "申し訳ございません。音声の生成に失敗しました。"
        if lang == "ja"
        else "I apologize, but I failed to generate the audio response."
    )


# -----------------------------------------------------------------------------
# Google TTS client (integration; can be monkeypatched in unit tests)
# -----------------------------------------------------------------------------


class GoogleTTSClient:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        # TS-compatible env vars
        self.credentials_source = os.getenv("GOOGLE_CLOUD_CREDENTIALS") or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        self.default_key_path = "config/service-account-key.json"

    def _load_credentials(self):
        # Lazy imports (unit tests may not need google-auth)
        from google.oauth2 import service_account

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]

        src = self.credentials_source
        if src:
            if os.path.exists(src):
                return service_account.Credentials.from_service_account_file(src, scopes=scopes)
            try:
                info = json.loads(src)
                return service_account.Credentials.from_service_account_info(info, scopes=scopes)
            except Exception as e:
                logger.warning("Failed to parse GOOGLE_CLOUD_CREDENTIALS as JSON: %s", e)

        if os.path.exists(self.default_key_path):
            return service_account.Credentials.from_service_account_file(
                self.default_key_path, scopes=scopes
            )

        raise RuntimeError(
            "Service account key not found. "
            "Set GOOGLE_CLOUD_CREDENTIALS/"
            "GOOGLE_APPLICATION_CREDENTIALS "
            f"or place {self.default_key_path}"
        )

    def _get_access_token(self) -> str:
        from google.auth.transport.requests import Request as GoogleAuthRequest

        now = time.time()
        if self._access_token and now < self._token_expiry:
            return self._access_token

        creds = self._load_credentials()
        creds.refresh(GoogleAuthRequest())
        if not creds.token:
            raise RuntimeError("Failed to obtain access token")

        self._access_token = creds.token
        self._token_expiry = now + 55 * 60
        return self._access_token

    def _tts_params(self, lang: str, tts_emotion: str) -> Dict[str, Any]:
        # Base settings aligned with TS google-cloud-voice-simple.ts
        if lang == "ja":
            speaker = "ja-JP-Wavenet-B"
            speed = 1.3
            pitch = 2.5
            volume = 2.0
            language_code = "ja-JP"
        else:
            speaker = "en-GB-Standard-F"
            speed = 1.05
            pitch = 0.3
            volume = 2.5
            language_code = "en-GB"

        # Emotion adjustments
        if tts_emotion == "excited":
            speed *= 1.1
            pitch += 0.3
        elif tts_emotion == "sad":
            speed *= 0.9
            pitch -= 0.5
        elif tts_emotion == "angry":
            speed *= 1.05
            pitch += 0.2
        elif tts_emotion == "calm":
            speed *= 0.95
            pitch -= 0.2

        return {
            "languageCode": language_code,
            "name": speaker,
            "speakingRate": speed,
            "pitch": pitch,
            "volumeGainDb": volume,
        }

    async def _get_access_token_async(self) -> str:
        """Get access token asynchronously (offloads blocking auth to thread pool)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_access_token)

    async def synthesize_mp3_base64(self, text: str, lang: str, tts_emotion: str) -> str:
        token = await self._get_access_token_async()
        params = self._tts_params(lang, tts_emotion)

        payload = {
            "input": {"text": text},
            "voice": {"languageCode": params["languageCode"], "name": params["name"]},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": params["speakingRate"],
                "pitch": params["pitch"],
                "volumeGainDb": params["volumeGainDb"],
                "effectsProfileId": ["telephony-class-application"],
            },
        }

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )

            if r.status_code >= 400:
                raise RuntimeError(f"TTS API Error {r.status_code}: {r.text}")

            data = r.json()
            audio_b64 = data.get("audioContent")
            if not audio_b64:
                raise RuntimeError("No audioContent in TTS response")

            return audio_b64


# =============================================================================
# VoiceVox TTS Client (Local, WAV format)
# =============================================================================


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
            self._client = httpx.AsyncClient(timeout=30)
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

        except httpx.TimeoutException as e:
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
            async with httpx.AsyncClient(timeout=30) as client:
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

        except httpx.TimeoutException as e:
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
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

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

        try:
            client = self._get_client()
            response = await client.post(
                f"{self.api_url}/synthesize",
                json=payload,
            )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"PiperPlus TTS API Error {response.status_code}: {response.text}"
                )

            wav_b64 = base64.b64encode(response.content).decode("utf-8")
            logger.info("PiperPlus TTS synthesis success: text_len=%d", len(text))
            return wav_b64

        except httpx.TimeoutException as e:
            logger.error("PiperPlus TTS timeout: %s", e)
            raise RuntimeError(f"PiperPlus TTS connection timeout: {e}")
        except Exception as e:
            logger.exception("PiperPlus TTS synthesis error: %s", e)
            raise RuntimeError(f"PiperPlus TTS synthesis error: {e}")


# =============================================================================
# VoiceAgent class (modified for provider switching + language detection)
# =============================================================================


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
        elif tts_provider == "google":
            self.tts_client = GoogleTTSClient()
            logger.info("Using Google Cloud TTS")
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

        self.google_fallback_client: Optional[GoogleTTSClient]
        if tts_provider == "google" or self.require_primary_tts_provider:
            self.google_fallback_client = None
        else:
            self.google_fallback_client = GoogleTTSClient()

        self._tts_cache_max_audio_bytes = get_tts_cache_max_audio_bytes()
        self._tts_cache: TTLCache = TTLCache(maxsize=DEFAULT_TTS_CACHE_MAX_ENTRIES, ttl=3600)

    async def close(self) -> None:
        """Close reusable TTS clients owned by this agent."""
        clients = [
            getattr(self, "tts_client", None),
            getattr(self, "kokoro_client", None),
            getattr(self, "voicevox_fallback_client", None),
            getattr(self, "google_fallback_client", None),
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
    def _tts_cache_key(text: str, language: str, provider: str, emotion: str) -> str:
        raw = f"{text}|{language}|{provider}|{emotion or 'neutral'}"
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

    @staticmethod
    def _require_audio_response(audio_b64: Any, provider: str) -> str:
        if isinstance(audio_b64, str) and audio_b64.strip():
            return audio_b64
        raise RuntimeError(f"{provider} TTS returned empty audio response")

    def _tts_audio_format(self, language: str) -> str:
        if self.tts_provider == "google":
            return "audio/mpeg"
        if self.tts_provider == "piper" or language == "en" or self.tts_provider == "voicevox":
            return "audio/wav"
        return "audio/mpeg"

    async def _await_tts_attempt(
        self,
        awaitable: Awaitable[str],
        *,
        provider: str,
        role: str,
    ) -> str:
        timeout_s = get_tts_timeout_seconds(provider, role)
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"{provider} TTS {role} timed out after {timeout_s:.2f}s") from exc

    def _google_fallback_available(self) -> bool:
        google_client = getattr(self, "google_fallback_client", None)
        if google_client is None:
            return False
        credentials_source = getattr(google_client, "credentials_source", None)
        default_key_path = getattr(google_client, "default_key_path", None)
        return bool(credentials_source) or bool(
            default_key_path and os.path.exists(default_key_path)
        )

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
    ) -> Dict[str, Any]:
        """Convert text to speech with language detection.

        Features:
            - Automatic language detection (when language is None)
            - TTS provider switching (voicevox / google / kokoro)

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
                - ambiguity_resolved (bool): Always False. Kept for response compatibility.
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
        cache_key = self._tts_cache_key(processed, language, self.tts_provider, vrm_emotion)
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
                log_tts_cache_event(hit=True, cache_key=cache_key, language=language)
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
                    "fallback_used": (
                        cached_entry.get("fallback_used")
                        if isinstance(cached_entry, dict)
                        else False
                    ),
                    "fallback_provider": (
                        cached_entry.get("fallback_provider")
                        if isinstance(cached_entry, dict)
                        else None
                    ),
                    "actual_provider": (
                        cached_entry.get("actual_provider")
                        if isinstance(cached_entry, dict)
                        else self.tts_provider
                    ),
                }

        log_tts_cache_event(hit=False, cache_key=cache_key, language=language)

        primary_attempt_provider: Optional[str] = None
        try:
            # ステップ5: 言語に基づいてTTSエンジンを選択
            if self.tts_provider == "piper":
                # piper-plus: 日本語・英語両対応（単一エンジン）
                primary_attempt_provider = "piper"
                audio_b64 = await self._await_tts_attempt(
                    self.tts_client.synthesize_wav_base64(processed, language),
                    provider="piper",
                    role="primary",
                )
                audio_format = "audio/wav"
            elif language == "en" and self.kokoro_client:
                # 英語 → Kokoro TTS (voicevox/google の場合)
                primary_attempt_provider = "kokoro"
                audio_b64 = await self._await_tts_attempt(
                    self.kokoro_client.synthesize_wav_base64(processed, language),
                    provider="kokoro",
                    role="primary",
                )
                audio_format = "audio/wav"
            elif self.tts_provider == "google":
                # Google TTS supports both ja/en; without Kokoro it must not
                # fall through to a WAV-only method that GoogleTTSClient lacks.
                primary_attempt_provider = "google"
                tts_emotion = map_vrm_to_tts_emotion(vrm_emotion)
                audio_b64 = await self._await_tts_attempt(
                    self.tts_client.synthesize_mp3_base64(processed, language, tts_emotion),
                    provider="google",
                    role="primary",
                )
                audio_format = "audio/mpeg"
            elif self.tts_provider == "voicevox":
                # 日本語 → VoiceVox（英語は最後のローカルWAV fallbackとしても使う）
                primary_attempt_provider = "voicevox"
                audio_b64 = await self._await_tts_attempt(
                    self.tts_client.synthesize_wav_base64(processed, language),
                    provider="voicevox",
                    role="primary",
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

            async def _google_fallback_audio() -> str:
                google_client = getattr(self, "google_fallback_client", None)
                if google_client is None:
                    raise RuntimeError("Google fallback client is not configured")
                if language not in ("ja", "en"):
                    raise RuntimeError(f"Google fallback does not support language={language}")
                return await self._await_tts_attempt(
                    google_client.synthesize_mp3_base64(processed, language, "sad"),
                    provider="google",
                    role="fallback",
                )

            try:
                if self.tts_provider == "piper":
                    # piper障害時: ローカルfallbackを優先し、未設定/失敗時だけGoogleへ退避する。
                    try:
                        if language == "en":
                            logger.warning("piper failed, falling back to Kokoro for en")
                            if not self.kokoro_client:
                                raise RuntimeError(
                                    "Piper unavailable and Kokoro not configured for English TTS"
                                )
                            fallback_provider = "kokoro"
                            audio_b64 = await self._await_tts_attempt(
                                self.kokoro_client.synthesize_wav_base64(processed, language),
                                provider="kokoro",
                                role="fallback",
                            )
                            audio_format = "audio/wav"
                        else:
                            if language not in ("ja",):
                                logger.warning(
                                    "piper fallback to VoiceVox for unsupported language: %s",
                                    language,
                                )
                            logger.warning(
                                "piper failed, falling back to VoiceVox for %s", language
                            )
                            if not self.voicevox_fallback_client:
                                raise RuntimeError(
                                    "No VoiceVox fallback client available for piper TTS fallback"
                                )
                            fallback_provider = "voicevox"
                            audio_b64 = await self._await_tts_attempt(
                                self.voicevox_fallback_client.synthesize_wav_base64(
                                    processed, language
                                ),
                                provider="voicevox",
                                role="fallback",
                            )
                            audio_format = "audio/wav"
                    except Exception as local_fallback_error:
                        if not self._google_fallback_available():
                            raise local_fallback_error
                        logger.warning(
                            "Local piper TTS fallback failed, trying Google fallback: %s",
                            local_fallback_error,
                        )
                        fallback_provider = "google"
                        audio_b64 = await _google_fallback_audio()
                        audio_format = "audio/mpeg"
                elif language == "en":
                    # 英語フォールバック: 同じ失敗 provider の即時再試行は避ける。
                    if self.tts_provider == "google" and primary_attempt_provider != "google":
                        fallback_provider = "google"
                        audio_b64 = await self._await_tts_attempt(
                            self.tts_client.synthesize_mp3_base64(processed, language, "sad"),
                            provider="google",
                            role="fallback",
                        )
                        audio_format = "audio/mpeg"
                    elif self.kokoro_client and primary_attempt_provider != "kokoro":
                        fallback_provider = "kokoro"
                        audio_b64 = await self._await_tts_attempt(
                            self.kokoro_client.synthesize_wav_base64(processed, language),
                            provider="kokoro",
                            role="fallback",
                        )
                        audio_format = "audio/wav"
                    elif self._google_fallback_available():
                        fallback_provider = "google"
                        audio_b64 = await _google_fallback_audio()
                        audio_format = "audio/mpeg"
                    elif self.tts_provider == "voicevox" and primary_attempt_provider != "voicevox":
                        fallback_provider = "voicevox"
                        audio_b64 = await self._await_tts_attempt(
                            self.tts_client.synthesize_wav_base64(processed, language),
                            provider="voicevox",
                            role="fallback",
                        )
                        audio_format = "audio/wav"
                    else:
                        raise RuntimeError(
                            "English TTS failed and no alternate fallback provider is configured"
                        )
                elif self.tts_provider == "voicevox":
                    if self._google_fallback_available():
                        fallback_provider = "google"
                        audio_b64 = await _google_fallback_audio()
                        audio_format = "audio/mpeg"
                    else:
                        fallback_provider = "voicevox"
                        audio_b64 = await self._await_tts_attempt(
                            self.tts_client.synthesize_wav_base64(processed, language),
                            provider="voicevox",
                            role="fallback",
                        )
                        audio_format = "audio/wav"
                else:
                    # Google TTSフォールバック
                    fallback_provider = "google"
                    audio_b64 = await self._await_tts_attempt(
                        self.tts_client.synthesize_mp3_base64(processed, language, "sad"),
                        provider="google",
                        role="fallback",
                    )
                    audio_format = "audio/mpeg"

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
                log_tts_event(
                    event="tts_complete",
                    provider=self.tts_provider,
                    language=language,
                    success=False,
                    tts_cache_hit=False,
                    tts_overall_duration_ms=int((time.perf_counter() - tts_started_at) * 1000),
                    error_type=type(fallback_error).__name__,
                )
                return {
                    "success": False,
                    "error": f"Failed to generate speech: {str(e)}",
                    "emotion": "confused",
                    "tts_cache_hit": False,
                    "tts_duration_ms": int((time.perf_counter() - tts_started_at) * 1000),
                    "fallback_used": False,
                    "fallback_provider": None,
                    "actual_provider": None,
                }
