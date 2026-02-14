# PR #62 ローカルSTT/TTS テスト手順書

> **対象PR**: [#62 feat(#56): ローカルSTT/TTS統合 - Vosk + VoiceVox対応](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/62)
> **対象ブランチ**: `feature/voice-agent`
> **作成日**: 2026-02-14

---

## 目次

1. [前提条件](#1-前提条件)
2. [環境構築](#2-環境構築)
3. [自動テスト（pytest）](#3-自動テストpytest)
4. [手動テスト（VoiceVox TTS）](#4-手動テストvoicevox-tts)
5. [手動テスト（Vosk STT）](#5-手動テストvosk-stt)
6. [手動テスト（APIエンドポイント経由）](#6-手動テストapiエンドポイント経由)
7. [手動テスト（Docker Compose 統合）](#7-手動テストdocker-compose-統合)
8. [確認チェックリスト](#8-確認チェックリスト)
9. [トラブルシューティング](#9-トラブルシューティング)
10. [アーキテクチャ概要](#10-アーキテクチャ概要)

---

## 1. 前提条件

### 必要なソフトウェア

| ソフトウェア | バージョン | 確認コマンド | 備考 |
|-------------|-----------|-------------|------|
| Python | 3.11以上 | `python --version` | |
| Docker | 20.10以上 | `docker --version` | VoiceVox実行用 |
| Docker Compose | v2以上 | `docker compose version` | |
| uv (推奨) | 最新 | `uv --version` | pipでも可 |
| curl | 任意 | `curl --version` | 動作確認用 |
| unzip | 任意 | `unzip -v` | Voskモデル展開用 |

### ディスク容量

| 項目 | サイズ | 必須 |
|------|--------|------|
| Vosk日本語モデル（small） | 約48MB | Yes |
| Vosk英語モデル（small） | 約40MB | No（英語テスト不要なら） |
| VoiceVox Dockerイメージ | 約2〜3GB | Yes |

---

## 2. 環境構築

### 2.1 ブランチの取得

```bash
cd /path/to/engineer-cafe-navigator2025
git fetch origin
git checkout feature/voice-agent
```

### 2.2 Python依存パッケージのインストール

```bash
cd backend

# uvの場合（推奨）
uv sync

# pipの場合
pip install -e ".[dev]"
```

vosk と pysoundfile が追加でインストールされます。

### 2.3 Voskモデルのダウンロード

スクリプトを使う方法（推奨）:

```bash
cd backend
bash scripts/download_vosk_models.sh
```

手動の場合:

```bash
cd backend
mkdir -p models

# 日本語モデル（必須）
curl -L -o /tmp/vosk-ja.zip https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip
unzip /tmp/vosk-ja.zip -d /tmp/vosk-ja-extract
mv /tmp/vosk-ja-extract/vosk-model-small-ja-0.22 models/vosk-model-ja
rm -rf /tmp/vosk-ja.zip /tmp/vosk-ja-extract

# 英語モデル（オプション）
curl -L -o /tmp/vosk-en.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip /tmp/vosk-en.zip -d /tmp/vosk-en-extract
mv /tmp/vosk-en-extract/vosk-model-small-en-us-0.15 models/vosk-model-en-us
rm -rf /tmp/vosk-en.zip /tmp/vosk-en-extract
```

ダウンロード後の確認:

```bash
ls -la backend/models/
# 以下が存在すればOK
# drwxr-xr-x  vosk-model-ja/
# drwxr-xr-x  vosk-model-en-us/   （オプション）
```

### 2.4 VoiceVox（Docker）の起動

```bash
# プロジェクトルートから実行
docker compose up voicevox -d

# 起動確認（数十秒〜1分程度かかる場合あり）
docker compose logs voicevox --tail 5

# ヘルスチェック
curl -s http://localhost:50021/version
# → バージョン情報のJSONが返ればOK
```

初回起動時はDockerイメージ(約2〜3GB)のダウンロードに時間がかかります。

### 2.5 環境変数の設定

`backend/.env` に以下を追加（既存の変数はそのまま残す）:

```env
# === STT/TTS ローカル設定 ===
TTS_PROVIDER=voicevox
STT_PROVIDER=vosk
VOICEVOX_API_URL=http://localhost:50021

# === 既存の設定（変更不要） ===
# OPENROUTER_API_KEY=...
# SUPABASE_URL=...
# SUPABASE_KEY=...
```

---

## 3. 自動テスト（pytest）

### 3.1 STT/TTSテストのみ実行

```bash
cd backend

# STTエージェントテスト（16件）
uv run pytest tests/agents/test_stt_agent.py -v

# VoiceAgentテスト（8件）
uv run pytest tests/agents/test_voice_agent.py -v

# 両方まとめて
uv run pytest tests/agents/test_stt_agent.py tests/agents/test_voice_agent.py -v
```

### 3.2 期待される結果

```
tests/agents/test_stt_agent.py::TestLocalSTTClient::test_init_default_paths PASSED
tests/agents/test_stt_agent.py::TestLocalSTTClient::test_init_custom_paths PASSED
tests/agents/test_stt_agent.py::TestLocalSTTClient::test_load_model_not_found_raises_error PASSED
tests/agents/test_stt_agent.py::TestLocalSTTClient::test_transcribe_vosk_success PASSED
tests/agents/test_stt_agent.py::TestLocalSTTClient::test_transcribe_empty_result_raises_error PASSED
tests/agents/test_stt_agent.py::TestLocalSTTClient::test_transcribe_invalid_json_raises_error PASSED
tests/agents/test_stt_agent.py::TestGoogleSTTClient::test_init PASSED
tests/agents/test_stt_agent.py::TestGoogleSTTClient::test_transcribe_sync_wrapper PASSED
tests/agents/test_stt_agent.py::TestSTTAgent::test_init_default_provider_vosk PASSED
tests/agents/test_stt_agent.py::TestSTTAgent::test_init_env_var_provider PASSED
tests/agents/test_stt_agent.py::TestSTTAgent::test_init_custom_provider PASSED
tests/agents/test_stt_agent.py::TestSTTAgent::test_init_invalid_provider_raises_error PASSED
tests/agents/test_stt_agent.py::TestSTTAgent::test_init_custom_client PASSED
tests/agents/test_stt_agent.py::TestSTTAgent::test_speech_to_text_success PASSED
tests/agents/test_stt_agent.py::TestSTTAgent::test_speech_to_text_failure PASSED
tests/agents/test_stt_agent.py::test_stt_agent_with_mock_vosk PASSED

16 passed
```

### 3.3 全テスト実行（回帰テスト確認）

```bash
cd backend
uv run pytest tests/ -v
```

既存テストが壊れていないことを確認してください。

---

## 4. 手動テスト（VoiceVox TTS）

VoiceVoxが起動した状態で、Pythonから直接テストします。

### 4.1 VoiceVox単体テスト

```bash
cd backend
uv run python -c "
import asyncio
from agents.voice_agent import VoiceVoxClient

async def test():
    client = VoiceVoxClient('http://localhost:50021')

    # 日本語TTS
    audio_b64 = await client.synthesize_wav_base64(
        text='こんにちは、エンジニアカフェへようこそ',
        lang='ja'
    )
    print(f'日本語TTS成功: base64長={len(audio_b64)} chars')

    # 短いテキスト
    audio_b64_short = await client.synthesize_wav_base64(
        text='はい',
        lang='ja'
    )
    print(f'短文TTS成功: base64長={len(audio_b64_short)} chars')

asyncio.run(test())
"
```

期待される出力:

```
日本語TTS成功: base64長=XXXXX chars
短文TTS成功: base64長=XXXXX chars
```

### 4.2 VoiceAgent経由のTTSテスト

```bash
cd backend
uv run python -c "
import asyncio
from agents.voice_agent import VoiceAgent

async def test():
    agent = VoiceAgent(tts_provider='voicevox')
    result = await agent.text_to_speech(
        text='エンジニアカフェの営業時間は、火曜日から土曜日の9時から22時です。',
        language='ja',
        emotion=None
    )
    print(f'成功: {result[\"success\"]}')
    print(f'フォーマット: {result.get(\"format\")}')
    print(f'感情: {result.get(\"emotion\")}')
    print(f'音声データ長: {len(result.get(\"audioResponse\", \"\"))} chars')

asyncio.run(test())
"
```

期待される出力:

```
成功: True
フォーマット: audio/wav
感情: neutral
音声データ長: XXXXX chars
```

### 4.3 感情タグ付きテスト

```bash
cd backend
uv run python -c "
import asyncio
from agents.voice_agent import VoiceAgent

async def test():
    agent = VoiceAgent(tts_provider='voicevox')

    # 感情タグ付きテキスト
    result = await agent.text_to_speech(
        text='[happy]ようこそ！エンジニアカフェへ！',
        language='ja',
        emotion=None
    )
    print(f'感情タグ解析: emotion={result.get(\"emotion\")}')
    print(f'成功: {result[\"success\"]}')

asyncio.run(test())
"
```

### 4.4 音声ファイルとして保存して再生確認

```bash
cd backend
uv run python -c "
import asyncio
import base64
from agents.voice_agent import VoiceAgent

async def test():
    agent = VoiceAgent(tts_provider='voicevox')
    result = await agent.text_to_speech(
        text='テスト音声です。正しく再生できていますか？',
        language='ja'
    )
    if result['success']:
        audio_bytes = base64.b64decode(result['audioResponse'])
        with open('/tmp/tts_test.wav', 'wb') as f:
            f.write(audio_bytes)
        print(f'音声ファイル保存: /tmp/tts_test.wav ({len(audio_bytes)} bytes)')
        print('再生: open /tmp/tts_test.wav  (macOS)')
    else:
        print(f'エラー: {result.get(\"error\")}')

asyncio.run(test())
"

# macOSで再生
open /tmp/tts_test.wav
```

---

## 5. 手動テスト（Vosk STT）

Voskモデルがダウンロード済みの状態でテストします。

### 5.1 モデルロードテスト

```bash
cd backend
uv run python -c "
from agents.stt_agent import LocalSTTClient
import os

client = LocalSTTClient()

# モデルパスの確認
ja_exists = os.path.exists('models/vosk-model-ja')
en_exists = os.path.exists('models/vosk-model-en-us')
print(f'日本語モデル: {\"OK\" if ja_exists else \"未ダウンロード\"}')
print(f'英語モデル: {\"OK\" if en_exists else \"未ダウンロード\"}')

# モデル実ロード（日本語）
if ja_exists:
    model = client._load_model('ja')
    print(f'日本語モデルロード: 成功')
"
```

### 5.2 STTAgent初期化テスト

```bash
cd backend
uv run python -c "
from agents.stt_agent import STTAgent

# デフォルト（Vosk）
agent = STTAgent()
print(f'プロバイダ: {agent.provider}')
print(f'クライアント型: {type(agent.client).__name__}')

# Google指定
agent_google = STTAgent(stt_provider='google')
print(f'Googleプロバイダ: {agent_google.provider}')
"
```

### 5.3 WAVファイルで音声認識テスト

テスト用のWAVファイルがある場合:

```bash
cd backend
uv run python -c "
import asyncio
from agents.stt_agent import STTAgent

async def test():
    agent = STTAgent(stt_provider='vosk')

    # テスト用WAVファイルのパスを指定
    wav_path = '/path/to/test.wav'  # 16kHz, 16bit, mono推奨

    import os
    if not os.path.exists(wav_path):
        print('テスト用WAVファイルが見つかりません')
        print('16kHz, 16bit, monoのWAVファイルを用意してください')
        return

    with open(wav_path, 'rb') as f:
        audio_data = f.read()

    result = await agent.speech_to_text(audio_data, language='ja')
    print(f'認識結果: {result}')

asyncio.run(test())
"
```

### 5.4 TTS→STTラウンドトリップテスト

VoiceVoxで生成した音声をVoskで認識する統合テスト:

```bash
cd backend
uv run python -c "
import asyncio
import base64
from agents.voice_agent import VoiceAgent
from agents.stt_agent import STTAgent

async def test():
    # 1. TTSで音声生成
    tts = VoiceAgent(tts_provider='voicevox')
    tts_result = await tts.text_to_speech(text='こんにちは', language='ja')

    if not tts_result['success']:
        print(f'TTS失敗: {tts_result.get(\"error\")}')
        return

    print(f'TTS成功: {len(tts_result[\"audioResponse\"])} chars (base64)')

    # 2. STTで認識
    stt = STTAgent(stt_provider='vosk')
    audio_bytes = base64.b64decode(tts_result['audioResponse'])
    stt_result = await stt.speech_to_text(audio_bytes, language='ja')

    print(f'STT結果: {stt_result}')
    if stt_result.get('success'):
        print(f'認識テキスト: {stt_result[\"transcript\"]}')
    else:
        print(f'STTエラー: {stt_result.get(\"error\")}')
        print('(VoiceVoxのWAV形式がVoskの期待と異なる可能性あり)')

asyncio.run(test())
"
```

---

## 6. 手動テスト（APIエンドポイント経由）

### 6.1 バックエンドサーバーの起動

```bash
cd backend
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 6.2 TTS APIテスト（curl）

```bash
# VoiceVox TTS
curl -X POST http://localhost:8000/api/voice \
  -H "Content-Type: application/json" \
  -d '{
    "action": "text_to_speech",
    "text": "こんにちは、エンジニアカフェへようこそ",
    "language": "ja",
    "sessionId": "test-session-001"
  }' | python -m json.tool
```

期待される応答:

```json
{
  "success": true,
  "transcript": null,
  "response": null,
  "audioResponse": "UklGRi...(base64音声データ)...",
  "emotion": "neutral",
  "sessionId": "test-session-001",
  "error": null
}
```

### 6.3 STT APIテスト（curl）

> 現時点では`/api/voice`の`process_voice`アクションはプレースホルダーです。
> STTAgent自体は実装済みですが、APIエンドポイントとの統合は未完了。

```bash
# process_voice（プレースホルダー応答）
curl -X POST http://localhost:8000/api/voice \
  -H "Content-Type: application/json" \
  -d '{
    "action": "process_voice",
    "audioData": "",
    "language": "ja",
    "sessionId": "test-session-001"
  }' | python -m json.tool
```

期待される応答（プレースホルダー）:

```json
{
  "success": true,
  "transcript": "音声処理中...",
  "response": "音声処理機能は実装中です。",
  "emotion": "neutral",
  "sessionId": "test-session-001",
  "error": null
}
```

### 6.4 エラーケーステスト

```bash
# 不正なアクション
curl -X POST http://localhost:8000/api/voice \
  -H "Content-Type: application/json" \
  -d '{
    "action": "invalid_action",
    "sessionId": "test-session-001"
  }' | python -m json.tool
# → 400 Bad Request

# text_to_speechでtext未指定
curl -X POST http://localhost:8000/api/voice \
  -H "Content-Type: application/json" \
  -d '{
    "action": "text_to_speech",
    "text": "",
    "sessionId": "test-session-001"
  }' | python -m json.tool
# → 400 Bad Request (Missing text)
```

---

## 7. 手動テスト（Docker Compose 統合）

フルスタック環境での統合テスト。

### 7.1 全サービス起動

```bash
# プロジェクトルートから
docker compose up -d

# 起動状態確認
docker compose ps
# frontend, backend, voicevox の3サービスが running であること
```

### 7.2 各サービスのヘルスチェック

```bash
# バックエンド
curl -s http://localhost:8000/health | python -m json.tool

# VoiceVox
curl -s http://localhost:50021/version

# フロントエンド
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}"
```

### 7.3 Docker環境でのTTSテスト

```bash
curl -X POST http://localhost:8000/api/voice \
  -H "Content-Type: application/json" \
  -d '{
    "action": "text_to_speech",
    "text": "Docker環境からのテスト音声です",
    "language": "ja",
    "sessionId": "docker-test-001"
  }' | python -m json.tool
```

### 7.4 ログ確認

```bash
# バックエンドログ
docker compose logs backend --tail 50

# VoiceVoxログ
docker compose logs voicevox --tail 20
```

---

## 8. 確認チェックリスト

テスト完了時に以下を確認してください。

### 自動テスト

- [ ] `test_stt_agent.py` 全16件パス
- [ ] `test_voice_agent.py` 全8件パス
- [ ] 既存テスト（`tests/` 全体）に回帰なし

### VoiceVox TTS

- [ ] VoiceVoxClient単体で音声生成できる
- [ ] VoiceAgent経由で音声生成できる
- [ ] 感情タグ（`[happy]`, `[sad]`等）が正しくパースされる
- [ ] 生成されたWAVファイルが正しく再生できる
- [ ] 日本語テキストが自然に読み上げられる

### Vosk STT

- [ ] Voskモデルが正常にロードできる
- [ ] WAVファイルからテキスト認識ができる（テスト用WAVがある場合）
- [ ] STTAgent のプロバイダ切り替え（vosk/google）が動作する

### APIエンドポイント

- [ ] `POST /api/voice` (text_to_speech) が200を返す
- [ ] `POST /api/voice` (process_voice) がプレースホルダー応答を返す
- [ ] 不正なリクエストが適切なエラーを返す

### Docker統合

- [ ] `docker compose up` で全サービスが起動する
- [ ] VoiceVoxヘルスチェックがパスする
- [ ] Docker環境からTTSが動作する

---

## 9. トラブルシューティング

### Q1: `ModuleNotFoundError: No module named 'vosk'`

```bash
# uvの場合
uv sync

# pipの場合
pip install vosk>=0.3.45 pysoundfile>=0.12.1
```

### Q2: `RuntimeError: Vosk model not found: models/vosk-model-ja`

```bash
# モデルをダウンロード
cd backend
bash scripts/download_vosk_models.sh
```

### Q3: VoiceVoxに接続できない（Connection refused）

```bash
# VoiceVoxが起動しているか確認
docker compose ps voicevox
# STATUS が healthy でなければ待つ or 再起動

docker compose restart voicevox
# 30秒〜1分待ってから再試行
curl http://localhost:50021/version
```

### Q4: VoiceVox Dockerイメージのダウンロードが遅い

初回は約2〜3GBのイメージをダウンロードします。安定したネットワーク環境で実行してください。

```bash
# プルのみ先に実行
docker pull voicevox/voicevox_engine:latest
```

### Q5: `backend.agents.clarification_agent` ImportError

voice_agent.pyが `from backend.agents.clarification_agent import ...` を使っています。
`backend` プレフィックス付きのimportなので、backendディレクトリの親からPYTHONPATHを通す必要がある場合があります。

```bash
# backendディレクトリ内で実行する場合
cd backend
PYTHONPATH=.. uv run python -c "from agents.voice_agent import VoiceAgent; print('OK')"
```

または、直接pytestで実行すれば`conftest.py`がパスを解決します。

### Q6: ポート50021が既に使用されている

```bash
# 使用中のプロセスを確認
lsof -i :50021

# 別ポートで起動する場合はdocker-compose.ymlを編集
# ports: "50022:50021" に変更し、.envも更新
# VOICEVOX_API_URL=http://localhost:50022
```

### Q7: Apple Silicon (M1/M2) での注意

VoiceVox DockerイメージはCPUモードで動作します。ARM版でも動作しますが、初回の音声合成に数秒かかる場合があります。

---

## 10. アーキテクチャ概要

```
┌─────────────────────────────────────────────────────┐
│                  フロントエンド                       │
│                  (Next.js)                           │
└─────────────┬───────────────────────────┬────────────┘
              │ POST /api/voice           │
              │ action: text_to_speech    │ action: process_voice
              ▼                           ▼
┌─────────────────────────────────────────────────────┐
│                  main.py                             │
│                  FastAPI                              │
└─────────────┬───────────────────────────┬────────────┘
              │                           │
              ▼                           ▼
┌──────────────────────┐    ┌──────────────────────────┐
│     VoiceAgent       │    │       STTAgent           │
│  (voice_agent.py)    │    │    (stt_agent.py)        │
├──────────────────────┤    ├──────────────────────────┤
│ tts_provider:        │    │ stt_provider:            │
│  ├ voicevox (default)│    │  ├ vosk (default)        │
│  └ google (fallback) │    │  └ google (fallback)     │
└──────────┬───────────┘    └──────────┬───────────────┘
           │                           │
           ▼                           ▼
┌──────────────────┐       ┌──────────────────────────┐
│  VoiceVoxClient  │       │   LocalSTTClient (Vosk)  │
│  localhost:50021  │       │   models/vosk-model-ja   │
└──────────────────┘       └──────────────────────────┘
           │
           ▼
┌──────────────────┐
│ VoiceVox Engine  │
│ (Docker Container)│
└──────────────────┘
```

### プロバイダ切り替え

環境変数で制御:

| 環境変数 | 値 | 説明 |
|---------|-----|------|
| `TTS_PROVIDER` | `voicevox` | ローカルTTS（デフォルト） |
| `TTS_PROVIDER` | `google` | Google Cloud TTS |
| `STT_PROVIDER` | `vosk` | ローカルSTT（デフォルト） |
| `STT_PROVIDER` | `google` | Google Cloud STT |
| `VOICEVOX_API_URL` | `http://localhost:50021` | VoiceVox APIのURL |

### 主要ファイル一覧

| ファイル | 説明 |
|---------|------|
| `backend/agents/voice_agent.py` | TTS実装（VoiceVoxClient + GoogleTTSClient + VoiceAgent） |
| `backend/agents/stt_agent.py` | STT実装（LocalSTTClient + GoogleSTTClient + STTAgent） |
| `backend/tests/agents/test_voice_agent.py` | VoiceAgentテスト（8件） |
| `backend/tests/agents/test_stt_agent.py` | STTAgentテスト（16件） |
| `backend/scripts/download_vosk_models.sh` | Voskモデルダウンロードスクリプト |
| `docker-compose.yml` | VoiceVoxサービス定義 |
| `backend/Dockerfile` | Voskモデル組み込みビルド |
| `backend/SETUP_STT_TTS.md` | セットアップガイド（詳細版） |
