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
- **Marp**: `@marp-team/marp-core` is already installed. MarpProcessor at `src/lib/marp-processor.ts`.
- **Audio**: All playback via Web Audio API (`src/lib/audio/`). No HTMLAudioElement.
- **Vercel**: Deployed to the Vercel dev environment with the Node.js runtime configured in `vercel.json`.

## Key Directories

```
src/app/           Pages (App Router) and API routes
src/app/api/       Route handlers: voice, slides, marp, qa, character, admin
src/lib/           Shared libs: audio, memory, STT correction, lip-sync
src/lib/audio/     AudioPlaybackService, MobileAudioService, WebAudioPlayer
src/mastra/        Mastra multi-agent system (being migrated to backend LangGraph)
src/slides/        Marp markdown slides + narration JSON
public/characters/ VRM models and character assets
```
