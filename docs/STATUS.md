# Current Status

Last updated: 2026-03-22

## Summary

Engineer Cafe Navigator is in active stabilization after completing Waves 1-3 of production integration.

Confirmed current-state signals:

- All frontend routes proxy to the FastAPI backend via `backendFetch()`.
- Wave 1 (PR #320): OCR frontend connection — `POST /api/ocr` endpoint added.
- Wave 2 (PR #321): Reception workflow integration — orchestrator gates on reception status, Welcome screen, device webhook.
- Wave 3 (PR #322): Bug fixes — TTS, slide rendering, character timeout.
- RAGAS baseline: context_precision 1.000, answer_correctness 0.770, answer_relevancy 0.895, faithfulness 0.871.

Implication:

- Core functionality is complete including OCR, reception flow, and chat.
- Reception flow integrated end-to-end: sensor/button → OCR or voice → reception workflow → main agent.
- Remaining gaps are operational (auth hardening, durable sessions, device testing).

## Current Architecture

### Frontend

- Next.js 15 App Router
- UI, VRM, audio interaction, admin UI
- `/api/*` routes act as backend proxies (voice, qa, slides, character, reception, ocr)
- OCR route (`/api/ocr`) proxies image data to backend chat with vision capabilities

### Backend

- FastAPI entrypoint in `backend/main.py`
- LangGraph workflow for chat and domain routing
- Dedicated APIs for chat, voice, slides, character, knowledge, STT vocabulary, reception, and OCR
- OrchestratorAgent gates on reception status before LLM routing
- Agent prompts include oral/conversational style for natural TTS output
- `clean_text_for_tts` strips Markdown and HTML before speech synthesis
- Supabase-backed data and external integrations

### Current GitHub context

Open issues / PRs that materially affect delivery:

- Issue `#301`: QA oral style improvements (merged via PR #313)
- Issue `#315`: Slide cascade fix (merged via PR #318)
- Issue `#314`: OCR frontend orchestration (merged via PR #320)
- Issue `#165`: Reception-2025 integration boundary and shared data usage
- Issue `#138`: Multi-language improvements (English OK, Korean/Chinese need work)
- Issue `#117`: Autonomous reception flow integration
- Issue `#128`: Non-camera visitor detection research
- Issue `#113`: Event participation / hosting flow guidance
- Issue `#114`: Feedback collection

## Confirmed Risks

### 1. Admin and ops routes are still exposed

Confirmed in code:

- [frontend/src/app/api/admin/knowledge/route.ts](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/app/api/admin/knowledge/route.ts#L1) performs knowledge-base reads and writes with no auth check.
- [frontend/src/app/api/cron/update-slides/route.ts](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/app/api/cron/update-slides/route.ts#L1) allows unauthenticated slide import execution.
- [frontend/src/app/api/alerts/webhook/route.ts](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/app/api/alerts/webhook/route.ts#L165) exposes recent alert retrieval via `GET` without auth.
- There is no `frontend/src/middleware.ts` in the repository as of 2026-03-14.

Risk:

- Unauthorized data access
- Unauthorized operational actions
- Monitoring leakage

Required before production:

- Route-level auth for admin, monitoring, alerts, and cron
- Clear split between public proxy routes and operator-only routes
- Tests for unauthorized access paths

### 2. Backend protection is optional if a secret is missing

Confirmed in code:

- [backend/main.py](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/main.py#L205) treats API key verification as optional.
- [backend/main.py](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/main.py#L208) only logs a warning if `API_SECRET_KEY` is missing in production.
- [backend/main.py](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/main.py#L214) returns early from auth when no secret is set.

Risk:

- A misconfigured production deploy can expose backend write-capable endpoints.

Required before production:

- Fail startup when `ENVIRONMENT=production` and `API_SECRET_KEY` is absent
- Document secret ownership and rotation
- Add deployment validation

### 3. Reception state is not durable

Confirmed in code:

- [backend/api/reception.py](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/api/reception.py#L54) stores active reception sessions in a process-local `OrderedDict`.

Risk:

- Session loss on restart
- Inconsistent state across multiple instances
- Weak observability and no recovery path

Required before production:

- Use the reception repository abstraction for durable storage
- Add cleanup / expiry semantics at the persistence layer
- Add multi-instance or restart recovery tests

### 4. Env validation exists but is not authoritative

Confirmed in code:

- [frontend/src/lib/env.ts](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/lib/env.ts#L1) still requires several vars that recent proxy cleanup has made optional.
- The validation helpers are not used by the runtime.

Risk:

- Docs and code disagree on required configuration
- False confidence from unused validation helpers

Required before production:

- Choose one env contract per service
- Enforce it at startup or build time
- Remove or rewrite unused validation layers

### 5. Rate limiting is soft, not guaranteed

Confirmed in code:

- [backend/main.py](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/main.py#L188) makes rate limiting a no-op when `slowapi` is unavailable.

Risk:

- Accidental unbounded exposure in production
- No explicit guarantee that abuse controls exist in every deploy

Required before production:

- Make rate limiting mandatory
- Document infra-level throttling
- Add deploy-time verification

### 6. Recent fixes still need manual device validation

Recent merged PRs:

- `#223` frontend hardening
- `#225` proxy unification
- `#226` Mastra-remnant cleanup
- `#227` env cleanup
- `#229` WebM-to-WAV conversion for Vosk
- `#231` test fix for closing-time warnings

Risk:

- Browser and tablet behavior can still regress even when CI is green
- Audio and VRM fixes are especially prone to environment-specific failures

Required before production:

- Repeatable smoke tests for kiosk browsers and tablets
- Device matrix with pass/fail history
- Post-deploy canary checks

### 7. Some frontend feature-discovery paths are inconsistent with backend behavior

Confirmed in code review:

- `LanguageSelector` requests `GET /api/voice?action=supported_languages`, but the backend currently implements `POST /api/voice` only.
- `CharacterAvatar` expects `GET /api/character?action=supported_features`, while the Next.js route returns a stub health payload.
- STT vocabulary admin calls still have paths that bypass the normal server-proxy pattern.

Risk:

- Silent fallback behavior in the UI
- Broken admin surfaces when backend auth is enabled
- Integration regressions that basic smoke coverage does not catch

Required before production:

- Align UI capability discovery with actual backend routes
- Move remaining browser-direct backend calls behind authenticated server routes
- Expand frontend E2E coverage beyond the current thin proxy smoke layer

## Production Readiness Gaps

The minimum additional work to call this production-ready is:

1. Authentication and authorization
2. Durable reception/session persistence
3. Mandatory secret validation and rate limiting
4. Operator runbooks for cron, alerts, and knowledge import
5. Browser/device smoke coverage for audio, VRM, and slides
6. Documentation cleanup so active docs are clearly separated from legacy docs

## Documentation State

### Updated in this pass

- [../README.md](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/README.md)
- [../README-EN.md](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/README-EN.md)
- [README.md](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/README.md)
- [plans/production-hardening-session-2026-03-14.md](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/plans/production-hardening-session-2026-03-14.md)
- [../frontend/README.md](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/README.md)
- [../backend/README.md](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/README.md)
- [archive/README.md](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/archive/README.md)

### Legacy docs still needing explicit refresh or archive decisions

- `docs/api/`
- `docs/architecture/`
- `docs/DEPLOYMENT.md`
- `docs/SECURITY.md`
- `docs/development/`
- Some API and testing docs that still mention Mastra-era behavior

### Removed duplication

- Deleted duplicate file `docs/spaces/spaces/basement-spaces.md`

## Recommended Next Workstream

1. Close Issue `#197` or merge/finish PR `#132`
2. Persist reception sessions through the repository layer
3. Rewrite env and deployment docs from actual runtime contracts
4. Refresh API, architecture, security, and deployment docs to remove deprecated agent descriptions and Vercel-era assumptions
5. Add operator-facing production checklist and smoke test checklist
6. Use umbrella Issue `#232` as the execution tracker for the next hardening session
