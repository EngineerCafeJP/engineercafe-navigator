# Environment Variables Guide

> 注意: この文書には deprecated agent 前提や古い env 依存が残っています。現行の env 判断は `docs/STATUS.md` と実装コードを優先してください。

このドキュメントでは、Engineer Cafe Navigator のバックエンドで使用される環境変数について説明します。

## 目次

- [環境変数一覧](#環境変数一覧)
- [エージェント別環境変数マトリクス](#エージェント別環境変数マトリクス)
- [API Key 取得方法](#api-key-取得方法)
- [ローカル開発環境のセットアップ](#ローカル開発環境のセットアップ)
- [トラブルシューティング](#トラブルシューティング)

---

## 環境変数一覧

### 必須環境変数

| 環境変数 | 必須/オプション | 用途 | 取得方法 |
|----------|----------------|------|----------|
| `OPENROUTER_API_KEY` | **必須** | LLM APIアクセス（全エージェント） | [OpenRouter](https://openrouter.ai/keys) |
| `SUPABASE_URL` | **必須** | Supabaseプロジェクト接続 | Supabase Dashboard |
| `SUPABASE_KEY` | **必須** | Supabase認証（Service Role Key） | Supabase Dashboard |
| `OPENAI_API_KEY` | **必須** | Embeddingsモデル使用 | [OpenAI](https://platform.openai.com/api-keys) |

### オプション環境変数

| 環境変数 | 必須/オプション | 用途 | 取得方法 |
|----------|----------------|------|----------|
| `GOOGLE_API_KEY` | オプション | Google Calendar API | Google Cloud Console |
| `GOOGLE_CALENDAR_ID` | オプション | カレンダーイベント取得 | Google Calendar設定 |
| `GOOGLE_APPLICATION_CREDENTIALS` | オプション | Voice/OCR Agent (GCP認証) | Google Cloud Console |
| `ENVIRONMENT` | オプション | 環境モード設定 | - |
| `PORT` | オプション | バックエンドポート | デフォルト: 8000 |
| `APP_URL` | オプション | アプリケーションURL | デフォルト: http://localhost:3000 |
| `LOG_LEVEL` | オプション | ログレベル | デフォルト: INFO |

---

## エージェント別環境変数マトリクス

各エージェントが必要とする環境変数の一覧です。

| エージェント | OPENROUTER | SUPABASE | OPENAI | GOOGLE_API | GOOGLE_CALENDAR | GCP_CREDENTIALS |
|-------------|:----------:|:--------:|:------:|:----------:|:---------------:|:---------------:|
| **RouterAgent** | X | - | - | - | - | - |
| **BusinessInfoAgent** | X | X | X | - | - | - |
| **FacilityAgent** | X | X | X | - | - | - |
| **EventAgent** | X | - | - | X | X | - |
| **MemoryAgent** | X | - | - | - | - | - |
| **SlideAgent** | X | - | - | - | - | - |
| **GeneralKnowledgeAgent** | X | X | X | - | - | - |
| **ClarificationAgent** | X | - | - | - | - | - |
| **CharacterControlAgent** | - | - | - | - | - | - |
| **VoiceAgent** | - | - | - | - | - | X |
| **OCRAgent** | - | - | - | - | - | X |

- X: 必須
- -: 不要

### 機能別の最小構成

#### 基本機能のみ（チャット応答）

```bash
OPENROUTER_API_KEY=sk-or-v1-xxx
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=your-service-role-key
OPENAI_API_KEY=sk-xxx
```

#### イベント機能追加

```bash
# 基本機能 + 以下を追加
GOOGLE_API_KEY=xxx
GOOGLE_CALENDAR_ID=xxx@group.calendar.google.com
```

#### 音声機能追加

```bash
# 基本機能 + 以下を追加
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

---

## API Key 取得方法

### 1. OpenRouter API Key

OpenRouterは400以上のLLMモデル（OpenAI, Google, Anthropic, Meta等）に統一的にアクセスできるAPIゲートウェイです。

1. [OpenRouter](https://openrouter.ai/) にアクセス
2. GitHubまたはGoogleアカウントでサインイン
3. [API Keys](https://openrouter.ai/keys) ページで「Create Key」をクリック
4. キー名を入力（例: `engineer-cafe-dev`）
5. 生成されたキーをコピー（`sk-or-v1-` で始まる）

**注意**: 無料クレジットが付与されますが、本番運用には有料プランが必要です。

### 2. Supabase設定

#### ローカル開発（推奨）

```bash
# Supabase CLIのインストール
npm install -g supabase

# プロジェクトディレクトリで初期化
supabase init
supabase start
```

ローカル起動後、以下の情報が表示されます:

```
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... (service_role key)
```

#### クラウド（本番用）

1. [Supabase](https://supabase.com/) にアクセス
2. 新しいプロジェクトを作成
3. Settings -> API から以下を取得:
   - Project URL → `SUPABASE_URL`
   - service_role (secret) → `SUPABASE_KEY`

### 3. OpenAI API Key

RAG検索のEmbeddings生成に使用します（`text-embedding-3-small`モデル）。

1. [OpenAI Platform](https://platform.openai.com/) にログイン
2. [API Keys](https://platform.openai.com/api-keys) ページにアクセス
3. 「Create new secret key」をクリック
4. キー名を入力し、生成されたキーをコピー（`sk-` で始まる）

**コスト目安**: text-embedding-3-small は $0.02 / 1M tokens（非常に低コスト）

### 4. Google Calendar API

EventAgentでカレンダーイベントを取得するために使用します。

#### API Keyの取得

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 新しいプロジェクトを作成（または既存を選択）
3. APIs & Services -> Library で「Google Calendar API」を有効化
4. APIs & Services -> Credentials で「Create Credentials」→「API Key」
5. 生成されたキーをコピー

#### Calendar IDの取得

1. [Google Calendar](https://calendar.google.com/) にアクセス
2. 対象カレンダーの設定を開く
3. 「Integrate calendar」セクションで「Calendar ID」をコピー

### 5. Google Cloud認証（Voice/OCR Agent用）

Speech-to-Text、Text-to-Speech、Vision APIに使用します。

#### サービスアカウントの作成

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. IAM & Admin -> Service Accounts で「Create Service Account」
3. 以下のロールを付与:
   - Cloud Speech-to-Text API User
   - Cloud Text-to-Speech API User
   - Cloud Vision API User
4. 「Keys」タブで「Add Key」→「Create new key」→「JSON」
5. ダウンロードしたJSONファイルのパスを `GOOGLE_APPLICATION_CREDENTIALS` に設定

#### 必要なAPIの有効化

```bash
# gcloud CLIを使用する場合
gcloud services enable speech.googleapis.com
gcloud services enable texttospeech.googleapis.com
gcloud services enable vision.googleapis.com
```

---

## ローカル開発環境のセットアップ

### 1. 環境ファイルの作成

```bash
cd backend
cp .env.example .env
```

### 2. 最小構成の設定

```bash
# .env ファイルを編集
OPENROUTER_API_KEY=sk-or-v1-your-actual-key
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=your-local-supabase-key
OPENAI_API_KEY=sk-your-openai-key
ENVIRONMENT=development
PORT=8000
APP_URL=http://localhost:3000
```

### 3. 設定の確認

```bash
# バックエンドの起動
cd backend
python -m uvicorn main:app --reload

# ヘルスチェック
curl http://localhost:8000/health
```

---

## トラブルシューティング

### 一般的なエラーと解決方法

#### OpenRouter API Key エラー

```
ValueError: OpenRouter API key not found.
Set OPENROUTER_API_KEY environment variable or pass api_key parameter.
```

**解決方法**:
1. `.env` ファイルに `OPENROUTER_API_KEY` が設定されているか確認
2. キーが `sk-or-v1-` で始まっているか確認
3. キーの有効期限を確認（OpenRouterダッシュボード）

#### Supabase 接続エラー

```
supabase.exceptions.AuthApiError: Invalid API key
```

**解決方法**:
1. `SUPABASE_URL` と `SUPABASE_KEY` が正しいか確認
2. ローカル開発の場合、`supabase start` が実行されているか確認
3. Service Role Key（`service_role`）を使用しているか確認（`anon` キーではない）

#### OpenAI Embeddings エラー

```
Embedding API error: 401 Unauthorized
```

**解決方法**:
1. `OPENAI_API_KEY` が正しいか確認
2. キーに有効なクレジットがあるか確認
3. キーの権限（Permissions）を確認

#### Google Calendar API エラー

```
[CalendarService] Calendar ID or API Key not configured
```

**解決方法**:
1. `GOOGLE_API_KEY` と `GOOGLE_CALENDAR_ID` が設定されているか確認
2. Calendar APIが有効化されているか確認
3. カレンダーが公開設定になっているか確認

#### Google Cloud 認証エラー

```
google.auth.exceptions.DefaultCredentialsError: Could not automatically determine credentials.
```

**解決方法**:
1. `GOOGLE_APPLICATION_CREDENTIALS` のパスが正しいか確認
2. JSONファイルが存在し、読み取り可能か確認
3. サービスアカウントに必要な権限があるか確認

### 環境変数のデバッグ

```python
# Pythonで環境変数を確認
import os

required_vars = [
    'OPENROUTER_API_KEY',
    'SUPABASE_URL',
    'SUPABASE_KEY',
    'OPENAI_API_KEY',
]

for var in required_vars:
    value = os.getenv(var)
    if value:
        # キーの先頭と末尾のみ表示（セキュリティのため）
        masked = value[:8] + '...' + value[-4:] if len(value) > 12 else '***'
        print(f"{var}: {masked}")
    else:
        print(f"{var}: NOT SET")
```

### ログレベルの調整

問題が発生した場合、ログレベルを `DEBUG` に設定すると詳細なログが出力されます。

```bash
LOG_LEVEL=DEBUG
```

---

## 関連ドキュメント

- [LOCAL-DEVELOPMENT-SETUP.md](./LOCAL-DEVELOPMENT-SETUP.md) - ローカル開発環境の詳細セットアップ
- [DEVELOPER-GUIDE.md](./DEVELOPER-GUIDE.md) - 開発者ガイド
- [backend/llm/models.py](../../backend/llm/models.py) - 利用可能なLLMモデル一覧
