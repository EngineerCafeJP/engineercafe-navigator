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

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

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

    async def synthesize_mp3_base64(self, text: str, lang: str, tts_emotion: str) -> str:
        token = self._get_access_token()
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


# -----------------------------------------------------------------------------
# VoiceAgent (Phase1: TTS only)
# -----------------------------------------------------------------------------


class VoiceAgent:
    def __init__(self, tts_client: Optional[GoogleTTSClient] = None):
        # Dependency injection friendly for tests
        self.tts_client = tts_client or GoogleTTSClient()

    async def text_to_speech(
        self,
        text: str,
        language: str = "ja",
        emotion: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = parse_emotion_tags(text)
        cleaned = clean_text_for_tts(parsed.clean_text)
        processed = preprocess_tts(cleaned, language)

        vrm_emotion = (
            map_to_vrm_emotion(emotion) if emotion else (parsed.primary_emotion or "neutral")
        )
        tts_emotion = map_vrm_to_tts_emotion(vrm_emotion)

        if len(processed.encode("utf-8")) > 5000:
            processed = truncate_by_bytes(processed, 5000)

        try:
            audio_b64 = await self.tts_client.synthesize_mp3_base64(
                processed, language, tts_emotion
            )
            return {
                "success": True,
                "audioResponse": audio_b64,
                "emotion": vrm_emotion,
                "cleanText": processed,
            }
        except Exception as e:
            logger.exception("TTS failed, trying fallback: %s", e)
            fb_text = fallback_error_message(language)
            try:
                audio_b64 = await self.tts_client.synthesize_mp3_base64(fb_text, language, "sad")
                return {
                    "success": True,
                    "audioResponse": audio_b64,
                    "emotion": "sad",
                    "cleanText": fb_text,
                    "error": str(e),
                }
            except Exception:
                return {
                    "success": False,
                    "error": f"Failed to generate speech: {str(e)}",
                    "emotion": "confused",
                }
