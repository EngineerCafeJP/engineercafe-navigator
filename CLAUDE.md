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
  src/app/api/     API route handlers (voice, slides, marp, qa, character, etc.)
  src/lib/         Shared libraries (audio, memory, STT correction, lip-sync)
  src/mastra/      Mastra multi-agent system (frontend AI layer — being migrated)

backend/           FastAPI + LangGraph + Python 3.11+
  main.py          FastAPI application entry point
  agents/          Agent implementations (13 agents)
  workflows/       LangGraph workflow definitions (main_workflow, reception_workflow)
  config/          Routing constants, prompt templates
  utils/           Input sanitizer, custom exceptions
  tests/           pytest test suite
  evaluation/      LangSmith evaluation scripts

supabase/          Database migrations and config
```

### Dual AI Layer (Migration in Progress)

The project has **two AI agent layers** — this is the most important architectural detail:

1. **Frontend Mastra agents** (`frontend/src/mastra/`): Original implementation with 8 specialized agents (Router, BusinessInfo, Facility, Memory, Event, GeneralKnowledge, Clarification). Uses Gemini for responses, OpenAI for embeddings.

2. **Backend LangGraph agents** (`backend/agents/`): New implementation using Supervisor Pattern with OrchestratorAgent controlling 13 agents. Uses OpenRouter (Gemini) via LangChain.

**Migration direction**: Frontend Mastra → Backend LangGraph. Frontend is being "thinned" to become a pure UI layer. Both systems are currently active.

### Key Data Flow

- Voice: Browser → `/api/voice` (FE route) → Google Cloud STT → AI Agent → Google Cloud TTS → Browser
- Q&A: Browser → `/api/qa` (FE route) → Mastra agents → Supabase RAG → Response
- Slides: Marp markdown in `frontend/src/slides/` → `/api/marp` renders HTML → MarpViewer component
- Backend API: Frontend → `http://localhost:8000/api/...` → FastAPI → LangGraph workflow

### Database

PostgreSQL (Supabase) with pgvector. Key tables:
- `knowledge_base`: RAG entries with 1536-dim OpenAI embeddings
- `conversation_sessions` / `conversation_history`: Chat state
- `agent_memory`: Short-term memory with 3-minute TTL
- RLS enabled on all tables; use service role key for server-side access

### External Services

- **Google Cloud**: STT, TTS, Gemini AI (needs service account at `config/service-account-key.json`)
- **OpenAI**: text-embedding-3-small for vector embeddings (1536 dimensions)
- **Supabase**: PostgreSQL + pgvector + auth
- **OpenRouter**: LLM provider for backend agents
- **Connpass API / Google Calendar**: Event data sources

## Critical Constraints

- **Tailwind CSS v3.4.17** — DO NOT upgrade to v4. PostCSS config uses `tailwindcss: {}`, not `@tailwindcss/postcss: {}`.
- **Black/Ruff line-length: 100** (configured in `pyproject.toml`).
- **pytest markers**: `ragas`, `e2e`, `integration`, `slow`, `vision`, `perf`, `adversarial` — use `-m` to filter.
- **`/api/marp` (FE) ≠ `/api/slides` (BE)**: Marp = markdown→HTML rendering. Slides = narration/navigation. Different purposes entirely.
- **Embeddings**: Always 1536 dimensions, always OpenAI text-embedding-3-small. No mixing.
- **Docker on Apple Silicon**: Use `--platform linux/amd64` when building for Cloud Run (GCP).
- **CI env**: `SUPABASE_DB_URI=postgresql://test:test@localhost:0/test` causes real connection attempts in CI.

## Deployment

- **Frontend**: Cloudflare Workers via `opennextjs-cloudflare` (`pnpm deploy`)
- **Backend**: Cloud Run `engineer-cafe-backend` in `asia-northeast1` (GCP project: `aipartner-426616`)
- **VoiceVox**: Separate Cloud Run `voicevox-proto` in `asia-northeast2`
- **Cloud Run env vars**: Use `--update-env-vars` (NOT `--set-env-vars` which overwrites ALL vars)

## CI Checks (must pass before merge)

```bash
# Frontend
cd frontend && pnpm lint && pnpm typecheck && pnpm build

# Backend
cd backend && ruff check . && black --check .
```
