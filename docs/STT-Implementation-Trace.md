# STT（Speech-to-Text）実装 完全トレースレポート

**作成日:** 2026-03-28
**プロジェクト:** Engineer Cafe Navigator
**対象:** フロントエンド → バックエンド → Docker デプロイメント

---

## 1. 全体アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────────┐
│                       ユーザーのブラウザ                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ VoiceInterface.tsx + VoiceRecorder                        │  │
│  │ 1. getUserMedia() → AudioContext + MediaRecorder          │  │
│  │ 2. 音声キャプチャ → Blob (WebM/audio format)             │  │
│  │ 3. arrayBufferToBase64() → Base64 文字列                  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                      POST /api/voice (JSON, Base64)
                      ┌─────────────────────┐
                      │ action: "speech_to_text"
                      │ audioData: <base64>
                      │ language: "ja"/"en"
                      └─────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                   フロントエンド Next.js                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ frontend/src/app/api/voice/route.ts                      │  │
│  │ 1. リクエスト受け取り                                       │  │
│  │ 2. backendFetch('/api/voice') でバックエンドにプロキシ      │  │
│  │ 3. VoiceResponse を返す                                   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                      POST /api/voice (JSON)
                      ┌─────────────────────┐
                      │ audioData: <base64>
                      │ language: "ja"
                      │ action: "speech_to_text"
                      └─────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│              バックエンド FastAPI (Python)                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ backend/main.py: @app.post("/api/voice")                │  │
│  │ 1. VoiceRequest Pydantic モデルで検証                     │  │
│  │ 2. Base64 デコード → audio_bytes                         │  │
│  │ 3. _handle_stt() 呼び出し                                 │  │
│  │    ↓                                                      │  │
│  │    _get_stt_agent().speech_to_text()                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                      │                          │
│  ┌────────────────────────────────────▼──────────────────────┐  │
│  │ backend/agents/stt_agent.py: STTAgent                     │  │
│  │                                                            │  │
│  │ speech_to_text(audio_bytes, language="ja")               │  │
│  │ ↓                                                          │  │
│  │ LocalSTTClient._sync_transcribe()                        │  │
│  │ ├─ WAV ヘッダ検証                                         │  │
│  │ ├─ WebM → WAV 変換（pydub 使用）                         │  │
│  │ ├─ Vosk モデル読み込み（models/vosk-model-ja など）       │  │
│  │ ├─ KaldiRecognizer 初期化                                │  │
│  │ ├─ AcceptWaveform() で音声フレーム入力                   │  │
│  │ ├─ FinalResult() で JSON 結果取得                        │  │
│  │ └─ TranscriptionResult に変換（confidence 計算）          │  │
│  │    ↓                                                      │  │
│  │ _try_fallback() → Google STT へフォールバック            │  │
│  │ （confidence < 0.4 の場合）                               │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                      │                          │
│  ┌────────────────────────────────────▼──────────────────────┐  │
│  │ VoiceResponse (JSON)                                      │  │
│  │ {                                                          │  │
│  │   "success": true,                                        │  │
│  │   "transcript": "...",                                    │  │
│  │   "confidence": 0.85,                                     │  │
│  │   "language": "ja",                                       │  │
│  │   "provider": "vosk"                                      │  │
│  │ }                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
            POST /api/voice → VoiceResponse (JSON)
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    フロントエンド（ブラウザ）                      │
│  VoiceInterface.tsx: sttResult.transcript をテキスト入力に利用     │
│  （STT補正後、会話ルーティングへ）                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. フロントエンド STT フロー

### 2.1 音声キャプチャ（VoiceRecorder）

**ファイル:** `frontend/src/lib/voice-recorder.ts`

#### 初期化フロー

```typescript
// 1. getUserMedia で音声ストリーム取得
const audioConstraints = {
  channelCount: 1,        // モノラル
  sampleRate: 16000,      // 16kHz（Vosk 推奨）
  echoCancellation: true, // エコーキャンセル有効
  noiseSuppression: true, // ノイズ抑制有効
  autoGainControl: true   // 自動ゲイン制御有効
};

this.stream = await navigator.mediaDevices.getUserMedia({
  audio: audioConstraints
});

// 2. MediaRecorder 作成
const mimeType = this.getSupportedMimeType(); // audio/webm など
this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });
```

#### サポート MIME タイプ

```typescript
getSupportedMimeType(): string {
  // ブラウザが対応している MIME タイプを順に試す
  const candidates = [
    'audio/webm',
    'audio/webm;codecs=opus',
    'audio/mp4',
    'audio/ogg',
    'audio/wav'
  ];

  for (const mimeType of candidates) {
    if (MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType;
    }
  }
  return ''; // フォールバック（OS デフォルト）
}
```

#### 音声記録

```typescript
start(): void {
  this.mediaRecorder.start();
  this.isRecording = true;
}

// MediaRecorder のイベントハンドラ
this.mediaRecorder.ondataavailable = (event) => {
  if (event.data.size > 0) {
    this.audioChunks.push(event.data); // Blob[] に蓄積
  }
};

this.mediaRecorder.onstop = () => {
  // 複数 Blob を結合
  const audioBlob = new Blob(this.audioChunks, {
    type: this.mediaRecorder.mimeType || 'audio/webm'
  });
  this.onDataAvailable(audioBlob); // コールバック
  this.audioChunks = [];
};
```

### 2.2 Base64 エンコーディング

**ファイル:** `frontend/src/lib/voice-recorder.ts:263-270`

```typescript
static arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary); // Base64 エンコード
}
```

**プロセス:**
1. `audioBlob.arrayBuffer()` で ArrayBuffer を取得
2. `Uint8Array` に変換
3. `btoa()` で Base64 エンコード

### 2.3 API 送信

**ファイル:** `frontend/src/app/components/VoiceInterface.tsx:520-550`

```typescript
const sttResponse = await fetch('/api/voice', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    action: 'speech_to_text',
    audioData: await toBase64(audioBlob),  // Base64 文字列
    language: currentLanguage,             // "ja" or "en"
    sessionId: sessionId                   // オプション
  }),
  signal: abortController.signal
});

const sttResult = await sttResponse.json();
// {
//   success: true,
//   transcript: "エンジニアカフェについて教えてください",
//   confidence: 0.85,
//   language: "ja",
//   detectedLanguage?: "ja",
//   provider?: "vosk"
// }

setTranscript(sttResult.transcript);
await sendMessage(sttResult.transcript);
```

### 2.4 STT 補正

**ファイル:** `frontend/src/lib/stt-correction.ts`

STT 補正は現在、フロントエンド側で実装されていません。バックエンド STT 結果はそのまま使用されます。

---

## 3. フロントエンド プロキシ API

**ファイル:** `frontend/src/app/api/voice/route.ts`

```typescript
// POST /api/voice
export async function POST(request: NextRequest) {
  const body = await request.json();
  // {
  //   action: "speech_to_text",
  //   audioData: <base64>,
  //   language: "ja",
  //   sessionId?: "..."
  // }

  const response = await backendFetch('/api/voice', {
    body: {
      action: body.action,
      audioData: body.audioData,
      sessionId: body.sessionId,
      language: body.language || 'ja',
      text: body.text,           // TTS 用
      streaming: body.streaming  // TTS 用
    }
  });

  if (!response.ok) {
    return createBackendErrorResponse(response);
  }

  return NextResponse.json(response.data);
}
```

**機能:**
- フロントエンド `/api/voice` はシンプルなプロキシ
- バックエンド `/api/voice` へ JSON を転送
- エラーハンドリング（createBackendErrorResponse）

---

## 4. バックエンド STT フロー

### 4.1 エンドポイント定義

**ファイル:** `backend/main.py:638-705`

```python
@app.post("/api/voice", response_model=VoiceResponse,
          dependencies=[Depends(verify_api_key)])
@_rate_limit("20/minute")
async def voice_api(request: Request, body: VoiceRequest):
    try:
        if body.action == "speech_to_text":
            return await _handle_stt(body)
        elif body.action == "process_voice":
            return await _handle_stt(body)
        # ... other actions
    except Exception as e:
        return VoiceResponse(success=False, error=str(e), ...)
```

### 4.2 Pydantic モデル

**ファイル:** `backend/main.py:511-535`

```python
class VoiceRequest(BaseModel):
    action: str                                          # "speech_to_text", "text_to_speech", etc.
    audioData: Optional[str] = None                      # Base64 音声データ
    sessionId: Optional[str] = None                      # セッション ID
    language: Optional[str] = Field(default="ja",
                                     max_length=10)      # "ja", "en"
    text: Optional[str] = Field(default=None,
                                max_length=5000)         # TTS 用テキスト
    streaming: Optional[bool] = False                    # ストリーミング TTS
    conversationStage: Optional[str] = None              # 会話ステージ
    emotion: Optional[str] = None                        # TTS 感情

class VoiceResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None                     # STT 結果
    response: Optional[str] = None
    audioResponse: Optional[str] = None                  # TTS 結果（Base64）
    emotion: Optional[str] = None
    sessionId: Optional[str] = None
    error: Optional[str] = None
    detectedLanguage: Optional[str] = None               # Vosk 検出言語
    confidence: Optional[float] = None                   # Vosk confidence
    interruptStatus: Optional[str] = None
```

### 4.3 STT ハンドラ

**ファイル:** `backend/main.py:576-605`

```python
async def _handle_stt(body: VoiceRequest) -> VoiceResponse:
    """Shared STT processing for process_voice and speech_to_text"""
    if not body.audioData:
        raise HTTPException(status_code=400,
                          detail="Missing audioData")

    # 1. Base64 デコード
    audio_bytes = base64.b64decode(body.audioData)

    # 2. STT エージェント呼び出し
    stt_result = await _get_stt_agent().speech_to_text(
        audio_bytes,
        language=body.language,
        conversation_stage=body.conversationStage
    )

    # 3. 結果レスポンス
    if not stt_result["success"]:
        return VoiceResponse(
            success=False,
            error=stt_result.get("error", "STT failed"),
            sessionId=body.sessionId
        )

    return VoiceResponse(
        success=True,
        transcript=stt_result["transcript"],
        emotion="neutral",
        detectedLanguage=stt_result.get("language"),
        confidence=stt_result.get("confidence"),
        sessionId=body.sessionId
    )
```

### 4.4 STT エージェント初期化

**ファイル:** `backend/main.py:548-575`

```python
def _get_stt_agent():
    """Lazy load STTAgent (singleton)"""
    global _stt_agent
    if _stt_agent is None:
        from backend.agents.stt_agent import STTAgent
        _stt_agent = STTAgent(
            stt_provider=os.getenv("STT_PROVIDER", "vosk"),
            use_grammar=False,
            confidence_threshold=0.4  # Vosk → Google fallback threshold
        )
    return _stt_agent
```

---

## 5. バックエンド STT エージェント詳細

### 5.1 STTAgent クラス

**ファイル:** `backend/agents/stt_agent.py:513-570`

```python
class STTAgent:
    def __init__(
        self,
        stt_provider: Optional[str] = None,
        stt_client: Optional[Any] = None,
        use_grammar: bool = False,
        language_processor: Optional[Any] = None,
        confidence_threshold: float = 0.4,
        fallback_client: Optional[Any] = None
    ):
        self.stt_provider = stt_provider or os.getenv("STT_PROVIDER", "vosk")
        self.use_grammar = use_grammar
        self.confidence_threshold = confidence_threshold

        # STT クライアント初期化
        if self.stt_provider == "vosk":
            self.stt_client = LocalSTTClient()
            self.fallback_client = GoogleSTTClient()  # Google STT フォールバック
        elif self.stt_provider == "google":
            self.stt_client = GoogleSTTClient()
            self.fallback_client = None
```

### 5.2 speech_to_text メソッド

**ファイル:** `backend/agents/stt_agent.py:712-785`

```python
async def speech_to_text(
    self,
    audio_data: bytes,
    language: Optional[str] = "ja",
    conversation_stage: Optional[str] = None
) -> Dict[str, Any]:
    """
    音声 → テキスト変換

    Args:
        audio_data: WAV バイナリ（16kHz, 16bit, mono 推奨）
        language: "ja", "en", or None（自動検出）
        conversation_stage: "greeting", "service_selection", "confirmation"

    Returns:
        {
            "success": bool,
            "transcript": str,
            "confidence": float,  # Vosk のみ
            "language": str,
            "provider": str,
            "error": str  # 失敗時
        }
    """
    provider = self.stt_provider
    grammar = self._resolve_grammar(conversation_stage)

    try:
        if language is None and isinstance(self.stt_client, LocalSTTClient):
            # 自動言語検出（日英並列実行）
            result = await self.stt_client.transcribe_auto_detect(
                audio_data, grammar=grammar
            )
        else:
            # 指定言語で STT
            lang = language or "ja"
            if isinstance(self.stt_client, LocalSTTClient):
                grammar_list = (grammar or {}).get(lang) if grammar else None
                result = await self.stt_client.transcribe(
                    audio_data, lang, grammar=grammar_list
                )
            else:
                result = await self.stt_client.transcribe(audio_data, lang)

        # TranscriptionResult（Vosk）vs str（Google STT）の処理
        if isinstance(result, TranscriptionResult):
            # 言語バリデーション
            validated = await self._validate_language(result, audio_data)
            response = {
                "success": True,
                "transcript": validated.text,
                "confidence": validated.confidence,
                "language": validated.language,
                "provider": provider
            }
            # 低信頼度時に Google STT へフォールバック
            return await self._try_fallback(audio_data, validated.language, response)
        else:
            # Google STT の場合
            return {
                "success": True,
                "transcript": result,
                "confidence": None,
                "language": language or "ja",
                "provider": provider
            }
    except Exception as e:
        logger.error("STT failed (%s): %s", provider, e)
        return {
            "success": False,
            "transcript": "",
            "confidence": 0.0,
            "language": language or "unknown",
            "provider": provider,
            "error": str(e)
        }
```

### 5.3 Vosk モデルパス

**ファイル:** `backend/agents/stt_agent.py:221-226`

```python
DEFAULT_MODEL_PATHS: Dict[str, str] = {
    "ja": "models/vosk-model-ja",
    "en": "models/vosk-model-en-us"
}

SUPPORTED_LANGUAGES = ("ja", "en")
```

---

## 6. オーディオフォーマット詳細

### 6.1 フロントエンド送信形式

| 項目 | 値 |
|------|------|
| **形式** | WebM（Opus コーデック）、MP4、OGG、WAV など（ブラウザサポートに依存） |
| **サンプルレート** | リクエスト時は 16kHz を指定（ブラウザが自動処理） |
| **チャネル数** | モノラル（1 チャネル） |
| **ビット深度** | 16-bit |
| **エンコーディング** | Base64（JSON 送信時） |

**実装:**
```typescript
// VoiceRecorder.tsx
const audioConstraints = {
  channelCount: 1,     // モノラル
  sampleRate: 16000,   // 16kHz
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true
};

// MediaRecorder は上記制約に従い、16kHz/mono の WebM を生成
// → Base64 エンコード → JSON POST
```

### 6.2 バックエンド処理フロー

```
Blob (WebM)
  ↓
toBase64() (JavaScript)
  ↓
JSON POST (Base64 文字列)
  ↓
backend/main.py: base64.b64decode()
  ↓
audio_bytes (バイナリ)
  ↓
LocalSTTClient (Vosk)
  ├─ WAV ヘッダチェック
  ├─ WebM → WAV 変換（pydub）
  ├─ Vosk モデル読み込み
  └─ 16kHz/16-bit/mono WAV で Kaldi 推論
```

### 6.3 WebM → WAV 変換（pydub）

**ファイル:** `backend/agents/stt_agent.py:239-268`

```python
def _convert_audio_to_wav(self, audio_data: bytes) -> bytes:
    """Convert WebM/Opus audio to WAV PCM for Vosk"""

    from pydub import AudioSegment

    segment = AudioSegment.from_file(
        io.BytesIO(audio_data),
        format=None  # 自動フォーマット検出
    )

    # 正規化：16kHz/16-bit/mono
    normalized = segment \
        .set_frame_rate(16000) \
        .set_sample_width(2) \     # 2 bytes = 16-bit
        .set_channels(1)

    # WAV export
    wav_buffer = io.BytesIO()
    normalized.export(wav_buffer, format="wav")

    return wav_buffer.getvalue()
```

---

## 7. Vosk 実装詳細

### 7.1 LocalSTTClient（Vosk ラッパー）

**ファイル:** `backend/agents/stt_agent.py:231-455`

#### モデル読み込み

```python
class LocalSTTClient:
    def __init__(self, model_paths: Optional[Dict[str, str]] = None):
        self.model_paths = {**DEFAULT_MODEL_PATHS, **(model_paths or {})}
        self._models: Dict[str, Any] = {}  # キャッシュ

    def _load_model(self, lang: str):
        """Lazy load Vosk model"""
        if lang in self._models:
            return self._models[lang]

        try:
            from vosk import Model
        except ImportError:
            raise RuntimeError("Vosk not installed. pip install vosk")

        model_path = os.path.expanduser(self.model_paths[lang])
        if not os.path.exists(model_path):
            raise RuntimeError(
                f"Vosk model not found: {model_path}\n"
                f"Download from https://alphacephei.com/vosk/models"
            )

        self._models[lang] = Model(model_path)
        logger.info(f"Loaded Vosk {lang} model from {model_path}")
        return self._models[lang]
```

#### 推論ロジック

**ファイル:** `backend/agents/stt_agent.py:301-375`

```python
def _sync_transcribe(
    self,
    audio_data: bytes,
    language: str = "ja",
    grammar: Optional[List[str]] = None
) -> TranscriptionResult:
    """同期 Vosk 推論（ThreadPoolExecutor で実行）"""

    # 1. WAV ヘッダ検証
    if audio_data[:4] != b"RIFF":
        audio_data = self._convert_audio_to_wav(audio_data)

    # 2. WAV フレームを読み込み
    import wave
    bio = io.BytesIO(audio_data)
    with wave.open(bio, "rb") as wf:
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    # 3. Vosk モデル読み込み
    model = self._load_model(language)

    # 4. KaldiRecognizer 初期化
    from vosk import KaldiRecognizer
    if grammar:
        rec = KaldiRecognizer(model, sample_rate, json.dumps(grammar))
    else:
        rec = KaldiRecognizer(model, sample_rate)

    # 5. SetWords で word-level confidence を取得
    rec.SetWords(True)

    # 6. 音声フレーム送入
    rec.AcceptWaveform(frames)

    # 7. 最終結果取得
    result_json = rec.FinalResult()
    result = json.loads(result_json)

    # 8. テキスト抽出
    text = result.get("text", "")

    # 9. Word-level confidence 計算
    word_results = result.get("result", [])
    word_confidences = [
        {"word": w.get("word", ""), "conf": w.get("conf", 0.0)}
        for w in word_results
    ]

    avg_confidence = (
        sum(w["conf"] for w in word_confidences) / len(word_confidences)
        if word_confidences else None
    )

    return TranscriptionResult(
        text=text or " ".join(w.get("word", "") for w in word_results),
        confidence=avg_confidence,
        language=language,
        word_confidences=word_confidences
    )

async def transcribe(
    self,
    audio_data: bytes,
    language: str = "ja",
    grammar: Optional[List[str]] = None
) -> TranscriptionResult:
    """非同期ラッパー（ThreadPoolExecutor で実行）"""
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(
            pool,
            lambda: self._sync_transcribe(audio_data, language, grammar)
        )
```

### 7.2 自動言語検出

**ファイル:** `backend/agents/stt_agent.py:390-447`

```python
async def transcribe_auto_detect(
    self,
    audio_data: bytes,
    grammar: Optional[Dict[str, List[str]]] = None
) -> TranscriptionResult:
    """日英並列実行、confidence が高い方を選択"""

    async def _run_model(lang: str) -> Optional[TranscriptionResult]:
        lang_grammar = (grammar or {}).get(lang)
        try:
            return await self.transcribe(audio_data, lang, grammar=lang_grammar)
        except (RuntimeError, ValueError):
            return None

    # 日英並列実行
    results = await asyncio.gather(
        _run_model("ja"),
        _run_model("en")
    )

    valid_results = [r for r in results if r is not None]

    if not valid_results:
        raise RuntimeError(
            "Auto-detect failed: neither Japanese nor English model produced a result"
        )

    # Confidence が高い方を選択
    best = max(
        valid_results,
        key=lambda r: r.confidence if r.confidence is not None else 0.0
    )

    logger.info(
        f"Auto-detect: selected {best.language} "
        f"(confidence={best.confidence:.3f})"
    )

    return best
```

### 7.3 Grammar（ドメイン固有語彙）

**ファイル:** `backend/agents/stt_agent.py:60-215`

#### Engineer Cafe Grammar

```python
ENGINEER_CAFE_GRAMMAR: Dict[str, List[str]] = {
    "ja": [
        "エンジニアカフェ",
        "エンジニアカフェラボ",
        "営業時間",
        "会議室",
        "ミーティング",
        "ミートアップ",
        "集中スペース",
        "メーカーズスペース",
        "地下",
        "赤煉瓦",
        "天神",
        "博多",
        # ... etc
    ],
    "en": [
        "engineer cafe",
        "meeting room",
        "coworking space",
        # ... etc
    ]
}
```

#### Stage-Specific Grammar

```python
STAGE_GRAMMARS: Dict[str, Dict[str, List[str]]] = {
    "greeting": {
        "ja": ["こんにちは", "すみません", "エンジニアカフェ", ...],
        "en": ["hello", "hi", "engineer cafe", ...]
    },
    "service_selection": {
        "ja": ["会議室", "コワーキング", "Wi-Fi", ...],
        "en": ["meeting room", "coworking", "wifi", ...]
    },
    "confirmation": {
        "ja": ["はい", "いいえ", "お願いします", ...],
        "en": ["yes", "no", "please", ...]
    }
}
```

---

## 8. フォールバック（Google STT）

**ファイル:** `backend/agents/stt_agent.py:456-510`

```python
class GoogleSTTClient:
    """Google Cloud Speech-to-Text フォールバック"""

    async def transcribe(self, audio_data: bytes, language: str):
        from google.cloud import speech_v1

        client = speech_v1.SpeechClient()

        audio = speech_v1.RecognitionAudio(content=audio_data)
        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=f"{language}-{language.upper()}"
        )

        response = client.recognize(config=config, audio=audio)

        for result in response.results:
            if result.alternatives:
                return result.alternatives[0].transcript

        raise ValueError("Google STT returned no results")
```

#### フォールバック条件

```python
async def _try_fallback(
    self,
    audio_data: bytes,
    language: str,
    vosk_response: Dict[str, Any]
) -> Dict[str, Any]:
    """Vosk confidence < threshold → Google STT へフォールバック"""

    confidence = vosk_response.get("confidence")

    if (confidence is not None and
        confidence < self.confidence_threshold and
        self.fallback_client):

        try:
            google_result = await self.fallback_client.transcribe(
                audio_data, language
            )

            vosk_response["transcript"] = google_result
            vosk_response["confidence"] = None  # Google STT は confidence なし
            vosk_response["provider"] = "google (fallback)"
            vosk_response["fallback_used"] = True

            logger.info(
                f"Vosk fallback to Google STT "
                f"(vosk_confidence={confidence:.3f})"
            )
        except Exception as e:
            logger.warning(f"Google fallback failed: {e}")
            # Vosk 結果を使用

    return vosk_response
```

---

## 9. 環境変数・設定

### 9.1 STT 関連環境変数

| 環境変数 | デフォルト | 説明 |
|---------|----------|------|
| `STT_PROVIDER` | `vosk` | `vosk` または `google` |
| `GOOGLE_APPLICATION_CREDENTIALS` | （未設定） | Google Cloud サービスアカウント JSON パス |

**ファイル:** `backend/main.py:548-575`

```python
stt_provider = os.getenv("STT_PROVIDER", "vosk")
```

### 9.2 STTAgent 初期化パラメータ

```python
STTAgent(
    stt_provider="vosk",           # Provider
    use_grammar=False,             # ドメイン語彙使用
    confidence_threshold=0.4,      # フォールバック閾値
    # language_processor: 言語バリデーション
    # fallback_client: Google STT クライアント
)
```

### 9.3 LocalSTTClient モデルパス

```python
DEFAULT_MODEL_PATHS = {
    "ja": "models/vosk-model-ja",      # 48MB
    "en": "models/vosk-model-en-us"    # 40MB
}
```

---

## 10. Docker 統合

### 10.1 Dockerfile（バックエンド）

**ファイル:** `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim AS base

# システム依存
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    unzip \
    ffmpeg          # pydub（WebM → WAV 変換）用
    && rm -rf /var/lib/apt/lists/*

# Python 依存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Development ターゲット
FROM base AS development

COPY . .

# Vosk モデルダウンロード（ビルド時）
RUN bash scripts/download_vosk_models.sh models

# Production ターゲット
FROM base AS production

COPY . .

# 注：Production では モデルをボリュームマウント
# volumes:
#   - ./models:/app/models
```

### 10.2 Vosk モデルダウンロード

**ファイル:** `backend/scripts/download_vosk_models.sh`

```bash
#!/bin/bash

MODEL_DIR="${1:-models}"

JA_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip"
EN_MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

# 各モデル（~88MB 合計）をダウンロード
curl -L -o /tmp/ja.zip "$JA_MODEL_URL"
unzip -q /tmp/ja.zip -d "$MODEL_DIR"

curl -L -o /tmp/en.zip "$EN_MODEL_URL"
unzip -q /tmp/en.zip -d "$MODEL_DIR"
```

**モデルサイズ:**
- 日本語：48MB
- 英語：40MB
- **合計：~88MB**

### 10.3 Docker Compose

**ファイル:** `docker-compose.yml:35-62`

```yaml
backend:
  build:
    context: ./backend
    target: development
  container_name: engineer-cafe-backend
  ports:
    - "0.0.0.0:8000:8000"
  volumes:
    - ./backend:/app
    - /app/__pycache__
    - backend-vosk-models:/app/models  # モデルボリューム永続化
  environment:
    - PYTHONUNBUFFERED=1
  env_file:
    - ./backend/.env
  depends_on:
    voicevox:
      condition: service_healthy
    kokoro-tts:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "python", "scripts/healthcheck.py"]
    interval: 30s
    timeout: 10s
    retries: 3

volumes:
  backend-vosk-models:
```

### 10.4 イメージサイズへの影響

```
Python 3.11-slim：~150MB
+ 依存パッケージ（numpy, pydub, etc）：~200MB
+ Vosk モデル（ja + en）：~88MB
──────────────────────────
合計：~440MB（Development image）

Production では モデルをボリュームマウント
→ イメージサイズ：~350MB
```

---

## 11. エラーハンドリング

### 11.1 空白音声（無音）処理

**ファイル:** `backend/agents/stt_agent.py:362-375`

```python
def _sync_transcribe(...) -> TranscriptionResult:
    # ... Vosk 推論 ...

    text = result.get("text", "")

    # フォールバック：word results から組み立て
    if not text and word_results:
        text = " ".join(w.get("word", "") for w in word_results).strip()

    text = (text or "").strip()

    # 空白チェック
    if not text:
        logger.warning("Vosk returned empty transcript")
        raise RuntimeError("Vosk returned empty recognition result")

    return TranscriptionResult(...)
```

### 11.2 バリデーションエラー

**ファイル:** `backend/main.py:576-605`

```python
async def _handle_stt(body: VoiceRequest) -> VoiceResponse:
    # audioData チェック
    if not body.audioData:
        raise HTTPException(status_code=400,
                          detail="Missing audioData")

    # Base64 デコード失敗
    try:
        audio_bytes = base64.b64decode(body.audioData)
    except Exception as e:
        raise HTTPException(status_code=400,
                          detail=f"Invalid base64 audio data: {e}")
```

### 11.3 WAV ヘッダ検証

**ファイル:** `backend/agents/stt_agent.py:39-41, 304-313`

```python
WAV_RIFF_HEADER = b"RIFF"
MIN_WAV_HEADER_BYTES = 44

def _sync_transcribe(...):
    if audio_data[:4] == WAV_RIFF_HEADER:
        if len(audio_data) < MIN_WAV_HEADER_BYTES:
            raise ValueError(
                "Audio data must be in WAV format (RIFF) "
                "and include a complete WAV header (minimum 44 bytes). "
                "Received truncated data."
            )
    else:
        # WebM → WAV 変換
        audio_data = self._convert_audio_to_wav(audio_data)
```

### 11.4 モデルロード失敗

**ファイル:** `backend/agents/stt_agent.py:278-297`

```python
def _load_model(self, lang: str):
    try:
        from vosk import Model
    except ImportError:
        logger.error("Vosk not installed. Install with: pip install vosk")
        raise RuntimeError("Vosk not installed. pip install vosk")

    model_path = os.path.expanduser(self.model_paths[lang])

    if not os.path.exists(model_path):
        logger.warning(f"Vosk model not found at {model_path}")
        raise RuntimeError(
            f"Vosk model not found: {model_path}. "
            f"Download from https://alphacephei.com/vosk/models"
        )
```

### 11.5 最大オーディオサイズ制限

**ファイル:** `backend/agents/stt_agent.py:34`

```python
MAX_AUDIO_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

def _convert_audio_to_wav(self, audio_data: bytes):
    if len(audio_data) > MAX_AUDIO_UPLOAD_BYTES:
        raise ValueError(
            f"Audio payload too large ({len(audio_data)} bytes). "
            f"Maximum: {MAX_AUDIO_UPLOAD_BYTES} bytes."
        )
```

---

## 12. テストケース

### 12.1 STT エージェント テスト

**ファイル:** `backend/tests/agents/test_stt_agent.py`

```python
class TestLocalSTTClient:
    def test_init_default_paths(self):
        client = LocalSTTClient()
        assert client.model_paths["ja"] == "models/vosk-model-ja"

    def test_load_model_not_found(self):
        client = LocalSTTClient(model_paths={"ja": "/nonexistent"})
        with pytest.raises(RuntimeError) as exc_info:
            client._load_model("ja")
        assert "not found" in str(exc_info.value).lower()
```

### 12.2 Voice API テスト

**ファイル:** `backend/tests/api/test_voice_api.py`

```python
@pytest.mark.asyncio
async def test_voice_api_speech_to_text():
    test_wav = generate_test_wav(16000, 0.5)
    audio_base64 = base64.b64encode(test_wav).decode()

    response = await client.post("/api/voice", json={
        "action": "speech_to_text",
        "audioData": audio_base64,
        "language": "ja"
    })

    assert response.status_code == 200
    result = response.json()
    assert result["success"]
    assert "transcript" in result
```

---

## 13. 現在の制限事項・既知の問題

### 13.1 Vosk の制限

- **精度：** 約 85-90%（Google Cloud STT の 95% に比べて）
- **リアルタイム処理：** オフライン STT はネットワーク遅延なし（利点）
- **モデルサイズ：** 日本語 48MB、英語 40MB（スマートフォンには大きい）
- **マルチスレッド：** Vosk は GIL の影響を受ける（ThreadPoolExecutor で回避）

### 13.2 オーディオフォーマット

- **入力形式の多様性：** WebM、MP4、OGG など複数形式をサポートしているが、pydub に依存
- **リサンプリング時間：** WebM → WAV 変換に 0.2～0.5 秒（ネットワークより遅い可能性）

### 13.3 Google STT フォールバック

- **API キー必須：** `GOOGLE_APPLICATION_CREDENTIALS` 環境変数が必要
- **API 料金：** 毎月 60 分まで無料、超過後は料金発生

### 13.4 言語検出

- **自動検出の信頼性：** 日英の confidence が近い場合、誤判定の可能性
- **その他言語未サポート：** 現在は日本語（ja）、英語（en）のみ

---

## 14. パフォーマンス特性

### 14.1 レイテンシ

| ステップ | 時間 |
|---------|------|
| ブラウザ → Base64 エンコード | 10～50ms |
| HTTP POST | 50～200ms（ネットワーク依存） |
| Base64 デコード | 5～10ms |
| WebM → WAV 変換（pydub） | 200～500ms |
| Vosk 推論（0.5秒音声） | 100～300ms |
| **合計** | **365～1,060ms** |

### 14.2 メモリ使用量

- **Vosk モデル（日本語）:** ~100MB（メモリ上ロード）
- **オーディオバッファ（10秒）:** ~320KB（16kHz/16-bit/mono）
- **推論時最大：** ~150MB

### 14.3 CPU 使用率

- **WebM → WAV 変換：** 1コア 20～40%（pydub/ffmpeg）
- **Vosk 推論：** 1コア 50～100%（Kaldi）

---

## 15. 改善提案

### 15.1 音声品質向上

1. **Vosk モデル更新**
   - 最新モデル：vosk-model-small-ja-0.22（現在） → vosk-model-ja-0.28（仮定）
   - 精度向上見込み：～2～3%

2. **piper-plus（軽量 STT）**
   - メモリフットプリント削減（Vosk 100MB → 20MB）
   - オフライン推論でレイテンシ削減
   - 参考：https://github.com/k2-fsa/sherpa-onnx

### 15.2 レイテンシ削減

1. **WebM → WAV 変換の事前化**
   - ブラウザ側で WAV キャプチャ（MediaRecorder 設定調整）
   - バックエンド変換スキップで ~200～500ms 短縮

2. **キャッシング戦略**
   - ユーザーの頻出フレーズをメモリキャッシュ
   - 同一フレーズ再認識時にキャッシュ結果返却

### 15.3 エラーハンドリング強化

1. **タイムアウト設定**
   ```python
   STT_TIMEOUT = 10  # 10秒以上の音声は失敗
   ```

2. **自動リトライ**
   - Vosk 失敗時、自動的に Google STT へフォールバック（現在実装済み）

---

## 16. デプロイメント チェックリスト

### 16.1 バックエンド デプロイ

- [ ] `STT_PROVIDER` 環境変数を `vosk` に設定
- [ ] `GOOGLE_APPLICATION_CREDENTIALS` を設定（Google STT フォールバック用）
- [ ] Vosk モデルをコンテナに含める、またはボリュームマウント
- [ ] Docker イメージサイズが 500MB 以下であることを確認
- [ ] Cloud Run メモリを 2GB 以上に設定

### 16.2 フロントエンド デプロイ

- [ ] VoiceRecorder が HTTPS で動作（iOS対応）
- [ ] マイク許可プロンプムが正しく表示される
- [ ] Base64 エンコーディングが正確

### 16.3 本番検証

- [ ] STT レイテンシが 1 秒以内
- [ ] エラーレート < 1%
- [ ] モデルロード時間を監視

---

## 付録 A：ファイル参照一覧

| ファイル | 行番号 | 説明 |
|---------|--------|------|
| `frontend/src/lib/voice-recorder.ts` | 1-270 | ブラウザ音声キャプチャ |
| `frontend/src/app/api/voice/route.ts` | 1-55 | フロントエンド STT プロキシ |
| `frontend/src/app/components/VoiceInterface.tsx` | 520-550 | STT API 送信ロジック |
| `backend/main.py` | 511-705 | バックエンド Voice API エンドポイント |
| `backend/agents/stt_agent.py` | 1-785 | STT エージェント実装 |
| `backend/agents/voice_agent.py` | 1-600+ | Voice エージェント（TTS含む） |
| `backend/scripts/download_vosk_models.sh` | 1-50 | Vosk モデルダウンロード |
| `backend/Dockerfile` | 1-75 | バックエンド Docker イメージ |
| `docker-compose.yml` | 35-62 | Docker Compose 設定 |
| `backend/tests/agents/test_stt_agent.py` | 1-300+ | STT テストケース |

---

## 付録 B：キー用語解説

| 用語 | 説明 |
|------|------|
| **Vosk** | オフライン音声認識ライブラリ（Kaldi ベース） |
| **Kaldi** | 音声認識ツールキット |
| **WebM** | ブラウザネイティブの音声形式（Opus コーデック） |
| **WAV** | PCM 波形形式（Vosk の標準入力） |
| **pydub** | Python 音声処理ライブラリ |
| **ffmpeg** | マルチメディア変換ツール |
| **Base64** | バイナリ → ASCII エンコーディング |
| **Confidence** | 認識信頼度（0.0～1.0） |
| **Grammar** | ドメイン固有の認識辞書 |
| **Fallback** | フォールバック（Vosk 失敗時に Google STT へ） |

---

**レポート終了**
