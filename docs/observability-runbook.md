# Observability Runbook

Issue #513 Phase 1b monitors Cloud Run logs through Terraform-managed log metrics,
dashboard panels, and alert policies. Terraform changes are applied manually after merge.

## Alpha Live Verification Permission Note

2026-04-25 の Alpha Live Verification run では、GitHub Actions の GCP service account
`engineer-cafe-navigator@aipartner-426616.iam.gserviceaccount.com` が Cloud Logging を読めず、
`scripts/stt-live-preflight.sh` と `scripts/cloud-logging-verify.sh` が
`PERMISSION_DENIED` で失敗した。

GO 判定前に、live verification 用 service account へ Cloud Logging 読み取り権限を付与する。
少なくとも `gcloud logging read` で Cloud Run revision logs を読める必要がある。

## Terraform Apply

Run from the Terraform observability directory used by the infra PR. Example:

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan
terraform -chdir=infra/terraform apply
```

Before apply, confirm `project_id`, local or remote state handling, `notification_channel_ids`,
and IAM permissions. Apply is manual after PR merge; the GitHub workflow never runs apply.

## STT Latency

Primary signal: `jsonPayload.event="stt_winner"` with `stt_overall_duration_ms`.

Useful Cloud Logging query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="stt_winner"
```

High-latency query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="stt_winner"
jsonPayload.stt_overall_duration_ms>=6000
```

Triage:

1. Compare `stt_overall_duration_ms`, `stt_qwen_duration_ms`, and `stt_vosk_duration_ms`.
2. Check whether `stt_winner` shifted from `qwen` to `vosk`.
3. Look for `stt_model_load_complete` spikes that indicate cold model load.
4. Confirm Cloud Run revision, CPU/memory, and `STT_PROVIDER` / `QWEN_STT_TIMEOUT`.

## Chat Response

Primary signal: `jsonPayload.event="chat_response"` with `latency_ms`, `route`, `language`,
`sources`, `rag_fallback`, and `hallucination_flag`.

Useful Cloud Logging query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="chat_response"
```

High-latency query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="chat_response"
jsonPayload.latency_ms>=10000
```

Triage:

1. Group by `route` and `language` to identify whether one agent path regressed.
2. Check `sources` and `rag_fallback` for RAG degradation.
3. Check Cloud Run request latency and 5xx logs for platform-level issues.
4. Compare the current revision against the previous healthy revision.

## Memory Errors

There is no structured `memory_*` event today. Phase 1b monitors existing root structured
logs from `backend.utils.memory_helper` at error level.

Useful Cloud Logging query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.logger="backend.utils.memory_helper"
jsonPayload.level="ERROR"
```

Connection-related query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.logger="backend.utils.memory_helper"
jsonPayload.level="ERROR"
jsonPayload.message=~"connection is closed|pool is closed|broken pipe|Supabase"
```

Triage:

1. Check whether errors started after a deploy or Supabase incident.
2. Inspect messages for connection pool exhaustion, closed connections, or timeout.
3. Validate Supabase availability and connection limits.
4. Run the alpha memory smoke if available, then keep the alert open until successful recall is verified.

## Fallback Rate

Primary signal: `chat_response` logs where `rag_fallback=true` or `sources` indicates fallback.

Useful Cloud Logging query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="chat_response"
jsonPayload.rag_fallback=true
```

Language-specific query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="chat_response"
jsonPayload.rag_fallback=true
jsonPayload.language="ja"
```

Triage:

1. Compare fallback rate by `language`.
2. Check whether fallback is isolated to one `route`.
3. Confirm RAG/Supabase availability and recent knowledge base changes.
4. Review hallucination flags and answer quality before lowering thresholds.

## SLO Burn-Rate Alerts

Burn-rate alerts use 1h and 6h windows. Treat a 1h-only alert as early warning and a
1h+6h alert as sustained degradation.

Triage:

1. Open the dashboard and confirm which panel is burning budget.
2. Use the matching log query above to find example requests.
3. Identify deploy, config, dependency, or data-change correlation.
4. Mitigate first, then tune thresholds only after the incident is understood.
