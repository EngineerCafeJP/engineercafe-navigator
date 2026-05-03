# Alpha Live Verification Status 2026-05-02

このドキュメントは、2026-05-02 JST 時点の alpha live verification 正本に、2026-05-03 JST
の PR #674/#675/#676 remediation 結果を追記したものです。古い 2026-04-25 status は履歴として残しますが、
次の実装判断ではこのファイルを優先します。

## 結論

**NO-GO** です。

`develop` と Cloud Run staging の SHA 同期、full-suite workflow、C/RAGAS direct OpenAI
実行経路は成立しました。一方で、alpha GO を止める blocker がまだ残っています。

2026-05-03 時点で、B routing / slide live smoke、Welcome UI、artifact split、Supabase UUID
log hygiene、Cloud Run Qwen runtime dependency、STT/voice preflight は解消済みです。残る P0 は
RAGAS coverage / accounting reconciliation と live-only proof 群です。

## 2026-05-02 Baseline Deploy / SHA Sync

- PR: #667
- develop SHA: `fa7745b7420c0709fcff950ed3bf4c090f0dfc55`
- Cloud Run revision: `engineer-cafe-backend-00144-q85`
- Image:
  `asia-northeast1-docker.pkg.dev/aipartner-426616/cloud-run-source-deploy/engineer-cafe-backend:fa7745b7420c0709fcff950ed3bf4c090f0dfc55`
- Health: `/health` OK
- `require_deployed_sha_match=true`: PASS

## Runs

### 2026-05-03 Targeted B Verification After PR #674/#675/#676

- Run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25254789937>
- Suites: `b`
- Result: success
- Cloud Run revision: `engineer-cafe-backend-00148-82c`
- Image:
  `asia-northeast1-docker.pkg.dev/aipartner-426616/cloud-run-source-deploy/engineer-cafe-backend:d789a2cd899779423947c40a3d65e19382f52d30`
- Health: `/health` OK
- `require_deployed_sha_match=true`: PASS
- Summary: `64 passed, 0 warned, 0 failed`
- B1-BIZ-003: `土日祝日も利用できますか。` -> `business_info`, `1258ms`
- Slide narration B5-1..B5-5: PASS, `171ms` to `180ms`
- Cloud Logging query for `invalid input syntax for type uuid`: 0 rows in the run window
- Cloud Logging query for `Reception session persistence failed`: 0 rows in the run window

Resolved by this remediation pass:

- #659: B routing / slide live smoke
- #660: H-UI Welcome UI live scenario
- #661: compact artifact visibility
- #662: Supabase UUID / Cloud Run log hygiene
- #671: RAGAS provider secret issue

### 2026-05-03 C-127 Harness Accounting Finding

- Run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25268597241>
- Suites: `c-127`
- Result: failure
- Backend SHA match: `d1280aa64643aae7b22df875ee22f13cbfe294a2`
- Case suite: `alpha-127`
- Expected cases: `127`
- Reported requested/evaluated cases: `85`
- Reported language counts: `ja=38`, `en=23`, `zh=12`, `ko=12`

This run confirmed a harness accounting bug. The `alpha-127` dataset still contains 127 cases
(`ja=80`, `en=23`, `zh=12`, `ko=12`), but `run_live_api_eval.py` currently drops `/api/chat`
collection failures from the report and then uses collected-success count as `requested_case_count`.
The missing 42 cases were all Japanese and were absent from the artifact instead of being reported as
collection failures.

Required next action is ADR 019 / #691:

- `requested_case_count` must mean selected manifest cases, not successfully collected responses.
- API collection failures must be persisted as `collection_errors`.
- `evaluation_complete` and `alpha_release_gate_met` must fail when collection errors exist.

Until this is fixed and rerun, C-127 artifacts cannot be used as alpha GO proof even when
`case_suite=alpha-127` is present.

### 2026-05-03 Targeted Q Verification After PR #690/#689

- Run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25269072919>
- Suites: `q`
- Result: failure
- Backend SHA match: `d1280aa64643aae7b22df875ee22f13cbfe294a2`
- Summary: `23 PASS / 0 WARN / 2 FAIL`

Remaining failures:

- `Q-BIZ-EN-003`: route is `business_info` and source is `enhanced_rag`, but expected fact
  `reservation` is missing.
- `Q-DAILY-JA-001`: route is `general_knowledge`, but latency is `2205ms`.

Improvement from the previous Q baseline: `Q-EVT-EN-001` now passes.

Resolved STT follow-up:

- Earlier STT-only run after PR #674 deploy failed with p95/max `29217ms`.
- A later `suites=stt,v` run `25258764528` passed on Cloud Run `engineer-cafe-backend-00153-r9r`.
- #658 is closed.

### Full Suite

- Run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25244933308>
- Suites: `all`
- Result: failure
- Artifact: `alpha-live-verification-25244933308`, artifact ID `6761318600`
- Artifact size: `932,009,663` bytes

Historical failing outcomes from that run:

| Outcome | Status | Current issue |
| --- | --- | --- |
| `stt_preflight` | failure | #658 |
| `alpha_b` | failure | #659 |
| `rag_api_live` | failure | #657, #583, #672 |
| `cloud_logging` | failure | #662 |
| `quality_q` | failure | #653 |
| `welcome_live` | failure | #660 |

Important hidden behavior: several workflow steps use `continue-on-error`, so the GitHub step
conclusion can read `success` while the suite outcome is still `failure`. Always inspect the
workflow summary and report artifacts before closing alpha issues.

### Targeted C/RAGAS Provider Verification

- Run: <https://github.com/EngineerCafeJP/engineercafe-navigator/actions/runs/25247945549>
- Suites: `c`
- Result: failure
- Provider: direct OpenAI
- Model: `gpt-5.2-2025-12-11`
- Runtime: about 6m52s for the current 29-case C gate

This run was dispatched after syncing GCP Secret Manager `openai-api-key` to GitHub Actions
`OPENAI_API_KEY`. It confirmed that #671 is fixed. The remaining C failure is now answer quality /
coverage, not provider configuration.

## Current Blockers

### P0

- #691 / #657 / #583: C/RAGAS gate now has `c-127`, but the first full run exposed harness accounting
  drift: `alpha-127` expected 127 while artifact reported only 85 requested/evaluated cases.
- #643 / #612: umbrella issues remain open until the alpha gate is green.
- #611 / #584 / #585: fast first-response, edge/failure tolerance, and 2h kiosk soak still need final proof.

### P1

- #672: Direct OpenAI C/RAGAS still misses answer quality targets after C-127.
  - JA: `0.585`, target `0.85`
  - EN: `0.7017`, target `0.75`
  - ZH: `0.7271`, target `0.65`
  - KO: `0.7151`, target `0.65`
  - JA/EN answer quality and live source fallback cases need product-side triage after harness
    accounting is fixed.
- #653: Q content quality still fails.
  - `Q-BIZ-EN-003`
  - `Q-DAILY-JA-001`
  - `Q-EVT-EN-001` now passes in run `25269072919`.
- #670: C/RAGAS runtime improved after direct OpenAI, and telemetry is now present, but full-run
  operational proof is still needed.
- #655: memory WARNs remain; TTS long Japanese case passed in the latest run.
- #668: GitHub Actions Node.js 20 deprecation warnings need post-alpha cleanup.

## RAGAS Provider Decision

Alpha RAGAS must use direct OpenAI unless explicitly running a diagnostic fallback.

Required behavior:

- `OPENAI_API_KEY` must be non-empty in GitHub Actions.
- The C step must print `RAGAS judge provider: direct OpenAI`.
- OpenRouter fallback must not be accepted for alpha GO proof unless the run is explicitly marked
  diagnostic.

Observed impact:

- OpenRouter fallback: about 22m46s for 29 cases.
- Direct OpenAI: about 6m52s for 29 cases.

## Next Implementation Order

1. ADR 019 / #691 / #657 / #583: fix C-127 harness accounting so 127 manifest cases are always reported,
   and collection failures are explicit.
2. #653 and #672: Q/C answer quality for current failing cases.
3. #670: verify full C/Q telemetry and runtime with the current artifact split.
4. #611 / #584 / #585: collect or split the remaining live-only alpha proof.

## Useful Commands

```bash
gh workflow run alpha-live-verification.yml \
  --ref develop \
  -f suites=all \
  -f require_deployed_sha_match=true

gh workflow run alpha-live-verification.yml \
  --ref develop \
  -f suites=c \
  -f require_deployed_sha_match=true

# Harness-only rerun when the workflow/scripts changed but Cloud Run backend did not:
gh workflow run alpha-live-verification.yml \
  --ref develop \
  -f suites=all \
  -f require_deployed_sha_match=true \
  -f expected_backend_sha=<40-char-deployed-backend-sha>

gcloud run services describe engineer-cafe-backend \
  --project aipartner-426616 \
  --region asia-northeast1 \
  --format='value(status.latestReadyRevisionName,spec.template.spec.containers[0].image,status.url)'
```
