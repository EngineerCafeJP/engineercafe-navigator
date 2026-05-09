# Observability Runbook

Issue #513 Phase 1b monitors Cloud Run logs through Terraform-managed log metrics,
dashboard panels, and alert policies. Terraform changes are applied manually after merge.

## On-site Ops Gate

Use `scripts/onsite-voice-live-proof.sh` for #774/#483/#489/#140 operational proof. It runs the
real live path:

```text
/api/voice speech_to_text -> /api/chat -> /api/voice text_to_speech
```

Default pass/fail windows are based on the 2026-05-09 post-alpha baseline: STT was still the
primary bottleneck (`p50=6877ms`, `p95/max=10006ms`), quick chat p50 was about `2486ms`, and
PiperPlus TTS was usable but still required provider-fault proof.

| Segment | PASS | WARN | FAIL |
| --- | ---: | ---: | ---: |
| STT | `<=5000ms` | `<=10000ms` | `>10000ms` |
| Chat | `<=5000ms` | `<=10000ms` | `>10000ms` |
| TTS | `<=5000ms` | `<=10000ms` | `>10000ms` |
| Full turn (`STT+chat+TTS`) | `<=12000ms` | `<=15000ms` | `>15000ms` |

Run from the repo root with a manifest built from actual kiosk/M5Stack microphone WAV files:

```bash
scripts/onsite-voice-live-proof.sh \
  --manifest backend/evaluation/datasets/onsite_voice_live_manifest.example.json \
  --timestamp onsite-YYYYMMDD-HHMM
```

Outputs:

- `backend/tests/reports/onsite-voice-live-proof-<timestamp>.md`
- `backend/tests/reports/onsite-voice-live-proof-<timestamp>.csv`
- `backend/tests/reports/onsite-voice-ops-gate-<timestamp>.md`

The shell gate fails on any runner failure, hop latency failure, missing STT/chat/TTS step, or
full-turn latency failure. Thresholds are intentionally overridable for controlled experiments:
`--stt-pass-ms`, `--stt-fail-ms`, `--chat-pass-ms`, `--chat-fail-ms`, `--tts-pass-ms`,
`--tts-fail-ms`, `--full-turn-pass-ms`, and `--full-turn-fail-ms`.

On-site checklist:

1. Record WAV files on the target kiosk/M5Stack microphone path; do not use laptop fixtures.
2. Note device, network, room/noise state, Cloud Run revision, and backend SHA beside the report.
3. Run the matching Cloud Logging queries for the proof window.
4. Treat TTS fallback, empty audio, `/api/chat` 5xx, memory helper errors, UUID hygiene hits, and
   reception persistence errors as blockers until triaged.
5. Do not apply Terraform from the on-site proof. Terraform remains review/plan/apply only.

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

## TTS Response

Primary signal: `jsonPayload.event="tts_complete"` with `tts_overall_duration_ms`, `provider`,
`language`, `success`, `tts_cache_hit`, `fallback_used`, and `fallback_provider`.

Useful Cloud Logging query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="tts_complete"
```

High-latency query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="tts_complete"
jsonPayload.tts_overall_duration_ms>=5000
```

Failure or fallback query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
jsonPayload.event="tts_complete"
(jsonPayload.success=false OR jsonPayload.fallback_used=true)
```

Triage:

1. Split by `provider`, `language`, `tts_cache_hit`, and `fallback_used`.
2. Check whether failures are empty audio, upstream provider failure, timeout, or fallback failure.
3. Confirm whether on-site cases used long answers that should be shortened before TTS.
4. Compare the TTS provider config against the last known healthy revision.

## Full-Turn Latency

There is no single production log event today that represents full user turn latency across
STT, chat, and TTS. The operational gate derives full-turn latency from
`onsite-voice-live-proof` CSV rows by summing:

```text
onsite_qwen_stt + live_langgraph_answer + live_answer_tts
```

Use the full-turn result in `onsite-voice-ops-gate-<timestamp>.md` as the on-site pass/fail signal.
If it fails, inspect the hop table first; do not tune Cloud Monitoring thresholds until the slow hop
is identified.

## Alpha Log Hygiene

The alpha Cloud Logging gate treats the following as release-blocking noise because they obscure
actual P0/P1 signal during live verification:

- `invalid input syntax for type uuid`
- `Reception session persistence failed`

Useful Cloud Logging query:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="engineer-cafe-backend"
("invalid input syntax for type uuid" OR "Reception session persistence failed")
```

Expected result during a targeted alpha run window is zero rows. If rows appear, first confirm
whether synthetic alpha `session_id` values are being passed into UUID-only persistence lookups or
whether Supabase reception persistence is genuinely unavailable. Keep structured request,
`chat_response`, STT, and TTS logs intact; do not hide real persistence errors by lowering severity.

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
