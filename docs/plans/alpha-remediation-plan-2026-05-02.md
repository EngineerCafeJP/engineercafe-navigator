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

The product is still **NO-GO** for alpha because there is no latest `suites=all` green proof and
the STT current-revision gate still fails.

Latest deployed verification:

- develop SHA: `d789a2cd899779423947c40a3d65e19382f52d30`
- Cloud Run revision: `engineer-cafe-backend-00148-82c`
- Targeted B run: `25254789937`
- B result: `64 passed, 0 warned, 0 failed`
- UUID / reception persistence log errors during the B run window: 0 rows

## Implementation Order

### 1. #658 STT long-tail latency

Goal: reduce the current deployed revision STT long-tail before relying on voice gates.

Status:

- Current-revision scoping is implemented.
- Historical risk reporting is separated from release gate reporting.
- The latest STT-only current-revision gate still failed: 7 samples, p50 `5180ms`,
  p95/max `29217ms`, 14.3% over 10s.

Next tasks:

- Implement Qwen STT long-tail mitigation: fallback threshold, warmup policy, and timeout-before-failure behavior.
- Re-run `stt` and `v` suites.

### 2. #657 / #583 RAGAS coverage

Goal: reconcile the 29-case diagnostic gate with the 127-case alpha requirement.

Status:

- Direct OpenAI provider path is confirmed.
- RAGAS progress telemetry is implemented.
- Coverage semantics are still unresolved.

Tasks:

- Define release-blocking cases versus diagnostic/soak cases.
- Add explicit workflow inputs for diagnostic C and full C-127.
- Ensure reports cannot imply that 29 cases satisfy the 127-case requirement.

### 3. #653 / #672 answer quality

Goal: remove current Q/C answer-quality failures without masking real product issues.

Current Q failures:

- `Q-BIZ-EN-003`
- `Q-EVT-EN-001`
- `Q-DAILY-JA-001`

Current C/RAGAS direct OpenAI failure:

- JA answer_correctness `0.8295`, target `0.85`
- weak cases: `ml-ja-003`, `ml-ja-004`

Tasks:

- Read the report artifacts for exact expected facts and actual answers.
- Decide whether each failure is response generation, source retrieval, ground truth, or threshold drift.
- Fix the smallest product-side issue first; only adjust tests when the expected answer is wrong.
- Re-run `q` and `c`.

### 4. #670 RAGAS operational closeout

Goal: make slow or failing C/Q gates diagnosable in GitHub Actions artifacts.

Status:

- Provider/model/case progress telemetry is implemented.
- Compact report artifact upload is implemented.

Tasks:

- Run full C/Q after #658 or in a diagnostic window.
- Confirm provider/model/case progress is present in logs and compact artifacts.
- Close #670 only after one full C/Q operational proof.

## Completed Items

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
gh workflow run alpha-live-verification.yml --ref develop -f suites=q,c -f require_deployed_sha_match=true
```

Only run `suites=all` after #658 and the C/Q gate decision have targeted green runs.
