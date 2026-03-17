# STT/TTS ローカル環境セットアップガイド

このドキュメントは、Vosk（STT）、VoiceVox（日本語TTS）、Kokoro TTS（英語TTS）のローカルセットアップ手順です。

## ディレクトリ構造

```
backend/
├── models/
│   ├── vosk-model-ja/          # 日本語 Vosk モデル
│   └── vosk-model-en-us/       # 英語 Vosk モデル
├── agents/
│   ├── voice_agent.py          # TTS エージェント（VoiceVox 統合）
│   ├── stt_agent.py            # STT エージェント（Vosk 統合）
├── requirements.txt            # vosk, soundfile 追加済み
└── .gitignore                  # models/ は除外済み
```

## セットアップ手順

### 1. Python 依存インストール

```bash
cd backend
pip install -r requirements.txt
# または uv の場合
uv pip install -r requirements.txt
```

このコマンドで以下が自動実行されます：
- `vosk>=0.3.44` — ローカル音声認識エンジン
- `soundfile>=0.12.1` — WAV ファイル処理
- `pydub>=0.25.1` — WebM(Opus) を WAV に正規化
- `langchain` / `langchain-core` — 他エージェント用（VoiceAgent の import 時に必要）

WebM(Opus) を WAV に変換する場合は `ffmpeg` または `libav` 互換のデコーダが実行環境に必要です。

### 2. Vosk モデルのダウンロード

#### 2.1 日本語モデル
```bash
cd backend/models

# Vosk 日本語モデル（約100MB）をダウンロード
wget https://alphacephei.com/vosk/models/vosk-model-ja-0.22.zip
# または curl の場合
curl -o vosk-model-ja-0.22.zip https://alphacephei.com/vosk/models/vosk-model-ja-0.22.zip

# 解凍
unzip vosk-model-ja-0.22.zip
mv vosk-model-ja-0.22 vosk-model-ja
rm vosk-model-ja-0.22.zip
```

#### 2.2 英語モデル（オプション）
```bash
cd backend/models

# Vosk 英語モデル（約100MB）をダウンロード
wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip vosk-model-en-us-0.22.zip
mv vosk-model-en-us-0.22 vosk-model-en-us
rm vosk-model-en-us-0.22.zip
```

**モデルダウンロード完了後の構造：**
```
backend/models/
├── vosk-model-ja/
│   ├── conf/
│   ├── fstbin/
│   ├── graph/
│   ├── am/
│   └── ...その他ファイル
└── vosk-model-en-us/
    └── ...同様の構造
```

### 3. Docker Compose で TTS エンジンを起動

`docker-compose.yml` に VoiceVox（日本語TTS）と Kokoro TTS（英語TTS）サービスが追加済みです。

```bash
# プロジェクトルートから実行
docker compose up voicevox kokoro-tts -d

# VoiceVox が起動したか確認（Health check）
curl http://localhost:50021/version
# 期待される応答例: {"version":"0.14.1",...}

# Kokoro TTS が起動したか確認（Health check）
curl http://localhost:8880/v1/audio/voices
# 期待される応答例: {"voices":[...]}
```

**注意**: Kokoro TTSは英語テキスト用、VoiceVoxは日本語テキスト用です。システムは自動的に言語を判定して適切なTTSエンジンを選択します。

### 4. 環境変数設定

`backend/.env` に以下を追加：

```env
# STT/TTS Provider settings
TTS_PROVIDER=voicevox          # ローカル優先（言語判定により自動切り替え）
STT_PROVIDER=vosk             # ローカル優先
VOICEVOX_API_URL=http://localhost:50021
KOKORO_API_URL=http://localhost:8880  # Kokoro TTS API URL（英語TTS用）

# Google Cloud（オプション・フォールバック用）
# GOOGLE_CLOUD_CREDENTIALS=...
# GOOGLE_CLOUD_PROJECT_ID=...
```

**環境変数の説明**:
- `TTS_PROVIDER`: TTSプロバイダ（`voicevox` または `google`）
- `VOICEVOX_API_URL`: VoiceVoxエンジンのAPI URL（デフォルト: `http://localhost:50021`）
- `KOKORO_API_URL`: Kokoro TTSエンジンのAPI URL（デフォルト: `http://localhost:8880`）
- システムは自動的に言語を判定し、英語テキストにはKokoro TTS、日本語テキストにはVoiceVoxを使用します

## 動作確認

### 1. Python インポートテスト

```bash
cd backend
python -c "from agents.stt_agent import STTAgent, LocalSTTClient; print('✅ STT Agent imported successfully')"
python -c "from agents.voice_agent import VoiceAgent, VoiceVoxClient; print('✅ Voice Agent imported successfully')"
```

### 2. Vosk モデルロードテスト

```bash
python -c "
from agents.stt_agent import LocalSTTClient
client = LocalSTTClient()
# モデル遅延ロード（初回利用時に実行）
try:
    # モデルが存在するか確認
    import os
    if os.path.exists('models/vosk-model-ja'):
        print('✅ Vosk Japanese model found')
    else:
        print('❌ Vosk Japanese model not found')
except Exception as e:
    print(f'❌ Error: {e}')
"
```

### 3. TTS エンジンのヘルスチェック

```bash
# VoiceVox（日本語TTS）
curl -s http://localhost:50021/version | jq .
# 期待される応答: {"version":"0.14.1","build":"..."}

# Kokoro TTS（英語TTS）
curl -s http://localhost:8880/v1/audio/voices | jq .
# 期待される応答: {"voices":[...]}
```

### 4. TTS テスト

**実行場所**: プロジェクトルート（`engineercafe-navigator`）で実行する場合は `from backend.agents.voice_agent import VoiceAgent` を使用してください。`backend` で実行する場合は `from agents.voice_agent import VoiceAgent` でOKです。`ModuleNotFoundError: No module named 'langchain_core'` が出る場合は、先に「Q4」の手順で依存関係をインストールしてください。

**日本語・英語をまとめて試す場合**（推奨）:
```bash
# プロジェクトルートから
python -m backend.scripts.test_tts
```
```bash
# backend ディレクトリから
python -m scripts.test_tts
```
上記で日本語（VoiceVox）と英語（Kokoro TTS）の両方を実行し、結果を表示します。

```bash
# 日本語TTSテスト（VoiceVox）
python -c "
import asyncio
from agents.voice_agent import VoiceAgent

async def test():
    agent = VoiceAgent(tts_provider='voicevox')
    result = await agent.text_to_speech('こんにちは', language='ja')
    print('✅ Japanese TTS Result (VoiceVox):')
    print(f\"  - Success: {result['success']}\")
    print(f\"  - Format: {result.get('format')}\")
    print(f\"  - Language: {result.get('language')}\")
    print(f\"  - Emotion: {result.get('emotion')}\")
    print(f\"  - Audio length: {len(result.get('audioResponse', ''))} chars (base64)\")

asyncio.run(test())
"

# 英語TTSテスト（Kokoro TTS）
python -c "
import asyncio
from agents.voice_agent import VoiceAgent

async def test():
    agent = VoiceAgent(tts_provider='voicevox')
    result = await agent.text_to_speech('Hello, welcome to Engineer Cafe!', language='en')
    print('✅ English TTS Result (Kokoro TTS):')
    print(f\"  - Success: {result['success']}\")
    print(f\"  - Format: {result.get('format')}\")
    print(f\"  - Language: {result.get('language')}\")
    print(f\"  - Emotion: {result.get('emotion')}\")
    print(f\"  - Audio length: {len(result.get('audioResponse', ''))} chars (base64)\")

asyncio.run(test())
"
```

## トラブルシューティング

### Q1: Vosk が見つからないというエラーが出る
```
RuntimeError: Vosk model not found: models/vosk-model-ja
```

→ セットアップ手順 2.1 でモデルをダウンロード・配置してください

### Q2: VoiceVox に接続できない
```
RuntimeError: VoiceVox connection timeout: ...
```

→ `docker compose up voicevox -d` で VoiceVox サービスが起動していることを確認：
```bash
docker ps | grep voicevox
curl http://localhost:50021/version
```

### Q2-2: Kokoro TTS に接続できない
```
RuntimeError: Kokoro TTS connection timeout: ...
```

→ `docker compose up kokoro-tts -d` で Kokoro TTS サービスが起動していることを確認：
```bash
docker ps | grep kokoro
curl http://localhost:8880/v1/audio/voices
```

### Q3: Google Cloud STT を使いたい
1. Google Cloud 認証キーを取得
2. `.env` に設定：
   ```env
   GOOGLE_CLOUD_CREDENTIALS=/path/to/service-account-key.json
   GOOGLE_CLOUD_PROJECT_ID=your-project-id
   STT_PROVIDER=google
   ```

### Q4: ModuleNotFoundError: No module named 'langchain_core'
```
from backend.agents.voice_agent import VoiceAgent で上記エラーになる
```

→ バックエンドの依存関係が入っていません。**プロジェクトルート**で次を実行してください：
```bash
cd /path/to/engineercafe-navigator
pip install -r backend/requirements.txt
```
仮想環境を使う場合：
```bash
cd engineercafe-navigator
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```
その後、再度 TTS テストを実行してください。コマンドは **行頭の `#` を除いた1行**で実行します（`#` はコメントなのでシェルに貼るとエラーになります）。

### Q5: モデルファイルが大きくて DL が遅い
- 日本語のみ必要な場合は `vosk-model-ja` だけダウンロード
- Wi-Fi が安定した環境で実行推奨（100MB × 2 = 約 200MB）

## ファイル一覧

| ファイル | 説明 |
|---------|------|
| `backend/agents/stt_agent.py` | Vosk/Google STT クライアント実装 |
| `backend/agents/voice_agent.py` | VoiceVox/Kokoro TTS/Google TTS クライアント実装 |
| `backend/requirements.txt` | vosk, soundfile 依存宣言 |
| `backend/pyproject.toml` | Poetry/uv 互換依存宣言 |
| `docker-compose.yml` | VoiceVox と Kokoro TTS サービス定義 |
| `backend/models/` | Vosk モデルの配置先（.gitignore で除外） |

## 参考リンク

- [Vosk API](https://github.com/alphacep/vosk-api)
- [Vosk Models](https://alphacephei.com/vosk/models)
- [VoiceVox Engine](https://github.com/VOICEVOX/voicevox_engine)
- [VoiceVox Docker Hub](https://hub.docker.com/r/voicevox/voicevox_engine)
- [Kokoro FastAPI](https://github.com/remsky/Kokoro-FastAPI)
- [Kokoro TTS Docker Setup](https://github.com/remsky/Kokoro-FastAPI/wiki/Setup-Docker)
