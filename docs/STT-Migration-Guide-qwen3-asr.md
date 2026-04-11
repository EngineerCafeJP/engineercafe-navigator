# STT マイグレーションガイド: qwen3-asr-1.7b

**Issue:** #370
**担当:** takegawa333
**作成日:** 2026-03-28
**プロジェクト:** Engineer Cafe Navigator

---

## 1. 現行実装サマリー

現在の STT は **Vosk** をプライマリ、**Google Cloud STT** をフォールバックとして使用しています。

### データフロー

```
ブラウザ (WebM/Opus)
  → Base64 エンコード
  → POST /api/voice (Frontend proxy)
  → POST /api/voice (Backend)
  → STTAgent.speech_to_text()
    → LocalSTTClient._sync_transcribe()
      ├─ WebM → WAV 変換 (pydub/ffmpeg)
      ├─ Vosk モデル読み込み (lazy, cached)
      ├─ KaldiRecognizer 推論
      └─ TranscriptionResult (text, confidence, language)
    → confidence < 0.4 → GoogleSTTClient (fallback)
  → VoiceResponse (transcript, confidence, language, provider)
```

### 主要ファイル

| ファイル | 役割 |
|---------|------|
| `backend/agents/stt_agent.py` | STTAgent, LocalSTTClient, GoogleSTTClient (785行) |
| `backend/main.py:548-605` | `_get_stt_agent()` 初期化, `_handle_stt()` ハンドラ |
| `frontend/src/app/api/voice/route.ts` | Frontend proxy (変更不要) |

### 現行パフォーマンス

| ステップ | 時間 |
|---------|------|
| WebM → WAV 変換 | 200-500ms |
| Vosk 推論 (0.5秒音声) | 100-300ms |
| 合計 (E2E) | 365-1,060ms |

---

## 2. 目標

**既存の Vosk 実装を維持したまま**、qwen3-asr-1.7b を代替 STT provider として追加する。

- `STT_PROVIDER=vosk` (デフォルト、変更なし)
- `STT_PROVIDER=qwen3` (新規追加)
- 環境変数で切り替え可能な Strategy Pattern を導入
- Vosk のコード・テスト・動作に一切影響を与えない

---

## 3. アーキテクチャ変更

### 3.1 Provider Pattern 導入

```
backend/agents/
├── stt_agent.py              ← Factory + STTAgent (既存ファイルを修正)
├── stt_providers/             ← 新規ディレクトリ
│   ├── __init__.py
│   ├── base.py                ← 抽象基底クラス
│   ├── vosk_provider.py       ← 既存 LocalSTTClient を移動
│   ├── google_provider.py     ← 既存 GoogleSTTClient を移動
│   └── qwen3_provider.py     ← 新規
```

### 3.2 Provider Interface

```python
# backend/agents/stt_providers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class STTResult:
    """STT provider の統一出力形式"""
    transcript: str
    confidence: Optional[float]  # 0.0-1.0, None = 不明
    detected_language: str       # "ja", "en"
    word_confidences: Optional[List[Dict[str, Any]]] = None
    provider: str = ""


class BaseSTTProvider(ABC):
    """STT provider の抽象基底クラス"""

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = "ja",
        grammar: Optional[List[str]] = None,
    ) -> STTResult:
        """
        音声データをテキストに変換する。

        Args:
            audio_data: 音声バイナリ (WAV or WebM)
            language: 言語コード ("ja", "en") or None (自動検出)
            grammar: ドメイン固有語彙リスト (provider がサポートする場合)

        Returns:
            STTResult

        Raises:
            RuntimeError: 推論失敗時
        """
        ...

    @abstractmethod
    async def transcribe_auto_detect(
        self,
        audio_data: bytes,
        grammar: Optional[Dict[str, List[str]]] = None,
    ) -> STTResult:
        """
        言語を自動検出して音声をテキストに変換する。

        Args:
            audio_data: 音声バイナリ
            grammar: 言語別ドメイン固有語彙

        Returns:
            STTResult (detected_language が設定される)
        """
        ...

    def convert_audio_to_wav(self, audio_data: bytes) -> bytes:
        """WebM/Opus → WAV 変換 (共通ユーティリティ)"""
        if audio_data[:4] == b"RIFF":
            return audio_data

        from pydub import AudioSegment
        import io

        MAX_AUDIO_UPLOAD_BYTES = 10 * 1024 * 1024
        if len(audio_data) > MAX_AUDIO_UPLOAD_BYTES:
            raise ValueError(
                f"Audio payload too large ({len(audio_data)} bytes). "
                f"Maximum: {MAX_AUDIO_UPLOAD_BYTES} bytes."
            )

        segment = AudioSegment.from_file(io.BytesIO(audio_data), format=None)
        normalized = segment.set_frame_rate(16000).set_sample_width(2).set_channels(1)

        wav_buffer = io.BytesIO()
        normalized.export(wav_buffer, format="wav")
        return wav_buffer.getvalue()
```

### 3.3 Factory Pattern

```python
# backend/agents/stt_providers/__init__.py

from backend.agents.stt_providers.base import BaseSTTProvider, STTResult


def create_stt_provider(provider_name: str, **kwargs) -> BaseSTTProvider:
    """STT provider を作成する Factory"""

    if provider_name == "vosk":
        from backend.agents.stt_providers.vosk_provider import VoskSTTProvider
        return VoskSTTProvider(**kwargs)

    elif provider_name == "qwen3":
        from backend.agents.stt_providers.qwen3_provider import Qwen3STTProvider
        return Qwen3STTProvider(**kwargs)

    elif provider_name == "google":
        from backend.agents.stt_providers.google_provider import GoogleSTTProvider
        return GoogleSTTProvider(**kwargs)

    else:
        raise ValueError(f"Unknown STT provider: {provider_name}")


__all__ = ["BaseSTTProvider", "STTResult", "create_stt_provider"]
```

### 3.4 STTAgent の修正

`stt_agent.py` の `STTAgent.__init__` を修正して factory を使用する:

```python
# backend/agents/stt_agent.py (修正箇所)

from backend.agents.stt_providers import create_stt_provider, STTResult

class STTAgent:
    def __init__(
        self,
        stt_provider: Optional[str] = None,
        stt_client: Optional[Any] = None,  # テスト用 DI
        use_grammar: bool = False,
        language_processor: Optional[Any] = None,
        confidence_threshold: float = 0.4,
        fallback_client: Optional[Any] = None,
    ):
        self.stt_provider = stt_provider or os.getenv("STT_PROVIDER", "vosk")
        self.use_grammar = use_grammar
        self.confidence_threshold = confidence_threshold

        # Provider 初期化 (factory 経由)
        if stt_client:
            self.stt_client = stt_client  # テスト用
        else:
            self.stt_client = create_stt_provider(self.stt_provider)

        # Fallback (Vosk の場合のみ Google へ fallback)
        if self.stt_provider == "vosk" and not fallback_client:
            self.fallback_client = create_stt_provider("google")
        else:
            self.fallback_client = fallback_client
```

### 3.5 `STT_PROVIDER` 環境変数による切り替え

```
# .env
STT_PROVIDER=vosk    # 明示推奨（Cloud Run イメージ同梱 Vosk を使う場合）
# STT_PROVIDER=qwen3  # qwen3-asr に切り替え
```

`main.py` の `_get_stt_agent()` は `STTAgent(stt_provider=os.getenv("STT_PROVIDER"))` で環境変数を渡す。
`STT_PROVIDER` 未設定時の既定は `STTAgent` 内で解決される（本番かつ未設定なら `google`、それ以外は `qwen0.6b-cpu`）。Vosk を既定にしたい場合は必ず `STT_PROVIDER=vosk` を設定すること。

---

## 4. 実装手順

### Step 1: `backend/agents/stt_providers/base.py` を作成

上記 3.2 の `BaseSTTProvider` と `STTResult` を作成する。

**注意:** 既存の `TranscriptionResult` (stt_agent.py:25-30 付近) との互換性を保つ。`STTResult` は `TranscriptionResult` を置き換えるのではなく、provider 層の出力として使用し、`STTAgent.speech_to_text()` 内部で `TranscriptionResult` → `STTResult` のマッピングを行う。

### Step 2: `backend/agents/stt_providers/vosk_provider.py` を作成

既存の `LocalSTTClient` (stt_agent.py:231-455) のロジックを `VoskSTTProvider` クラスに移動する。

```python
# backend/agents/stt_providers/vosk_provider.py

import asyncio
import concurrent.futures
import io
import json
import logging
import os
from typing import Any, Dict, List, Optional

from backend.agents.stt_providers.base import BaseSTTProvider, STTResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATHS: Dict[str, str] = {
    "ja": "models/vosk-model-ja",
    "en": "models/vosk-model-en-us",
}

WAV_RIFF_HEADER = b"RIFF"
MIN_WAV_HEADER_BYTES = 44


class VoskSTTProvider(BaseSTTProvider):
    """Vosk ベースの STT provider"""

    def __init__(self, model_paths: Optional[Dict[str, str]] = None):
        self.model_paths = {**DEFAULT_MODEL_PATHS, **(model_paths or {})}
        self._models: Dict[str, Any] = {}

    def _load_model(self, lang: str):
        if lang in self._models:
            return self._models[lang]

        try:
            from vosk import Model
        except ImportError:
            raise RuntimeError("Vosk not installed. pip install vosk")

        model_path = os.path.expanduser(self.model_paths[lang])
        if not os.path.exists(model_path):
            raise RuntimeError(
                f"Vosk model not found: {model_path}. "
                f"Download from https://alphacephei.com/vosk/models"
            )

        self._models[lang] = Model(model_path)
        logger.info("Loaded Vosk %s model from %s", lang, model_path)
        return self._models[lang]

    # ... 既存の _sync_transcribe, transcribe, transcribe_auto_detect を移動
    # TranscriptionResult → STTResult に変換して返す
```

**重要:** `stt_agent.py` 内の `LocalSTTClient` は削除せず、`VoskSTTProvider` からの import alias として残す。既存テストが壊れないようにする。

```python
# stt_agent.py 末尾 (後方互換)
from backend.agents.stt_providers.vosk_provider import VoskSTTProvider as LocalSTTClient
```

### Step 3: `backend/agents/stt_providers/google_provider.py` を作成

既存の `GoogleSTTClient` (stt_agent.py:456-510) を移動。

```python
# backend/agents/stt_providers/google_provider.py

from backend.agents.stt_providers.base import BaseSTTProvider, STTResult


class GoogleSTTProvider(BaseSTTProvider):
    """Google Cloud Speech-to-Text provider"""

    async def transcribe(
        self, audio_data: bytes, language: str = "ja", grammar=None
    ) -> STTResult:
        from google.cloud import speech_v1

        wav_data = self.convert_audio_to_wav(audio_data)

        client = speech_v1.SpeechClient()
        audio = speech_v1.RecognitionAudio(content=wav_data)
        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=f"{language}-{language.upper()}",
        )

        response = client.recognize(config=config, audio=audio)

        for result in response.results:
            if result.alternatives:
                return STTResult(
                    transcript=result.alternatives[0].transcript,
                    confidence=result.alternatives[0].confidence,
                    detected_language=language,
                    provider="google",
                )

        raise ValueError("Google STT returned no results")

    async def transcribe_auto_detect(self, audio_data, grammar=None) -> STTResult:
        return await self.transcribe(audio_data, language="ja", grammar=grammar)
```

### Step 4: `backend/agents/stt_providers/qwen3_provider.py` を作成 (新規)

```python
# backend/agents/stt_providers/qwen3_provider.py

import asyncio
import concurrent.futures
import io
import logging
import os
from typing import Dict, List, Optional

from backend.agents.stt_providers.base import BaseSTTProvider, STTResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "Qwen/Qwen3-ASR-1.7B"
DEFAULT_DEVICE = "cpu"


class Qwen3STTProvider(BaseSTTProvider):
    """Qwen3-ASR-1.7B ベースの STT provider"""

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.model_id = model_path or os.getenv(
            "QWEN3_ASR_MODEL_PATH", DEFAULT_MODEL_ID
        )
        self.device = device or os.getenv("QWEN3_ASR_DEVICE", DEFAULT_DEVICE)
        self._model = None
        self._processor = None

    def _load_model(self):
        """Lazy load qwen3-asr model"""
        if self._model is not None:
            return

        try:
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        except ImportError:
            raise RuntimeError(
                "transformers not installed. "
                "pip install transformers torch torchaudio"
            )

        logger.info(
            "Loading qwen3-asr model: %s (device=%s)",
            self.model_id, self.device,
        )

        self._processor = AutoProcessor.from_pretrained(
            self.model_id, trust_remote_code=True,
        )
        self._model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.model_id, trust_remote_code=True,
        )

        if self.device == "cuda":
            import torch
            if torch.cuda.is_available():
                self._model = self._model.to("cuda")
            else:
                logger.warning("CUDA requested but not available. Falling back to CPU.")
                self.device = "cpu"

        logger.info("qwen3-asr model loaded successfully")

    def _sync_transcribe(
        self, audio_data: bytes, language: Optional[str] = "ja",
    ) -> STTResult:
        """同期推論 (ThreadPoolExecutor で実行)"""
        import numpy as np
        import wave

        self._load_model()

        wav_data = self.convert_audio_to_wav(audio_data)

        bio = io.BytesIO(wav_data)
        with wave.open(bio, "rb") as wf:
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            audio_array = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            audio_array /= 32768.0  # Normalize to [-1.0, 1.0]

        # ⚠️ qwen3-asr の正確な API は PoC で検証が必要
        inputs = self._processor(
            audio_array, sampling_rate=sample_rate, return_tensors="pt",
        )

        if self.device == "cuda":
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        import torch
        with torch.no_grad():
            generated_ids = self._model.generate(
                **inputs, max_new_tokens=256,
                language=language,  # ⚠️ qwen3-asr 固有パラメータ要検証
            )

        transcription = self._processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]

        return STTResult(
            transcript=transcription.strip(),
            confidence=None,
            detected_language=language or "ja",
            provider="qwen3",
        )

    async def transcribe(
        self, audio_data: bytes, language: Optional[str] = "ja",
        grammar: Optional[List[str]] = None,
    ) -> STTResult:
        """非同期ラッパー"""
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(
                pool, lambda: self._sync_transcribe(audio_data, language),
            )

    async def transcribe_auto_detect(
        self, audio_data: bytes,
        grammar: Optional[Dict[str, List[str]]] = None,
    ) -> STTResult:
        """
        qwen3-asr は多言語対応のため、language=None で自動検出可能。
        ⚠️ 自動検出の精度は PoC で要検証
        """
        return await self.transcribe(audio_data, language=None, grammar=None)
```

### Step 5: Docker / モデルダウンロード

#### 5.1 requirements.txt への追加

```
# backend/requirements.txt (追加分 — qwen3 使用時のみ必要)
transformers>=4.40.0
torch>=2.0.0
torchaudio>=2.0.0
sentencepiece>=0.2.0
```

#### 5.2 Dockerfile 修正

```dockerfile
# backend/Dockerfile (追加箇所)

# qwen3-asr のモデルダウンロード (オプション)
ARG STT_PROVIDER=vosk
RUN if [ "$STT_PROVIDER" = "qwen3" ]; then \
    python -c "from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq; \
    AutoProcessor.from_pretrained('Qwen/Qwen3-ASR-1.7B', trust_remote_code=True); \
    AutoModelForSpeechSeq2Seq.from_pretrained('Qwen/Qwen3-ASR-1.7B', trust_remote_code=True)"; \
    fi
```

#### 5.3 モデルダウンロードスクリプト

```bash
# backend/scripts/download_qwen_model.sh
#!/bin/bash
set -e

MODEL_ID="${QWEN3_ASR_MODEL_PATH:-Qwen/Qwen3-ASR-1.7B}"

echo "Downloading qwen3-asr model: $MODEL_ID"

python -c "
from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
print('Downloading processor...')
AutoProcessor.from_pretrained('$MODEL_ID', trust_remote_code=True)
print('Downloading model...')
AutoModelForSpeechSeq2Seq.from_pretrained('$MODEL_ID', trust_remote_code=True)
print('Done.')
"

echo "Estimated disk usage: ~3.4GB"
```

### Step 6: テスト追加

```python
# backend/tests/agents/test_stt_providers.py

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from backend.agents.stt_providers import create_stt_provider, STTResult
from backend.agents.stt_providers.base import BaseSTTProvider


class TestSTTProviderFactory:
    def test_create_vosk_provider(self):
        provider = create_stt_provider("vosk")
        assert isinstance(provider, BaseSTTProvider)

    def test_create_qwen3_provider(self):
        provider = create_stt_provider("qwen3")
        assert isinstance(provider, BaseSTTProvider)

    def test_create_google_provider(self):
        provider = create_stt_provider("google")
        assert isinstance(provider, BaseSTTProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown STT provider"):
            create_stt_provider("unknown")


class TestQwen3Provider:
    def test_init_default(self):
        from backend.agents.stt_providers.qwen3_provider import Qwen3STTProvider
        provider = Qwen3STTProvider()
        assert provider.model_id == "Qwen/Qwen3-ASR-1.7B"
        assert provider.device == "cpu"

    def test_init_custom_model(self):
        from backend.agents.stt_providers.qwen3_provider import Qwen3STTProvider
        provider = Qwen3STTProvider(
            model_path="Qwen/Qwen3-ASR-0.6B", device="cuda",
        )
        assert provider.model_id == "Qwen/Qwen3-ASR-0.6B"

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_transcribe_with_real_model(self):
        """実モデル推論テスト (CI ではスキップ)"""
        from backend.agents.stt_providers.qwen3_provider import Qwen3STTProvider
        provider = Qwen3STTProvider()
        test_wav = _generate_silent_wav(16000, 1.0)
        result = await provider.transcribe(test_wav, language="ja")
        assert isinstance(result, STTResult)
        assert result.provider == "qwen3"


class TestSTTResultDataclass:
    def test_create_result(self):
        result = STTResult(
            transcript="テスト", confidence=0.95,
            detected_language="ja", provider="vosk",
        )
        assert result.transcript == "テスト"

    def test_optional_fields(self):
        result = STTResult(
            transcript="test", confidence=None,
            detected_language="en", provider="qwen3",
        )
        assert result.confidence is None


def _generate_silent_wav(sample_rate: int, duration: float) -> bytes:
    import struct, io, wave
    n_frames = int(sample_rate * duration)
    frames = struct.pack(f"<{n_frames}h", *([0] * n_frames))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)
    return buf.getvalue()
```

### Step 7: docker-compose.yml 更新

qwen3 はバックエンドコンテナ内で動作するため、新サービス追加は不要。環境変数のみ追加:

```yaml
# docker-compose.yml (backend サービスの environment に追加)
backend:
  environment:
    - STT_PROVIDER=${STT_PROVIDER:-vosk}
    - QWEN3_ASR_MODEL_PATH=${QWEN3_ASR_MODEL_PATH:-Qwen/Qwen3-ASR-1.7B}
    - QWEN3_ASR_DEVICE=${QWEN3_ASR_DEVICE:-cpu}
```

---

## 5. Provider インターフェース仕様

### Input

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `audio_data` | `bytes` | Yes | WAV or WebM バイナリ (最大 10MB) |
| `language` | `Optional[str]` | No | `"ja"`, `"en"`, or `None` (自動検出) |
| `grammar` | `Optional[List[str]]` | No | ドメイン固有語彙 (Vosk のみ使用) |

### Output: `STTResult`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `transcript` | `str` | 認識テキスト |
| `confidence` | `Optional[float]` | 認識信頼度 (0.0-1.0)。qwen3 は `None` |
| `detected_language` | `str` | 検出言語 (`"ja"`, `"en"`) |
| `word_confidences` | `Optional[List[Dict]]` | 単語レベル信頼度 (Vosk のみ) |
| `provider` | `str` | `"vosk"`, `"qwen3"`, `"google"` |

### 必須処理

- WebM → WAV 変換: `BaseSTTProvider.convert_audio_to_wav()` を再利用
- 空音声: 空文字列の transcript を返す場合は `RuntimeError` を raise
- タイムアウト: 30秒以内に推論完了しない場合は `RuntimeError` を raise

---

## 6. qwen3-asr 固有の注意点

### 6.1 モデルサイズ

| モデル | パラメータ | ディスク容量 | メモリ使用量 |
|--------|-----------|-------------|-------------|
| Qwen3-ASR-1.7B | 1.7B | ~3.4GB | ~4.7GB (推論時) |
| Qwen3-ASR-0.6B | 0.6B | ~1.2GB | ~2.0GB (推論時) |

**推奨:** 開発・テストには 0.6B、本番には 1.7B を使用。

### 6.2 GPU vs CPU

| 環境 | 推論時間 (5秒音声) | メモリ |
|------|-------------------|--------|
| GPU (CUDA) | ~1-2秒 | 4.7GB VRAM |
| CPU | ~5-15秒 | 4.7GB RAM |

**注意:** CPU モードでは Vosk より大幅に遅い。CPU 環境では 0.6B 推奨。

### 6.3 依存パッケージ

```
transformers>=4.40.0
torch>=2.0.0
torchaudio>=2.0.0
sentencepiece>=0.2.0
```

**Docker イメージサイズ増加:** +2-3GB (PyTorch + モデル)

### 6.4 ストリーミング非対応

qwen3-asr は Vosk と異なりストリーミング推論をサポートしていない。音声全体をバッファしてからバッチ推論を行う。現行アーキテクチャ (フロントエンドで録音完了後に送信) と一致するため問題なし。

### 6.5 Grammar 非対応

qwen3-asr はドメイン固有語彙 (Grammar) をサポートしていない。`grammar` パラメータは無視される。

### ⚠️ PoC 検証が必要な項目

1. **qwen3-asr の正確な transformers API** — `AutoModelForSpeechSeq2Seq` で正しいか、`AutoModelForCausalLM` の可能性あり
2. **`language` パラメータの渡し方** — `generate()` の引数として渡せるか
3. **自動言語検出の精度** — 明示指定なしで日英判定できるか
4. **CPU 推論速度** — 0.6B モデルが実用的なレイテンシ (2秒以内) を達成できるか
5. **出力フォーマット** — transcript のみか、タイムスタンプ付きか

---

## 7. 環境変数

| 環境変数 | デフォルト | 説明 |
|---------|----------|------|
| `STT_PROVIDER` | `vosk` | `vosk` \| `qwen3` \| `google` |
| `QWEN3_ASR_MODEL_PATH` | `Qwen/Qwen3-ASR-1.7B` | HuggingFace モデル ID or ローカルパス |
| `QWEN3_ASR_DEVICE` | `cpu` | `cpu` \| `cuda` |
| `GOOGLE_APPLICATION_CREDENTIALS` | (未設定) | Google STT fallback 用 |

### .env 設定例

```bash
# Vosk (デフォルト — 変更不要)
STT_PROVIDER=vosk

# qwen3-asr (切り替え時)
STT_PROVIDER=qwen3
QWEN3_ASR_MODEL_PATH=Qwen/Qwen3-ASR-1.7B
QWEN3_ASR_DEVICE=cpu

# 低リソース環境
STT_PROVIDER=qwen3
QWEN3_ASR_MODEL_PATH=Qwen/Qwen3-ASR-0.6B
QWEN3_ASR_DEVICE=cpu
```

---

## 8. テスト計画

### 8.1 Unit テスト

| テスト | 内容 |
|--------|------|
| Factory テスト | `create_stt_provider("vosk")`, `("qwen3")`, `("google")`, `("unknown")` |
| STTResult テスト | dataclass の作成、optional フィールド |
| Qwen3Provider init | デフォルトパラメータ、カスタムパラメータ |
| Audio 変換 | `convert_audio_to_wav()` (WebM → WAV) |
| 空音声処理 | 空の transcript で RuntimeError |

### 8.2 Integration テスト (`@pytest.mark.slow`)

| テスト | 内容 |
|--------|------|
| Vosk 推論 | 既存テストがそのまま通ること |
| qwen3 推論 | テスト WAV → transcript |
| Provider 切り替え | `STT_PROVIDER` 環境変数による切り替え |
| Fallback | qwen3 失敗時の動作 |

### 8.3 Benchmark

| メトリクス | 計測方法 |
|-----------|---------|
| WER (Word Error Rate) | Common Voice ja/en テストセットで比較 |
| レイテンシ | 5秒音声の推論時間 (p50, p95, p99) |
| メモリ使用量 | `tracemalloc` で計測 |

---

## 9. Cloud Run デプロイ考慮

### 9.1 メモリ要件

| Provider | 最小メモリ | 推奨メモリ |
|----------|-----------|-----------|
| Vosk | 512MB | 2GB |
| qwen3-asr 1.7B | 6GB | 8GB |
| qwen3-asr 0.6B | 3GB | 4GB |

### 9.2 Cold Start

| Provider | Cold Start 時間 |
|----------|----------------|
| Vosk | ~2秒 |
| qwen3-asr 1.7B | ~30-60秒 |
| qwen3-asr 0.6B | ~15-30秒 |

### 9.3 別サービス化の検討

qwen3-asr の要件 (大メモリ、長い Cold Start) を考慮すると、**別の Cloud Run サービスとして分離**することを推奨:

```
engineer-cafe-backend (既存)
  ├─ STT_PROVIDER=vosk (デフォルト)
  └─ QWEN3_ASR_URL=https://qwen3-asr-xxx.run.app  (別サービスへ委譲)

qwen3-asr-service (新規)
  ├─ POST /transcribe
  ├─ Memory: 8GB
  ├─ Min instances: 0 (コスト削減)
  └─ Max instances: 2 (スケーリング)
```

この場合、`Qwen3STTProvider` は内蔵推論ではなく HTTP クライアントとして実装する。

---

## 10. 受入基準

### 必須 (P0)

- [ ] `STT_PROVIDER=vosk` (デフォルト) で既存動作が一切変わらないこと
- [ ] `STT_PROVIDER=qwen3` で qwen3-asr による音声認識が動作すること
- [ ] Provider factory (`create_stt_provider`) が正しく provider を選択すること
- [ ] `BaseSTTProvider` 抽象クラスと `STTResult` dataclass が定義されていること
- [ ] 既存テストが全て通ること (`pytest -m "not slow"`)
- [ ] 新規テスト (factory, qwen3 provider) が追加されていること
- [ ] ruff / black が通ること

### 推奨 (P1)

- [ ] qwen3-asr の推論ベンチマーク結果 (WER, レイテンシ)
- [ ] 0.6B モデルでの動作確認
- [ ] Docker イメージビルド確認
- [ ] Cloud Run デプロイ計画 (別サービス vs 統合)

### 将来対応 (P2)

- [ ] qwen3-asr 専用の Fallback 機構 (qwen3 → vosk)
- [ ] ストリーミング推論対応
- [ ] 0.6B / 1.7B の自動切り替え (リソースベース)

---

## 変更しないもの

| 対象 | 理由 |
|------|------|
| `frontend/` 全体 | STT provider の切り替えはバックエンド内部の問題 |
| `backend/main.py` の `_handle_stt()` | STTAgent のインターフェースは変わらない |
| `backend/main.py` の `_get_stt_agent()` | 既に `STT_PROVIDER` env var に対応済み |
| `VoiceResponse` Pydantic モデル | レスポンス形式は変わらない |
| Vosk モデルファイル | 既存モデルはそのまま |
| `docker-compose.yml` の voicevox/kokoro 設定 | TTS は別の Issue (#371) |
| Grammar 定義 (`ENGINEER_CAFE_GRAMMAR` 等) | Vosk 専用、qwen3 では不使用 |

---

## 付録 A: ファイル作成・変更一覧

### 新規作成

| ファイル | 説明 |
|---------|------|
| `backend/agents/stt_providers/__init__.py` | Factory + exports |
| `backend/agents/stt_providers/base.py` | BaseSTTProvider, STTResult |
| `backend/agents/stt_providers/vosk_provider.py` | Vosk 実装 (既存ロジック移動) |
| `backend/agents/stt_providers/google_provider.py` | Google STT 実装 (既存ロジック移動) |
| `backend/agents/stt_providers/qwen3_provider.py` | qwen3-asr 実装 (新規) |
| `backend/tests/agents/test_stt_providers.py` | Provider テスト |
| `backend/scripts/download_qwen_model.sh` | モデルダウンロードスクリプト |

### 修正

| ファイル | 変更内容 |
|---------|---------|
| `backend/agents/stt_agent.py` | Provider factory を使用するように `__init__` を修正 |
| `backend/requirements.txt` | `transformers`, `torch`, `torchaudio` を追加 (optional) |

### 変更なし

| ファイル |
|---------|
| `frontend/` (全て) |
| `backend/main.py` |
| `backend/agents/voice_agent.py` |

---

## 付録 B: 開発環境セットアップ

```bash
# 1. ブランチ作成
git checkout develop
git pull origin develop
git checkout -b feat/370-stt-qwen3-asr

# 2. 依存パッケージ追加 (qwen3 テスト用)
cd backend
pip install transformers torch torchaudio sentencepiece

# 3. モデルダウンロード (テスト用、0.6B 推奨)
QWEN3_ASR_MODEL_PATH=Qwen/Qwen3-ASR-0.6B bash scripts/download_qwen_model.sh

# 4. テスト実行
pytest tests/agents/test_stt_providers.py -v
pytest -m "not slow and not ragas" --tb=short -q

# 5. Lint
ruff check .
black --check .

# 6. qwen3 モードで動作確認
STT_PROVIDER=qwen3 python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
