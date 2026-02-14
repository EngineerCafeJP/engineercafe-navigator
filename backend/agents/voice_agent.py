"""backend/agents/voice_agent.py

Phase 1 (TTS only):
- Emotion tag parsing + alias normalization (TS EmotionTagParser / EmotionMapping compatible)
- Text cleaning for TTS (TS VoiceOutputAgent.cleanTextForTTS compatible)
- preprocessTTS (currently MTG -> ミーティング/meeting)
- 5000 bytes truncation
- Fallback handling
- Google TTS REST client (service account -> bearer token) for integration (can be monkeypatched in unit tests)

Note: Unit tests can monkeypatch `VoiceAgent.tts_client.synthesize_mp3_base64` to avoid external calls.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from backend.agents.clarification_agent import ClarificationAgent, ClarificationCategory
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

    # Remove markdown emphasis markers
    t = re.sub(r"\*\*", "", t)
    t = re.sub(r"\*", "", t)

    # Numbered list prefixes
    t = re.sub(r"^\d+\.\s*", "", t, flags=re.M)

    # Headers (requires # at start of line)
    t = re.sub(r"^#+\s+", "", t, flags=re.M)

    # Convert markdown links [text](url) -> text  ✅ r"\1" が正しい
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)

    # Remove fenced code blocks ```...``` (non-greedy)
    t = re.sub(r"```[\s\S]*?```", "", t)

    # Inline code `code` -> code  ✅ r"\1" が正しい
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Normalize whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


# -----------------------------------------------------------------------------
# Truncate by UTF-8 bytes (limit 5000 by default)
# -----------------------------------------------------------------------------


def truncate_by_bytes(text: str, max_bytes: int = 5000) -> str:
    def byte_len(s: str) -> int:
        return len(s.encode("utf-8"))

    truncated = text
    while truncated and byte_len(truncated) > max_bytes:
        if "。" in truncated:
            parts = truncated.split("。")
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
            "Service account key not found. Set GOOGLE_CLOUD_CREDENTIALS/GOOGLE_APPLICATION_CREDENTIALS "
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
        logger.info(f"VoiceVoxClient initialized: {self.api_url}")

    async def _ensure_speaker_initialized(
        self, client: httpx.AsyncClient, speaker_id: int
    ) -> None:
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
                logger.info(f"VoiceVox speaker {speaker_id} initialized")
        except Exception as e:
            logger.warning(f"VoiceVox speaker init failed (non-fatal): {e}")

    async def synthesize_wav_base64(
        self, text: str, lang: str, speaker_id: Optional[int] = None
    ) -> str:
        """
        テキストを音声に合成し、base64エンコードされたWAVを返す
        """
        if speaker_id is None:
            speaker_id = self.DEFAULT_SPEAKER_JA if lang == "ja" else self.DEFAULT_SPEAKER_EN

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Step 0: スピーカー初期化 (初回のみ、公式推奨)
                await self._ensure_speaker_initialized(client, speaker_id)

                # Step 1: Query 作成
                query_url = f"{self.api_url}/audio_query"
                query_response = await client.post(
                    query_url,
                    params={"text": text, "speaker": speaker_id},
                )
                
                if query_response.status_code >= 400:
                    raise RuntimeError(
                        f"VoiceVox audio_query failed: {query_response.status_code}"
                    )
                
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
                    raise RuntimeError(
                        f"VoiceVox synthesis failed: {synthesis_response.status_code}"
                    )
                
                wav_data = synthesis_response.content
                wav_b64 = base64.b64encode(wav_data).decode("utf-8")
                
                logger.info(f"VoiceVox synthesis success: text_len={len(text)}")
                return wav_b64
                
        except httpx.TimeoutException as e:
            logger.error(f"VoiceVox timeout: {e}")
            raise RuntimeError(f"VoiceVox connection timeout: {e}")
        except Exception as e:
            logger.error(f"VoiceVox synthesis error: {e}", exc_info=True)
            raise RuntimeError(f"VoiceVox synthesis error: {e}")


# =============================================================================
# VoiceAgent class (modified for provider switching + language detection + clarification)
# =============================================================================


class VoiceAgent:
    def __init__(
        self,
        tts_provider: str = "voicevox",
        tts_client: Optional[Any] = None,
        language_processor: Optional[LanguageProcessor] = None,
        clarification_agent: Optional[ClarificationAgent] = None,
    ):
        """
        VoiceAgent with TTS provider switching + LanguageProcessor + ClarificationAgent integration
        """
        self.tts_provider = tts_provider
        
        if tts_client:
            self.tts_client = tts_client
        elif tts_provider == "voicevox":
            voicevox_api_url = os.getenv("VOICEVOX_API_URL", "http://localhost:50021")
            self.tts_client = VoiceVoxClient(api_url=voicevox_api_url)
            logger.info(f"Using VoiceVox TTS: {voicevox_api_url}")
        elif tts_provider == "google":
            self.tts_client = GoogleTTSClient()
            logger.info("Using Google Cloud TTS")
        else:
            raise ValueError(f"Unknown TTS provider: {tts_provider}")
        
        self.language_processor = language_processor or LanguageProcessor(default_language="ja")
        logger.info("LanguageProcessor initialized for voice_agent")
        
        self.clarification_agent = clarification_agent or ClarificationAgent()
        logger.info("ClarificationAgent initialized for voice_agent")
    
    def _detect_category(self, text: str, language: str) -> Optional[ClarificationCategory]:
        """
        テキストから曖昧性カテゴリを検出
        """
        text_lower = text.lower()
        
        # カフェ関連キーワード
        cafe_keywords = (
            ["カフェ", "cafe"]
            if language == "ja"
            else ["cafe"]
        )
        
        # 会議室関連キーワード
        meeting_keywords = (
            ["会議室", "mtg", "ミーティング"]
            if language == "ja"
            else ["meeting", "room"]
        )
        
        # カフェの曖昧性チェック
        if any(kw in text_lower for kw in cafe_keywords):
            if any(word in text_lower for word in (["どこ", "どちら"] if language == "ja" else ["which", "where"])):
                return "cafe-clarification-needed"
        
        # 会議室の曖昧性チェック
        if any(kw in text_lower for kw in meeting_keywords):
            if any(word in text_lower for word in (["どこ", "どちら"] if language == "ja" else ["which", "what"])):
                return "meeting-room-clarification-needed"
        
        return None

    async def text_to_speech(
        self,
        text: str,
        language: Optional[str] = None,
        emotion: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        テキストを音声に変換
        
        - 言語自動検出（language未指定時）
        - 曖昧性チェック（ClarificationAgent統合）
        - TTSプロバイダ切り替え（voicevox / google）
        """
        # ステップ1: 言語自動検出（未指定時）
        if language is None:
            try:
                language = await self.language_processor.detect(text)
                logger.info(f"Language auto-detected: {language}")
            except Exception as e:
                logger.warning(f"Language detection failed: {e}, using default 'ja'")
                language = "ja"
        
        # ステップ2: 感情タグパースとテキスト前処理
        parsed = parse_emotion_tags(text)
        cleaned = clean_text_for_tts(parsed.clean_text)
        processed = preprocess_tts(cleaned, language)

        vrm_emotion = map_to_vrm_emotion(emotion) if emotion else (parsed.primary_emotion or "neutral")
        
        # ステップ3: 曖昧性チェック
        ambiguity_category = self._detect_category(text, language)
        if ambiguity_category:
            logger.info(f"Ambiguity detected: {ambiguity_category}")
            try:
                clarification_result = await self.clarification_agent.handle_clarification(
                    query=text,
                    category=ambiguity_category,
                    language=language,
                )
                clarification_text = clarification_result["response"]
                logger.info("Using clarification response instead of original query")
                processed = preprocess_tts(clarification_text, language)
                vrm_emotion = clarification_result.get("emotion", "surprised")
            except Exception as e:
                logger.error(f"Clarification handling failed: {e}, proceeding with original text")
        
        # ステップ4: テキスト長チェック
        if len(processed.encode("utf-8")) > 5000:
            processed = truncate_by_bytes(processed, 5000)
            logger.warning("Text truncated to 5000 bytes")

        try:
            # ステップ5: Provider ごとの呼び出し分岐
            if self.tts_provider == "voicevox":
                audio_b64 = await self.tts_client.synthesize_wav_base64(processed, language)
            else:  # google
                tts_emotion = map_vrm_to_tts_emotion(vrm_emotion)
                audio_b64 = await self.tts_client.synthesize_mp3_base64(processed, language, tts_emotion)
            
            return {
                "success": True,
                "audioResponse": audio_b64,
                "emotion": vrm_emotion,
                "cleanText": processed,
                "format": "audio/wav" if self.tts_provider == "voicevox" else "audio/mpeg",
                "language": language,
                "ambiguity_resolved": ambiguity_category is not None,
            }
        except Exception as e:
            logger.exception("TTS failed, trying fallback: %s", e)
            fb_text = fallback_error_message(language)
            try:
                if self.tts_provider == "voicevox":
                    audio_b64 = await self.tts_client.synthesize_wav_base64(fb_text, language)
                else:
                    audio_b64 = await self.tts_client.synthesize_mp3_base64(fb_text, language, "sad")
                
                return {
                    "success": True,
                    "audioResponse": audio_b64,
                    "emotion": "sad",
                    "cleanText": fb_text,
                    "error": str(e),
                    "format": "audio/wav" if self.tts_provider == "voicevox" else "audio/mpeg",
                }
            except Exception as fallback_error:
                logger.error(f"Fallback TTS also failed: {fallback_error}")
                return {
                    "success": False,
                    "error": f"Failed to generate speech: {str(e)}",
                    "emotion": "confused",
                }
