# Codex Completion: Issue #513 Observability Phase 1b

Date: 2026-04-25
Branch: `feat/observability-phase1b-513`
Base: `develop`
Origin: PR #550 / Phase 1a structured logs

## PR

PR URL: not created locally. `git add` / commit / push are blocked by this Codex sandbox because the Git worktree index is outside the writable roots:

```text
fatal: Unable to create '/Users/teradakousuke/Developer/engineer-cafe-navigator2025/.git/worktrees/engineer-cafe-navigator2025-feat-observability-phase1b-513/index.lock': Operation not permitted
```

Required PR title:

```text
feat(infra): observability Phase 1b - dashboard + SLO alerts (#513 Phase 1b)
```

Required PR body references:

```text
Closes #513
Refs #550
```

## Implemented

- Terraform root module under `infra/terraform/`.
- Log-based metrics for:
  - `chat_response` count and latency distribution.
  - `chat_response` fallback count.
  - `stt_winner` count with `qwen` / `vosk` / `none` labels.
  - `stt_overall_duration_ms` latency distribution.
  - `backend.utils.memory_helper` ERROR logs.
- Alert policies for:
  - chat fallback SLO burn rate, 1h + 6h multi-window.
  - STT `winner=none` SLO burn rate, 1h + 6h multi-window.
  - chat p95 latency.
  - STT p95 latency.
  - memory helper errors.
- Terraform-managed Cloud Monitoring dashboard with four required sections:
  - `STT latency`
  - `Chat response`
  - `Memory errors`
  - `Fallback rate`
- GitHub Actions `Terraform Plan` PR validation workflow.
- ADR 017 and observability runbook.

## Structured Log Alignment

Verified against current `origin/develop`:

- `backend.observability.structured_logger.log_chat_response()` emits top-level `jsonPayload.event="chat_response"` with `language`, `route`, `sources`, `rag_fallback`, `hallucination_flag`, `ltm_store_write`, and `latency_ms`.
- STT emits top-level `jsonPayload.event="stt_winner"` with `stt_winner` and `stt_overall_duration_ms`.
- There is no structured `memory_*` event in current backend code and `backend/**` is out of scope for this task. Phase 1b therefore monitors existing root structured logs where `jsonPayload.logger="backend.utils.memory_helper"` and `jsonPayload.level="ERROR"`.

## Local Terraform Output

`terraform fmt -recursive -check -diff infra/terraform`:

```text
passed
```

`terraform -chdir=infra/terraform init -backend=false -no-color`:

```text
Initializing provider plugins...
- Finding hashicorp/google versions matching "~> 6.0"...

Error: Failed to query available provider packages

Could not retrieve the list of available versions for provider
hashicorp/google: could not connect to registry.terraform.io: failed to
request discovery document: Get
"https://registry.terraform.io/.well-known/terraform.json": dial tcp: lookup
registry.terraform.io: no such host
```

`terraform -chdir=infra/terraform validate -no-color`:

```text
Error: Missing required provider

This configuration requires provider registry.terraform.io/hashicorp/google,
but that provider isn't available. You may be able to install it
automatically by running:
  terraform init
```

`terraform -chdir=infra/terraform plan -no-color -input=false`:

```text
Error: Inconsistent dependency lock file

The following dependency selections recorded in the lock file are
inconsistent with the current configuration:
  - provider registry.terraform.io/hashicorp/google: required by this configuration but no version is selected

To make the initial dependency selections that will initialize the dependency
lock file, run:
  terraform init
```

Local plan could not proceed because this sandbox has no DNS/network access to `registry.terraform.io` and no cached Google provider. The GitHub workflow runs `terraform init -backend=false`, `terraform validate`, and `terraform plan` when Workload Identity secrets are configured.

## Other Local Checks

```text
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/terraform-plan.yml"); puts "yaml ok"'
yaml ok

git diff --check
passed

terraform providers
Providers required by configuration:
.
└── provider[registry.terraform.io/hashicorp/google] ~> 6.0
```

## Commit / PR Command

Run from a shell with normal write access to the parent repository `.git` directory:

```bash
git add .claude/analysis/codex-2026-04-25-complete-513-phase-1b.md \
  .github/workflows/terraform-plan.yml \
  docs/adr/017-observability-phase1b.md \
  docs/observability-runbook.md \
  infra/terraform
git commit -m "feat(infra): add observability phase 1b monitoring"
git push -u origin feat/observability-phase1b-513
gh pr create \
  --base develop \
  --title "feat(infra): observability Phase 1b - dashboard + SLO alerts (#513 Phase 1b)" \
  --body $'Closes #513\nRefs #550'
```

## Manual Apply Example

After PR merge and CI review, operator applies manually:

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan \
  -var='project_id=aipartner-426616' \
  -var='cloud_run_service_name=engineer-cafe-backend' \
  -var='region=asia-northeast1' \
  -var='notification_channel_ids=["projects/aipartner-426616/notificationChannels/CHANNEL_ID"]'
terraform -chdir=infra/terraform apply \
  -var='project_id=aipartner-426616' \
  -var='cloud_run_service_name=engineer-cafe-backend' \
  -var='region=asia-northeast1' \
  -var='notification_channel_ids=["projects/aipartner-426616/notificationChannels/CHANNEL_ID"]'
```

## Operationally Ready Notes

- Required GCP IAM for CI/manual operator: Logging metric admin and Monitoring dashboard/alert policy editor, plus Workload Identity token permissions for CI.
- Required GitHub secrets for CI plan: `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`; optional project override via `GCP_PROJECT_ID`.
- `notification_channel_ids` defaults to `[]`; set before production apply if paging/notification is required.
- No backend/frontend runtime behavior changes.
- No migrations, Docker changes, CORS/domain changes, schedulers, or auto-apply workflow changes.
