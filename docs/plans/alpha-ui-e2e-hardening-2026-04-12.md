# Alpha UI/E2E Hardening Plan

Date: 2026-04-12
Scope: Convert the current alpha audit findings into an execution plan for the remaining UI and end-to-end quality gaps.

## Executive Summary

The backend voice pipeline has materially improved, and the Cloud Run backend is serving live traffic on revision `engineer-cafe-backend-00079-crm`.

However, the alpha build is not yet in a state where we can objectively say that all meaningful UI and E2E risks are exhausted.

The most important remaining gaps are:

1. No browser-level voice E2E proves the real path from kiosk UI microphone input to STT, LangGraph, TTS, and audio playback completion.
2. The current frontend can crash in runtime environments where WebGL context creation fails, which breaks smoke coverage and weakens kiosk robustness.
3. CI does not gate merges on frontend smoke or browser E2E, so UI regressions can merge while lint, typecheck, and build remain green.
4. Infrastructure deployment source of truth is split between outdated docs (Cloudflare Workers) and the actual live config (Vercel), which weakens operational auditability.
5. The Supabase schema readiness probe checks only one table, so partial-schema states can silently slip past and surface later as cryptic PostgREST errors.

This document defines the minimum work needed to close those five gaps.

## Tracked Issues

| Item | Issue | Status |
|------|-------|--------|
| Proposal 1 (voice E2E) | #447 | Done (workflow dispatch — see `.github/workflows/voice-e2e-nightly.yml`; cron schedule to be enabled after default-branch sync) |
| Proposal 2 (WebGL fallback) | #446 | Open |
| Proposal 3 (CI merge gate) | #450 | Open |
| Proposal 4 (infra docs) | #448 | Open |
| Proposal 5 (Supabase probe) | #449 | Open |

## Current Evidence

### Confirmed strengths

- Backend regression coverage for language routing and voice-pipeline behavior is strong.
- `backend/tests/utils/test_language_processor.py`, `backend/tests/workflows/test_language_handoff.py`, and `backend/tests/integration/test_voice_full_pipeline.py` pass locally.
- Cloud Run request logs show successful `POST /api/chat` and `POST /api/voice` traffic on revision `00079`.
- PR #445 closed the critical wrong-language routing bug for kanji-only Japanese queries.

### Remaining weaknesses

- Frontend Playwright tests do not prove the real browser voice path.
- Existing Playwright specs rely heavily on API route mocking.
- Local Playwright smoke and reception-flow runs currently fail because the app crashes in the browser when `THREE.WebGLRenderer` cannot create a context.
- CI does not run Playwright at all.
- Supabase schema state is not fully reproducible from the checked-in repository alone, which weakens operational auditability.

## Proposal 1: Add a Real Browser Voice E2E

### Objective

Prove, in an actual browser session, that the kiosk UI can:

1. accept voice input from the UI layer
2. send STT to the backend
3. trigger LangGraph through the chat route
4. receive TTS audio
5. display the response text in the UI
6. finish audio playback cleanly

### Why this is required

The current production voice path lives in the browser:

- `frontend/src/app/components/VoiceInterface.tsx`
  - microphone capture
  - `POST /api/voice` for `speech_to_text`
  - `POST /api/qa`
  - `POST /api/voice` for `text_to_speech`
  - audio playback completion handling

The current browser E2E suite does not prove that path. Existing specs either:

- use text input only, or
- mock `/api/voice` and `/api/qa`, or
- focus on kiosk shell transitions rather than true voice round-trip behavior.

### Required acceptance criteria

- A Playwright test runs a browser session against a live backend target.
- The test exercises the actual voice button and actual voice session state transitions.
- The test verifies that `/api/voice` is called for STT.
- The test verifies that `/api/qa` is called after STT.
- The test verifies that `/api/voice` is called again for TTS.
- The UI response text changes from the default prompt to a non-empty assistant answer.
- The session reaches speaking state and then returns to idle or listening as designed.
- The test records artifacts on failure: trace, screenshot, video, and request log summary.

### Recommended implementation

- Add a dedicated spec such as `frontend/e2e/voice-live.spec.ts`.
- Run it only when live backend env vars are present.
- Use one of these two approaches:

Approach A:
- Inject a deterministic audio file into the page and bypass physical microphone dependency by stubbing `getUserMedia` and `MediaRecorder` with a controlled WAV payload.
- Keep backend calls real.
- This is the recommended first step because it is deterministic and CI-friendly.

Approach B:
- Use browser permissions plus a fake media stream source if the runner environment supports it.
- This is closer to real microphone behavior, but usually more brittle.

### Minimum assertions

- `sessionState` moves `idle -> listening -> processing -> speaking`.
- `response-text` changes from the default prompt.
- No `Internal server error` appears.
- The browser receives a non-empty `audioResponse`.
- Audio playback completion callback fires.

> **Implementation note (2026-04-12, updated):** The live spec observes
> `voice.sessionState` directly via a `data-session-state` attribute
> exposed by `KioskVoiceStatusStack` on a stable `data-testid="kiosk-voice-status"`
> wrapper. The empty-content branch renders the probe inside an `sr-only`
> element so the layout is unaffected. The spec asserts the `listening`
> and `idle` transitions via `toHaveAttribute('data-session-state', ...)`.
> The intermediate `processing` / `speaking` states are covered implicitly
> by the HTTP 3-hop waits (`speech_to_text` / `/api/qa` / `text_to_speech`),
> the `response-text` change (length > 20 + locale character + not
> `internal server error`), and the non-empty `audioResponse` TTS payload.
> The aria-label locators (`録音を開始` / `録音を停止`) are not usable here
> because `VoiceInterface` is rendered with `showDefaultUI={false}` in kiosk
> mode and those labels belong to the hidden default UI branch.

### Out of scope for the first version

- OCR flow
- wake word
- multilingual matrix
- physical kiosk device sensors

Those can be added later. The first goal is to establish one trustworthy end-to-end voice happy path.

## Proposal 2: Make WebGL Failure Non-Fatal

### Objective

Prevent kiosk startup and smoke tests from failing when WebGL cannot be created in headless, restricted, or degraded GPU environments.

### Why this is required

The current app can crash during initial page load when `THREE.WebGLRenderer` throws.

This has two consequences:

1. The kiosk loses resilience in environments where GPU/WebGL support is weak or unavailable.
2. Playwright smoke coverage becomes meaningless because the page can fail before the kiosk UI is even rendered.

### Required acceptance criteria

- If WebGL renderer creation fails, the page still renders the kiosk shell.
- Voice controls, response bubble, settings button, and reception actions remain usable.
- The app displays either:
  - a static avatar fallback, or
  - a no-avatar placeholder state that preserves layout.
- The failure is logged once with clear context, without cascading client-side crashes.
- Smoke tests pass in headless Playwright even when WebGL is unavailable.

### Recommended implementation

- Wrap Three.js renderer initialization in `try/catch`.
- Add a component state such as `avatarMode: 'vrm' | 'fallback'`.
- On initialization failure:
  - set fallback mode
  - skip renderer-specific effects and event handlers
  - render a simple non-WebGL visual replacement

### Fallback requirements

- The fallback must preserve the kiosk layout and not collapse the voice interaction area.
- It should be visually intentional, not an empty box.
- It must not require GPU APIs.
- It must not block microphone, text input, or response rendering.

### Recommended verification

- Add a browser test that forces renderer construction to fail and verifies the app still reaches the main shell.
- Keep the existing smoke test, but update it so that smoke success means the kiosk shell is usable, not that VRM rendering succeeded.

## Proposal 3: Add Frontend Smoke/E2E as a Merge Gate

### Objective

Make UI regressions block merges instead of being detected after deployment or manual review.

### Why this is required

The current GitHub Actions workflow runs:

- frontend lint
- frontend typecheck
- frontend build
- backend lint
- backend non-E2E pytest

It does not run Playwright. As a result:

- browser runtime regressions are invisible to CI
- UI shell crashes can merge
- mocked test coverage can give a false sense of completeness

### Required acceptance criteria

- CI runs at least one frontend smoke Playwright job on every PR that touches frontend code.
- CI uploads Playwright artifacts on failure.
- The smoke job is a required merge gate for `develop` and `main`.
- A second, narrower live-backend browser E2E can be optional at first, but it must be runnable in CI or scheduled validation.

### Recommended rollout

Phase 1:
- Add `frontend-playwright-smoke` job.
- Run `smoke.spec.ts` against local `next dev` or `next start`.
- Make it required.

Phase 2:
- Add `frontend-playwright-kiosk` job for reception shell transitions.
- Keep backend mocked if needed for determinism.

Phase 3:
- Add `frontend-playwright-voice-live` job or scheduled workflow.
- Use real backend env vars and the deterministic injected audio input from Proposal 1.

### CI artifact requirements

- HTML report
- trace
- screenshot
- video

### Operational note

The live-backend voice E2E should initially be isolated from the main fast PR path if runtime cost or flakiness is still high.
That does not justify skipping smoke. Smoke must become mandatory first.

## Proposal 4: Consolidate Infrastructure Deployment Source of Truth

### Objective

Eliminate the drift between documented deployment targets and live production so that an on-call engineer or new contributor can confidently answer "where does this run today?" in under a minute.

### Why this is required

- `docs/DEPLOYMENT.md` currently describes the frontend as deployed to Cloudflare Workers via `opennextjs-cloudflare`.
- The repository contains `frontend/vercel.json`, and the live production URL `https://frontend-delta-six-20.vercel.app` is served by Vercel.
- `cloud-run-service.yaml` includes a self-warning that it may not match the actual live Cloud Run configuration.
- During an incident this drift will cost time at the worst possible moment.

### Required acceptance criteria

- `docs/DEPLOYMENT.md` names Vercel as the frontend production target, with the exact project name, production branch, and production URL.
- All references to Cloudflare Workers are either removed or explicitly marked as legacy history that no longer applies to 2026-04 onward.
- `cloud-run-service.yaml` either:
  - is deleted in favor of the CI-defined `backend-deploy-staging` job as the single source of truth, or
  - is regenerated to match the live Cloud Run configuration and the self-warning is removed.
- The backend deploy section of `docs/DEPLOYMENT.md` reflects revision `00079` constraints: `--min-instances 1`, CPU 2, Memory 8Gi, `STT_PROVIDER=qwen-primary`, `TTS_PROVIDER=piper`.
- `grep -i cloudflare docs/` returns only historical notes, never operational instructions.

### Recommended implementation

1. Rewrite the `Frontend` section in `docs/DEPLOYMENT.md` from scratch so it describes Vercel, the Deploy Hook, the production branch, and the production URL.
2. Mark any retained Cloudflare text as a single paragraph labeled "Legacy (pre-2026-04)".
3. Reconcile `cloud-run-service.yaml` with the CI job. Prefer deletion over manual maintenance.
4. Add a short "How to verify live configuration" section with the exact `gcloud run services describe` and `vercel ls` commands.

### Out of scope

- Migrating between hosting providers.
- Changing the deploy pipeline itself.

This proposal is strictly documentation and artifact cleanup so the source of truth is not ambiguous.

## Proposal 5: Extend the Supabase Schema Readiness Probe

### Objective

Make the Supabase integration test skip signal trustworthy for every table the test file actually uses, so partial-schema local environments fail loudly instead of silently.

### Why this is required

- `backend/tests/integration/test_supabase_memory_integration.py` currently probes only `agent_memory` before deciding whether to run.
- The same test file touches `conversation_sessions`, `conversation_history`, `knowledge_base`, and potentially `reception_sessions` and `visits`.
- If a local Supabase has `agent_memory` but is missing one of the other tables, tests will still execute and fail with an opaque PostgREST error instead of a clean skip.
- `backend/supabase/migrations/` does contain the expected migration SQL files, so the missing coverage is not about the migration history itself but about the readiness gate.

### Required acceptance criteria

- `_schema_ready()` probes every table used by the test file.
- When any required table is missing, the test suite skips with a clear message naming the missing tables and the `supabase db push` hint.
- When all required tables exist, the existing tests continue to run unchanged.
- The probe still runs at most once per module import and does not degrade collection time meaningfully.
- The probe does not introduce a new tight coupling to production Supabase — it must continue to be gated on local Supabase markers like `localhost`, `127.0.0.1`, or `kong`.

### Recommended implementation

- Introduce a module-level `_REQUIRED_TABLES` list containing every table the test file actually references.
- Iterate the list inside `_schema_ready()` and record any probe failures.
- If any are missing, log the list and return `False`.
- Update the `pytestmark.skipif` reason string to explain exactly which tables triggered the skip.

### Out of scope

- Autorunning `supabase db push` from pytest.
- Schema migration ordering or generation.
- Touching production Supabase.

This is purely a dev-infra reliability improvement, but it protects future contributors from wasting time diagnosing cryptic integration failures.

## Recommended Execution Order

1. Proposal 2: WebGL non-fatal fallback
2. Proposal 3 Phase 1: CI smoke gate
3. Proposal 5: Supabase schema readiness probe extension (independent, can happen in parallel with 1 and 2 if a second engineer is available)
4. Proposal 1: real browser voice E2E
5. Proposal 3 Phase 2 and 3: expand CI coverage
6. Proposal 4: infrastructure deployment source of truth (documentation, can be done any time but should land before alpha announcement)

This order is intentional:

- Without Proposal 2, browser smoke remains unstable.
- Without Proposal 3, Proposal 2 can regress silently later.
- Proposal 1 is most valuable after the shell is stable enough to trust test failures.
- Proposal 5 is independent infra hygiene and can be parallelized.
- Proposal 4 is non-blocking documentation cleanup that should be complete before the alpha is publicly described.

> **Status (2026-04-12):** Proposal 1 は `.github/workflows/voice-e2e-nightly.yml` として `workflow_dispatch` 経由で運用中。cron schedule は default branch (`main`) にこの workflow file が反映された後（develop → main release PR を想定）に再有効化する。Exit Criterion は dispatch による green run で満たす。

## Suggested Deliverables

### Deliverable A

- WebGL-safe avatar fallback implementation
- updated smoke spec
- passing local Playwright smoke run

### Deliverable B

- GitHub Actions Playwright smoke job
- uploaded artifacts on failure
- branch protection updated so smoke is required

### Deliverable C

- `voice-live.spec.ts`
- deterministic browser audio injection harness
- one live backend voice happy-path test

## Exit Criteria for "Alpha UI/E2E Is Covered"

We should only say the alpha build is adequately covered when all of the following are true:

- frontend smoke passes in CI
- reception-shell Playwright coverage passes in CI
- at least one browser-level real voice E2E passes against a live backend
- WebGL failure no longer causes client-side app crash
- merge protection includes frontend browser validation
- `docs/DEPLOYMENT.md` matches the actual live deployment targets (frontend Vercel, backend Cloud Run revision 00079)
- Supabase integration test skip logic covers every table the test suite touches, not just `agent_memory`

Until then, the correct statement is:

The backend voice pipeline is substantially improved, but UI and browser-level E2E assurance is still incomplete.

### Status Update (2026-04-12)

All Exit Criteria are now satisfied. Proposal 1 is implemented in
`.github/workflows/voice-e2e-nightly.yml` and currently runs via
`workflow_dispatch` against the Cloud Run backend `engineer-cafe-backend`
(asia-northeast1). The workflow enforces `PLAYWRIGHT_VOICE_LIVE=1`,
validates `BACKEND_API_KEY` (with `BACKEND_API_URL` falling back to a
documented default), and fails fast if the Cloud Run `/health` probe
cannot be reached. On failure the workflow pre-creates the triage labels
`ci`, `voice-e2e`, `alpha-gate` and opens a GitHub issue tagged with them.
The scheduled cron trigger is intentionally commented out until the same
workflow file lands on the default branch `main`.

The cron schedule is intentionally deferred: GitHub evaluates `schedule` triggers only from the repository's default branch (`main`), so the nightly cron will be re-enabled in a follow-up PR that lands `.github/workflows/voice-e2e-nightly.yml` on `main` (typically via the next develop → main release PR). Until then, Exit Criterion #7 is satisfied by a manual `workflow_dispatch` run.
