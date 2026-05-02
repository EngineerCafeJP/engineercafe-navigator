# Alpha Remediation Plan 2026-05-02

This is the execution plan for the next implementation session after the 2026-05-02 alpha live
verification run.

## Current State

The workflow infrastructure is now complete enough to run the alpha gate end to end:

- Cloud Run SHA match gate works.
- Full suite dispatch works.
- C/RAGAS can run with direct OpenAI after syncing `OPENAI_API_KEY`.
- Reports and artifacts are uploaded.

The product is still **NO-GO** for alpha because the latest full suite ended in failure.

## Implementation Order

### 1. #658 STT preflight latency

Goal: make the preflight evaluate the current deployed revision and remove avoidable long-tail
latency before relying on voice gates.

Tasks:

- Scope `scripts/stt-live-preflight.sh` to the current Cloud Run revision when
  `ALPHA_SMOKE_CLOUD_RUN_REVISION` is present.
- Separate historical 24h risk reporting from the release gate for the current revision.
- Investigate current revision outliers above 30s.
- Re-run `stt` and `v` suites.

### 2. #660 H-UI Welcome OCR overlay

Goal: make the live welcome scenario assert the real UI state without depending on a missing or
renamed test id.

Tasks:

- Inspect `frontend/e2e/welcome-live.spec.ts` around the `kiosk-welcome-ocr-overlay` assertion.
- Confirm whether the overlay is intentionally absent, hidden behind a timing transition, or renamed.
- Fix the UI/test contract, then run the H-UI suite.

### 3. #659 B routing

Goal: make `B1-BIZ-002` route to `business_info`.

Tasks:

- Reproduce the single query locally or with a targeted live request.
- Inspect route metadata and classifier decision path for `今日の最終受付は何時ですか。`.
- Add a focused regression test.
- Re-run suite `b`.

### 4. #653 / #672 answer quality

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

### 5. #662 Supabase UUID/log hygiene

Goal: stop synthetic alpha session IDs from causing 400 UUID lookup noise.

Tasks:

- Guard UUID-only Supabase queries before hitting `reception_sessions` and `conversation_sessions`.
- Keep synthetic session IDs valid for test isolation without logging avoidable errors.
- Add tests around non-UUID session IDs.
- Re-run the suites that exercise A/B/D.

### 6. #661 / #670 test infrastructure

Goal: make failures obvious and keep artifacts usable.

Tasks:

- Upload compact Markdown/JSON failure summaries separately from Playwright videos and traces.
- Keep video/trace upload opt-in or failure-only.
- Emit RAGAS provider/model/case progress while the C gate runs.

### 7. #657 / #583 RAGAS coverage

Goal: reconcile the 29-case diagnostic gate with the 127-case alpha requirement.

Tasks:

- Define which cases are release-blocking versus diagnostic/soak.
- Add explicit workflow inputs for diagnostic C and full C-127.
- Do not expand to 127 until #670 telemetry is in place.

## Re-run Strategy

Use targeted suites until the relevant blocker is fixed:

```bash
gh workflow run alpha-live-verification.yml --ref develop -f suites=stt,v -f require_deployed_sha_match=true
gh workflow run alpha-live-verification.yml --ref develop -f suites=h-ui -f require_deployed_sha_match=true
gh workflow run alpha-live-verification.yml --ref develop -f suites=b -f require_deployed_sha_match=true
gh workflow run alpha-live-verification.yml --ref develop -f suites=q,c -f require_deployed_sha_match=true
```

Only run `suites=all` after the current P0 blockers have targeted green runs.

