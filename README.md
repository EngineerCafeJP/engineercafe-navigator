# Engineer Cafe Navigator

> 福岡市エンジニアカフェ向けの音声 AI ナビゲーター。モノレポ構成で、`frontend/` は UI と API proxy、`backend/` は FastAPI + LangGraph の実処理を担います。

**[English](README-EN.md)** | **日本語**

## 現在の要約

- 2026-05-02 時点で、alpha live verification の full-suite workflow は Cloud Run SHA match 付きで実行できます。
- Cloud Run staging は develop SHA `fa7745b7420c0709fcff950ed3bf4c090f0dfc55` の revision `engineer-cafe-backend-00144-q85` で検証済みです。
- RAGAS evaluator は GitHub Actions secret 修正後、direct OpenAI で動くことを確認済みです。
- ただし alpha はまだ **NO-GO** です。STT latency、B routing、Welcome UI、Q/C answer quality、RAGAS 127-case coverage、Cloud Run log hygiene が残っています。

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

- alpha gate は end-to-end で回るが、最新 full run は failure です。
- `continue-on-error` のため、GitHub step が success に見えても suite outcome が failure の場合があります。
- STT preflight は現行 revision と過去24h履歴が混ざり、release 判定として過敏/不透明です。
- RAGAS は direct OpenAI に修正済みですが、JA answer_correctness と 29-vs-127 coverage が未解決です。
- Welcome UI live scenario は `kiosk-welcome-ocr-overlay` が見つからず失敗します。

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

- [docs/STATUS.md](docs/STATUS.md): 現在の alpha / production readiness 状態
- [docs/README.md](docs/README.md): 現役ドキュメントと履歴ドキュメントの整理
- [docs/testing/alpha-live-verification-status-2026-05-02.md](docs/testing/alpha-live-verification-status-2026-05-02.md): 最新 alpha live verification 結果
- [docs/plans/alpha-remediation-plan-2026-05-02.md](docs/plans/alpha-remediation-plan-2026-05-02.md): 次実装順
- [frontend/README.md](frontend/README.md): フロントエンドの現況と環境変数
- [backend/README.md](backend/README.md): バックエンドの現況と運用上の注意
- [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md): 現行の開発導線

## GitHub の現況

2026-05-02 時点で把握した主要な alpha open items:

- P0: `#658`, `#659`, `#660`, `#657`, `#643`, `#623`, `#612`, `#611`, `#585`, `#584`, `#583`
- P1: `#672`, `#670`, `#669`, `#663`, `#662`, `#661`, `#655`, `#653`
- `#671` は GitHub Actions RAGAS provider secret 問題として作成し、direct OpenAI 確認後に close 済みです。

## 注意

- ワークツリーにはこの README 更新と無関係なローカル変更が存在する可能性があります。今回の更新では既存の未コミット実装には触れていません。
- 古い Mastra / RouterAgent / MemoryAgent 前提の文書は一部アーカイブ、一部保留です。現行判断は必ず [docs/STATUS.md](docs/STATUS.md) と照合してください。
