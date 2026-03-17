# Deployment Guide

> Engineer Cafe Navigator production deployment reference.
> Last updated: 2026-03-15.
> This document reflects the current runtime setup. Legacy references to Vercel and Mastra-era configuration have been removed.

## Infrastructure Overview

```
Browser / Kiosk
     |
     v
Cloudflare Workers  (Next.js 15 frontend — opennextjs-cloudflare)
     |
     v
Cloud Run: engineer-cafe-backend   asia-northeast1   GCP: aipartner-426616
  FastAPI + LangGraph
     |
     +---> Supabase PostgreSQL + pgvector   (database)
     |
     +---> Cloud Run: voicevox-proto        asia-northeast2
              VoiceVox TTS
```

### Service Registry

| Service | Platform | Region | Purpose |
|---------|----------|--------|---------|
| Frontend | Cloudflare Workers | Global edge | Next.js UI + API proxy routes |
| Backend | Cloud Run `engineer-cafe-backend` | `asia-northeast1` | FastAPI + LangGraph agents |
| VoiceVox | Cloud Run `voicevox-proto` | `asia-northeast2` | Japanese TTS synthesis |
| Database | Supabase (PostgreSQL + pgvector) | Managed | Chat history, knowledge base, sessions |

---

## Environment Variables

### Frontend (Cloudflare Workers)

Set these in the Cloudflare dashboard under Workers & Pages > Settings > Environment Variables, or via `wrangler secret put`.

| Variable | Required | Description |
|----------|----------|-------------|
| `BACKEND_API_URL` | Yes | Full URL of the backend Cloud Run service |
| `BACKEND_API_KEY` | Yes | Shared secret used by frontend to authenticate requests to the backend |
| `ADMIN_API_SECRET` | Yes | Secret that protects admin API routes (`/api/admin/*`, `/api/cron/*`, `/api/alerts/*`) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase anonymous (public) key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key — server-side only, never exposed to browser |
| `GOOGLE_CLOUD_PROJECT_ID` | Yes | GCP project ID |

### Backend (Cloud Run)

Set via `gcloud run services update --update-env-vars` — see the Cloud Run section below for the correct command. Do NOT use `--set-env-vars` as it overwrites all existing variables.

| Variable | Required | Description |
|----------|----------|-------------|
| `API_SECRET_KEY` | Yes (mandatory in production) | Backend auth secret. Startup fails if absent when `ENVIRONMENT=production`. |
| `ENVIRONMENT` | Yes | Set to `production` on Cloud Run. Controls startup validation and logging behavior. |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for LLM access (Gemini via LangChain) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase service role key |
| `SUPABASE_DB_URI` | Yes | Full PostgreSQL connection string for direct DB access |
| `VOICEVOX_API_URL` | Yes | URL of the `voicevox-proto` Cloud Run service |
| `GOOGLE_APPLICATION_CREDENTIALS` | See note | Path to GCP service account key file, or use Workload Identity |
| `OPENAI_API_KEY` | Yes | Used for text-embedding-3-small (1536-dim vectors) |

> Note on `API_SECRET_KEY`: As of PR #234, the backend enforces mandatory authentication when `ENVIRONMENT=production`. A missing `API_SECRET_KEY` in production causes the application to fail at startup rather than log a warning and continue. Do not deploy to production without this variable set.

> Note on `ADMIN_API_SECRET`: As of PR #233, admin, cron, and alert routes on the frontend require this secret in the `Authorization: Bearer <secret>` header. Requests without a valid secret receive a 401 response.

---

## Deployment Procedures

### Frontend: Cloudflare Workers

The frontend deploys via `opennextjs-cloudflare`. The `pnpm deploy` command builds and publishes to Cloudflare Workers.

#### Pre-deployment checks

```bash
cd frontend

# Confirm lint is clean
pnpm lint

# Confirm TypeScript compiles without errors
pnpm typecheck

# Confirm production build succeeds locally
pnpm build
```

#### Deploy

```bash
cd frontend
pnpm deploy
```

This runs the opennextjs-cloudflare build pipeline and publishes to the Cloudflare Workers deployment bound to the project.

#### Verify deployment

After `pnpm deploy` reports success:

1. Open the Cloudflare Workers dashboard and confirm the deployment is listed as active.
2. Send a health check request to the deployed URL:

```bash
curl -f https://<your-workers-domain>/api/voice
```

3. Confirm the admin routes return 401 without credentials:

```bash
curl -o /dev/null -w "%{http_code}" https://<your-workers-domain>/api/admin/knowledge
# Expected: 401
```

---

### Backend: Cloud Run

GCP project: `aipartner-426616`
Service name: `engineer-cafe-backend`
Region: `asia-northeast1`

#### Build and push container image

The backend uses a multi-stage Dockerfile with a production target. Always build for `linux/amd64` when deploying to Cloud Run from Apple Silicon:

```bash
cd backend

docker build \
  --platform linux/amd64 \
  --target production \
  -t gcr.io/aipartner-426616/engineer-cafe-backend:$(git rev-parse --short HEAD) \
  .

docker push gcr.io/aipartner-426616/engineer-cafe-backend:$(git rev-parse --short HEAD)
```

#### Deploy to Cloud Run

```bash
gcloud run deploy engineer-cafe-backend \
  --image gcr.io/aipartner-426616/engineer-cafe-backend:<TAG> \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --platform managed \
  --allow-unauthenticated
```

#### Update environment variables

Use `--update-env-vars` to add or change individual variables without overwriting the full set:

```bash
gcloud run services update engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --update-env-vars "ENVIRONMENT=production,API_SECRET_KEY=<value>"
```

Do NOT use `--set-env-vars`. That command replaces all environment variables with only what you specify.

#### Verify deployment

```bash
# Health check endpoint
curl -f https://<backend-cloud-run-url>/health

# Confirm auth is enforced — expect 401
curl -o /dev/null -w "%{http_code}" https://<backend-cloud-run-url>/api/chat
# Expected: 401

# Confirm authenticated request succeeds
curl -H "X-API-Key: <API_SECRET_KEY>" \
  -o /dev/null -w "%{http_code}" \
  https://<backend-cloud-run-url>/health
# Expected: 200
```

---

### VoiceVox: Cloud Run

Service name: `voicevox-proto`
Region: `asia-northeast2`

VoiceVox runs as a separate Cloud Run service. The backend reaches it via the URL configured in `VOICEVOX_API_URL`. The VoiceVox service does not require a custom build from this repository; it runs the upstream VoiceVox container image.

To update:

```bash
gcloud run services update voicevox-proto \
  --region asia-northeast2 \
  --project aipartner-426616 \
  --image <voicevox-image>:<tag>
```

---

### Database: Supabase

RLS (Row Level Security) is enabled on all tables. Server-side access uses the service role key.

#### Apply migrations

```bash
# From the repository root
supabase db push
```

#### Confirm pgvector is available

```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

#### Key tables

| Table | Purpose |
|-------|---------|
| `knowledge_base` | RAG entries with 1536-dim OpenAI embeddings |
| `conversation_sessions` | Active chat sessions |
| `conversation_history` | Per-session message history |
| `agent_memory` | Short-term agent memory (3-minute TTL) |

---

## CI/CD

CI runs on every pull request. The pipeline must be fully green before merging to `develop` or `main`.

### Frontend CI checks

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

### Backend CI checks

```bash
cd backend
ruff check .
black --check .
pytest -m "not ragas and not slow" --tb=short -q
```

### Deployment pipeline

There is no automated deploy-on-push to Cloud Run at this time. Deployments are manual following the procedures above. The recommended sequence after merging to `main` is:

1. Run CI checks locally or confirm all GitHub Actions checks are green.
2. Build and push the backend container image tagged with the merge commit SHA.
3. Deploy backend to Cloud Run with the new image tag.
4. Run `pnpm deploy` from `frontend/` for the Cloudflare Workers deployment.
5. Execute post-deployment verification (see each service section above).

---

## Pre-Deployment Checklist

### Before every deployment

- [ ] All CI checks pass on the branch being deployed
- [ ] `API_SECRET_KEY` is set in Cloud Run environment (`ENVIRONMENT=production`)
- [ ] `ADMIN_API_SECRET` is set in Cloudflare Workers environment
- [ ] `BACKEND_API_KEY` in frontend matches the `API_SECRET_KEY` value in backend
- [ ] No new environment variables have been added without corresponding documentation
- [ ] Database migrations have been applied if this release includes schema changes
- [ ] The backend Docker image is built with `--platform linux/amd64`

### After deployment

- [ ] Backend health endpoint returns 200
- [ ] Unauthenticated request to a protected backend route returns 401
- [ ] Frontend loads without console errors
- [ ] Admin routes return 401 without the `ADMIN_API_SECRET`
- [ ] Voice flow completes end-to-end (STT → agent → TTS)
- [ ] VoiceVox TTS is reachable from the backend service

---

## Rollback Procedure

### Frontend (Cloudflare Workers)

Use the Cloudflare dashboard to roll back to a previous deployment:

1. Open Workers & Pages for the engineer-cafe project.
2. Select Deployments.
3. Find the last known-good deployment and select "Rollback to this deployment."

### Backend (Cloud Run)

```bash
# List recent revisions
gcloud run revisions list \
  --service engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616

# Route all traffic to a specific revision
gcloud run services update-traffic engineer-cafe-backend \
  --region asia-northeast1 \
  --project aipartner-426616 \
  --to-revisions <REVISION-NAME>=100
```

---

## Troubleshooting

### Backend returns 422 or 500 on all routes after deploy

1. Check Cloud Run logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="engineer-cafe-backend"' \
  --project aipartner-426616 \
  --limit 50 \
  --format "table(timestamp, textPayload)"
```

2. Confirm `ENVIRONMENT` and `API_SECRET_KEY` are both set. The backend will refuse to start in production if `API_SECRET_KEY` is absent.

### Frontend admin routes return 500 instead of 401

Confirm `ADMIN_API_SECRET` is set in the Cloudflare Workers environment and that the Workers deployment is using the latest code version.

### VoiceVox TTS fails with connection errors

1. Confirm `VOICEVOX_API_URL` is set in the backend Cloud Run environment.
2. Check that `voicevox-proto` is running in `asia-northeast2`:

```bash
gcloud run services describe voicevox-proto \
  --region asia-northeast2 \
  --project aipartner-426616 \
  --format "value(status.url)"
```

### Supabase connection errors in backend

1. Confirm `SUPABASE_DB_URI` is set and is not the CI placeholder (`postgresql://test:test@localhost:0/test`).
2. Confirm `SUPABASE_URL` and `SUPABASE_KEY` are both set.
3. Check that the Supabase project is active and not paused.

### Local Docker build fails with platform errors

When building on Apple Silicon for deployment to Cloud Run, always include `--platform linux/amd64`:

```bash
docker build --platform linux/amd64 --target production -t <image> .
```

---

## Known Production Risks (as of 2026-03-15)

The following gaps are tracked in Issue #232 and are required before production sign-off. They are listed here so operators are aware of them:

| Risk | Status |
|------|--------|
| Admin and cron routes require `ADMIN_API_SECRET` — partial fix merged in PR #233 | In progress |
| Backend mandatory `API_SECRET_KEY` enforcement — merged in PR #234 | Merged, verify in deploy |
| Reception sessions are stored in-process (not durable across restarts) | Open — Issue tracked |
| Rate limiting is a no-op if `slowapi` is not installed | Open |
| Frontend E2E coverage is thin — audio and VRM regressions may not be caught by CI | Open |

See `docs/STATUS.md` for the full production readiness assessment.

---

[Back to docs index](README.md)
