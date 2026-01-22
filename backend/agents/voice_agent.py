# backend/agents/voice_agent.py
import os
import re
import json
import time
import base64
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple

import httpx  # already in requirements

logger = logging.getLogger(__name__)

# -----------------------------
# Emotion mapping (TS準拠)
# -----------------------------
SUPPORTED_VRM_EMOTIONS = {"neutral", "happy", "sad", "angry", "surprised", "relaxed"}

# TS: EmotionMapping.VRM_EMOTION_MAP を移植
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
    if not isinstance(emotion, str):
        return False
    return emotion.lower().strip() in VRM_EMOTION_MAP  # TS isSupportedEmotion
def map_to_vrm_emotion(emotion: Any) -> str:
    if not isinstance(emotion, str):
        return "neutral"  # TS normalize behavior
    return VRM_EMOTION_MAP.get(emotion.lower().strip(), "neutral")

def map_vrm_to_tts_emotion(vrm_emotion: str) -> str:
    """
    VRM(6種) → TTS(音声側: happy/sad/excited/calm/angry) へ変換
    TSの音声サービス側(EMOTION_VOICE_PARAMS)に合わせるための変換
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

# -----------------------------
# EmotionTagParser (TS準拠)
# -----------------------------
EMOTION_TAG_REGEX = re.compile(r"\[\/?([a-zA-Z_]+)(?::(\d*\.?\d+))?\]")

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

        # TS: aliasチェックして、対応してる場合のみ採用
        if is_supported_emotion_alias(raw):
            vrm_emotion = map_to_vrm_emotion(raw)  # TS mapToVRMEmotion
            emotions.append(EmotionTag(emotion=vrm_emotion, position=pos, intensity=intensity))
        else:
            logger.warning("Unknown emotion tag: [%s]", raw)

    clean = EMOTION_TAG_REGEX.sub("", text).strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    primary = None
    if emotions:
        # TS: intensity降順ソート先頭
        primary = sorted(emotions, key=lambda e: e.intensity, reverse=True)[0].emotion

    return ParsedResponse(clean_text=clean, emotions=emotions, primary_emotion=primary)

# -----------------------------
# TTS preprocess (TS準拠: MTG置換)
# -----------------------------
def preprocess_tts(text: str, lang: str) -> str:
    # TS: MTG -> ミーティング/meeting
    replacement = "ミーティング" if lang == "ja" else "meeting"
    return re.sub(r"\bMTG\b", replacement, text, flags=re.IGNORECASE)

# -----------------------------
# TTS text cleaning (VoiceOutputAgent準拠)
# -----------------------------
def clean_text_for_tts(text: str) -> str:
    # TS voice-output-agent.ts のcleanTextForTTSを移植
    t = text
    t = re.sub(r"\*\*", "", t)                       # bold
    t = re.sub(r"\*", "", t)                         # italic/list markers
    t = re.sub(r"^\d+\.\s*", "", t, flags=re.M)      # numbered list
    t = re.sub(r"^#+\s+", "", t, flags=re.M)         # headers
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)   # links -> text
    t = re.sub(r"```[^`]*```", "", t)                # code blocks (simple)
    t = re.sub(r"`([^`]+)`", r"\1", t)               # inline code
    t = re.sub(r"\s+", " ", t).strip()
    return t

def truncate_by_bytes(text: str, max_bytes: int = 5000) -> str:
    # TS: TextEncoderでbyte数チェックし超過なら文単位で削る
    def byte_len(s: str) -> int:
        return len(s.encode("utf-8"))

    truncated = text
    while byte_len(truncated) > max_bytes and truncated:
        # 日本語優先で「。」、次に英語句読点で分割
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
            # fallback: 句点系で削る
            parts = re.split(r"[.!?\n]", truncated)
            if len(parts) > 1:
                parts.pop()
                truncated = ". ".join([p.strip() for p in parts if p.strip()]).strip()
            else:
                truncated = truncated[:-10]
    return truncated.strip()

def fallback_error_message(lang: str) -> str:
    # TS voice-output-agent.ts 相当
    return "申し訳ございません。音声の生成に失敗しました。" if lang == "ja" else "I apologize, but I failed to generate the audio response."

# -----------------------------
# Google TTS (PR2で実装)
# -----------------------------
class GoogleTTSClient:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0  # epoch seconds

        # TS: GOOGLE_CLOUD_CREDENTIALS or GOOGLE_APPLICATION_CREDENTIALS を参照
        self.credentials_source = os.getenv("GOOGLE_CLOUD_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")

        # TS: デフォルトで config/service-account-key.json を探す
        self.default_key_path = "config/service-account-key.json"

    async def synthesize_mp3_base64(self, text: str, lang: str, tts_emotion: str) -> str:
        raise NotImplementedError("PR2で実装します")

# -----------------------------
# VoiceAgent (Phase1はTTSのみ)
# -----------------------------
class VoiceAgent:
    def __init__(self):
        self.tts_client = GoogleTTSClient()

    async def text_to_speech(self, text: str, language: str = "ja", emotion: Optional[str] = None) -> Dict[str, Any]:
        """
        返り値は main.py の VoiceResponse に詰めやすい dict を返す想定
        """
        parsed = parse_emotion_tags(text)  # tags removed & primaryEmotion
        clean = clean_text_for_tts(parsed.clean_text)
        processed = preprocess_tts(clean, language)

        # 感情決定: request.emotion 優先、なければ primaryEmotion、なければ neutral
        vrm_emotion = map_to_vrm_emotion(emotion) if emotion else (parsed.primary_emotion or "neutral")
        tts_emotion = map_vrm_to_tts_emotion(vrm_emotion)

        # 5000 bytes制限
        if len(processed.encode("utf-8")) > 5000:
            processed = truncate_by_bytes(processed, 5000)

        try:
            audio_b64 = await self.tts_client.synthesize_mp3_base64(processed, language, tts_emotion)
            return {
                "success": True,
                "audioResponse": audio_b64,
                "emotion": vrm_emotion,
                "cleanText": processed,
            }
        except Exception as e:
            logger.exception("TTS failed, trying fallback: %s", e)
            fallback_text = fallback_error_message(language)
            try:
                audio_b64 = await self.tts_client.synthesize_mp3_base64(fallback_text, language, "sad")
                return {
                    "success": True,
                    "audioResponse": audio_b64,
                    "emotion": "sad",
                    "cleanText": fallback_text,
                    "error": str(e),
                }
            except Exception:
                return {"success": False, "error": f"Failed to generate speech: {str(e)}", "emotion": "confused"}


# backend/agents/voice_agent.py 追記（PR2）
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

# ... GoogleTTSClient class 内に実装

class GoogleTTSClient:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        self.credentials_source = os.getenv("GOOGLE_CLOUD_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        self.default_key_path = "config/service-account-key.json"

    def _load_credentials(self):
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]  # TSと同じスコープ

        # TSと同様: envがパスならそれ、JSON文字列ならparse、無ければdefaultファイル
        src = self.credentials_source
        if src:
            # path
            if os.path.exists(src):
                return service_account.Credentials.from_service_account_file(src, scopes=scopes)
            # json string
            try:
                info = json.loads(src)
                return service_account.Credentials.from_service_account_info(info, scopes=scopes)
            except Exception as e:
                logger.warning("Failed to parse GOOGLE_CLOUD_CREDENTIALS as JSON: %s", e)

        # fallback default path
        if os.path.exists(self.default_key_path):
            return service_account.Credentials.from_service_account_file(self.default_key_path, scopes=scopes)

        raise RuntimeError(
            f"Service account key not found. Set GOOGLE_CLOUD_CREDENTIALS/GOOGLE_APPLICATION_CREDENTIALS or place {self.default_key_path}"
        )

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expiry:
            return self._access_token

        creds = self._load_credentials()
        creds.refresh(GoogleAuthRequest())
        if not creds.token:
            raise RuntimeError("Failed to obtain access token")

        # 55分キャッシュ（TSと同じ思想）
        self._access_token = creds.token
        self._token_expiry = now + 55 * 60
        return self._access_token

    def _tts_params(self, lang: str, tts_emotion: str) -> Dict[str, Any]:
        # TSの EMOTION_VOICE_PARAMS を最小限再現
        # ja base: speed 1.3, pitch 2.5, volume 2.0, speaker ja-JP-Wavenet-B
        # en base: speed 1.05, pitch 0.3, volume 2.5, speaker en-GB-Standard-F
        if lang == "ja":
            speaker = "ja-JP-Wavenet-B"
            speed = 1.3
            pitch = 2.5
            volume = 2.0
        else:
            speaker = "en-GB-Standard-F"
            speed = 1.05
            pitch = 0.3
            volume = 2.5

        # emotion adjust（TSの係数に寄せる）
        if lang == "ja":
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
        else:
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

        language_code = "ja-JP" if lang == "ja" else "en-GB"  # TS準拠
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
                "audioEncoding": "MP3",  # TSと同じ
                "speakingRate": params["speakingRate"],
                "pitch": params["pitch"],
                "volumeGainDb": params["volumeGainDb"],
                "effectsProfileId": ["telephony-class-application"],  # TSと同じ
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

# """
# VoiceAgent骨組み（専門エンジニア向け）

# 音声処理（STT/TTS）を担当するエージェント。
# ユーザーの音声入力を認識し、システムの応答を音声で返す。

# 参考:
# - docs/migration/agents/voice-agent/README.md
# - engineer-cafe-navigator-repo/src/mastra/agents/voice-agent.ts (Mastra版)

# 2026年1月20日追記：frontend/src/_reference/mastra/agents/voice-output-agent.ts

# TODO (専門エンジニア - Chie, takegg0311):
# 2026年1月20日追記：たけがわやります
# 1. Google Cloud STT (Speech-to-Text) 連携
# 2. Google Cloud TTS (Text-to-Speech) 連携
# 3. STT補正システム実装（発音の揺らぎ補正）
# 4. 感情タグ処理（応答テキストに含まれる感情を音声に反映）
# 5. 音声ファイル管理（一時ファイル保存/削除）
# 6. エラーハンドリングとフォールバック
# """

# import logging
# from typing import Dict, Any, Optional

# # TODO: 実装時に必要なインポート
# # from google.cloud import speech
# # from google.cloud import texttospeech
# # from llm.openrouter import OpenRouterProvider
# # from llm.models import get_model_config

# logger = logging.getLogger(__name__)


# class VoiceAgent:
#     """
#     VoiceAgent骨組み（専門エンジニア向け）

#     このクラスは骨組みのみを提供します。完全実装は専門エンジニア（Chie, takegg0311）が担当。
#     """

#     def __init__(self):
#         """
#         初期化

#         TODO:
#         - Google Cloud STTクライアントの初期化
#         - Google Cloud TTSクライアントの初期化
#         - 音声設定の読み込み（サンプリングレート、言語コード等）
#         """
#         logger.info("VoiceAgent骨組み初期化")
#         # TODO: Google Cloud クライアント等の初期化

#     async def speech_to_text(
#         self, audio_data: bytes, language_code: str = "ja-JP"
#     ) -> Dict[str, Any]:
#         """
#         音声をテキストに変換（STT）

#         Args:
#             audio_data: 音声データ（バイト列）
#             language_code: 言語コード（デフォルト: ja-JP）

#         Returns:
#             認識結果
#             {
#                 "text": str,  # 認識されたテキスト
#                 "confidence": float,  # 信頼度（0.0～1.0）
#                 "language": str  # 検出された言語
#             }

#         TODO:
#         - Google Cloud STT APIを使用
#         - 音声データの形式チェック
#         - 認識精度の閾値判定
#         - STT補正システムの適用（発音の揺らぎ補正）
#         """
#         logger.info(f"STT処理開始（骨組み）: language={language_code}")

#         # TODO: 実装
#         # プレースホルダー
#         return {"text": "", "confidence": 0.0, "language": language_code}

#     async def text_to_speech(
#         self,
#         text: str,
#         language_code: str = "ja-JP",
#         emotion: Optional[str] = None,
#     ) -> Dict[str, Any]:
#         """
#         テキストを音声に変換（TTS）

#         Args:
#             text: 変換するテキスト
#             language_code: 言語コード（デフォルト: ja-JP）
#             emotion: 感情タグ（"happy", "sad", "neutral"等）

#         Returns:
#             音声生成結果
#             {
#                 "audio_data": bytes,  # 音声データ
#                 "duration": float,  # 音声の長さ（秒）
#                 "file_path": str  # 一時ファイルパス（オプション）
#             }

#         TODO:
#         - Google Cloud TTS APIを使用
#         - 感情タグに応じた音声パラメータ調整（ピッチ、速度等）
#         - 音声ファイルの一時保存
#         - SSMLマークアップの使用
#         """
#         logger.info(f"TTS処理開始（骨組み）: text={text[:50]}..., emotion={emotion}")

#         # TODO: 実装
#         # プレースホルダー
#         return {"audio_data": b"", "duration": 0.0, "file_path": ""}

#     async def correct_speech_text(self, text: str) -> str:
#         """
#         STTで認識されたテキストを補正

#         Args:
#             text: STTで認識されたテキスト

#         Returns:
#             補正されたテキスト

#         TODO:
#         - カタカナ/ひらがなの統一
#         - 発音の揺らぎ補正（「えんじにあかふぇ」→「Engineer Cafe」）
#         - 固有名詞の補正
#         - LLMを使用した文脈補正
#         """
#         logger.info(f"STT補正処理（骨組み）: {text}")

#         # TODO: 実装
#         # プレースホルダー: そのまま返す
#         return text

#     async def extract_emotion_from_text(self, text: str) -> str:
#         """
#         テキストから感情タグを抽出

#         Args:
#             text: 応答テキスト（感情タグを含む可能性がある）

#         Returns:
#             感情タグ（"happy", "sad", "neutral", "excited"等）

#         TODO:
#         - テキスト内の感情マーカー検出（例: [happy], [sad]）
#         - LLMを使用した感情分析
#         - デフォルト感情の設定
#         """
#         logger.info(f"感情抽出（骨組み）: {text[:50]}...")

#         # TODO: 実装
#         # プレースホルダー
#         return "neutral"

#     async def process(
#         self, audio_data: Optional[bytes] = None, text: Optional[str] = None
#     ) -> Dict[str, Any]:
#         """
#         音声処理のメインエントリーポイント

#         Args:
#             audio_data: 音声データ（STTの場合）
#             text: テキストデータ（TTSの場合）

#         Returns:
#             処理結果
#             {
#                 "mode": str,  # "stt" or "tts"
#                 "text": str,  # STTの場合: 認識されたテキスト
#                 "audio_data": bytes,  # TTSの場合: 生成された音声
#                 "confidence": float,  # STTの場合: 信頼度
#                 "emotion": str  # 感情タグ
#             }

#         TODO:
#         - STT/TTSの自動判定
#         - エラーハンドリング
#         - ログ出力
#         """
#         logger.info("VoiceAgent処理開始（骨組み）")

#         try:
#             # TODO: 実装
#             if audio_data:
#                 # STTモード
#                 stt_result = await self.speech_to_text(audio_data)
#                 corrected_text = await self.correct_speech_text(stt_result["text"])

#                 return {
#                     "mode": "stt",
#                     "text": corrected_text,
#                     "confidence": stt_result["confidence"],
#                     "emotion": "neutral",
#                 }

#             elif text:
#                 # TTSモード
#                 emotion = await self.extract_emotion_from_text(text)
#                 tts_result = await self.text_to_speech(text, emotion=emotion)

#                 return {
#                     "mode": "tts",
#                     "audio_data": tts_result["audio_data"],
#                     "duration": tts_result["duration"],
#                     "emotion": emotion,
#                 }

#             else:
#                 raise ValueError("audio_data または text のどちらかが必要です")

#         except Exception as e:
#             logger.error(f"VoiceAgent処理エラー（骨組み）: {e}", exc_info=True)
#             # TODO: エラーハンドリング
#             return {"mode": "error", "error": str(e), "emotion": "confused"}