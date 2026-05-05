> **Docs hub**: [docs/README.md](../docs/README.md) · **STATUS**: [docs/STATUS.md](../docs/STATUS.md)

# フロントエンド

Engineer Cafe Navigator の Next.js 15 フロントエンドです。

## ドキュメント動線

1. この README … フロント固有
2. [docs/README.md](../docs/README.md) … **索引**
3. [docs/STATUS.md](../docs/STATUS.md) … 運用正本
4. [docs/adr/README.md](../docs/adr/README.md) · [SYSTEM-ARCHITECTURE](../docs/architecture/SYSTEM-ARCHITECTURE.md) · [setup-guide](../docs/setup-guide.md) · [DEVELOPER-GUIDE](../docs/DEVELOPER-GUIDE.md) · [CLAUDE.md](../CLAUDE.md)

**注意**: キオスクスライドは **静的 PDF + `public/reception/audio/`**。SlideAgent Q&A は **`/api/slides`（FE→BE）**。**`/api/marp` と BE `/api/slides` を同一視しない**（`CLAUDE.md`）。

## 役割

UI・VRM・ブラウザ音声・管理画面・バックエンドへのプロキシ。AI ワークフローの正本ではない。

## 構成の要点

`src/app/page.tsx`、`src/app/api/voice`、`qa`、`calendar`、`slides`、`character`、`reception/*`、`admin/*`、`monitoring/*`、`cron/*`。

## 環境変数

`BACKEND_API_URL`、`BACKEND_API_KEY`、`NEXT_PUBLIC_SUPABASE_*`、`SUPABASE_SERVICE_ROLE_KEY`、`ADMIN_API_SECRET` 等。必須度は [docs/STATUS.md](../docs/STATUS.md) とコードで確認。

## ローカル・コマンド

```bash
cd frontend && pnpm install && cp .env.example .env.local && pnpm dev
```

```bash
pnpm lint && pnpm typecheck && pnpm build && pnpm test
```

`pnpm test:e2e` は `BACKEND_API_URL` と `BACKEND_API_KEY` が必要な場合あり。

## リスク

middleware の matcher 更新、`src/lib/env.ts` の契約が完全ではない点など — [docs/STATUS.md](../docs/STATUS.md)。

