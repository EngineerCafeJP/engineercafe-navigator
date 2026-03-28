# TTS マイグレーションガイド: piper-plus

**Issue:** #371
**担当:** junfabregas4
**作成日:** 2026-03-28
**プロジェクト:** Engineer Cafe Navigator

---

## 1. 現行実装サマリー

現在の TTS は言語別に2つの provider を使い分けています:

- **日本語:** VOICEVOX (ローカル REST API, speaker #3 ずんだもん)
- **英語:** Kokoro TTS (ローカル REST API, voice af_bella)
- **フォールバック:** Google Cloud TTS (MP3 形式)

### データフロー

```
Frontend (VoiceInterface.tsx)
  → POST /api/voice { action: "text_to_speech", text, language }
  → Frontend proxy (route.ts)
  → Backend POST /api/voice
  → VoiceAgent.text_to_speech()
    ├─ 言語検出 (LanguageProcessor)
    ├─ Emotion タグ解析 + テキスト前処理
    ├─ 言語ルーティング:
    │   ├─ "en" → KokoroTTSClient → WAV
    │   ├─ "ja" + voicevox → VoiceVoxClient → WAV
    │   └─ google → GoogleTTSClient → MP3
    ├─ Base64 エンコード
    └─ VoiceResponse { audioResponse, emotion, format }
  → Frontend playAudio() + Lip-sync
```

### 主要ファイル

| ファイル | 役割 |
|---------|------|
| `backend/agents/voice_agent.py` | VoiceAgent, VoiceVoxClient, KokoroTTSClient (807行) |
| `backend/main.py:638-688` | `/api/voice` エンドポイント |
| `docker-compose.yml` | voicevox (port 50021), kokoro-tts (port 8880) |

### 現行パフォーマンス

| Provider | Cold Start | Warm レイテンシ | メモリ |
|----------|-----------|----------------|--------|
| VOICEVOX | 2-5秒 | 200-500ms | 4GB |
| Kokoro | 1-2秒 | 300-800ms | 2GB |
| Google TTS | - | 500ms-2秒 | - |

### 言語ルーティングロジック (voice_agent.py:751-768)

```python
if language == "en":
    audio_b64 = await self.kokoro_client.synthesize_wav_base64(processed, language)
    audio_format = "audio/wav"
elif self.tts_provider == "voicevox":
    audio_b64 = await self.tts_client.synthesize_wav_base64(processed, language)
    audio_format = "audio/wav"
else:  # google
    tts_emotion = map_vrm_to_tts_emotion(vrm_emotion)
    audio_b64 = await self.tts_client.synthesize_mp3_base64(processed, language, tts_emotion)
    audio_format = "audio/mpeg"
```

---

## 2. 目標

**既存の VOICEVOX/Kokoro 実装を維持したまま**、piper-plus を代替 TTS provider として追加する。

- `TTS_PROVIDER_JA=voicevox` (デフォルト、変更なし)
- `TTS_PROVIDER_EN=kokoro` (デフォルト、変更なし)
- `TTS_PROVIDER_JA=piper` / `TTS_PROVIDER_EN=piper` (新規追加)
- 言語別に独立して provider を切り替え可能
- VOICEVOX/Kokoro のコード・テスト・動作に一切影響を与えない

---

## 3. アーキテクチャ変更

### 3.1 Provider Pattern 導入

```
backend/agents/
├── voice_agent.py             ← Factory + VoiceAgent (既存ファイルを修正)
├── tts_providers/              ← 新規ディレクトリ
│   ├── __init__.py
│   ├── base.py                 ← 抽象基底クラス
│   ├── voicevox_provider.py    ← 既存 VoiceVoxClient を移動
│   ├── kokoro_provider.py      ← 既存 KokoroTTSClient を移動
│   ├── google_provider.py      ← 既存 GoogleTTSClient を移動
│   └── piper_provider.py      ← 新規
```

### 3.2 Provider Interface

```python
# backend/agents/tts_providers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TTSResult:
    """TTS provider の統一出力形式"""
    audio_data: bytes       # WAV or MP3 バイナリ
    format: str             # "audio/wav" or "audio/mpeg"
    sample_rate: int        # 例: 24000, 44100
    provider: str           # "voicevox", "kokoro", "piper", "google"


class BaseTTSProvider(ABC):
    """TTS provider の抽象基底クラス"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        language: str = "ja",
        speaker_id: Optional[int] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        """
        テキストを音声に変換する。

        Args:
            text: 合成テキスト (前処理済み, 最大 5000 bytes)
            language: 言語コード ("ja", "en")
            speaker_id: 話者 ID (VOICEVOX 用, 例: 3)
            voice: 音声モデル名 (Kokoro/piper 用, 例: "af_bella")
            speed: 再生速度 (1.0 = 通常)

        Returns:
            TTSResult

        Raises:
            RuntimeError: 合成失敗時
        """
        ...

    async def synthesize_wav_base64(
        self,
        text: str,
        language: str = "ja",
        **kwargs,
    ) -> str:
        """Base64 エンコード済み WAV を返す (既存 API との互換性)"""
        import base64

        result = await self.synthesize(text, language, **kwargs)
        return base64.b64encode(result.audio_data).decode("utf-8")

    async def health_check(self) -> bool:
        """Provider の健全性チェック (オプション)"""
        return True
```

### 3.3 Factory Pattern

```python
# backend/agents/tts_providers/__init__.py

from backend.agents.tts_providers.base import BaseTTSProvider, TTSResult


def create_tts_provider(provider_name: str, **kwargs) -> BaseTTSProvider:
    """TTS provider を作成する Factory"""

    if provider_name == "voicevox":
        from backend.agents.tts_providers.voicevox_provider import VoicevoxTTSProvider
        return VoicevoxTTSProvider(**kwargs)

    elif provider_name == "kokoro":
        from backend.agents.tts_providers.kokoro_provider import KokoroTTSProvider
        return KokoroTTSProvider(**kwargs)

    elif provider_name == "piper":
        from backend.agents.tts_providers.piper_provider import PiperTTSProvider
        return PiperTTSProvider(**kwargs)

    elif provider_name == "google":
        from backend.agents.tts_providers.google_provider import GoogleTTSProvider
        return GoogleTTSProvider(**kwargs)

    else:
        raise ValueError(f"Unknown TTS provider: {provider_name}")


__all__ = ["BaseTTSProvider", "TTSResult", "create_tts_provider"]
```

### 3.4 VoiceAgent の修正

`voice_agent.py` の `VoiceAgent.__init__` と言語ルーティングを修正:

```python
# backend/agents/voice_agent.py (修正箇所)

from backend.agents.tts_providers import create_tts_provider

class VoiceAgent:
    def __init__(
        self,
        tts_provider: str = "voicevox",     # 後方互換
        tts_client: Optional[Any] = None,   # テスト用 DI
        language_processor: Optional[LanguageProcessor] = None,
        clarification_agent: Optional[Any] = None,
    ):
        # 言語別 provider (環境変数で切り替え)
        self.tts_provider_ja = os.getenv("TTS_PROVIDER_JA", tts_provider)
        self.tts_provider_en = os.getenv("TTS_PROVIDER_EN", "kokoro")

        # Provider 初期化 (factory 経由)
        if tts_client:
            self.tts_client = tts_client  # テスト用 (日本語)
        else:
            self.tts_client = create_tts_provider(self.tts_provider_ja)

        self.tts_client_en = create_tts_provider(self.tts_provider_en)

        # ... 既存の language_processor, clarification_agent 初期化
```

### 3.5 言語ルーティングの修正

```python
# voice_agent.py text_to_speech() 内 (Lines 751-768 を修正)

if language == "en":
    # 英語 → TTS_PROVIDER_EN で指定された provider
    audio_b64 = await self.tts_client_en.synthesize_wav_base64(processed, language)
    audio_format = "audio/wav"
else:
    # 日本語 → TTS_PROVIDER_JA で指定された provider
    result = await self.tts_client.synthesize(processed, language)
    audio_b64 = base64.b64encode(result.audio_data).decode("utf-8")
    audio_format = result.format
```

### 3.6 環境変数による切り替え

```
# .env
TTS_PROVIDER_JA=voicevox   # デフォルト（既存動作）
TTS_PROVIDER_EN=kokoro     # デフォルト（既存動作）

# piper-plus に切り替え
# TTS_PROVIDER_JA=piper
# TTS_PROVIDER_EN=piper
```

---

## 4. 実装手順

### Step 1: `backend/agents/tts_providers/base.py` を作成

上記 3.2 の `BaseTTSProvider` と `TTSResult` を作成する。

`synthesize_wav_base64()` メソッドを基底クラスに実装し、既存の `VoiceVoxClient.synthesize_wav_base64()` / `KokoroTTSClient.synthesize_wav_base64()` との互換性を保つ。

### Step 2: `backend/agents/tts_providers/voicevox_provider.py` を作成

既存の `VoiceVoxClient` (voice_agent.py:440-520) のロジックを移動。

```python
# backend/agents/tts_providers/voicevox_provider.py

import base64
import logging
import os
from typing import Optional

import httpx

from backend.agents.tts_providers.base import BaseTTSProvider, TTSResult

logger = logging.getLogger(__name__)

DEFAULT_SPEAKER_JA = 3  # ずんだもん - Normal
DEFAULT_SPEAKER_EN = 3


class VoicevoxTTSProvider(BaseTTSProvider):
    """VOICEVOX REST API ベースの TTS provider"""

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = (
            api_url or os.getenv("VOICEVOX_API_URL", "http://localhost:50021")
        ).rstrip("/")
        self._initialized_speakers: set[int] = set()

    async def _initialize_speaker(self, speaker_id: int) -> None:
        if speaker_id in self._initialized_speakers:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.api_url}/initialize_speaker",
                    params={"speaker": speaker_id},
                )
            self._initialized_speakers.add(speaker_id)
        except Exception as e:
            logger.warning("Speaker init failed (non-fatal): %s", e)

    async def synthesize(
        self,
        text: str,
        language: str = "ja",
        speaker_id: Optional[int] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        sid = speaker_id or DEFAULT_SPEAKER_JA
        await self._initialize_speaker(sid)

        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Audio Query
            query_resp = await client.post(
                f"{self.api_url}/audio_query",
                params={"text": text, "speaker": sid},
            )
            if query_resp.status_code >= 400:
                raise RuntimeError(
                    f"VOICEVOX audio_query failed: {query_resp.status_code}"
                )
            audio_query = query_resp.json()

            # Speed 調整
            if speed != 1.0:
                audio_query["speedScale"] = speed

            # Step 2: Synthesis
            synth_resp = await client.post(
                f"{self.api_url}/synthesis",
                params={"speaker": sid},
                json=audio_query,
                headers={"Content-Type": "application/json"},
            )
            if synth_resp.status_code >= 400:
                raise RuntimeError(
                    f"VOICEVOX synthesis failed: {synth_resp.status_code}"
                )

        return TTSResult(
            audio_data=synth_resp.content,
            format="audio/wav",
            sample_rate=24000,  # VOICEVOX default
            provider="voicevox",
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.api_url}/version")
                return resp.status_code == 200
        except Exception:
            return False
```

**重要:** `voice_agent.py` 内の `VoiceVoxClient` は後方互換として alias を残す:

```python
# voice_agent.py 末尾
from backend.agents.tts_providers.voicevox_provider import VoicevoxTTSProvider as VoiceVoxClient
```

### Step 3: `backend/agents/tts_providers/kokoro_provider.py` を作成

既存の `KokoroTTSClient` (voice_agent.py:527-593) を移動。

```python
# backend/agents/tts_providers/kokoro_provider.py

import base64
import logging
import os
from typing import Optional

import httpx

from backend.agents.tts_providers.base import BaseTTSProvider, TTSResult

logger = logging.getLogger(__name__)

DEFAULT_VOICE_EN = "af_bella"


class KokoroTTSProvider(BaseTTSProvider):
    """Kokoro FastAPI ベースの TTS provider"""

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = (
            api_url or os.getenv("KOKORO_API_URL", "http://localhost:8880")
        ).rstrip("/")

    async def synthesize(
        self,
        text: str,
        language: str = "en",
        speaker_id: Optional[int] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        voice_name = voice or DEFAULT_VOICE_EN

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_url}/v1/audio/speech",
                json={
                    "model": "kokoro",
                    "input": text,
                    "voice": voice_name,
                    "response_format": "wav",
                    "speed": speed,
                },
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Kokoro synthesis failed: {resp.status_code} {resp.text}"
                )

        return TTSResult(
            audio_data=resp.content,
            format="audio/wav",
            sample_rate=24000,
            provider="kokoro",
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.api_url}/v1/audio/voices")
                return resp.status_code == 200
        except Exception:
            return False
```

### Step 4: `backend/agents/tts_providers/piper_provider.py` を作成 (新規)

```python
# backend/agents/tts_providers/piper_provider.py

import logging
import os
from typing import Optional

import httpx

from backend.agents.tts_providers.base import BaseTTSProvider, TTSResult

logger = logging.getLogger(__name__)

# piper-plus デフォルト設定
DEFAULT_PIPER_URL = "http://localhost:10200"
DEFAULT_VOICE_JA = "ja_JP-takumi-medium"   # ⚠️ 利用可能モデル要確認
DEFAULT_VOICE_EN = "en_US-amy-medium"      # ⚠️ 利用可能モデル要確認


class PiperTTSProvider(BaseTTSProvider):
    """piper-plus ベースの TTS provider

    piper-plus repository: https://github.com/ayutaz/piper-plus/

    ⚠️ piper-plus の REST API 仕様は PoC で検証が必要。
    以下は piper (rhasspy/piper) の一般的な HTTP API を想定。
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        voice_ja: Optional[str] = None,
        voice_en: Optional[str] = None,
    ):
        self.api_url = (
            api_url or os.getenv("PIPER_PLUS_URL", DEFAULT_PIPER_URL)
        ).rstrip("/")
        self.voice_ja = voice_ja or os.getenv("PIPER_VOICE_JA", DEFAULT_VOICE_JA)
        self.voice_en = voice_en or os.getenv("PIPER_VOICE_EN", DEFAULT_VOICE_EN)

    def _get_voice(self, language: str, voice: Optional[str] = None) -> str:
        """言語に応じた音声モデルを返す"""
        if voice:
            return voice
        if language == "en":
            return self.voice_en
        return self.voice_ja

    async def synthesize(
        self,
        text: str,
        language: str = "ja",
        speaker_id: Optional[int] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> TTSResult:
        if not text or not text.strip():
            raise RuntimeError("Empty text for TTS synthesis")

        voice_model = self._get_voice(language, voice)

        # ⚠️ piper-plus の正確な API エンドポイントは PoC で検証が必要
        # 以下は piper HTTP server の一般的なパターン
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_url}/api/tts",
                json={
                    "text": text,
                    "voice": voice_model,
                    "output_format": "wav",
                    "speed": speed,
                    "speaker_id": speaker_id,
                },
            )

            if resp.status_code >= 400:
                # フォールバック: GET パラメータ形式を試行
                # ⚠️ piper-plus が GET/POST どちらをサポートするか要確認
                resp = await client.get(
                    f"{self.api_url}/api/tts",
                    params={
                        "text": text,
                        "voice": voice_model,
                    },
                )
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"piper-plus synthesis failed: {resp.status_code} {resp.text}"
                    )

        # piper の出力は WAV (16-bit PCM)
        audio_data = resp.content

        # WAV ヘッダ検証
        if audio_data[:4] != b"RIFF":
            raise RuntimeError(
                f"piper-plus returned unexpected format "
                f"(expected WAV, got {audio_data[:4]!r})"
            )

        return TTSResult(
            audio_data=audio_data,
            format="audio/wav",
            sample_rate=22050,  # piper default (⚠️ モデルにより異なる)
            provider="piper",
        )

    async def health_check(self) -> bool:
        """piper-plus の健全性チェック"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # ⚠️ health check エンドポイントは piper-plus の実装による
                resp = await client.get(f"{self.api_url}/api/voices")
                return resp.status_code == 200
        except Exception:
            return False
```

### Step 5: VoiceAgent の言語ルーティング修正

`voice_agent.py` の `text_to_speech()` メソッド内の言語ルーティング (Lines 751-768) を修正:

```python
# voice_agent.py text_to_speech() 内 (修正後)

import base64

if language == "en":
    # 英語 provider で合成
    result = await self.tts_client_en.synthesize(
        processed, language=language, speed=1.0,
    )
    audio_b64 = base64.b64encode(result.audio_data).decode("utf-8")
    audio_format = result.format
else:
    # 日本語 provider で合成
    result = await self.tts_client.synthesize(
        processed, language=language, speed=1.0,
    )
    audio_b64 = base64.b64encode(result.audio_data).decode("utf-8")
    audio_format = result.format
```

### Step 6: piper-plus Docker サービス追加

```yaml
# docker-compose.yml (追加)

services:
  # ... 既存の voicevox, kokoro-tts, backend ...

  piper-tts:
    image: ghcr.io/ayutaz/piper-plus:latest  # ⚠️ 正確なイメージ名要確認
    container_name: engineer-cafe-piper-tts
    ports:
      - "10200:10200"
    volumes:
      - piper-models:/app/models
    environment:
      - PIPER_PORT=10200
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:10200/api/voices"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped
    networks:
      - engineer-cafe-network

volumes:
  # ... 既存 volumes ...
  piper-models:
```

**production 用 (docker-compose.production.yml):**

```yaml
  piper-tts:
    image: ghcr.io/ayutaz/piper-plus:latest  # ⚠️ 要確認
    expose:
      - "10200"
    volumes:
      - piper-models:/app/models
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512M
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    restart: unless-stopped
    networks:
      - engineer-cafe-network
```

### Step 7: テスト追加

```python
# backend/tests/agents/test_tts_providers.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.agents.tts_providers import create_tts_provider, TTSResult
from backend.agents.tts_providers.base import BaseTTSProvider


class TestTTSProviderFactory:
    def test_create_voicevox_provider(self):
        provider = create_tts_provider("voicevox")
        assert isinstance(provider, BaseTTSProvider)

    def test_create_kokoro_provider(self):
        provider = create_tts_provider("kokoro")
        assert isinstance(provider, BaseTTSProvider)

    def test_create_piper_provider(self):
        provider = create_tts_provider("piper")
        assert isinstance(provider, BaseTTSProvider)

    def test_create_google_provider(self):
        provider = create_tts_provider("google")
        assert isinstance(provider, BaseTTSProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            create_tts_provider("unknown")


class TestPiperProvider:
    def test_init_default(self):
        from backend.agents.tts_providers.piper_provider import PiperTTSProvider
        provider = PiperTTSProvider()
        assert "10200" in provider.api_url

    def test_init_custom_url(self):
        from backend.agents.tts_providers.piper_provider import PiperTTSProvider
        provider = PiperTTSProvider(api_url="http://custom:9999")
        assert provider.api_url == "http://custom:9999"

    def test_get_voice_ja(self):
        from backend.agents.tts_providers.piper_provider import PiperTTSProvider
        provider = PiperTTSProvider()
        voice = provider._get_voice("ja")
        assert "ja" in voice.lower()

    def test_get_voice_en(self):
        from backend.agents.tts_providers.piper_provider import PiperTTSProvider
        provider = PiperTTSProvider()
        voice = provider._get_voice("en")
        assert "en" in voice.lower()

    def test_get_voice_custom(self):
        from backend.agents.tts_providers.piper_provider import PiperTTSProvider
        provider = PiperTTSProvider()
        voice = provider._get_voice("ja", voice="custom_voice")
        assert voice == "custom_voice"

    @pytest.mark.asyncio
    async def test_synthesize_empty_text_raises(self):
        from backend.agents.tts_providers.piper_provider import PiperTTSProvider
        provider = PiperTTSProvider()
        with pytest.raises(RuntimeError, match="Empty text"):
            await provider.synthesize("", language="ja")


class TestTTSResultDataclass:
    def test_create_result(self):
        result = TTSResult(
            audio_data=b"RIFF...",
            format="audio/wav",
            sample_rate=22050,
            provider="piper",
        )
        assert result.format == "audio/wav"
        assert result.provider == "piper"


class TestVoicevoxProvider:
    """既存 VOICEVOX の provider 化が後方互換であることを確認"""

    def test_init(self):
        from backend.agents.tts_providers.voicevox_provider import VoicevoxTTSProvider
        provider = VoicevoxTTSProvider()
        assert "50021" in provider.api_url


class TestKokoroProvider:
    """既存 Kokoro の provider 化が後方互換であることを確認"""

    def test_init(self):
        from backend.agents.tts_providers.kokoro_provider import KokoroTTSProvider
        provider = KokoroTTSProvider()
        assert "8880" in provider.api_url
```

---

## 5. Provider インターフェース仕様

### Input

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `text` | `str` | Yes | 合成テキスト (前処理済み, 最大 5000 bytes) |
| `language` | `str` | Yes | `"ja"` or `"en"` |
| `speaker_id` | `Optional[int]` | No | VOICEVOX 話者 ID (例: 3) |
| `voice` | `Optional[str]` | No | 音声モデル名 (例: "af_bella", "ja_JP-takumi-medium") |
| `speed` | `float` | No | 再生速度 (デフォルト 1.0) |

### Output: `TTSResult`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `audio_data` | `bytes` | WAV or MP3 バイナリ |
| `format` | `str` | `"audio/wav"` or `"audio/mpeg"` |
| `sample_rate` | `int` | サンプルレート (例: 22050, 24000) |
| `provider` | `str` | `"voicevox"`, `"kokoro"`, `"piper"`, `"google"` |

### 必須処理

- 空テキスト: `RuntimeError` を raise
- 長テキスト (>5000 chars): `VoiceAgent.text_to_speech()` で事前に truncation 済み (provider では処理不要)
- Emotion タグ: `VoiceAgent` で事前にパースされている。provider は clean text を受け取る
- タイムアウト: 30秒

---

## 6. piper-plus 固有の注意点

### 6.1 ONNX Runtime ベース

piper-plus は ONNX Runtime を使用しており、GPU なしで高速推論が可能。これは VOICEVOX (CPU_NUM_THREADS 依存) や Kokoro (CPU 版イメージ使用) と同等の環境で動作する。

### 6.2 日本語モデルの可用性

⚠️ **PoC 検証が必要:**

- piper-plus が日本語モデルを提供しているか確認
- 利用可能な日本語音声の品質を VOICEVOX と比較
- 日本語モデルが存在しない場合、piper-plus は英語専用として使い、日本語は引き続き VOICEVOX を使用

### 6.3 音声モデル選択

| 言語 | デフォルトモデル | 備考 |
|------|---------------|------|
| 日本語 | `ja_JP-takumi-medium` | ⚠️ 存在確認要 |
| 英語 | `en_US-amy-medium` | piper standard voice |

**モデル一覧取得:**
```bash
# piper-plus のモデル一覧を確認
curl http://localhost:10200/api/voices
```

### 6.4 レスポンス形式

piper は WAV (16-bit PCM) を出力する。これはフロントエンドの `AudioDataProcessor.detectAudioFormat()` と互換性がある。

### 6.5 piper-plus リポジトリ

- Repository: https://github.com/ayutaz/piper-plus/
- オリジナル piper: https://github.com/rhasspy/piper

### ⚠️ PoC 検証が必要な項目

1. **piper-plus の REST API 仕様** — エンドポイント URL、リクエスト/レスポンス形式
2. **Docker イメージ** — `ghcr.io/ayutaz/piper-plus:latest` で正しいか
3. **日本語モデルの有無と品質** — VOICEVOX との比較
4. **出力サンプルレート** — 22050Hz or 24000Hz (モデル依存)
5. **Health check エンドポイント** — `/api/voices` で良いか
6. **同時リクエスト処理** — 複数ユーザー同時使用時の性能

---

## 7. 環境変数

| 環境変数 | デフォルト | 説明 |
|---------|----------|------|
| `TTS_PROVIDER_JA` | `voicevox` | 日本語 TTS: `voicevox` \| `piper` \| `google` |
| `TTS_PROVIDER_EN` | `kokoro` | 英語 TTS: `kokoro` \| `piper` \| `google` |
| `PIPER_PLUS_URL` | `http://localhost:10200` | piper-plus サービス URL |
| `PIPER_VOICE_JA` | `ja_JP-takumi-medium` | 日本語音声モデル名 |
| `PIPER_VOICE_EN` | `en_US-amy-medium` | 英語音声モデル名 |
| `VOICEVOX_API_URL` | `http://localhost:50021` | (既存、変更なし) |
| `KOKORO_API_URL` | `http://localhost:8880` | (既存、変更なし) |

### .env 設定例

```bash
# デフォルト（既存動作、変更不要）
TTS_PROVIDER_JA=voicevox
TTS_PROVIDER_EN=kokoro

# piper-plus に全面切り替え
TTS_PROVIDER_JA=piper
TTS_PROVIDER_EN=piper
PIPER_PLUS_URL=http://piper-tts:10200

# 日本語は VOICEVOX、英語のみ piper
TTS_PROVIDER_JA=voicevox
TTS_PROVIDER_EN=piper
PIPER_PLUS_URL=http://piper-tts:10200
```

---

## 8. Docker / デプロイ

### 8.1 piper-plus Docker サービス

```yaml
# docker-compose.yml (piper-tts サービス追加)
piper-tts:
  image: ghcr.io/ayutaz/piper-plus:latest  # ⚠️ 正確なイメージ名要確認
  container_name: engineer-cafe-piper-tts
  ports:
    - "10200:10200"
  volumes:
    - piper-models:/app/models
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:10200/api/voices"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s
  networks:
    - engineer-cafe-network
```

### 8.2 イメージサイズ

| サービス | イメージサイズ |
|---------|-------------|
| VOICEVOX | ~2.5GB |
| Kokoro | ~1.5GB |
| piper-plus | ~50-100MB (⚠️ 要確認) + モデル (~50MB/voice) |

### 8.3 backend の依存関係

piper-plus を使用する場合、`backend` サービスの `depends_on` を更新:

```yaml
backend:
  depends_on:
    voicevox:
      condition: service_healthy
    kokoro-tts:
      condition: service_healthy
    piper-tts:
      condition: service_healthy  # piper 使用時のみ必要
  environment:
    - TTS_PROVIDER_JA=${TTS_PROVIDER_JA:-voicevox}
    - TTS_PROVIDER_EN=${TTS_PROVIDER_EN:-kokoro}
    - PIPER_PLUS_URL=http://piper-tts:10200
```

**注意:** `depends_on` に piper-tts を追加すると、piper を使わない場合もコンテナが起動する。これを避けるには Docker Compose profiles を使用:

```yaml
piper-tts:
  profiles:
    - piper  # docker compose --profile piper up で起動
```

### 8.4 Health check

```bash
# piper-plus の Health check
curl -f http://localhost:10200/api/voices

# VOICEVOX の Health check (既存)
curl -f http://localhost:50021/version

# Kokoro の Health check (既存)
curl -f http://localhost:8880/v1/audio/voices
```

---

## 9. テスト計画

### 9.1 Unit テスト

| テスト | 内容 |
|--------|------|
| Factory テスト | `create_tts_provider("voicevox")`, `("kokoro")`, `("piper")`, `("google")`, `("unknown")` |
| TTSResult テスト | dataclass の作成 |
| PiperProvider init | デフォルト URL、カスタム URL |
| Voice 選択 | `_get_voice("ja")`, `_get_voice("en")`, custom voice |
| 空テキスト | `synthesize("")` で RuntimeError |
| VoicevoxProvider init | 後方互換確認 |
| KokoroProvider init | 後方互換確認 |

### 9.2 Integration テスト

| テスト | 内容 |
|--------|------|
| VOICEVOX 合成 | 既存テストがそのまま通ること |
| Kokoro 合成 | 既存テストがそのまま通ること |
| piper 合成 | テストテキスト → WAV audio |
| Provider 切り替え | `TTS_PROVIDER_JA` / `TTS_PROVIDER_EN` 環境変数 |
| 言語ルーティング | 日本語 → JA provider, 英語 → EN provider |

### 9.3 主観評価 (Subjective)

| テスト | 内容 |
|--------|------|
| 日本語品質 | VOICEVOX vs piper の聴き比べ (5段階評価) |
| 英語品質 | Kokoro vs piper の聴き比べ |
| 自然さ | イントネーション、ポーズ、発音の自然さ |

### 9.4 Performance ベンチマーク

| メトリクス | 目標 | 計測方法 |
|-----------|------|---------|
| レイテンシ (日本語 100文字) | VOICEVOX の 50% 以下 | p50, p95 計測 |
| レイテンシ (英語 100 words) | Kokoro と同等 | p50, p95 計測 |
| メモリ使用量 | 512MB 以下 | Docker stats |
| Cold Start | 10秒以下 | コンテナ起動→Health check |

---

## 10. 受入基準

### 必須 (P0)

- [ ] `TTS_PROVIDER_JA=voicevox` + `TTS_PROVIDER_EN=kokoro` (デフォルト) で既存動作が一切変わらないこと
- [ ] `TTS_PROVIDER_JA=piper` で piper-plus による日本語音声合成が動作すること
- [ ] `TTS_PROVIDER_EN=piper` で piper-plus による英語音声合成が動作すること
- [ ] Provider factory (`create_tts_provider`) が正しく provider を選択すること
- [ ] `BaseTTSProvider` 抽象クラスと `TTSResult` dataclass が定義されていること
- [ ] 出力形式が WAV であること (フロントエンドの Lip-sync と互換)
- [ ] 既存テストが全て通ること
- [ ] 新規テスト (factory, piper provider) が追加されていること
- [ ] ruff / black が通ること
- [ ] docker-compose.yml に piper-tts サービスが追加されていること

### 推奨 (P1)

- [ ] VOICEVOX vs piper の品質比較レポート (日本語)
- [ ] Kokoro vs piper の品質比較レポート (英語)
- [ ] レイテンシベンチマーク (目標: VOICEVOX の 50% 以下)
- [ ] Docker Compose profiles による条件起動

### 将来対応 (P2)

- [ ] Emotion サポート (piper が SSML をサポートする場合)
- [ ] 複数話者切り替え
- [ ] Cloud Run 用の piper-plus サービス設定

---

## 変更しないもの

| 対象 | 理由 |
|------|------|
| `frontend/` 全体 | TTS provider の切り替えはバックエンド内部の問題。フロントエンドは WAV/MP3 の Base64 を受け取るだけ |
| `backend/main.py` の `voice_api()` | VoiceAgent のインターフェースは変わらない |
| `VoiceResponse` Pydantic モデル | レスポンス形式は変わらない |
| Emotion タグ解析 (`parse_emotion_tags`, `map_to_vrm_emotion`) | provider の前段で処理済み |
| テキスト前処理 (`clean_text_for_tts`, `preprocess_tts`) | provider の前段で処理済み |
| Lip-sync 処理 (フロントエンド) | WAV 形式であれば互換 |
| `backend/agents/stt_agent.py` | STT は別の Issue (#370) |
| VOICEVOX Docker サービス設定 | 既存サービスはそのまま |
| Kokoro Docker サービス設定 | 既存サービスはそのまま |

---

## 付録 A: ファイル作成・変更一覧

### 新規作成

| ファイル | 説明 |
|---------|------|
| `backend/agents/tts_providers/__init__.py` | Factory + exports |
| `backend/agents/tts_providers/base.py` | BaseTTSProvider, TTSResult |
| `backend/agents/tts_providers/voicevox_provider.py` | VOICEVOX 実装 (既存ロジック移動) |
| `backend/agents/tts_providers/kokoro_provider.py` | Kokoro 実装 (既存ロジック移動) |
| `backend/agents/tts_providers/google_provider.py` | Google TTS 実装 (既存ロジック移動) |
| `backend/agents/tts_providers/piper_provider.py` | piper-plus 実装 (新規) |
| `backend/tests/agents/test_tts_providers.py` | Provider テスト |

### 修正

| ファイル | 変更内容 |
|---------|---------|
| `backend/agents/voice_agent.py` | Provider factory を使用するように `__init__` と言語ルーティングを修正。VoiceVoxClient/KokoroTTSClient の alias を残す |
| `docker-compose.yml` | piper-tts サービス追加、backend の環境変数追加 |
| `docker-compose.production.yml` | piper-tts サービス追加 |

### 変更なし

| ファイル |
|---------|
| `frontend/` (全て) |
| `backend/main.py` |
| `backend/agents/stt_agent.py` |

---

## 付録 B: 開発環境セットアップ

```bash
# 1. ブランチ作成
git checkout develop
git pull origin develop
git checkout -b feat/371-tts-piper-plus

# 2. piper-plus コンテナ起動
docker compose --profile piper up -d piper-tts
# or
docker run -d -p 10200:10200 ghcr.io/ayutaz/piper-plus:latest  # ⚠️ 要確認

# 3. piper-plus の動作確認
curl http://localhost:10200/api/voices          # モデル一覧
curl -X POST http://localhost:10200/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world","voice":"en_US-amy-medium"}' \
  --output test.wav                             # 音声合成テスト

# 4. テスト実行
cd backend
pytest tests/agents/test_tts_providers.py -v
pytest -m "not slow and not ragas" --tb=short -q

# 5. Lint
ruff check .
black --check .

# 6. piper モードで動作確認
TTS_PROVIDER_JA=piper TTS_PROVIDER_EN=piper \
  PIPER_PLUS_URL=http://localhost:10200 \
  python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
