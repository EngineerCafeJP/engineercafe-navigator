# Engineer Cafe Navigator

> 福岡市エンジニアカフェ向けの音声 AI ナビゲーター。モノレポ構成で、`frontend/` は UI と API proxy、`backend/` は FastAPI + LangGraph の実処理を担います。

**[English](README-EN.md)** | **日本語**

## 現在の要約

- フロントエンドの主要 API route は 2026-03-14 時点で FastAPI バックエンドへの proxy 化が進み、Mastra 依存の残骸除去も進行済みです。
- 直近では Web Audio autoplay、VRM 互換性、WebM→WAV 変換などの修正が続いており、現在は機能追加より安定化フェーズの色が強いです。
- バックエンドは `pytest --collect-only -q` ベースで 2,868 件のテストが収集されますが、リポジトリ全体では fix 連打と低い test commit 比率が続いています。
- すぐに本番品質とみなせる状態ではありません。特に管理系 route の認証、受付フローの永続化、運用ガードレールが未完です。

詳細は [docs/STATUS.md](docs/STATUS.md) を参照してください。

## 現在のアーキテクチャ

```text
Browser
  -> Next.js 15 frontend
     - UI rendering
     - VRM / audio client
     - /api/* proxy routes
  -> FastAPI backend
     - LangGraph workflow
     - knowledge / reception / STT vocabulary APIs
     - voice, chat, slides, character endpoints
  -> Supabase / OpenRouter / Google / external calendar services
```

主な責務:

- `frontend/`: 画面、音声 UX、VRM 表示、Next.js API route、管理 UI
- `backend/`: LangGraph オーケストレーション、RAG、受付フロー、STT/TTS、外部サービス連携
- `docs/`: 現役ドキュメントと履歴アーカイブ

## 現時点の主要リスク

- フロント側の管理・監視系 endpoint に未認証 route が残っています。
- バックエンドの API key 保護は local/dev では `API_SECRET_KEY` 未設定時に無効化されますが、`staging` / `preview` / `production` では fail-closed です。
- `backend/api/reception.py` は受付セッションをメモリ保持しており、再起動や複数インスタンスに弱いです。
- ドキュメント群には Mastra 前提や古い agent 構成が残っており、文書の現役/履歴の区別が不十分でした。

この README は現況の入口だけを扱います。監査結果と production readiness の論点は [docs/STATUS.md](docs/STATUS.md) に集約しています。

## クイックスタート

### 前提

- Node.js 20 系推奨
- pnpm 10 系推奨
- Python 3.11+
- Supabase
- 必要に応じて Docker

### フロントエンド

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

### バックエンド

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### モノレポ全体

```bash
make dev
```

## ドキュメント

- [docs/STATUS.md](docs/STATUS.md): 2026-03-14 時点の実装状況、リスク、production gap
- [docs/README.md](docs/README.md): 現役ドキュメントと履歴ドキュメントの整理
- [frontend/README.md](frontend/README.md): フロントエンドの現況と環境変数
- [backend/README.md](backend/README.md): バックエンドの現況と運用上の注意
- [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md): 現行の開発導線

## GitHub の現況

2026-03-14 時点で把握した主要な open items:

- Issue `#232`: 2026-03-14 production hardening umbrella tracker
- Issue `#197`: Admin / CRON / Monitoring 保護
- Issue `#209`: 音声主体 UI に対するバブルオーバーレイ整理
- Issue `#224`: フロントの完全 backend proxy 化の残課題整理
- Issue `#165`: Reception-2025 との統合境界と shared data 活用
- PR `#132`: 管理認証 middleware の draft
- PR `#215`: 新 knowledge UI

## 注意

- ワークツリーにはこの README 更新と無関係なローカル変更が存在する可能性があります。今回の更新では既存の未コミット実装には触れていません。
- 古い Mastra / RouterAgent / MemoryAgent 前提の文書は一部アーカイブ、一部保留です。現行判断は必ず [docs/STATUS.md](docs/STATUS.md) と照合してください。
