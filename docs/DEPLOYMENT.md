# デプロイガイド

> Engineer Cafe Navigator の production deployment 運用ガイド
> Last updated: 2026-04-19

## インフラ構成

```text
Browser / Kiosk
     |
     v
Vercel (Next.js 15 frontend)
  - 本番公開面
  - App Router + API proxy routes
     |
     v
Cloud Run: engineer-cafe-backend (asia-northeast1)
  - FastAPI + LangGraph
  - protected API の本体
     |
     +---> Supabase (PostgreSQL + pgvector)
     |
     +---> Cloud Run: voicevox-proto (任意の TTS 経路)
```

### Service Registry

| Service | Platform | Region | Purpose |
| --- | --- | --- | --- |
| Frontend | Vercel | Global CDN | Next.js UI + API proxy routes |
| Backend | Cloud Run `engineer-cafe-backend` | `asia-northeast1` | FastAPI + LangGraph agents |
| VoiceVox | Cloud Run `voicevox-proto` | `asia-northeast2` | 日本語 TTS 経路（利用時のみ） |
| Database | Supabase (PostgreSQL + pgvector) | Managed | chat history, knowledge base, session data |

### Frontend origin の source of truth

- canonical な production origin は Vercel project の primary production domain
- arbitrary な preview URL を source of truth にしない
- backend 側の `FRONTEND_PRODUCTION_ORIGIN` と `ALLOWED_ORIGINS` はこの値と一致させる

### Legacy note

- 旧 Cloudflare Workers frontend は現行 production default ではない
- 運用判断は Vercel + Cloud Run を正とする

## 環境変数

### Frontend (Vercel)

Vercel project の Environment Variables に設定する。

| Variable | Required | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_BACKEND_API_URL` | Yes | browser から見える backend URL |
| `BACKEND_API_URL` | Yes (server) | server-side proxy の転送先 |
| `BACKEND_API_KEY` | Yes (server) | protected backend route へ送る `X-API-Key` |
| `ADMIN_API_SECRET` | Yes | `/api/admin/*`, `/api/cron/*`, `/api/monitoring/*` を保護 |
| `ALERT_WEBHOOK_SECRET` | If used | `/api/alerts/webhook` POST を保護 |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | server-only の service role |
| Other AI / optional keys | As needed | frontend README と CI 設定に合わせる |

### Backend (Cloud Run)

source of truth は `.github/workflows/ci.yml` の deploy job。

典型的な deploy 設定:

- `--memory 8Gi --cpu 2 --min-instances 1 --max-instances 3`
- non-secret env 例:
  - `ENVIRONMENT=production`
  - `TTS_PROVIDER=piper`
  - `STT_PROVIDER=qwen-primary`
  - `FRONTEND_PRODUCTION_ORIGIN=<vercel-production-origin>`
  - `ALLOWED_ORIGINS=<vercel-production-origin>`
- secret は `--update-secrets` で更新する

| Variable | Required | Description |
| --- | --- | --- |
| `API_SECRET_KEY` | Yes (production) | frontend -> backend 認証の正本 |
| `ENVIRONMENT` | Yes | Cloud Run では `production` |
| `OPENROUTER_API_KEY` | Yes | LLM provider |
| `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_DB_URI` | Yes | Supabase / Postgres 接続 |
| `ALLOWED_ORIGINS` | Yes | CORS origin |
| `TTS_PROVIDER` / `STT_PROVIDER` | Per deploy | 音声経路設定 |
| `VOICEVOX_API_URL` | If using VoiceVox | `voicevox-proto` URL |

注意:

- Cloud Run の env 更新は `--update-env-vars` を使う
- `--set-env-vars` で既存値を消さない

## デプロイ手順

### Frontend: Vercel

1. `develop` へ merge する
2. Vercel の Git integration または deploy hook で build / deploy を走らせる
3. production domain を canonical URL として扱う

release 前の local check:

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

### Backend: Cloud Run

`develop` への push で backend path に変更がある場合、GitHub Actions の
`backend-deploy-staging` が image build と Cloud Run deploy を実施する。

manual deploy をする場合も、workflow と同じ前提に寄せる:

- `linux/amd64` build
- Artifact Registry push
- `gcloud run deploy`
- secret は `--update-secrets`

## CI / CD

- Pull request: lint, typecheck, build, backend tests, Playwright merge-gate
- Backend auto-deploy: `develop` push -> GitHub Actions -> Cloud Run
- Frontend auto-deploy: `develop` push -> Vercel

## live 設定の確認方法

### Backend (Cloud Run)

```bash
gcloud run services describe engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --format yaml
```

確認ポイント:

- image
- env vars
- secret bindings
- traffic / revision

### Frontend (Vercel)

- Vercel dashboard の Deployments / Domains を確認
- CLI を使う場合は `vercel list --yes`
- `FRONTEND_PRODUCTION_ORIGIN` が production domain と一致していることを確認

### Recent log review

- Cloud Run: deploy 後 15-60 分は `gcloud logging read` を見る
- Vercel: deployment history を first signal とし、`vercel logs` だけに依存しない
- Supabase: 現行 operator flow では CLI だけで十分な recent runtime log が取れない場合がある

### Health

```bash
curl -sf "$(gcloud run services describe engineer-cafe-backend --region asia-northeast1 --format='value(status.url)')/health"
```

## リリース前チェック

### Before every release

- CI が green
- Vercel target 環境に `BACKEND_API_KEY` がある
- Cloud Run target 環境に `API_SECRET_KEY` がある
- Vercel に `ADMIN_API_SECRET` がある
- `FRONTEND_PRODUCTION_ORIGIN` が Vercel production domain と一致
- backend の `ALLOWED_ORIGINS` が同じ origin を含む
- 新しい env var を追加した場合は docs を更新済み
- schema change がある場合は Supabase migration 適用済み
- Apple Silicon で build する場合は `--platform linux/amd64`

### After deployment

- backend `/health` が `200`
- backend protected route に `X-API-Key` なしで投げると `403`
- frontend が critical console error なしで表示される
- admin route は `ADMIN_API_SECRET` なしで `401`
- voice path の smoke test が通る
- production frontend 経由の `GET /api/voice?action=supported_languages` が `200`
- production frontend 経由の `POST /api/character` が `200`
- Cloud Run logs に immediate な `403` / `5xx` spike がない

## Release Guardrails

現在の最重要 release risk は、backend auth 自体の欠如ではなく、次の不整合です。

- Vercel `BACKEND_API_KEY`
- Cloud Run `API_SECRET_KEY`

frontend は `BACKEND_API_KEY` が missing / stale でも startup 自体は止まりません。
そのため release validation では、実際の Vercel -> Cloud Run 経路を通す必要があります。

最低限の運用ルール:

1. target production deployment を Vercel で特定する
2. その deployment に対して frontend-authenticated smoke check を実行する
3. 同じ時間帯の Cloud Run logs を確認する
4. ここまで通って初めて healthy deploy とみなす

## ロールバック

### Frontend (Vercel)

- Vercel Deployments から previous deployment を promote / revert

### Backend (Cloud Run)

```bash
gcloud run revisions list \
  --service engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616

gcloud run services update-traffic engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --to-revisions REVISION_NAME=100
```

## Database: Supabase

- RLS は有効
- service role access は server-side only

```bash
supabase db push
```

代表 table:

- `knowledge_base`
- `conversation_sessions`
- `conversation_history`
- `agent_memory`
- `reception_sessions`

## トラブルシューティング

### Backend errors after deploy

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="engineer-cafe-backend"' \
  --project aipartner-426616 \
  --limit 50 \
  --format "table(timestamp, textPayload)"
```

### Frontend admin routes misconfigured

- `ADMIN_API_SECRET` が Vercel 側と一致しているか確認

### `POST /api/character` で `403` が増える

まず deploy / config mismatch を疑う:

- Vercel の `BACKEND_API_KEY` を確認
- Cloud Run の `API_SECRET_KEY` を確認
- frontend-authenticated smoke check を再実行
- 同じ deploy window の Cloud Run logs を確認

### Supabase errors

- `SUPABASE_DB_URI` が CI placeholder になっていないか確認

## 現在の production risk

追跡先:

- `#468`: deploy-time auth drift guardrails
- `#140`: latency / load baseline
- `#458`: emotion / animation contract mismatch
- `#138` / `#398`: multilingual quality closure

[Back to docs index](README.md)
