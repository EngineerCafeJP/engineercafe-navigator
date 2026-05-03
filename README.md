# Engineer Cafe Navigator

> 福岡市エンジニアカフェ向けの音声 AI ナビゲーター。モノレポ構成で、`frontend/` は UI と API proxy、`backend/` は FastAPI + LangGraph の実処理を担います。

**[English](README-EN.md)** | **日本語**

## 現在の要約

- 2026-05-03 時点で、alpha live verification の workflow は Cloud Run SHA match 付きで targeted / full suite を実行できます。
- Cloud Run staging は develop SHA `6ce1ac81983c7ae53ddfdfc58eba1ee043a83fa8` の revision `engineer-cafe-backend-00162-mlr` で SHA 一致、`/health` OK です。
- B routing / slide live smoke は targeted run `25254789937` で `64 passed, 0 warned, 0 failed` まで復旧しました。
- Welcome UI, compact artifact, Cloud Run Supabase UUID/log hygiene は resolved として issue close 済みです。
- ただし alpha はまだ **NO-GO** です。最新 full suite run `25272361091` の完走結果、C-127 live collection completion、Q/C answer quality、live/device proof が残っています。
- PR #692/#693/#695/#699/#700/#701/#702/#703/#705/#707/#709 は merge 済みです。#696 は live proof 後に close 済み、#697/#698 は live/device proof が終わるまで open 維持です。

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

- alpha gate は end-to-end で回るが、latest `suites=all` の green proof はまだありません。
- `continue-on-error` のため、GitHub step が success に見えても suite outcome が failure の場合があります。
- STT / voice preflight は run `25258764528` で PASS し、#658 は close 済みです。
- RAGAS は direct OpenAI と C-127 manifest accounting まで修正済みですが、post-#692 run `25270459825`
  は `/api/chat` 429 により `35/127` evaluated でした。current proof run `25272361091` の artifact 確認が必要です。
- Q suite は PR #693 merge 後の proof を、最新 full suite run `25272361091` で再確認中です。
- Voice timeout / mobile audio は PR #705/#707/#709 で修正済みです。#696 は close 済み、#697/#698 は live/device proof 待ちです。
- B routing / slide live smoke と Cloud Run UUID log hygiene は 2026-05-03 時点の deployed staging で解消確認済みです。

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

2026-05-03 時点で把握した主要な alpha open items:

- P0 / alpha-scope: `#583`, `#584`, `#585`, `#611`, `#612`, `#643`, `#697`
- P1 / alpha-scope: `#653`, `#670`, `#672`, `#698`
- Resolved in the latest remediation pass: `#658`, `#659`, `#660`, `#661`, `#662`, `#671`, `#691`, `#694`, `#696`
- Merged and awaiting live proof: PR `#693` for Q quality, PR `#695/#701` for C-127 pacing / coverage, PR `#699` for C source routing, PR `#700/#703` for live harness hardening, PR `#702` for log hygiene, PR `#705/#709` for voice timeout budget, PR `#707` for mobile audio playback

## 注意

- ワークツリーにはこの README 更新と無関係なローカル変更が存在する可能性があります。今回の更新では既存の未コミット実装には触れていません。
- 古い Mastra / RouterAgent / MemoryAgent 前提の文書は一部アーカイブ、一部保留です。現行判断は必ず [docs/STATUS.md](docs/STATUS.md) と照合してください。
