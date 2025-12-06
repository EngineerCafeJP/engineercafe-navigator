# ローカル開発環境セットアップガイド

このガイドでは、Engineer Cafe Navigator プロジェクトのローカル開発環境をセットアップする方法を説明します。

## 目次

1. [前提条件](#前提条件)
2. [プロジェクト構成](#プロジェクト構成)
3. [Supabase ローカル環境のセットアップ](#supabase-ローカル環境のセットアップ)
4. [Frontend（Next.js/Mastra）のセットアップ](#frontendnextjsmastraのセットアップ)
5. [Backend（LangGraph）のセットアップ](#backendlanggraphのセットアップ)
6. [環境変数の設定](#環境変数の設定)
7. [データベースマイグレーション](#データベースマイグレーション)
8. [開発の開始](#開発の開始)
9. [トラブルシューティング](#トラブルシューティング)

---

## 前提条件

以下のツールがインストールされている必要があります：

| ツール | バージョン | インストール方法 |
|--------|-----------|-----------------|
| **Node.js** | 18.x 以上 | [nodejs.org](https://nodejs.org/) |
| **pnpm** | 8.x 以上 | `npm install -g pnpm` |
| **Python** | 3.11 以上 | [python.org](https://www.python.org/) |
| **Docker** | 最新版 | [docker.com](https://www.docker.com/) |
| **Supabase CLI** | 最新版 | `brew install supabase/tap/supabase` |
| **Git** | 最新版 | `brew install git` |

### Supabase CLI のインストール

```bash
# macOS (Homebrew)
brew install supabase/tap/supabase

# Windows (Scoop)
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase

# npm (全プラットフォーム)
npm install -g supabase
```

---

## プロジェクト構成

```
engineer-cafe-navigator2025/
├── frontend/              # Next.js + Mastra フロントエンド
│   ├── src/              # ソースコード
│   ├── supabase/         # Supabase設定・マイグレーション
│   │   ├── config.toml   # ローカルSupabase設定
│   │   ├── migrations/   # SQLマイグレーションファイル
│   │   └── seed.sql      # 初期データ
│   └── .env.example      # 環境変数テンプレート
├── backend/              # Python + LangGraph バックエンド
│   ├── src/              # ソースコード
│   │   └── agents/       # LangGraphエージェント
│   ├── requirements.txt  # Python依存関係
│   └── .env.example      # 環境変数テンプレート
├── docs/                 # ドキュメント
│   └── migration/        # エージェント移行ドキュメント
└── langgraph-reference/  # 参考実装
```

---

## Supabase ローカル環境のセットアップ

### 1. Docker の起動確認

Supabase CLI は Docker を使用します。Docker Desktop が起動していることを確認してください。

```bash
docker info
```

### 2. Supabase ローカル環境の起動

```bash
cd frontend

# Supabase ローカル環境を起動
supabase start
```

初回起動時は Docker イメージのダウンロードに時間がかかります（約5-10分）。

### 3. 起動確認

起動が完了すると、以下の情報が表示されます：

```
Started supabase local development setup.

         API URL: http://127.0.0.1:54321
     GraphQL URL: http://127.0.0.1:54321/graphql/v1
          DB URL: postgresql://postgres:postgres@127.0.0.1:54322/postgres
      Studio URL: http://127.0.0.1:54323
    Inbucket URL: http://127.0.0.1:54324
      JWT secret: super-secret-jwt-token-with-at-least-32-characters-long
        anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**重要な接続情報：**

| サービス | URL | 用途 |
|---------|-----|------|
| **API** | http://127.0.0.1:54321 | Supabase API エンドポイント |
| **Studio** | http://127.0.0.1:54323 | データベース管理UI |
| **Database** | postgresql://postgres:postgres@127.0.0.1:54322/postgres | 直接DB接続 |
| **Inbucket** | http://127.0.0.1:54324 | メールテスト用 |

### 4. Supabase Studio へのアクセス

ブラウザで http://127.0.0.1:54323 を開くと、Supabase Studio（データベース管理UI）にアクセスできます。

### 5. Supabase の停止

```bash
supabase stop
```

データを保持したまま停止する場合：
```bash
supabase stop --backup
```

---

## Frontend（Next.js/Mastra）のセットアップ

### 1. 依存関係のインストール

```bash
cd frontend
pnpm install
```

### 2. 環境変数の設定

```bash
cp .env.example .env.local
```

`.env.local` を編集し、以下の値を設定します：

```env
# Supabase ローカル環境（supabase start で表示された値を使用）
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase start で表示された anon key>
SUPABASE_SERVICE_ROLE_KEY=<supabase start で表示された service_role key>

# Google Cloud（音声処理用）
GOOGLE_CLOUD_PROJECT_ID=your-gcp-project-id
GOOGLE_CLOUD_CREDENTIALS=./config/service-account-key.json
GOOGLE_GENERATIVE_AI_API_KEY=your-gemini-api-key

# OpenAI（埋め込み用）
OPENAI_API_KEY=your-openai-api-key
```

### 3. サービスアカウントキーの設定

Google Cloud の音声機能を使用する場合、サービスアカウントキーが必要です：

```bash
mkdir -p config
# service-account-key.json を config/ ディレクトリに配置
```

### 4. 開発サーバーの起動

```bash
pnpm dev
```

http://localhost:3000 でアクセスできます。

---

## Backend（LangGraph）のセットアップ

### 1. Python 仮想環境の作成

```bash
cd backend

# venv を使用する場合
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# または Poetry を使用する場合
poetry install
poetry shell
```

### 2. 依存関係のインストール

```bash
pip install -r requirements.txt
```

主要な依存関係：

| パッケージ | バージョン | 用途 |
|-----------|-----------|------|
| langgraph | >=0.2.0 | ワークフローエンジン |
| langchain | >=0.3.0 | LLM フレームワーク |
| langchain-openai | >=0.2.0 | OpenAI 統合 |
| langchain-google-genai | >=2.0.0 | Gemini 統合 |
| fastapi | >=0.115.0 | Web フレームワーク |
| uvicorn | >=0.30.0 | ASGI サーバー |
| supabase | >=2.0.0 | Supabase クライアント |

### 3. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集：

```env
# AI API Keys
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key

# Supabase ローカル環境
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=<supabase start で表示された service_role key>

# サーバー設定
ENVIRONMENT=development
PORT=8000
```

### 4. 開発サーバーの起動

```bash
uvicorn src.main:app --reload --port 8000
```

http://localhost:8000/docs で API ドキュメント（Swagger UI）にアクセスできます。

---

## 環境変数の設定

### 必須の API キー取得

#### 1. OpenAI API Key

1. https://platform.openai.com/api-keys にアクセス
2. 「Create new secret key」をクリック
3. キーを安全に保存

**用途**: テキスト埋め込み（text-embedding-3-small、1536次元）

#### 2. Google Gemini API Key

1. https://makersuite.google.com/app/apikey にアクセス
2. 「Create API key」をクリック
3. キーを安全に保存

**用途**: AI 応答生成（Gemini 2.5 Flash Preview）

#### 3. Google Cloud サービスアカウント

音声機能（STT/TTS）を使用する場合：

1. Google Cloud Console でプロジェクトを作成
2. Cloud Speech-to-Text API と Cloud Text-to-Speech API を有効化
3. サービスアカウントを作成し、JSONキーをダウンロード
4. `frontend/config/service-account-key.json` として保存

### 環境変数一覧

#### Frontend (.env.local)

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase API URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase 匿名キー |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase サービスロールキー |
| `OPENAI_API_KEY` | ✅ | OpenAI API キー |
| `GOOGLE_GENERATIVE_AI_API_KEY` | ✅ | Gemini API キー |
| `GOOGLE_CLOUD_PROJECT_ID` | ⚠️ | GCP プロジェクトID（音声用） |
| `GOOGLE_CLOUD_CREDENTIALS` | ⚠️ | サービスアカウントキーパス |
| `CRON_SECRET` | ⚠️ | CRON ジョブ認証（本番用） |

#### Backend (.env)

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `OPENAI_API_KEY` | ✅ | OpenAI API キー |
| `GOOGLE_API_KEY` | ✅ | Gemini API キー |
| `SUPABASE_URL` | ✅ | Supabase API URL |
| `SUPABASE_KEY` | ✅ | Supabase サービスロールキー |
| `ENVIRONMENT` | ❌ | 環境（development/production） |
| `PORT` | ❌ | サーバーポート（デフォルト: 8000） |

---

## データベースマイグレーション

### マイグレーションファイル構成

```
frontend/supabase/migrations/
├── 20250529005253_init_engineer_cafe_navigator.sql  # 初期スキーマ
├── 20250601000000_add_knowledge_base_search.sql     # ベクトル検索
├── 20250601010000_add_analytics_tables.sql          # 分析テーブル
├── 20250607000000_add_metrics_tables.sql            # メトリクステーブル
└── 20250607010000_add_production_monitoring.sql     # 監視テーブル
```

### 主要テーブル

| テーブル | 説明 |
|---------|------|
| `conversation_sessions` | 会話セッション |
| `conversation_history` | 会話履歴 |
| `knowledge_base` | RAG 用ナレッジベース（1536次元ベクトル） |
| `agent_memory` | エージェントメモリ（TTL付き） |
| `conversation_analytics` | 会話分析 |
| `rag_search_metrics` | RAG 検索メトリクス |
| `system_metrics` | システムメトリクス |

### マイグレーションの実行

Supabase ローカル環境では、`supabase start` 時に自動的にマイグレーションが適用されます。

手動でマイグレーションを適用する場合：

```bash
cd frontend
supabase db reset  # データベースをリセットして全マイグレーションを適用
```

### シードデータの投入

```bash
# ナレッジベースの初期データ投入
pnpm seed:knowledge

# スライドナレーションのインポート
pnpm import:narrations
```

---

## 開発の開始

### 1. 全サービスの起動（推奨順序）

```bash
# ターミナル 1: Supabase
cd frontend
supabase start

# ターミナル 2: Frontend
cd frontend
pnpm dev

# ターミナル 3: Backend（LangGraph開発時のみ）
cd backend
source venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

### 2. 動作確認

| URL | サービス |
|-----|---------|
| http://localhost:3000 | Frontend（Next.js） |
| http://localhost:8000/docs | Backend API ドキュメント |
| http://127.0.0.1:54323 | Supabase Studio |

### 3. 開発コマンド

```bash
# Frontend
pnpm dev              # 開発サーバー起動
pnpm build            # ビルド
pnpm lint             # リント
pnpm typecheck        # 型チェック

# Backend
uvicorn src.main:app --reload  # 開発サーバー起動
pytest                         # テスト実行
```

---

## トラブルシューティング

### Supabase が起動しない

```bash
# Docker の状態確認
docker ps

# Supabase のログ確認
supabase logs

# クリーンリスタート
supabase stop
docker system prune -f
supabase start
```

### ポートが使用中

```bash
# 使用中のポートを確認
lsof -i :54321
lsof -i :54322

# プロセスを終了
kill -9 <PID>
```

### マイグレーションエラー

```bash
# マイグレーション状態の確認
supabase migration list

# データベースのリセット
supabase db reset
```

### pgvector 関連エラー

pgvector 拡張は `supabase start` 時に自動的にインストールされます。エラーが発生した場合：

```bash
# Supabase の再起動
supabase stop
supabase start
```

### API キーエラー

1. `.env.local` / `.env` のキーが正しいか確認
2. Supabase の `anon key` と `service_role key` が `supabase start` の出力と一致しているか確認
3. OpenAI / Google API キーが有効か確認

---

## 次のステップ

- [エージェント移行ガイド](./migration/agents/README.md) - LangGraph エージェントの実装方法
- [Router Agent](./migration/agents/router-agent/README.md) - ルーティングエージェントの詳細
- [Backend README](../backend/README.md) - バックエンドの詳細

---

## 参考リソース

- [Supabase CLI ドキュメント](https://supabase.com/docs/reference/cli)
- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Next.js ドキュメント](https://nextjs.org/docs)
- [Mastra ドキュメント](https://mastra.ai/docs)
