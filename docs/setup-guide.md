# ローカル開発環境セットアップガイド

対象読者: プロジェクトに参加するすべての開発者 (takegawa, Jun ほか)
所要時間: 約30〜45分 (ネットワーク速度による)

---

## このガイドで達成できること

- フロントエンド (Next.js) とバックエンド (FastAPI) を両方ローカルで起動する
- ブラウザで `http://localhost:3000` を開き、音声エージェントが動作する状態にする
- テストとLintをパスさせ、PR が出せる状態にする

---

## 目次

1. [前提条件](#1-前提条件)
2. [リポジトリのクローン](#2-リポジトリのクローン)
3. [バックエンドのセットアップ](#3-バックエンドのセットアップ)
4. [フロントエンドのセットアップ](#4-フロントエンドのセットアップ)
5. [起動して動作確認](#5-起動して動作確認)
6. [Dockerを使ったフルスタック起動（任意）](#6-dockerを使ったフルスタック起動任意)
7. [テストとLint](#7-テストとlint)
8. [プロジェクト構成の概要](#8-プロジェクト構成の概要)
9. [本番環境URL一覧](#9-本番環境url一覧)
10. [よくあるエラーと対処法](#10-よくあるエラーと対処法)

---

## 1. 前提条件

以下をインストールしてから作業を開始してください。

### 必須ツール

| ツール | 最低バージョン | インストール方法 |
|--------|--------------|----------------|
| Node.js | 20以上 | [nodejs.org](https://nodejs.org/) または `mise install node` |
| pnpm | 10以上 | `npm install -g pnpm` または `mise install pnpm` |
| Python | 3.11以上 | [python.org](https://www.python.org/) または `mise install python` |
| ffmpeg | 任意のバージョン | `brew install ffmpeg` (macOS) |

### ffmpeg が必要な理由

音声機能 (STT) でブラウザから送られてくる WebM 形式の音声を変換するために ffmpeg が必要です。インストールしていないと STT が動作しません。

```bash
# macOS
brew install ffmpeg

# 確認
ffprobe -version
```

### アクセスが必要なAPIキー

セットアップ前にチームから以下のキーを受け取ってください。

| サービス | 用途 | 取得先 |
|----------|------|--------|
| OpenRouter | LLM (Gemini など) | チームリーダーに確認 |
| OpenAI | ベクトル埋め込み | チームリーダーに確認 |
| Supabase | データベース | チームリーダーに確認 |
| Google Cloud | STT / TTS | チームリーダーに確認 |
| Tavily | Web検索 (省略可) | https://tavily.com |

---

## 2. リポジトリのクローン

```bash
git clone https://github.com/EngineerCafeJP/engineer-cafe-navigator2025.git
cd engineer-cafe-navigator2025
```

ブランチ戦略: `main <- develop <- feat/*`。作業は必ず `develop` から新しいブランチを切ってください。

```bash
git checkout develop
git pull
git checkout -b feat/あなたの作業名
```

---

## 3. バックエンドのセットアップ

### 3-1. 仮想環境を作成して有効化する

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

ターミナルのプロンプトに `(.venv)` が表示されれば有効化できています。

### 3-2. 依存パッケージをインストールする

```bash
pip install -e ".[dev]"
```

`[dev]` を付けることで pytest / black / ruff など開発ツールも一緒にインストールされます。

### 3-3. 環境変数ファイルを作成する

```bash
cp .env.example .env
```

`.env` をテキストエディタで開き、以下の項目を設定してください。

#### 必須の環境変数

```dotenv
# LLM プロバイダー (OpenRouter)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx

# OpenAI (ベクトル埋め込み専用)
OPENAI_API_KEY=sk-xxxxxxxx

# Supabase
SUPABASE_URL=https://xxxxxxxxxx.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_DB_URI=postgresql://postgres:password@db.xxxxxxxxxx.supabase.co:5432/postgres
```

#### 推奨の環境変数

```dotenv
# Web検索エージェント (なくても起動するが一部機能が低下する)
TAVILY_API_KEY=tvly-xxxxxxxx

# Google Calendar イベント情報取得
GOOGLE_CALENDAR_ICAL_URL=https://calendar.google.com/calendar/ical/YOUR_CALENDAR_ID/public/basic.ics
```

#### ローカル開発では省略できる環境変数

```dotenv
# ローカルでは認証なしで動作する (省略可)
# API_SECRET_KEY=your-api-secret-key
# ALLOWED_ORIGINS=http://localhost:3000
```

> **注意**: `API_SECRET_KEY` を設定した場合、フロントエンドの `BACKEND_API_KEY` に同じ値を設定する必要があります。ローカル開発では両方とも空のままにしておくのが簡単です。

### 3-4. Google Cloud サービスアカウントキーを配置する (STT/TTS を使う場合)

音声機能を使う場合のみ必要です。

1. チームリーダーからサービスアカウントキー (JSON) を受け取る
2. `backend/config/service-account-key.json` として保存する

```bash
# ファイルが正しい場所にあるか確認
ls backend/config/service-account-key.json
```

### 3-5. バックエンドを起動する

```bash
# backend/ ディレクトリで実行
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

起動に成功すると以下のようなログが表示されます。

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

ブラウザで `http://localhost:8000/docs` を開くと API ドキュメントが確認できます。

---

## 4. フロントエンドのセットアップ

バックエンドとは別のターミナルウィンドウで作業してください。

### 4-1. 依存パッケージをインストールする

```bash
cd frontend
pnpm install
```

### 4-2. 環境変数ファイルを作成する

```bash
cp .env.example .env.local
```

`.env.local` を開き、以下の項目を設定してください。

#### 必須の環境変数

```dotenv
# バックエンドAPIへの接続先 (ローカル起動時はこのまま)
BACKEND_API_URL=http://localhost:8000

# バックエンドと同じ API_SECRET_KEY を設定 (ローカルでは空でも可)
BACKEND_API_KEY=

# Supabase (フロントエンド用 anon key を使用)
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

#### 推奨の環境変数

```dotenv
# サーバーサイドの管理機能で使用
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# 管理API / cron ルート保護
ADMIN_API_SECRET=your-admin-api-secret
```

> **Supabase の anon key と service role key の違い**:
> - `NEXT_PUBLIC_SUPABASE_ANON_KEY`: ブラウザに公開されるキー。RLS で行レベルアクセス制御される
> - `SUPABASE_SERVICE_ROLE_KEY`: サーバーサイド専用。RLS をバイパスするため、ブラウザに公開しない

### 4-3. フロントエンドを起動する

```bash
# frontend/ ディレクトリで実行
pnpm dev
```

起動に成功すると以下のようなログが表示されます。

```
  ▲ Next.js 15.x.x
  - Local:        http://localhost:3000
  - Ready in xxxms
```

ブラウザで `http://localhost:3000` を開いてください。

---

## 5. 起動して動作確認

バックエンド (ポート 8000) とフロントエンド (ポート 3000) の両方が起動している状態で確認します。

### 確認項目チェックリスト

- [ ] `http://localhost:3000` がブラウザで表示される
- [ ] `http://localhost:8000/docs` で API ドキュメントが表示される
- [ ] ブラウザのコンソールに CORS エラーが出ていない
- [ ] (音声機能を使う場合) マイクのアクセス許可ダイアログが表示される

### 簡易動作確認コマンド

```bash
# バックエンドのヘルスチェック
curl http://localhost:8000/health

# 期待するレスポンス: {"status": "ok"} または類似のJSON
```

---

## 6. Dockerを使ったフルスタック起動（任意）

Docker を使うとフロントエンドとバックエンドを一括で起動できます。ただし初回ビルドに時間がかかります。

```bash
# リポジトリルートで実行
make setup   # 初回のみ: mise install + deps + Docker イメージビルド
make dev     # frontend:3000 + backend:8000 を起動
```

> **Apple Silicon (M1/M2/M3) ユーザーへ**: GCP Cloud Run 向けにビルドする場合は `--platform linux/amd64` が必要です。ローカル開発では不要です。

---

## 7. テストとLint

PR を出す前に以下がすべてパスすることを確認してください。

### バックエンド

```bash
cd backend
source .venv/bin/activate

# 高速テスト (ragas と slow を除外)
pytest -m "not ragas and not slow" --tb=short -q

# Lint チェック
ruff check .

# フォーマットチェック
black --check .

# フォーマット自動修正
black .
```

### フロントエンド

```bash
cd frontend

# Lint
pnpm lint

# 型チェック
pnpm typecheck

# ビルド確認
pnpm build

# テスト
pnpm test
```

### 特定エージェントのテスト

```bash
# リポジトリルートで実行
make test-agent AGENT=business_info QUERY='営業時間は？'
make debug-agent   # インタラクティブなエージェントデバッガー
```

---

## 8. プロジェクト構成の概要

開発を始める前に理解しておくべき重要な構成です。

```
engineer-cafe-navigator2025/
├── frontend/          Next.js 15 (App Router) + TypeScript
│   ├── src/app/       ページと API ルート
│   ├── src/app/api/   APIルートハンドラ (voice, slides, marp, qa, character, calendar, admin)
│   ├── src/lib/       共通ライブラリ (audio, memory, STT補正 など)
│   └── e2e/           Playwright E2E テスト
│
├── backend/           FastAPI + LangGraph + Python 3.11
│   ├── main.py        FastAPI エントリーポイント
│   ├── agents/        エージェント実装 (12エージェント)
│   ├── workflows/     LangGraph ワークフロー定義
│   ├── tools/         共有ツール (calendar_service, enhanced_rag, tavily_search)
│   ├── config/        ルーティング定数、プロンプトテンプレート
│   └── tests/         pytest テストスイート
│
└── supabase/          DBマイグレーションと設定
```

### AIエージェント構成

バックエンドの **LangGraph** が唯一のAIレイヤーです（フロントエンドは純粋なUIプロキシ）。

| 構成要素 | 技術 |
|---------|------|
| オーケストレーション | OrchestratorAgent (Supervisor Pattern) |
| 専門エージェント | BusinessInfo, Facility, Event, GeneralKnowledge, CharacterControl, Slide, STT, Voice, OCR, Farewell + agent_tools |
| LLM | OpenRouter (Gemini) via LangChain |
| RAG | EnhancedRAGSearch (Supabase RPC) + Tavily Web検索フォールバック |
| Embeddings | OpenRouter API (`openai/text-embedding-3-small`, 1536次元) |

### 重要: APIエンドポイントの混同に注意

| エンドポイント | 場所 | 目的 |
|--------------|------|------|
| `/api/marp` | フロントエンド | Markdown → HTML レンダリング (スライド表示) |
| `/api/slides` | バックエンド | ナレーション / ナビゲーション |

この2つは別物です。混同しないように注意してください。

### データフローの概要

```
音声:     ブラウザ → /api/voice (FE proxy) → Backend STT/TTS → ブラウザ
Q&A:      ブラウザ → /api/qa (FE proxy) → Backend /api/chat → LangGraph → RAG/Web検索 → レスポンス
カレンダー: ブラウザ → /api/calendar (FE proxy) → Backend /api/calendar → Google Calendar ICS
スライド:  Marp markdown → /api/marp (FE) → HTML レンダリング → MarpViewer
```

---

## 9. 本番環境URL一覧

| サービス | URL |
|----------|-----|
| フロントエンド (Vercel) | https://frontend-delta-six-20.vercel.app |
| バックエンド (Cloud Run) | https://engineer-cafe-backend-639959525777.asia-northeast1.run.app |
| VoiceVox (Cloud Run) | https://voicevox-proto-639959525777.asia-northeast2.run.app |

ローカル開発では本番環境を直接操作しないでください。

---

## 10. よくあるエラーと対処法

### APIコールで 403 エラーが返ってくる

**原因**: フロントエンドの `BACKEND_API_KEY` とバックエンドの `API_SECRET_KEY` が一致していない。

**対処**:
- ローカル開発では両方を空にする (`.env.local` の `BACKEND_API_KEY=` と `.env` の `# API_SECRET_KEY=...` をコメントアウト)
- または、両方に同じ値を設定する

### `ffprobe: command not found` または STT が動作しない

**原因**: ffmpeg がインストールされていない。

**対処**:
```bash
brew install ffmpeg
ffprobe -version  # 動作確認
```

### `WebM` 形式の音声変換に失敗する

**原因**: ffmpeg が必要。上記と同じ対処をしてください。

### TAVILY に関するエラーが出る

**原因**: `TAVILY_API_KEY` が未設定。

**対処**: https://tavily.com でアカウントを作成してキーを取得し、`backend/.env` に設定してください。Tavily がなくてもエージェントは起動しますが、Web検索機能が低下します。

### `ModuleNotFoundError` または `ImportError` が出る

**原因**: 仮想環境が有効化されていない、またはパッケージが未インストール。

**対処**:
```bash
cd backend
source .venv/bin/activate  # 仮想環境を有効化
pip install -e ".[dev]"    # 再インストール
```

### `pnpm install` でエラーが出る

**原因**: Node.js のバージョンが古い可能性がある。

**対処**:
```bash
node --version   # 20以上であることを確認
pnpm --version   # 10以上であることを確認
```

バージョンが古い場合は mise や nvm でバージョンを切り替えてください。

### Supabase への接続エラーが出る

**原因**: `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_DB_URI` の設定ミス。

**対処**:
1. Supabase ダッシュボード → Settings → API でキーを確認する
2. `SUPABASE_KEY` には **service role key** (anon key ではない) を使用する
3. `SUPABASE_DB_URI` は Supabase ダッシュボード → Settings → Database → Connection string (URI) から取得する

### Google Cloud STT が動作しない

**原因**: サービスアカウントキーが配置されていない。

**対処**:
```bash
# ファイルの存在を確認
ls -la backend/config/service-account-key.json
```

ファイルがなければチームリーダーに連絡してください。

### `pnpm typecheck` で型エラーが出る

**原因**: TypeScript の型エラー。修正してからコミットしてください。

**対処**:
```bash
pnpm typecheck  # エラー箇所を確認
# エラーを修正してから再実行
```

### `ruff check .` で Lint エラーが出る

**原因**: Python コードのスタイル違反。

**対処**:
```bash
ruff check . --fix  # 自動修正できるものを修正
black .              # フォーマット統一
```

---

## 困ったときは

1. まずこのガイドの「よくあるエラーと対処法」を確認する
2. `backend/` で `pytest -m "not ragas and not slow" --tb=short -q` を実行してエラーメッセージを確認する
3. チームの Slack チャンネルで質問する (エラーメッセージ全文を貼り付けること)

---

*最終更新: 2026-03-21*
