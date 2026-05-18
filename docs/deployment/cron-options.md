# Event KB Sync Cron Options

The portable entry point is:

```bash
python -m backend.scripts.sync_event_kb --include-spreadsheet
```

Use `--dry-run` to plan rows without embeddings or Supabase writes:

```bash
python -m backend.scripts.sync_event_kb --dry-run --include-spreadsheet
```

Required live-write secrets are `OPENROUTER_API_KEY`, `SUPABASE_URL`, and
`SUPABASE_KEY`. Source secrets are `GOOGLE_CALENDAR_ICAL_URL`,
`EVENT_SHEET_GAS_URL`, and `EVENT_SHEET_GAS_TOKEN`.

## Option 1: GCP Cloud Scheduler to Cloud Run Job

This is the current production shape.

```bash
PROJECT_ID=aipartner-426616
REGION=asia-northeast1
JOB_NAME=event-kb-sync
SCHEDULER_JOB_NAME=event-kb-sync-daily
JOB_SERVICE_ACCOUNT="engineer-cafe-navigator@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="asia-northeast1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/engineer-cafe-backend:latest"

gcloud services enable cloudscheduler.googleapis.com run.googleapis.com \
  --project="${PROJECT_ID}" \
  --quiet

gcloud run jobs deploy "${JOB_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --service-account="${JOB_SERVICE_ACCOUNT}" \
  --command=python \
  --args=-m,backend.scripts.sync_event_kb,--include-spreadsheet \
  --tasks=1 \
  --max-retries=1 \
  --task-timeout=3600s \
  --cpu=1 \
  --memory=1Gi \
  --set-env-vars="ENVIRONMENT=production,TZ=Asia/Tokyo,SECRET_BACKEND=gcp,GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-secrets="OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest,SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_KEY=SUPABASE_KEY:latest,GOOGLE_CALENDAR_ICAL_URL=GOOGLE_CALENDAR_ICAL_URL:latest,EVENT_SHEET_GAS_URL=EVENT_SHEET_GAS_URL:latest,EVENT_SHEET_GAS_TOKEN=EVENT_SHEET_GAS_TOKEN:latest"

JOB_RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}:run"
gcloud scheduler jobs create http "${SCHEDULER_JOB_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --schedule="0 9 * * *" \
  --time-zone="Asia/Tokyo" \
  --uri="${JOB_RUN_URI}" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --message-body="{}" \
  --oauth-service-account-email="${JOB_SERVICE_ACCOUNT}" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --attempt-deadline=30s \
  --max-retry-attempts=1
```

For an existing scheduler job, replace the final `create http` with
`gcloud scheduler jobs update http` and keep the same flags.

## Option 2: GitHub Actions Cron

Copy `.github/workflows/event-kb-sync.example.yml` to
`.github/workflows/event-kb-sync.yml`, then add repository secrets with these
names:

```text
OPENROUTER_API_KEY
SUPABASE_URL
SUPABASE_KEY
GOOGLE_CALENDAR_ICAL_URL
EVENT_SHEET_GAS_URL
EVENT_SHEET_GAS_TOKEN
```

Run it manually from the Actions tab first. The example uses `SECRET_BACKEND=env`
because GitHub Actions exposes repository secrets as environment variables.

## Option 3: systemd Timer

Copy the example unit files:

```bash
sudo install -m 0644 infra/systemd/event-kb-sync.service.example /etc/systemd/system/event-kb-sync.service
sudo install -m 0644 infra/systemd/event-kb-sync.timer.example /etc/systemd/system/event-kb-sync.timer
sudo mkdir -p /etc/engineer-cafe
```

Create `/etc/engineer-cafe/event-kb-sync.env`:

```bash
sudo tee /etc/engineer-cafe/event-kb-sync.env >/dev/null <<'EOF'
SECRET_BACKEND=sops
SOPS_SECRETS_FILE=/etc/engineer-cafe/secrets.enc.yaml
PYTHONUNBUFFERED=1
EOF
```

Install your encrypted SOPS file at `/etc/engineer-cafe/secrets.enc.yaml`, then
enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now event-kb-sync.timer
sudo systemctl start event-kb-sync.service
journalctl -u event-kb-sync.service -n 100 --no-pager
```

## Option 4: In-process APScheduler

Use this only when the backend process is already long-running and you accept
that process restarts can skip an interval. Install APScheduler and wire it in
your deployment bootstrap:

```bash
python -m pip install apscheduler
```

```python
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.scripts.sync_event_kb import run_event_kb_sync

scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
scheduler.add_job(
    lambda: asyncio.create_task(run_event_kb_sync(include_spreadsheet=True)),
    "cron",
    hour=9,
    minute=0,
    id="event-kb-sync",
    replace_existing=True,
    max_instances=1,
)
scheduler.start()
```

For multi-replica deployments, run exactly one scheduler instance or use Cloud
Scheduler, GitHub Actions, or systemd instead.
