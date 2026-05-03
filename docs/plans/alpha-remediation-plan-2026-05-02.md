# Alpha Remediation Plan 2026-05-02

This is the execution plan for the implementation sessions after the 2026-05-02 alpha live
verification run. It includes the 2026-05-03 remediation status after PR #674, #675, and #676.

## Current State

The workflow infrastructure is now complete enough to run targeted alpha gates end to end:

- Cloud Run SHA match gate works.
- Full suite dispatch works.
- C/RAGAS can run with direct OpenAI after syncing `OPENAI_API_KEY`.
- Compact reports and failure-oriented heavy artifacts are split.
- RAGAS provider/model/case progress telemetry is emitted.
- B routing / slide live smoke is green on deployed staging.

The product is still **NO-GO** for alpha because there is no latest `suites=all` green proof, and
the first C-127 run exposed a live RAGAS harness accounting defect.

Latest deployed verification:

- backend deploy SHA: `d1280aa64643aae7b22df875ee22f13cbfe294a2`
- Cloud Run revision: `engineer-cafe-backend-00157-b6c`
- C-127 run: `25268597241`
- C-127 result: failure, `alpha-127` expected `127` but artifact reported `85`
- Q targeted run after C-127 dispatch: `25269072919` failed with `23 PASS / 0 WARN / 2 FAIL`

## Implementation Order

### 1. ADR 019 / #691 / #657 / #583 RAGAS coverage and accounting

Goal: make C-127 artifacts prove both selected manifest coverage and live API collection success.

Status:

- Direct OpenAI provider path is confirmed.
- RAGAS progress telemetry is implemented.
- `c-127` workflow selection is implemented.
- The first C-127 run selected `alpha-127`, but artifact accounting reported only 85 requested cases
  because live API collection failures were dropped from the report.

Tasks:

- Implement ADR 019 in `backend/evaluation/run_live_api_eval.py`.
- Keep `requested_case_count` tied to selected manifest cases, not collected successful responses.
- Persist `/api/chat` collection failures as `collection_errors`.
- Fail `evaluation_complete` and `alpha_release_gate_met` when collection errors exist.
- Add regression coverage in `backend/tests/evaluation/test_ragas_live_case_suites.py`.
- Re-run `suites=c-127` before interpreting C answer quality metrics.

### 2. #653 / #672 answer quality

Goal: remove current Q/C answer-quality failures without masking real product issues.

Current Q failures:

- `Q-BIZ-EN-003`
- `Q-DAILY-JA-001`

Latest Q run `25269072919` improved from 3 failures to 2 failures:

- `Q-BIZ-EN-003`: route OK, sources OK, missing expected fact `reservation`.
- `Q-DAILY-JA-001`: route OK, answer OK, latency `2205ms`.
- `Q-EVT-EN-001` now passes.

Current C/RAGAS direct OpenAI C-127 failure:

- Run `25268597241`: `alpha-127` expected `127`, reported `85`; interpret answer quality only
  after ADR 019 is merged and rerun.
- Current reported metrics from the incomplete artifact:
  - JA answer_correctness `0.585`, target `0.85`
  - EN answer_correctness `0.7017`, target `0.75`
  - ZH answer_correctness `0.7271`, target `0.65`
  - KO answer_correctness `0.7151`, target `0.65`
- Source gate failures: `gt-019` JA, `gt-065` EN, `gt-115` KO.

Tasks:

- Read the report artifacts for exact expected facts and actual answers.
- Decide whether each failure is response generation, source retrieval, ground truth, or threshold drift.
- Fix the smallest product-side issue first; only adjust tests when the expected answer is wrong.
- Re-run `q` and `c`.

### 3. #670 RAGAS operational closeout

Goal: make slow or failing C/Q gates diagnosable in GitHub Actions artifacts.

Status:

- Provider/model/case progress telemetry is implemented.
- Compact report artifact upload is implemented.

Tasks:

- Run full C/Q after #691 and the targeted Q/C fixes, or in a diagnostic window.
- Confirm provider/model/case progress is present in logs and compact artifacts.
- Close #670 only after one full C/Q operational proof.

## Completed Items

### #658 STT long-tail latency

Status: completed and closed.

- Current-revision scoping is implemented.
- Historical risk reporting is separated from release gate reporting.
- GitHub issue #658 is closed after run `25258764528` passed `suites=stt,v`.

### #660 H-UI Welcome OCR overlay

Goal: make the live welcome scenario assert the real UI state without depending on a missing or
renamed test id.

Status: completed in PR #674.

- H-UI targeted run passed after the contract was updated to the current voice-first UI.
- Issue #660 is closed.

### #659 B routing

Goal: make `B1-BIZ-002` and `B1-BIZ-003` route to `business_info`.

Status: completed in PR #675 and verified again after PR #676.

- Targeted B run `25254789937`: `64 passed, 0 warned, 0 failed`.
- Issue #659 is closed.

### #662 Supabase UUID/log hygiene

Goal: stop synthetic alpha session IDs from causing 400 UUID lookup noise.

Status: completed in PR #675 and PR #676.

- UUID-only lookups are guarded.
- Reception persistence now stores non-UUID conversation session IDs outside UUID columns.
- Cloud Logging queries for UUID parsing and reception persistence failures returned 0 rows for targeted B run `25254789937`.
- Issue #662 is closed.

### #661 artifact size

Goal: make failures obvious and keep artifacts usable.

Status: completed in PR #674.

- Compact Markdown/JSON reports are uploaded separately.
- Heavy browser artifacts are failure-oriented.
- Issue #661 is closed.

## Re-run Strategy

Use targeted suites until the relevant blocker is fixed:

```bash
gh workflow run alpha-live-verification.yml --ref develop -f suites=stt,v -f require_deployed_sha_match=true
gh workflow run alpha-live-verification.yml --ref develop -f suites=c-127 -f require_deployed_sha_match=true -f expected_backend_sha=<current-backend-sha>
gh workflow run alpha-live-verification.yml --ref develop -f suites=q,c -f require_deployed_sha_match=true
```

Only run `suites=all` after #691 and the C/Q gate decision have targeted green runs. For C-127,
do not treat an artifact as release proof unless `suite_coverage.requested_total_cases=127` and
collection failures are explicitly represented.
