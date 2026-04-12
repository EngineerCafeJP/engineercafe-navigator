# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Engineer Cafe Navigator — a multilingual voice AI agent system for Fukuoka Engineer Cafe. Monorepo with a Next.js frontend and a Python/LangGraph backend.

## Development Commands

### Frontend (Next.js) — runs from `frontend/`

```bash
cd frontend
pnpm dev              # Dev server at http://localhost:3000
pnpm build            # Production build
pnpm lint             # ESLint
pnpm typecheck        # TypeScript type checking (tsc --noEmit)
pnpm test             # Run test suite
pnpm test:e2e         # Playwright E2E tests
```

### Backend (FastAPI/LangGraph) — runs from `backend/`

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000  # Dev server
pytest -m "not ragas and not slow" --tb=short -q                  # Unit tests (fast)
pytest                                                             # All tests
ruff check .                                                       # Linting
black --check .                                                    # Format check
black .                                                            # Auto-format
```

### Docker (full stack)

```bash
make dev              # docker-compose up (frontend:3000 + backend:8000)
make setup            # Initial setup (mise install + deps + Docker build)
make lint             # Lint both frontend and backend
make test:backend     # Backend tests excluding slow/ragas markers
```

### Specific Agent Testing

```bash
make test-agent AGENT=business_info QUERY='営業時間は？'
make debug-agent                    # Interactive agent debugger
```

## Architecture

### Monorepo Structure

```
frontend/          Next.js 15 (App Router) + React 19 + TypeScript
  src/app/         Pages and API routes
  src/app/api/     API route handlers (voice, slides, marp, qa, character, calendar, admin)
  src/lib/         Shared libraries (audio, memory, STT correction, lip-sync)
  e2e/             Playwright E2E tests

backend/           FastAPI + LangGraph + Python 3.11+
  main.py          FastAPI application entry point
  agents/          Agent implementations (12 agents)
  workflows/       LangGraph workflow definitions (main_workflow, reception_workflow)
  tools/           Shared tools (calendar_service, enhanced_rag, tavily_search)
  config/          Routing constants, prompt templates
  utils/           Input sanitizer, custom exceptions
  tests/           pytest test suite
  evaluation/      RAGAS evaluation scripts

supabase/          Database migrations and config
```

### AI Agent Architecture

The backend uses **LangGraph** with a Supervisor Pattern:

- **OrchestratorAgent** controls 12 specialized agents
- Agents: BusinessInfoAgent, FacilityAgent, EventAgent, GeneralKnowledgeAgent, CharacterControlAgent, SlideAgent, STTAgent, VoiceAgent, OCRAgent, FarewellAgent, plus agent_tools
- LLM: OpenRouter (Gemini) via LangChain
- RAG: EnhancedRAGSearch with Supabase RPC `search_knowledge_base()` + Tavily web search fallback
- Embeddings: OpenRouter API (`openai/text-embedding-3-small`, 1536 dimensions)

**Reception subgraph (Wave 7, PR #390)**: Reception handling is a first-class LangGraph subgraph. The three previously separate implementations (main_workflow.py inline handlers, reception_workflow.py standalone, api/reception.py) are unified. `reception_workflow.py` is invoked via `invoke_reception_subgraph()` with explicit state conversion functions. `api/reception.py` uses a singleton workflow instance (protected by `asyncio.Lock`). `consultation` routes to `general_knowledge` (not `business_info`).

**Multilingual RAG — tRAG pattern (Wave 7, PR #389)**: The knowledge base is Japanese-only. For English queries, tRAG translates to Japanese before embedding lookup and sets `language="ja"` on the RAG call. Chinese and Korean queries skip translation and use cross-lingual embeddings directly. `text_fallback_search` always filters by `"ja"`. Entity labels and advice templates support en/zh/ko. RAGAS targets: ja >= 0.85, en >= 0.75, zh/ko >= 0.65 (answer_correctness).

The frontend is a **pure UI layer** — all AI processing is proxied to the backend via `backendFetch()`.

### Key Data Flow

- Voice: Browser → `/api/voice` (FE proxy) → Backend STT/TTS → Browser
- Q&A: Browser → `/api/qa` (FE proxy) → Backend `/api/chat` → LangGraph → RAG/Web search → Response
- Reception: Browser → `/api/reception/*` (FE proxy) → Backend → `invoke_reception_subgraph()` → LangGraph reception subgraph → Response
- Calendar: Browser → `/api/calendar` (FE proxy) → Backend `/api/calendar` → Google Calendar ICS
- Slides: Marp markdown in `frontend/src/slides/` → `/api/marp` renders HTML → MarpViewer component

### Database

PostgreSQL (Supabase) with pgvector. Key tables:
- `knowledge_base`: RAG entries with 1536-dim embeddings (OpenRouter via text-embedding-3-small)
- `conversation_sessions` / `conversation_history`: Chat state
- `agent_memory`: Short-term memory with 3-minute TTL
- `reception_sessions` / `visits`: Reception flow state
- RLS enabled on all tables; use service role key for server-side access

### External Services

- **Google Cloud**: STT, TTS (needs service account at `config/service-account-key.json`)
- **OpenRouter**: LLM provider (Gemini) + embeddings (text-embedding-3-small, 1536d)
- **Supabase**: PostgreSQL + pgvector + auth
- **Tavily**: Web search fallback for GeneralKnowledgeAgent
- **Google Calendar**: ICS feed for event data (backend managed via `GOOGLE_CALENDAR_ICAL_URL`)

## Critical Constraints

- **`/api/marp` (FE) ≠ `/api/slides` (BE)**: Marp = markdown→HTML rendering. Slides = narration/navigation. Different purposes entirely.
- **Embeddings**: Always 1536 dimensions, always `openai/text-embedding-3-small` via OpenRouter API. No mixing.
- **Alpha UI/E2E gating**: `.github/workflows/voice-e2e-nightly.yml` runs the browser voice round-trip against the live Cloud Run backend via `workflow_dispatch` (nightly cron to be re-enabled after the workflow file lands on the default branch `main`). Do not delete or weaken this workflow without updating `docs/plans/alpha-ui-e2e-hardening-2026-04-12.md`.

<important if="you are modifying frontend code (TypeScript, React, Next.js, CSS)">
- **Tailwind CSS v3.4.17** — DO NOT upgrade to v4. PostCSS config uses `tailwindcss: {}`, not `@tailwindcss/postcss: {}`.
- CI: `cd frontend && pnpm lint && pnpm typecheck && pnpm build`
</important>

<important if="you are modifying backend Python code">
- **Black/Ruff line-length: 100** (configured in `pyproject.toml`).
- **pytest markers**: `ragas`, `e2e`, `integration`, `slow`, `vision`, `perf`, `adversarial` — use `-m` to filter.
- CI: `cd backend && ruff check . && black --check .`
- **CI env**: `SUPABASE_DB_URI=postgresql://test:test@localhost:0/test` causes real connection attempts in CI.
</important>

<important if="you are deploying, building Docker images, or modifying CI/CD">
- **Docker on Apple Silicon**: Use `--platform linux/amd64` when building for Cloud Run (GCP).
- **Frontend**: Vercel (`pnpm deploy` or auto-deploy on develop push)
- **Backend**: Cloud Run `engineer-cafe-backend` in `asia-northeast1` (GCP project: `aipartner-426616`)
- **VoiceVox**: Separate Cloud Run `voicevox-proto` in `asia-northeast2`
- **Cloud Run env vars**: Use `--update-env-vars` (NOT `--set-env-vars` which overwrites ALL vars)
</important>

<important if="you are creating or modifying API endpoints">
- ALWAYS trace full data flow: client → API route → backend → response
- 4つ全て一致しなければ「修正」ではない
- `/api/marp` (FE) ≠ `/api/slides` (BE) — different purposes entirely
</important>

<important if="you are touching browser-level voice E2E tests, `frontend/e2e/voice-live.spec.ts`, or `.github/workflows/voice-e2e-nightly.yml`">
- `frontend/e2e/fixtures/voice/sample.wav` is a deterministic fixture committed as binary. Never regenerate in CI; run `frontend/e2e/fixtures/voice/generate.sh` locally on intentional change and update the sha256 in the README.
- `PLAYWRIGHT_VOICE_LIVE=1` is required for the spec to run; without it the test is `test.skip`-ed and the existing `frontend-playwright-e2e` PR job is unaffected.
- Nightly workflow uses `BACKEND_API_KEY` synced from GCP Secret Manager (`API_SECRET_KEY`) via `gcloud | gh secret set`.
</important>

<important if="you are working with database, embeddings, or Supabase">
- PostgreSQL (Supabase) with pgvector — RLS enabled on all tables
- Embeddings: Always 1536 dimensions, always OpenAI text-embedding-3-small
- Use service role key for server-side access
</important>

## CI Checks (must pass before merge)

```bash
# Frontend
cd frontend && pnpm lint && pnpm typecheck && pnpm build

# Backend
cd backend && ruff check . && black --check .
```

## Skill Usage Guide

### Think → Plan phase (gstack)
- `/office-hours` — YC-style product discovery (before writing code)
- `/plan-ceo-review` — CEO/founder scope validation (4 modes: Expansion/Hold/Reduction)
- `/plan-eng-review` — Architecture locking with diagrams + test matrices
- `/plan-design-review` — Design quality audit (0-10 rating per dimension)
- `/retro` — Team-aware weekly retrospective

### Build → Review → Ship phase (existing skills + hooks)
- Use existing `code-reviewer`, `review-loop`, `e2e`, `bugfix` skills
- Use existing hook system for CI/CD quality gates (PR merge blocks, review requirements)
- Do NOT use gstack's `/review`, `/ship` for this project — existing hooks are stricter
