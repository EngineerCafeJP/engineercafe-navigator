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

## メンテナンス表示

公開用の GCP バックエンドと Supabase は 2026-09-27 に停止した。そのため Vercel の Production（`VERCEL_ENV=production`）では、`src/middleware.ts` が全ページに「メンテナンス中です」の HTML を、`/api/*` に `{"error":"Service Unavailable","reason":"maintenance"}` を返す（いずれも 503、`Retry-After: 86400`）。`/api/alerts/webhook` と Next.js のアセットは対象外。

| `MAINTENANCE_MODE` | 動作 |
| --- | --- |
| 未設定 | Vercel Production のときだけメンテナンス表示。ローカルと Preview は通常どおり |
| `on` / `true` / `1` | どこで動かしてもメンテナンス表示 |
| `off` / `false` / `0` | メンテナンス表示にしない。バックエンドを戻したら Vercel の Production にこれを設定して再デプロイする |

メンテナンス表示の間は、ビルド時の `pnpm env:check:production` と起動時の `src/instrumentation.ts` が `BACKEND_API_URL`・`BACKEND_API_KEY`・`NEXT_PUBLIC_SUPABASE_URL`・`NEXT_PUBLIC_SUPABASE_ANON_KEY` の必須チェックを飛ばす。停止したサービスの資格情報を Vercel から消しても、メンテナンス表示はデプロイできる。

判定は `src/lib/maintenance-mode.ts`、応答は `src/lib/maintenance-response.ts`。テストは次のとおり。

```bash
pnpm exec tsx --test --import ./src/__tests__/node-test-setup.ts src/__tests__/middleware.test.ts src/__tests__/maintenance-startup.test.ts
```

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

