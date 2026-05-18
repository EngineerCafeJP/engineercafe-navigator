# Secret Backends and SOPS

The backend reads runtime secrets through `backend.utils.secrets`. The default
backend is `env`, so the current Cloud Run secret bindings continue to work:

```bash
export SECRET_BACKEND=env
export OPENROUTER_API_KEY=sk-or-...
export SUPABASE_URL=https://example.supabase.co
export SUPABASE_KEY=...
python -m backend.scripts.sync_event_kb --dry-run --ics-file ./events.ics
```

## Provider Selection

Set `SECRET_BACKEND` to one of:

| Backend | Use case | Required configuration |
| --- | --- | --- |
| `env` | Cloud Run bindings, docker-compose, systemd, GitHub Actions | process env vars |
| `sops` | OSS deployers keeping encrypted secrets in git | `sops` CLI plus `SOPS_SECRETS_FILE` |
| `gcp` | Cloud Run secret bindings | process env vars injected by Cloud Run |
| `vault` | HashiCorp Vault KV | `VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_SECRET_PATH` |

## SOPS Example

Install SOPS and age:

```bash
brew install sops age
age-keygen -o ~/.config/sops/age/keys.txt
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

Create `.sops.yaml` at the repo root. Replace the age recipient with the public
key printed by `age-keygen`.

```yaml
creation_rules:
  - path_regex: secrets\.enc\.yaml$
    age: age1replace-with-your-public-recipient
```

Create the plaintext template:

```bash
cat > secrets.yaml <<'EOF'
OPENROUTER_API_KEY: sk-or-replace-me
SUPABASE_URL: https://replace-me.supabase.co
SUPABASE_KEY: replace-me
GOOGLE_CALENDAR_ICAL_URL: https://calendar.google.com/calendar/ical/replace/basic.ics
EVENT_SHEET_GAS_URL: https://script.google.com/macros/s/replace/exec
EVENT_SHEET_GAS_TOKEN: replace-me
EOF
```

Encrypt it:

```bash
sops --encrypt secrets.yaml > secrets.enc.yaml
rm secrets.yaml
```

Run the sync job with the SOPS provider:

```bash
export SECRET_BACKEND=sops
export SOPS_SECRETS_FILE="$PWD/secrets.enc.yaml"
python -m backend.scripts.sync_event_kb --dry-run --include-spreadsheet
```

For a live write, remove `--dry-run` after checking the planned titles:

```bash
SECRET_BACKEND=sops \
SOPS_SECRETS_FILE="$PWD/secrets.enc.yaml" \
python -m backend.scripts.sync_event_kb --include-spreadsheet
```

## GCP Example

Cloud Run should keep binding secrets as environment variables. The `gcp`
provider is env-binding only and imports no Google SDKs:

```bash
gcloud run jobs deploy event-kb-sync \
  --region=asia-northeast1 \
  --image="${IMAGE}" \
  --command=python \
  --args=-m,backend.scripts.sync_event_kb,--include-spreadsheet \
  --set-env-vars=SECRET_BACKEND=gcp,GOOGLE_CLOUD_PROJECT="${PROJECT_ID}" \
  --set-secrets=OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest,SUPABASE_URL=SUPABASE_URL:latest,SUPABASE_KEY=SUPABASE_KEY:latest,GOOGLE_CALENDAR_ICAL_URL=GOOGLE_CALENDAR_ICAL_URL:latest,EVENT_SHEET_GAS_URL=EVENT_SHEET_GAS_URL:latest,EVENT_SHEET_GAS_TOKEN=EVENT_SHEET_GAS_TOKEN:latest
```

If a local script sets `SECRET_BACKEND=gcp` without env bindings, it behaves
like `env` and returns caller defaults for missing keys.

## Vault Example

Store all runtime keys under one KV v2 path:

```bash
vault kv put secret/engineer-cafe \
  OPENROUTER_API_KEY=sk-or-replace-me \
  SUPABASE_URL=https://replace-me.supabase.co \
  SUPABASE_KEY=replace-me \
  GOOGLE_CALENDAR_ICAL_URL=https://calendar.google.com/calendar/ical/replace/basic.ics \
  EVENT_SHEET_GAS_URL=https://script.google.com/macros/s/replace/exec \
  EVENT_SHEET_GAS_TOKEN=replace-me
```

Run with Vault:

```bash
export SECRET_BACKEND=vault
export VAULT_ADDR=https://vault.example.com
export VAULT_TOKEN="$(vault print token)"
export VAULT_SECRET_PATH=secret/data/engineer-cafe
python -m backend.scripts.sync_event_kb --dry-run --include-spreadsheet
```
