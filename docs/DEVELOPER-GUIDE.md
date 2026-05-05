# 開発者ガイド — Engineer Cafe Navigator

> **前のページ**: [Documentation hub（docs/README.md）](README.md) · [ADR 一覧](adr/README.md)

> **運用・ゲートの正本**: [STATUS.md](STATUS.md)  
> **環境変数**: [development/ENVIRONMENT-VARIABLES.md](development/ENVIRONMENT-VARIABLES.md)  
> **CI・コマンド**: ルート [CLAUDE.md](../CLAUDE.md)

最終整理: 2026-05-05 — エンドポイント一覧は [backend/README.md](../backend/README.md) と OpenAPI に一本化。

## 言語ルール

- Issue / PR / レビューは原則 **日本語**
- 識別子・API 名は英語のままでよい

## クイックスタート

### 前提条件

- Node.js 20 + pnpm 10
- Python 3.11+
- Docker（任意、`make dev` や Voice 検証用）

### ローカル開発

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev    # http://localhost:3000

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### アーキテクチャ（一行）

```
Browser → Next.js（/api/* プロキシ）→ FastAPI（LangGraph）→ Supabase / OpenRouter / 外部
```

詳細: [architecture/SYSTEM-ARCHITECTURE.md](architecture/SYSTEM-ARCHITECTURE.md)

## API とエンドポイント

**正**: `http://localhost:8000/docs`（OpenAPI）。早見: [backend/README.md](../backend/README.md)。

**注意**: `/api/marp`（FE）と `/api/slides`（BE）は別用途（`CLAUDE.md`）。

## 環境変数

[development/ENVIRONMENT-VARIABLES.md](development/ENVIRONMENT-VARIABLES.md) と [frontend/README.md](../frontend/README.md)。

## エージェントとルーティング（概要）

`backend/config/routing_constants.py`、`backend/workflows/main_workflow.py`。詳細は SYSTEM-ARCHITECTURE と [リファクタ計画](plans/comprehensive-refactoring-plan-2026-05-05.md)。

## テストと CI（必須）

```bash
cd backend && ruff check . && black --check .
cd frontend && pnpm lint && pnpm typecheck && pnpm build
```

## トラブルシュート

1. **音声**: `TTS_PROVIDER` — [backend/README.md](../backend/README.md)、[DEPLOYMENT.md](DEPLOYMENT.md)
2. **チャット**: `SUPABASE_DB_URI`、`OPENROUTER_API_KEY`
3. **スライド**: Marp と BE slides の混同に注意

歴史資料: [archive/](archive/) · 旧長文 [development/DEVELOPER-GUIDE.md](development/DEVELOPER-GUIDE.md)

