# Engineer Cafe Navigator

> Voice AI navigator for Engineer Cafe. This monorepo uses `frontend/` for UI and API proxy routes, and `backend/` for the FastAPI + LangGraph runtime.

**English** | **[Japanese](README.md)**

## Current Snapshot

- As of March 14, 2026, the main frontend API routes have largely been converted into backend proxies and recent fixes focused on Web Audio, VRM compatibility, and WebM-to-WAV STT handling.
- The backend test suite currently collects 2,868 tests with `pytest --collect-only -q`.
- The project is not yet production-ready. The biggest gaps are admin/ops route authentication, persistent reception state, and clearer operational guardrails.
- Documentation had drifted badly; this README now serves only as an entry point, while the current audit lives in [docs/STATUS.md](docs/STATUS.md).

## Architecture

```text
Browser
  -> Next.js frontend
     - UI
     - VRM / audio client logic
     - /api/* proxy routes
  -> FastAPI backend
     - LangGraph workflow
     - chat / voice / slides / character endpoints
     - knowledge / reception / STT vocabulary APIs
  -> Supabase / OpenRouter / Google / external calendar services
```

## Main Risks Right Now

- Some frontend admin and monitoring routes are still unauthenticated.
- Backend API-key protection becomes a no-op if `API_SECRET_KEY` is missing in production.
- `backend/api/reception.py` keeps reception session state in memory, which is fragile across restarts and multi-instance deployments.
- Many legacy docs still describe old Mastra-era architecture.

See [docs/STATUS.md](docs/STATUS.md) for the detailed audit.

## Quick Start

### Frontend

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Monorepo

```bash
make dev
```

## Docs

- [docs/STATUS.md](docs/STATUS.md): current implementation status, production gaps, tracked risks
- [docs/README.md](docs/README.md): active docs vs legacy docs
- [frontend/README.md](frontend/README.md): frontend runtime and env notes
- [backend/README.md](backend/README.md): backend runtime and operational cautions
- [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md): current developer flow

## GitHub Status

Items worth watching as of March 14, 2026:

- Issue `#232`: umbrella tracker for the March 14, 2026 production hardening sprint
- Issue `#197`: protect admin / cron / monitoring routes
- Issue `#209`: bubble-overlay response UI for the fullscreen character layout
- Issue `#224`: complete backend-proxy migration cleanup
- Issue `#165`: Reception-2025 integration boundary and shared data usage
- PR `#132`: draft admin authentication middleware
- PR `#215`: new knowledge UI
