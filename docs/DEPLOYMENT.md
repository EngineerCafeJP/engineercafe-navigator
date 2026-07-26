# Deployment Guide

> Index: [Documentation hub](README.md)
>
> Engineer Cafe Navigator deployment guide for Wave 3.
> Last updated: 2026-05-18. Live revision and run IDs are tracked in
> [STATUS.md](STATUS.md).

This project now supports two deployment paths:

| Path | Target operator | Runtime shape | Use when |
| --- | --- | --- | --- |
| Path A: GCP production | Current Engineer Cafe production operators | Vercel frontend, Cloud Run backend/TTS, Supabase, Google Secret Manager, Cloud Monitoring/Terraform | You are reproducing or changing the current production environment |
| Path B: OSS docker-compose self-hosting | Contributors and external deployers without a GCP account | Docker Compose app stack, Postgres + pgvector, OpenTelemetry Collector, Prometheus, Loki, Grafana, Alertmanager, Mailhog | You need a portable local or VPS deployment |

The two paths share the same application contract: FastAPI backend on port
`8000`, Next.js frontend on port `3000`, protected backend routes using
`X-API-Key`, and Wave 3 telemetry emitted through OpenTelemetry-compatible
metrics/logs.

## Common Deployment Contract

### Runtime Components

```text
Browser / Kiosk
  |
  v
Next.js frontend
  |
  v
FastAPI backend
  |
  +--> PostgreSQL + pgvector
  +--> LLM provider: OpenRouter / Cerebras / configured fallback
  +--> STT/TTS provider: Qwen primary, Piper/VoiceVox/Kokoro as configured
  +--> Observability: Cloud Monitoring or Prometheus/Grafana
```

### Required Invariants

- The frontend's `BACKEND_API_KEY` must equal the backend's
  `API_SECRET_KEY`.
- Production frontend origin must match backend `FRONTEND_PRODUCTION_ORIGIN`
  and be included in `ALLOWED_ORIGINS`.
- Secrets are never committed or pasted into logs. Use environment bindings,
  Google Secret Manager, SOPS, or Vault.
- Cloud Run env updates must use `--update-env-vars` and `--update-secrets`;
  avoid `--set-env-vars` on an existing service because it can drop unrelated
  values.
- Apple Silicon manual image builds for Cloud Run must target `linux/amd64`.
- Gemini, Cerebras, and other model IDs must be verified against the provider's
  real API availability before deployment.

## Environment Variables

### Frontend Variables

Set these in Vercel for Path A. For Path B, set them in `frontend/.env.local`
or an equivalent compose/host environment.

| Variable | Required | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Production build/startup | Supabase project URL. Required by `frontend/src/lib/env.ts` and `pnpm env:check:production` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Production build/startup | Supabase anon key. Public by design, but do not print it in smoke output |
| `BACKEND_API_URL` | Production build/startup | Server-side proxy target, for example Cloud Run URL or `http://backend:8000` in compose |
| `BACKEND_API_KEY` | Production build/startup | Value sent to backend as `X-API-Key`; must match `API_SECRET_KEY` |
| `ADMIN_API_SECRET` | Protected routes | Protects `/api/admin/*`, `/api/cron/*`, and `/api/monitoring/*`; production fails closed when absent |
| `NEXT_PUBLIC_BACKEND_API_URL` | Direct-call frontend modes | Browser-visible backend URL, for example `http://localhost:8000` |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side admin features | Server-only service role key |
| `ALERT_WEBHOOK_SECRET` | Alert webhook | Protects `/api/alerts/webhook` when used |
| `OPENROUTER_API_KEY` | Cron/knowledge jobs | Required by frontend-side knowledge update jobs |

Production frontend validation:

```bash
cd frontend
VERCEL_ENV=production pnpm env:check:production
pnpm lint
pnpm typecheck
pnpm build
```

### Backend Variables

| Variable | Path A | Path B | Description |
| --- | --- | --- | --- |
| `API_SECRET_KEY` | Required secret | Required secret | Backend API auth key |
| `ENVIRONMENT` | `production` | `development` or `production` | Runtime environment; backend refuses production startup without `API_SECRET_KEY` |
| `SECRET_BACKEND` | `gcp` or `env` | `env`, `sops`, or `vault` | Secret provider selector; see [SOPS and secret backend docs](deployment/secrets-sops.md) |
| `OPENROUTER_API_KEY` | Required secret | Required for real chat/RAG | LLM provider key |
| `SUPABASE_URL` | Required secret | Required if using Supabase API features | Supabase API URL |
| `SUPABASE_KEY` | Required secret | Required if using Supabase API features | Supabase service/server key |
| `SUPABASE_DB_URI` | Required secret | Defaults to compose Postgres in `docker-compose.yml` | PostgreSQL/pgvector connection string |
| `ALLOWED_ORIGINS` | Required | Required for browser access | Comma-separated allowed origins |
| `FRONTEND_PRODUCTION_ORIGIN` | Required | Optional | Canonical production frontend origin |
| `STT_PROVIDER` | `qwen-primary` | `qwen-primary` or local-compatible setting | STT provider dispatch |
| `TTS_PROVIDER` | `piper` in production Piper deploys | `voicevox` by default, or `piper` if configured | TTS provider dispatch |
| `TTS_REQUIRE_PRIMARY_PROVIDER` | `true` for Piper production | Optional | Prevents silent fallback from primary TTS |
| `VOICEVOX_API_URL` | If VoiceVox is used | `http://voicevox:50021` with compose voice profile | VoiceVox engine URL |
| `OTEL_SERVICE_NAME` | Recommended | Set by compose | Service name in telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector endpoint when used | `http://otel-collector:4318` | OTLP HTTP endpoint |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` when used | `http/protobuf` | OTLP transport |
| `FAST_LLM_ENABLED` and `FAST_LLM_*` | Optional | Optional | Fast answer provider/model settings |
| `CEREBRAS_ENABLED`, `CEREBRAS_API_KEY`, `CEREBRAS_FAST_MODEL` | Optional | Optional | Cerebras fallback/filler settings |
| `GOOGLE_CALENDAR_ICAL_URL`, `EVENT_SHEET_GAS_URL`, `EVENT_SHEET_GAS_TOKEN` | Event KB sync | Event KB sync | Source secrets for event knowledge sync |

For secret backend examples, do not duplicate secret values in this file. Use:

- [deployment/secrets-sops.md](deployment/secrets-sops.md) for `env`, `sops`,
  `gcp`, and `vault`.
- [deployment/cron-options.md](deployment/cron-options.md) for portable event
  knowledge sync schedules.

## Path A: GCP Production

### Architecture

```text
Browser / Kiosk
  |
  v
Vercel production deployment
  |
  v
Cloud Run: engineer-cafe-backend (asia-northeast1)
  |
  +--> Supabase managed PostgreSQL + pgvector
  +--> Cloud Run TTS service: PiperPlus / VoiceVox as configured
  +--> OpenRouter / Cerebras / configured LLM providers
  +--> Cloud Logging / Cloud Monitoring / Terraform alerts
```

Current canonical backend service:

```text
project: aipartner-426616
region: asia-northeast1
service: engineer-cafe-backend
```

The canonical production frontend origin is the primary Vercel production
domain. Do not promote a preview URL into `FRONTEND_PRODUCTION_ORIGIN`.

### Services

| Service | Platform | Region | Purpose |
| --- | --- | --- | --- |
| Frontend | Vercel | Global CDN | Next.js UI and API proxy routes |
| Backend | Cloud Run `engineer-cafe-backend` | `asia-northeast1` | FastAPI + LangGraph protected API |
| PiperPlus / VoiceVox | Cloud Run | Deployment-specific | TTS path |
| Database | Supabase managed PostgreSQL + pgvector | Managed | Conversation history, knowledge, sessions |
| Observability | Cloud Logging, Cloud Monitoring, Terraform | GCP | Production logs, metrics, alerting |

### Deploy Frontend

1. Merge to `develop`.
2. Let Vercel Git integration or the deployment hook build and deploy.
3. Confirm the production deployment is attached to the primary production
   domain.

Pre-deploy validation:

```bash
cd frontend
VERCEL_ENV=production pnpm env:check:production
pnpm lint
pnpm typecheck
pnpm build
```

### Deploy Backend

The source of truth for automated deployment is `.github/workflows/ci.yml`.
When backend paths change on `develop`, the backend deploy job builds the image
and deploys to Cloud Run.

Manual deploys should match the workflow:

```bash
PROJECT=aipartner-426616
REGION=asia-northeast1
SERVICE=engineer-cafe-backend
IMAGE="asia-northeast1-docker.pkg.dev/${PROJECT}/cloud-run-source-deploy/${SERVICE}:latest"

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --platform=managed \
  --memory=8Gi \
  --cpu=4 \
  --concurrency=1 \
  --min-instances=1 \
  --max-instances=3 \
  --update-env-vars="ENVIRONMENT=production,STT_PROVIDER=qwen-primary,TTS_PROVIDER=piper,TTS_REQUIRE_PRIMARY_PROVIDER=true,FRONTEND_PRODUCTION_ORIGIN=https://YOUR-PRODUCTION-DOMAIN,ALLOWED_ORIGINS=https://YOUR-PRODUCTION-DOMAIN,SECRET_BACKEND=gcp" \
  --update-secrets="API_SECRET_KEY=API_SECRET_KEY:latest,OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest,SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_KEY=SUPABASE_KEY:latest,SUPABASE_DB_URI=SUPABASE_DB_URI:latest"
```

Add optional secrets only when the feature is enabled:

```text
CEREBRAS_API_KEY=CEREBRAS_API_KEY:latest
LANGSMITH_API_KEY=LANGSMITH_API_KEY:latest
GOOGLE_CALENDAR_ICAL_URL=GOOGLE_CALENDAR_ICAL_URL:latest
EVENT_SHEET_GAS_URL=EVENT_SHEET_GAS_URL:latest
EVENT_SHEET_GAS_TOKEN=EVENT_SHEET_GAS_TOKEN:latest
```

### Scaling and Cost Posture

Cloud Run scaling is the dominant cost lever. Two postures are supported; switch
between them depending on whether the system is in live production use or in a
cost-minimal development/test phase.

| Posture | When | backend | piper-plus | voicevox-proto |
| --- | --- | --- | --- | --- |
| **Cost-minimal (test)** | No live kiosk traffic; dev/test only | `min=0 / max=2` | `min=0 / max=2` | `min=0 / max=2` |
| **Production (warm)** | Live event / kiosk in use | `min=5 / max=15` | `min=2 / max=10` | `min=0 / max=12` |

Idle baseline (min instances running 24/7; estimate from config x public pricing,
actual billing unverified): production posture ~$1,350/mo (backend ~$1,140 +
piper ~$207); cost-minimal posture ~$0 idle (pay only per request).

**Source of truth**: backend scaling values live in `.github/workflows/ci.yml`
(the `engineer-cafe-backend` deploy step). Any manual `gcloud run services update`
to the backend is **overwritten on the next `develop` backend deploy** — to make a
backend scaling change durable, edit ci.yml. `piper-plus` and `voicevox-proto` are
not deployed by any workflow, so manual updates to them persist until a manual
redeploy.

**Cold start**: with `min=0`, the first request after idle pays a cold start
(~40s) because the backend preloads the Qwen STT model
(`STT_PRELOAD_QWEN_PRIMARY=true`) during startup; subsequent requests are 2-5s.
`--cpu-boost` is kept on to speed startup. This is expected in cost-minimal
posture — do not "fix" it by raising `minScale` unless returning to production.

**Constraints**: keep backend memory at `8Gi` (4Gi OOMs at ~4270 MiB during model
load). Do not pin traffic to a specific revision; deploys route `--to-latest`.

### STT hedge posture

`QWEN_STT_HEDGE_DELAY_SECONDS=0` — the Vosk hedge is **disabled on purpose** (#929).

With the previous value (`1.5`), a Vosk transcription started on every single turn
and competed with Qwen for the same container CPU. Across the turns measured on
2026-07-25, Vosk was `cancelled` **4 times out of 4** — it never once produced the
winning transcript, so it was pure overhead.

Disabling the hedge does **not** remove the Vosk safety net. The "Qwen failed or
was rejected → fall back to Vosk" path (`backend/agents/stt/qwen_primary.py:481`)
is independent of the hedge setting, and was observed working in production after
the change. What is removed is only the *speculative concurrent* run: with the
hedge off, the Vosk task blocks on `vosk_fallback_allowed.wait()` and consumes no
CPU (`backend/agents/stt/qwen_primary.py:228-244`).

Measured effect (Cloud Run, same container spec):

| | hedge `1.5` | hedge `0` |
| --- | --- | --- |
| STT total | 8.3–12.5 s | 7.8 s |
| Voice turn total | 16.6–22.6 s | 6.3–9.6 s (warm) |

Trade-off: if Qwen *hangs* rather than fails, recovery is now slower — the request
waits out `QWEN_STT_TIMEOUT=15` before Vosk runs sequentially. Every measured turn
had Qwen succeed, so this is accepted.

That `QWEN_STT_HEDGE_DELAY_SECONDS=0` restores hard-timeout-only behaviour is
covered by `backend/tests/agents/test_stt_agent.py:1464`.

#### Switch to cost-minimal test posture

Immediate (live, until next CI deploy):

```bash
gcloud run services update engineer-cafe-backend --region=asia-northeast1 --min-instances=0 --max-instances=2
gcloud run services update piper-plus            --region=asia-northeast1 --min-instances=0 --max-instances=2
gcloud run services update voicevox-proto        --region=asia-northeast2 --min-instances=0 --max-instances=2
```

Durable (backend): set `--min-instances 0 --max-instances 2` in the
`engineer-cafe-backend` deploy step of `.github/workflows/ci.yml`.

#### Revert to production warm posture

```bash
gcloud run services update engineer-cafe-backend --region=asia-northeast1 --min-instances=5 --max-instances=15
gcloud run services update piper-plus            --region=asia-northeast1 --min-instances=2 --max-instances=10
gcloud run services update voicevox-proto        --region=asia-northeast2 --max-instances=12
```

Then restore `--min-instances 5 --max-instances 15` in the backend deploy step of
`.github/workflows/ci.yml` so the next deploy keeps the warm pool, **and** restore
the matching `minScale`/`maxScale` in `scripts/validate-p0-cloudrun-vercel-timeouts.mjs`
(the P0 guard tracks the intended posture; it fails CI if ci.yml and the guard
disagree). (Optional: drive these from GitHub repo variables to switch postures
without a code change.)

> Current posture (2026-06-01): **cost-minimal test** (Phase 1 complete, no live
> kiosk traffic). `ci.yml` is set to `min=0 / max=2`.

### GCP Secret Manager

Create a secret container once, then add versions:

```bash
PROJECT=aipartner-426616

gcloud secrets create CEREBRAS_API_KEY \
  --project="${PROJECT}" \
  --replication-policy=automatic

printf "%s" "$CEREBRAS_API_KEY" | \
  gcloud secrets versions add CEREBRAS_API_KEY \
    --project="${PROJECT}" \
    --data-file=-
```

Terraform defines runtime secret containers in `infra/terraform/secrets.tf`,
but `manage_runtime_secrets` defaults to `false` to avoid taking ownership of
existing Secret Manager resources. Do not put secret values into Terraform
state.

### GCP Observability

Terraform lives in `infra/terraform/` and covers Cloud Monitoring alerting,
log-based metrics, dashboards, and secret containers. Notification channels are
environment-specific and must be provided before manual apply.

```bash
cd infra/terraform
terraform init
terraform plan \
  -var='project_id=aipartner-426616' \
  -var='region=asia-northeast1'
```

Wave 3 also keeps portable alert definitions in
`infra/observability/alerts.rules.yml`. When using the GCP path, keep Cloud
Monitoring policies and portable alert rules behaviorally aligned.

### Path A Smoke Test

Use the production secret from Secret Manager and run the six inherited Wave 2
queries against Cloud Run:

```bash
PROJECT=aipartner-426616
REGION=asia-northeast1
SERVICE=engineer-cafe-backend
API_KEY="$(gcloud secrets versions access latest --secret=API_SECRET_KEY --project="${PROJECT}")"
URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --project="${PROJECT}" --format='value(status.url)')"

run_chat() {
  curl -sSL -X POST "${URL}/api/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" \
    -d "{\"query\":\"$1\",\"session_id\":\"smoke-$(date +%s%N)\",\"language\":\"ja\"}" \
    --max-time 60 | jq -r '.metadata.agent + " | " + .answer[0:100]'
}

run_chat "今日は何月何日ですか"
run_chat "今週開催されるイベントを全部教えて"
run_chat "ハッカソンの予定はありますか？"
run_chat "Engineer Cafe のメインホールの広さは？"
run_chat "営業時間とWi-Fiについて教えて"
run_chat "サイノカフェのランチメニュー"
```

Expected result: all six requests return HTTP `200`, the selected agent is
reasonable for the question, and no provider self-disclosure appears in the
answer.

Run the existing endpoint/auth verification script as an additional backend
check:

```bash
API_SECRET_KEY="${API_KEY}" ./scripts/verify-deployment.sh
```

Verify the real Vercel-to-Cloud-Run route after the Vercel deployment is live:

```bash
FRONTEND_BASE_URL="https://YOUR-PRODUCTION-DOMAIN" \
  ./scripts/verify-frontend-production.sh
```

Check logs and alert surfaces:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="engineer-cafe-backend"' \
  --project="${PROJECT}" \
  --limit=50 \
  --freshness=1h \
  --format='table(timestamp,severity,jsonPayload.event,textPayload)'

gcloud alpha monitoring policies list \
  --project="${PROJECT}" \
  --format='value(displayName,enabled)'
```

## Path B: OSS Docker Compose Self-Hosting

Path B is for deployers without GCP. It should be enough to clone the repo,
provide local secrets, and run Docker Compose.

### Architecture

```text
Browser
  |
  v
frontend container :3000
  |
  v
backend container :8000
  |
  +--> postgres container :5432 (pgvector image)
  +--> otel-collector :4317/:4318/:9464
  +--> prometheus :9090
  +--> loki :3100
  +--> grafana :3001
  +--> alertmanager :9093
  +--> mailhog :8025
```

Default `docker-compose.yml` services:

| Service | URL/port | Purpose |
| --- | --- | --- |
| `frontend` | `http://localhost:3000` | Next.js app |
| `backend` | `http://localhost:8000` | FastAPI app |
| `postgres` | `localhost:5432` | Local PostgreSQL + pgvector |
| `otel-collector` | `localhost:4317`, `4318`, `9464` | OTLP receiver and Prometheus exporter |
| `loki` | `http://localhost:3100` | Logs |
| `prometheus` | `http://localhost:9090` | Metrics and portable alert rules |
| `grafana` | `http://localhost:3001` | Dashboards, default `admin` / `admin` |
| `alertmanager` | `http://localhost:9093` | Alert routing |
| `mailhog` | `http://localhost:8025` | Local alert email capture |

Optional voice services are under the `voice` compose profile:

```bash
docker compose --profile voice up -d voicevox kokoro-tts
```

### Prerequisites

- Docker Engine or Docker Desktop with Compose v2.
- Node and Python are only required for local host-side validation; compose
  builds the app containers itself.
- A real `OPENROUTER_API_KEY` for full chat/RAG smoke tests.
- Either local env files or a supported secret backend.

### Local Env Files

Create `backend/.env` for compose. Minimum useful local example:

```bash
API_SECRET_KEY=replace-with-local-dev-key
ENVIRONMENT=development
SECRET_BACKEND=env
OPENROUTER_API_KEY=sk-or-replace-me
SUPABASE_DB_URI=postgresql://postgres:postgres@postgres:5432/engineer_cafe
SUPABASE_URL=http://localhost:54321
SUPABASE_KEY=replace-if-needed
ALLOWED_ORIGINS=http://localhost:3000
FRONTEND_PRODUCTION_ORIGIN=http://localhost:3000
STT_PROVIDER=qwen-primary
TTS_PROVIDER=voicevox
VOICEVOX_API_URL=http://voicevox:50021
OTEL_SERVICE_NAME=engineer-cafe-backend
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=replace-if-needed
BACKEND_API_URL=http://backend:8000
NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000
BACKEND_API_KEY=replace-with-local-dev-key
ADMIN_API_SECRET=replace-with-local-admin-key
```

For real local Supabase-compatible API features, point `SUPABASE_URL`,
`SUPABASE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` at your Supabase project or add a local
Supabase service. The compose file already provides Postgres for backend
database access through `SUPABASE_DB_URI`.

If you do not want plaintext env files on disk, use SOPS or Vault as described
in [deployment/secrets-sops.md](deployment/secrets-sops.md). Keep
`SECRET_BACKEND=env` for standard Docker Compose env files.

### Start Path B

Build and start the base nine-service stack:

```bash
docker compose up -d --build
docker compose ps
```

Expected base services: `frontend`, `backend`, `postgres`, `otel-collector`,
`loki`, `prometheus`, `grafana`, `alertmanager`, and `mailhog` are `Up` or
`healthy`.

Start with local voice engines when validating voice:

```bash
docker compose --profile voice up -d --build
```

### Path B Health Smoke

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:3000 >/dev/null
curl -fsS http://localhost:9090/-/healthy
curl -fsS http://localhost:9093/-/healthy
curl -fsS http://localhost:8025 >/dev/null
```

Grafana is available at `http://localhost:3001` with default credentials
`admin` / `admin`.

### Path B Six-Query Chat Smoke

Use the same six questions as Path A, pointed at localhost:

```bash
API_KEY="${API_SECRET_KEY:-replace-with-local-dev-key}"
URL="http://localhost:8000"

run_chat() {
  body="$(jq -nc --arg query "$1" --arg session_id "smoke-$(date +%s%N)" \
    '{query:$query,session_id:$session_id,language:"ja"}')"

  status_and_body="$(curl -sS -w '\n%{http_code}' -X POST "${URL}/api/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" \
    -d "${body}" \
    --max-time 60)"

  status="$(printf '%s' "${status_and_body}" | tail -n1)"
  response="$(printf '%s' "${status_and_body}" | sed '$d')"
  test "${status}" = "200"
  printf '%s\n' "${response}" | jq -r '.metadata.agent + " | " + .answer[0:100]'
}

run_chat "今日は何月何日ですか"
run_chat "今週開催されるイベントを全部教えて"
run_chat "ハッカソンの予定はありますか？"
run_chat "Engineer Cafe のメインホールの広さは？"
run_chat "営業時間とWi-Fiについて教えて"
run_chat "サイノカフェのランチメニュー"
```

Expected result: six `200` responses. If a query fails because a real LLM,
embedding, or knowledge source key is missing, fix env configuration first; do
not weaken the smoke criteria.

### Path B Observability Smoke

Prometheus should scrape the collector:

```bash
curl -fsS http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job:.labels.job, health:.health}'
```

Alert rules should load from `infra/observability/alerts.rules.yml`:

```bash
curl -fsS http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[].name'
```

Mailhog captures Alertmanager email locally:

```bash
curl -fsS http://localhost:8025/api/v2/messages | jq '.total'
```

Grafana provisions the dashboard and data sources from
`infra/observability/grafana/provisioning`.

### Stop Path B

```bash
docker compose down
```

Remove local persisted data only when you intentionally want a clean database
and observability state:

```bash
docker compose down -v
```

## Event Knowledge Sync

The portable entry point is:

```bash
python -m backend.scripts.sync_event_kb --include-spreadsheet
```

Use `--dry-run` before a live write:

```bash
python -m backend.scripts.sync_event_kb --dry-run --include-spreadsheet
```

Supported scheduler shapes are documented in
[deployment/cron-options.md](deployment/cron-options.md):

- GCP Cloud Scheduler to Cloud Run Job for Path A.
- GitHub Actions cron.
- systemd timer.
- In-process APScheduler for single-process deployments.

## Release Checklist

### Before Deploying

- CI is green.
- Frontend production env check passes.
- `BACKEND_API_KEY` and `API_SECRET_KEY` are present and intentionally paired.
- `FRONTEND_PRODUCTION_ORIGIN` and `ALLOWED_ORIGINS` match the canonical
  frontend origin.
- Database migrations are applied when schema changes exist.
- New env vars are documented in this file or the linked deployment docs.
- Provider model IDs and regional availability are verified.
- The selected path has a rollback procedure ready.

### After Deploying

- `/health` returns `200`.
- Protected backend routes return `403` without `X-API-Key`.
- Six-query smoke passes on the deployed backend.
- Frontend-authenticated smoke passes through the real frontend route.
- Voice smoke passes when voice was changed.
- Logs show no immediate `403` or `5xx` spike.
- Wave 3 metrics and alert surfaces are visible in Cloud Monitoring or
  Prometheus/Grafana.

## Rollback

### Path A Frontend

Use Vercel Deployments to promote or revert to the previous healthy production
deployment.

### Path A Backend

```bash
PROJECT=aipartner-426616
REGION=asia-northeast1
SERVICE=engineer-cafe-backend

gcloud run revisions list \
  --service="${SERVICE}" \
  --region="${REGION}" \
  --project="${PROJECT}"

gcloud run services update-traffic "${SERVICE}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --to-revisions=REVISION_NAME=100
```

### Path B Compose

Pin the previous image tag or git revision, then recreate the affected
containers:

```bash
git checkout <known-good-revision>
docker compose up -d --build backend frontend
docker compose ps
```

If the rollback includes database changes, restore from the operator's database
backup before restarting the backend.

## Troubleshooting

### Backend returns 403 after deploy

Check auth drift first:

```bash
# Path A: verify Cloud Run API_SECRET_KEY binding and Vercel BACKEND_API_KEY.
gcloud run services describe engineer-cafe-backend \
  --region=asia-northeast1 \
  --project=aipartner-426616 \
  --format='yaml(spec.template.spec.containers[0].env)'

# Path B: verify local env files and container env.
docker compose exec backend printenv API_SECRET_KEY
docker compose exec frontend printenv BACKEND_API_KEY
```

Do not print real production secret values in shared logs or issue comments.

### Backend is unhealthy in Path B

```bash
docker compose ps
docker compose logs --tail=200 backend
docker compose logs --tail=100 postgres
docker compose exec backend python scripts/healthcheck.py --verbose
```

Common causes are missing `API_SECRET_KEY` with `ENVIRONMENT=production`,
missing LLM key, Postgres startup still in progress, or invalid
`SUPABASE_DB_URI`.

### Observability is blank in Path B

```bash
docker compose logs --tail=100 otel-collector
curl -fsS http://localhost:9464/metrics | head
curl -fsS http://localhost:9090/api/v1/targets | jq '.data.activeTargets'
```

Confirm `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` inside the
backend container and that Prometheus target `otel-collector:9464` is healthy.

### Supabase or database errors

- Path A: verify `SUPABASE_URL`, `SUPABASE_KEY`, and `SUPABASE_DB_URI` are bound
  from Secret Manager.
- Path B: verify the compose Postgres URI is
  `postgresql://postgres:postgres@postgres:5432/engineer_cafe` from inside the
  backend container.

### Event KB sync fails

Run dry-run first and check the selected secret provider:

```bash
SECRET_BACKEND=env \
python -m backend.scripts.sync_event_kb --dry-run --include-spreadsheet
```

See [deployment/cron-options.md](deployment/cron-options.md) for scheduler
setup and required source secrets.

## Current Production Risk References

- `#468`: deploy-time auth drift guardrails.
- `#140`: latency and load baseline.
- `#458`: emotion / animation contract mismatch.
- `#138` / `#398`: multilingual quality closure.
- `#896`: Wave 3 two-path deployment documentation.

[Back to documentation index](README.md)
