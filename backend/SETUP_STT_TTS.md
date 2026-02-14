# STT/TTS ローカル環境セットアップガイド

このドキュメントは、Vosk（STT）と VoiceVox（TTS）のローカルセットアップ手順です。

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
- `vosk>=0.3.45` — ローカル音声認識エンジン
- `soundfile>=0.12.1` — WAV ファイル処理

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

### 3. Docker Compose で VoiceVox を起動

`docker-compose.yml` に VoiceVox サービスが追加済みです。

```bash
# プロジェクトルートから実行
docker compose up voicevox -d

# VoiceVox が起動したか確認（Health check）
curl http://localhost:50021/version
# 期待される応答例: {"version":"0.14.1",...}
```

### 4. 環境変数設定

`backend/.env` に以下を追加：

```env
# STT/TTS Provider settings
TTS_PROVIDER=voicevox          # ローカル優先
STT_PROVIDER=vosk             # ローカル優先
VOICEVOX_API_URL=http://localhost:50021

# Google Cloud（オプション・フォールバック用）
# GOOGLE_CLOUD_CREDENTIALS=...
# GOOGLE_CLOUD_PROJECT_ID=...
```

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

### 3. VoiceVox ヘルスチェック

```bash
curl -s http://localhost:50021/version | jq .
# 期待される応答: {"version":"0.14.1","build":"..."}
```

### 4. TTS テスト

```bash
python -c "
import asyncio
from agents.voice_agent import VoiceAgent

async def test():
    agent = VoiceAgent(tts_provider='voicevox')
    result = await agent.text_to_speech('こんにちは', language='ja')
    print('✅ TTS Result:')
    print(f\"  - Success: {result['success']}\")
    print(f\"  - Format: {result.get('format')}\")
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

### Q3: Google Cloud STT を使いたい
1. Google Cloud 認証キーを取得
2. `.env` に設定：
   ```env
   GOOGLE_CLOUD_CREDENTIALS=/path/to/service-account-key.json
   GOOGLE_CLOUD_PROJECT_ID=your-project-id
   STT_PROVIDER=google
   ```

### Q4: モデルファイルが大きくて DL が遅い
- 日本語のみ必要な場合は `vosk-model-ja` だけダウンロード
- Wi-Fi が安定した環境で実行推奨（100MB × 2 = 約 200MB）

## ファイル一覧

| ファイル | 説明 |
|---------|------|
| `backend/agents/stt_agent.py` | Vosk/Google STT クライアント実装 |
| `backend/agents/voice_agent.py` | VoiceVox/Google TTS クライアント実装 |
| `backend/requirements.txt` | vosk, soundfile 依存宣言 |
| `backend/pyproject.toml` | Poetry/uv 互換依存宣言 |
| `docker-compose.yml` | VoiceVox サービス定義 |
| `backend/models/` | Vosk モデルの配置先（.gitignore で除外） |

## 参考リンク

- [Vosk API](https://github.com/alphacep/vosk-api)
- [Vosk Models](https://alphacephei.com/vosk/models)
- [VoiceVox Engine](https://github.com/VOICEVOX/voicevox_engine)
- [VoiceVox Docker Hub](https://hub.docker.com/r/voicevox/voicevox_engine)
