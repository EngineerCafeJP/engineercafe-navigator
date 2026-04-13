# Deployment Guide

> Engineer Cafe Navigator production deployment reference.  
> Last updated: 2026-04-12.

## Infrastructure Overview

```
Browser / Kiosk
     |
     v
Vercel  (Next.js 15 frontend — App Router)
  Production domain: Vercel project primary production alias
  Auto-deploy: push to `develop` (Vercel Git integration / deploy hook)
     |
     v
Cloud Run: engineer-cafe-backend   asia-northeast1   GCP: aipartner-426616
  FastAPI + LangGraph
  Auto-deploy: push to `develop` via GitHub Actions (`backend-deploy-staging` in `.github/workflows/ci.yml`)
     |
     +---> Supabase PostgreSQL + pgvector   (database)
     |
     +---> Cloud Run: voicevox-proto        asia-northeast2  (optional TTS path; staging backend uses Piper per CI)
```

### Service Registry

| Service | Platform | Region | Purpose |
|---------|----------|--------|---------|
| Frontend | Vercel | Global CDN | Next.js UI + API proxy routes |
| Backend | Cloud Run `engineer-cafe-backend` | `asia-northeast1` | FastAPI + LangGraph agents |
| VoiceVox | Cloud Run `voicevox-proto` | `asia-northeast2` | Japanese TTS (when configured; not bundled in default staging deploy) |
| Database | Supabase (PostgreSQL + pgvector) | Managed | Chat history, knowledge base, sessions |

### Source of truth for frontend origin

- The canonical frontend production origin is the **Vercel project's primary production domain**, not an arbitrary preview deployment URL.
- Operators should verify it in the Vercel dashboard or `vercel list --yes`.
- Backend deploys mirror that value through the GitHub Actions repo variable `FRONTEND_PRODUCTION_ORIGIN` and write it to both `FRONTEND_PRODUCTION_ORIGIN` and `ALLOWED_ORIGINS` on Cloud Run.

### Legacy (pre-2026-04): Cloudflare Workers

Earlier revisions of this project used **Cloudflare Workers** with `opennextjs-cloudflare` for the frontend. That path is **not** the current production default. If you still have a Workers deployment, treat it as legacy-only and prefer Vercel + the URLs above for operator truth.

---

## Environment Variables

### Frontend (Vercel)

Configure in the Vercel project: **Settings → Environment Variables** (per environment: Production / Preview). Values mirror what CI uses for `pnpm build` (see `frontend-build` and `frontend-playwright-e2e` in `.github/workflows/ci.yml`).

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_BACKEND_API_URL` | Yes | Public backend URL (Cloud Run) |
| `BACKEND_API_URL` | Yes (server) | Server-side proxy target; often same as public URL |
| `ADMIN_API_SECRET` | Yes | Protects admin API routes (`/api/admin/*`, cron, alerts) |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anonymous (public) key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role — server-only, never exposed to the browser |
| Other AI / optional keys | As needed | Same categories as local `.env` (see `frontend` README) |

### Backend (Cloud Run)

**Source of truth:** the `backend-deploy-staging` job in `.github/workflows/ci.yml` (image build + `gcloud run deploy`). Do **not** rely on a checked-in Knative YAML; use `gcloud` and the workflow.

Typical **staging / production-aligned** flags from CI include:

- `--memory 8Gi --cpu 2 --min-instances 1 --max-instances 3`
- Non-secret env (example from workflow):  
  `ENVIRONMENT=production`, `TTS_PROVIDER=piper`, `STT_PROVIDER=qwen-primary`, `FRONTEND_PRODUCTION_ORIGIN=<vercel-production-origin>`, `ALLOWED_ORIGINS=<vercel-production-origin>`
- Secrets via `--update-secrets` (never `--set-secrets` in a way that drops existing bindings)

| Variable | Required | Description |
|----------|----------|-------------|
| `API_SECRET_KEY` | Yes (production) | Backend auth; startup fails if missing when `ENVIRONMENT=production` |
| `ENVIRONMENT` | Yes | `production` on Cloud Run |
| `OPENROUTER_API_KEY` | Yes | LLM (Gemini via LangChain) |
| `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_DB_URI` | Yes | Supabase + direct Postgres |
| `ALLOWED_ORIGINS` | Yes | CORS; include the Vercel production URL |
| `TTS_PROVIDER` / `STT_PROVIDER` | Per deploy | CI staging uses Piper + Qwen-primary |
| `VOICEVOX_API_URL` | If using VoiceVox | URL of `voicevox-proto` when that stack is active |

Use `gcloud run services update --update-env-vars` to change individual vars. **Do not** use `--set-env-vars` if it would wipe unrelated variables.

---

## Deployment Procedures

### Frontend: Vercel

1. Merge to `develop` (or trigger the configured **Deploy Hook** if you use hook-based deploys).
2. Vercel builds from the linked Git repo; use the project's **Production** domain shown in Vercel as the canonical frontend URL.

Local checks before shipping:

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

### Backend: Cloud Run

Pushes to **`develop`** with backend path changes run tests, then **`backend-deploy-staging`** builds `linux/amd64`, pushes to Artifact Registry, and deploys `engineer-cafe-backend` in `asia-northeast1`.

Manual deploy (operators): follow the same `docker build --platform linux/amd64` + `gcloud run deploy` pattern as the workflow; keep secrets on `--update-secrets`.

---

## CI/CD

- **Pull requests** to `main` / `develop`: lint, typecheck, build, backend tests, and (when `frontend/**` changes) Playwright E2E subset (`smoke`, `reception-flow`). Additional specs such as `e2e/webgl-fallback.spec.ts` can be run locally or added to CI as needed.
- **Backend auto-deploy:** push to `develop` → GitHub Actions → Cloud Run (see workflow).
- **Frontend auto-deploy:** push to `develop` → Vercel (Git or deploy hook).

---

## How to verify live configuration

**Backend (Cloud Run)**

```bash
gcloud run services describe engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --format yaml
```

Confirm image, env vars, and secret bindings match expectations.

**Frontend (Vercel)**

- Dashboard: Vercel project → Deployments / Domains.  
- CLI (if installed): `vercel list --yes` for recent deployments.
- Repo/CI source of truth: GitHub Actions repo variable `FRONTEND_PRODUCTION_ORIGIN` should match the Vercel Production domain.

**Health**

```bash
# Replace with the URL from gcloud describe
curl -sf "$(gcloud run services describe engineer-cafe-backend --region asia-northeast1 --format='value(status.url)')/health"
```

---

## Pre-Deployment Checklist

### Before every release

- [ ] CI green on the branch being deployed
- [ ] `API_SECRET_KEY` set on Cloud Run for production
- [ ] `ADMIN_API_SECRET` set in **Vercel** (not Cloudflare) for the frontend project
- [ ] `FRONTEND_PRODUCTION_ORIGIN` matches the Vercel Production domain
- [ ] `ALLOWED_ORIGINS` on the backend includes that same production origin (and preview URLs if you use them)
- [ ] No new env vars without documentation
- [ ] Supabase migrations applied if schema changed
- [ ] Backend image built with `--platform linux/amd64` when building on Apple Silicon

### After deployment

- [ ] Backend `/health` returns 200
- [ ] Protected backend routes return 401 without credentials where expected
- [ ] Frontend loads without critical console errors
- [ ] Admin routes return 401 without `ADMIN_API_SECRET`
- [ ] Voice path smoke-tested for the configured TTS/STT stack

---

## Rollback

### Frontend (Vercel)

Use Vercel **Deployments** → promote a previous deployment or revert from the dashboard.

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

---

## Database: Supabase

RLS is enabled on all tables. Server-side access uses the service role key.

```bash
supabase db push
```

Key tables include `knowledge_base`, `conversation_sessions`, `conversation_history`, `agent_memory`.

---

## Troubleshooting

### Backend errors after deploy

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="engineer-cafe-backend"' \
  --project aipartner-426616 \
  --limit 50 \
  --format "table(timestamp, textPayload)"
```

### Frontend admin routes misconfigured

Confirm `ADMIN_API_SECRET` in **Vercel** matches what your server routes expect.

### Supabase errors

Confirm `SUPABASE_DB_URI` is not the CI placeholder (`postgresql://test:test@localhost:0/test`).

---

## Known production risks

Track remaining gaps in `docs/STATUS.md` and open issues (e.g. reception durability, rate limiting, E2E coverage for audio/VRM beyond the current CI subset).

---

[Back to docs index](README.md)
