# Frontend

Next.js 15 frontend for Engineer Cafe Navigator.

The frontend is primarily responsible for:

- UI rendering
- VRM character presentation
- browser-side audio interaction
- operator/admin screens
- proxying browser requests to the FastAPI backend

It should not be treated as the source of truth for AI workflow logic.

## Current Architecture

Main route groups:

- `src/app/page.tsx`: main kiosk UI
- `src/app/api/voice/route.ts`: proxy to backend voice API
- `src/app/api/qa/route.ts`: proxy to backend chat API
- `src/app/api/slides/route.ts`: proxy to backend slides API
- `src/app/api/character/route.ts`: proxy to backend character API
- `src/app/api/reception/*`: proxy to backend reception API
- `src/app/api/admin/*`: server-side admin endpoints
- `src/app/api/monitoring/*`: server-side monitoring endpoints
- `src/app/api/cron/*`: scheduled or operator-style actions

Recent cleanup removed most direct Mastra-era remnants from active request paths.

## Environment

Actual usage varies by feature, but the important frontend-side variables currently include:

- `BACKEND_API_URL`
- `BACKEND_API_KEY`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `CRON_SECRET`
- `ADMIN_API_SECRET`
- `ALERT_WEBHOOK_SECRET`
- `SLACK_WEBHOOK_URL`

Important caveat:

- `src/lib/env.ts` and `src/lib/env-client.ts` do not yet define a fully authoritative runtime contract.
- Some documented variables are optional in practice.
- Some validation helpers are not wired into startup.

Use [docs/STATUS.md](../docs/STATUS.md) when deciding what is actually required right now.

## Local Run

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

## Commands

```bash
cd frontend
pnpm dev
pnpm lint
pnpm typecheck
pnpm build
pnpm test
pnpm test:e2e
```

## Current Risks

- Admin, cron, and monitoring API routes are protected by `src/middleware.ts`; any new sensitive API prefix must be added to that matcher explicitly.
- Audio behavior still depends on real browser/device validation even after recent fixes.
- Some server routes still talk directly to Supabase, so auth and secret handling need tightening.

The tracked status and GitHub issues are summarized in [docs/STATUS.md](../docs/STATUS.md).
