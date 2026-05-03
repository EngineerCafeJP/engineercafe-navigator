# Alpha Remediation Plan 2026-05-02

This is the execution plan for the implementation sessions after the 2026-05-02 alpha live
verification run. It includes the 2026-05-03 remediation status through PR #709 and the
SHA-matched full alpha-live-verification run `25272361091`.

> 2026-05-03 reset note: this plan is now historical for the long remediation sweep. Use
> [Alpha Reset Plan 2026-05-03](alpha-reset-plan-2026-05-03.md) for the next implementation session.
> The previous "watch full run" posture has been replaced by targeted STT, C/RAGAS, and device-proof
> work.

## Current State

The workflow infrastructure is now complete enough to run targeted alpha gates end to end:

- Cloud Run SHA match gate works.
- Full suite dispatch works.
- C/RAGAS can run with direct OpenAI after syncing `OPENAI_API_KEY`.
- Compact reports and failure-oriented heavy artifacts are split.
- RAGAS provider/model/case progress telemetry is emitted.
- B routing / slide live smoke is green on deployed staging.
- Voice backend timeout budget is aligned across Vercel proxy, Next.js routes, and Cloud Run deploy guard.
- iOS delayed TTS and Android large-audio playback have product-side fixes merged.

The product is still **NO-GO** for alpha because there is no latest `suites=all` green proof.
The C-127 manifest accounting defect is fixed by PR #692, but post-#692 validation exposed a
live `/api/chat` 429 collection blocker. A new SHA-matched full run is in progress.

Latest deployed verification:

- backend deploy SHA: `6ce1ac81983c7ae53ddfdfc58eba1ee043a83fa8`
- Cloud Run revision: `engineer-cafe-backend-00162-mlr`
- PR #692 merge SHA: `d74264e808e9b2a0244d3a1a9e5dfe12671530ea`
- C-127 run after #692: `25270459825`
- C-127 result after #692: failure, `alpha-127` requested `127`, evaluated `35`, collection errors `92`
- PR #695 merge SHA: `ed25199e4c7104ac0f6e2f027c4fdadd72280182`
- PR #699/#700/#701/#702/#703 are merged for C source routing, Welcome guard, C-127 coverage, log hygiene, and STT warmup
- PR #705/#707/#709 are merged; #696 is closed after live proof, and #697/#698 mobile audio proof remains open
- At this historical snapshot, full alpha-live-verification run `25272361091` had been dispatched with
  `suites=all`, `c_ragas_suite=alpha-127`
- Q targeted run before #693: `25269072919` failed with `23 PASS / 0 WARN / 2 FAIL`
- PR #693 merge SHA: `14cb8e5b3c4f9711a77c634d3db80f8bf4f80efd`; post-#693 Q proof is included in run `25272361091`

## Implementation Order

This section is superseded by [Alpha Reset Plan 2026-05-03](alpha-reset-plan-2026-05-03.md). It is
kept for audit history only.

### 1. Watch full run `25272361091`

Goal: use the first post-#709 full run as the current alpha gate proof attempt.

Tasks:

- Confirm SHA match against Cloud Run image `6ce1ac81983c7ae53ddfdfc58eba1ee043a83fa8`.
- Collect the compact report artifact and workflow summary.
- If C-127 or Q still fails, split only the failing area into targeted reruns.
- Do not close #643/#612 until this run is green or an explicit waiver/demotion is recorded.

### 2. #583 / #694 C-127 live collection completion

Goal: make C-127 collect and evaluate all 127 selected manifest cases through live `/api/chat`.

Status:

- Direct OpenAI provider path is confirmed.
- RAGAS progress telemetry is implemented.
- `c-127` workflow selection is implemented.
- PR #692 fixed manifest accounting: post-#692 run `25270459825` reports `requested=127`.
- The same run evaluated only `35/127` because live `/api/chat` returned `92` `429 Too Many Requests`
  collection errors.
- PR #695 is merged with C-127 pacing / 429 retry, and PR #701 adds coverage summary polish, but live proof is pending.

Tasks:

- Use run `25272361091` as the current C-127 proof attempt. If it fails, re-run only `suites=c-127`
  against the deployed SHA or the next targeted fix SHA.
- Require `suite_coverage.requested_total_cases=127`, `evaluated=127`, and `collection_errors=0`.
- Only interpret #672 C answer/source metrics after collection completes.

### 3. #653 / #672 answer quality

Goal: remove current Q/C answer-quality failures without masking real product issues.

Current Q failures:

- `Q-BIZ-EN-003`
- `Q-DAILY-JA-001`

Latest Q run `25269072919` improved from 3 failures to 2 failures:

- `Q-BIZ-EN-003`: route OK, sources OK, missing expected fact `reservation`.
- `Q-DAILY-JA-001`: route OK, answer OK, latency `2205ms`.
- `Q-EVT-EN-001` now passes.
- PR #693 is merged for the two remaining failures; proof is pending in the current full run.

Current C/RAGAS direct OpenAI C-127 status:

- Run `25270459825`: `alpha-127` requested `127`, evaluated `35`, collection errors `92`.
- Current answer/source metrics are not release-proof because most cases were not collected.
- Known evaluated-subset source failure: `gt-019` JA consultation had actual sources `[]`.

Tasks:

- Read Q outcome from run `25272361091` and close #653 only if the Q suite has `0 FAIL`.
- Read C-127 outcome from run `25272361091` and only then inspect report artifacts for exact expected facts and actual answers.
- Decide whether each failure is response generation, source retrieval, ground truth, or threshold drift.
- Fix the smallest product-side issue first; only adjust tests when the expected answer is wrong.
- Re-run `q` and `c`.

### 4. #670 RAGAS operational closeout

Goal: make slow or failing C/Q gates diagnosable in GitHub Actions artifacts.

Status:

- Provider/model/case progress telemetry is implemented.
- Compact report artifact upload is implemented.

Tasks:

- Run full C/Q after #695 and the targeted Q/C fixes, or in a diagnostic window.
- Confirm provider/model/case progress is present in logs and compact artifacts.
- Close #670 only after one full C/Q operational proof.

## Completed Items

### #696 / #697 / #698 voice and mobile playback implementation

Status: #696 closed after live proof; #697/#698 implemented, device proof pending.

- PR #705/#709 align Vercel maxDuration, voice/filler proxy timeout, controlled 504 UX, and Cloud Run deploy guard.
- PR #707 keeps the iOS gesture-unlocked AudioContext path and adds Android large-audio HTML playback fallback.
- #697/#698 remain open until target-device proof is attached. #696 timeout regression remains covered by #643 full-run evidence.

### #658 STT long-tail latency

Status: completed and closed.

- Current-revision scoping is implemented.
- Historical risk reporting is separated from release gate reporting.
- GitHub issue #658 was closed after run `25258764528` passed `suites=stt,v`, but this historical
  status is superseded by the 2026-05-03 reset after run `25275030436` failed STT latency again.

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
gh workflow run alpha-live-verification.yml --ref develop -f suites=c-127 -f require_deployed_sha_match=true -f expected_backend_sha=<current-backend-sha>
gh workflow run alpha-live-verification.yml --ref develop -f suites=q -f require_deployed_sha_match=true -f expected_backend_sha=<current-backend-sha>
```

Only run `suites=all` after post-#695 C-127 and post-#693 Q have targeted green runs. For C-127,
do not treat an artifact as release proof unless `suite_coverage.requested_total_cases=127`,
`evaluated=127`, and `collection_errors=0`.
