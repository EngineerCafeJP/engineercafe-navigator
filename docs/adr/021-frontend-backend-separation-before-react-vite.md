# ADR 021: Frontend/backend separation before React/Vite migration

## Status

Accepted, 2026-05-09.

## Context

The current frontend uses Next.js App Router for both the kiosk/admin UI and
server-side route handlers under `frontend/src/app/api`.

The route-handler layer is not just UI plumbing. It currently provides:

- backend API key secrecy
- Vercel-to-Cloud Run proxying
- request/response shape adaptation for `/api/qa`, `/api/voice`,
  `/api/reception/*`, and admin knowledge endpoints
- operational middleware for admin, cron, and monitoring routes
- CSP/security headers
- PDF worker bundling through `next.config.js`

The post-alpha refactoring discussion raised whether replacing Next.js with a
plain React/Vite frontend would significantly reduce code and improve
development velocity.

The inventory found 29 route-handler files under `frontend/src/app/api`, with
about 1797 lines of code. That is the main removable surface. A framework
rewrite alone does not remove it unless the backend first owns authentication,
CORS, rate limits, and public API contracts.

## Decision

Do not start with a Next.js to React/Vite rewrite.

First, separate the browser UI from backend server responsibilities:

1. Define backend auth for browser-origin requests. Candidate designs are
   short-lived kiosk/admin tokens, public read-only endpoints with stricter
   rate limits, or a limited backend-for-frontend boundary kept only where
   secrets must remain server-side.
2. Move `/api/qa` traffic to backend `/api/chat` directly as the first slice.
3. Move `/api/voice` only after STT/TTS timeout and CORS behavior are measured
   without the Vercel proxy.
4. Move admin knowledge endpoints after upload/preview auth and file-size
   limits are explicitly owned by the backend.
5. After `frontend/src/app/api` is mostly gone, measure whether keeping Next as
   a client shell is still useful. If not, migrate to Vite/React as a mechanical
   frontend build-tool change.

## Consequences

- Code reduction is expected from deleting proxy routes, not from changing the
  React renderer.
- The first implementation issue remains #358, but its priority is raised from
  generic P2 cleanup to post-alpha P1-C architecture work.
- Vite remains a good target if the frontend becomes a static SPA, but it must
  not become a replacement for the current server-side secret boundary by
  accident.
- Frontend migration work must not block the P1-A voice latency work.

## Verification

The first PR in this lane should prove:

- `/api/qa` can be replaced by direct backend `/api/chat` calls in development
  and production-like environments.
- Browser CORS, rate limit, auth, and error responses remain explicit.
- Existing voice and admin knowledge flows are unchanged.
- Playwright voice-live and admin knowledge tests still pass.

## Related

- #358: Frontend `/api/qa` proxy retirement / backend `/api/chat` direct call
- ADR 005: Backend-first logic
- ADR 020: Knowledge ingestion mutation contract
