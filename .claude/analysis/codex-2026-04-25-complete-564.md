# Codex completion summary: Issue #564

## Scope

- Follow-up to PR #563 / commit `6d940d6` for Phase 1b pre-apply safety.
- Route C bounded Terraform/docs implementation.

## Changes

- Dropped the `message` label from `google_logging_metric.memory_helper_error_count`.
- Removed dashboard grouping by `metric.label.message`.
- Changed Terraform metric type locals to reference `google_logging_metric.*.name`, so alert policies and dashboard filters have implicit Terraform graph dependencies on the log-based metrics.
- Updated ADR 017 with the adopted M1/P2 decisions.

## Validation

- `terraform fmt -recursive -check -diff infra/terraform`: pass.
- `terraform init -backend=false`: blocked locally because the sandbox cannot resolve `registry.terraform.io` and no local Google provider cache is present.
- `terraform validate`: blocked locally by missing `registry.terraform.io/hashicorp/google` provider after init could not complete.
- `terraform plan -no-color -input=false > /tmp/plan.txt`: blocked locally because Terraform has not been initialized.

CI should run init/validate and plan via `.github/workflows/terraform-plan.yml` when GitHub Actions has network access and GCP Workload Identity secrets are configured.

## Operational readiness

- Env vars/secrets: no application env vars changed. CI plan still requires optional `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, and `GCP_SERVICE_ACCOUNT`.
- Permissions/IAM: no IAM resources changed. The GitHub Actions service account still needs enough Monitoring/Logging read/plan permissions for Terraform plan.
- Terraform/apply: apply remains manual after merge. Operator should review `terraform plan` before apply.
- Rollback: revert this commit or restore the previous metric label/dashboard grouping before manual apply. If already applied, run Terraform apply with the reverted configuration.
