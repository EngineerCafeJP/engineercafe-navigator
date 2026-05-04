# CLAUDE.md — Frontend

See the root [CLAUDE.md](../CLAUDE.md) for full project context. This file covers frontend-specific guidance only.

## Commands

```bash
pnpm dev              # Dev server at http://localhost:3000
pnpm build            # Production build
pnpm lint             # ESLint
pnpm typecheck        # tsc --noEmit
pnpm test             # Test suite (scripts/tests/run-tests.ts)
pnpm test:e2e         # Playwright E2E tests
pnpm test:e2e:ui      # Playwright with UI
pnpm deploy           # Deploy to Vercel production
pnpm deploy:dev       # Deploy to Vercel dev environment
```

## Frontend-Specific Constraints

- **Tailwind CSS v3.4.17** — DO NOT upgrade to v4. PostCSS: `tailwindcss: {}` not `@tailwindcss/postcss: {}`.
- **Kiosk slides (PDF)**: Bundled `public/reception/engineer-cafe-{ja,en}.pdf` via `ReceptionPdfGuide` + pdfjs (`pnpm build` copies `pdf.worker.min.mjs` to `public/`, gitignored). Static narration audio is served from `public/reception/audio/{ja,en}/`.
- **Audio**: All playback via Web Audio API (`src/lib/audio/`). No HTMLAudioElement.
- **Vercel**: Deployed to the Vercel dev environment with the Node.js runtime configured in `vercel.json`.

## Env Notes

- `frontend/.env.example` is pruned to the manually managed vars still documented for `frontend/src`.
- Keep `BACKEND_API_URL`, `BACKEND_API_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY` populated in local/dev envs.
- Runtime-managed vars such as `NODE_ENV` and `VERCEL_DEPLOYMENT_ID` are intentionally not listed in `.env.example`.
- Additional ad hoc flags still read in `frontend/src` include `NEXT_PUBLIC_SHOW_AVATAR_SETTINGS` and the `FF_*` rollout flags in `src/lib/feature-flags.ts`.

## Key Directories

```
src/app/           Pages (App Router) and API routes
src/app/api/       Route handlers: voice, slides, qa, character, calendar, admin
src/lib/           Shared libs: audio, memory, STT correction, lip-sync
src/lib/audio/     AudioPlaybackService, MobileAudioService, WebAudioPlayer
src/lib/api/       Backend proxy (backendFetch)
e2e/               Playwright E2E tests
public/reception/  Kiosk PDF deck + optional audio/lipsync per page
public/characters/ VRM models and character assets
```
