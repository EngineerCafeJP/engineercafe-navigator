# Developer Guide - Engineer Cafe Navigator

## Quick Start

### Prerequisites
- Node.js 20+ with pnpm
- Python 3.11+ with pip
- Docker (for VoiceVox/Kokoro TTS in local dev)
- Supabase project (PostgreSQL + pgvector)

### Local Development

```bash
# Frontend
cd frontend
cp .env.example .env.local  # Configure environment variables
pnpm install
pnpm dev                     # http://localhost:3000

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# Voice Services (Docker)
docker run -d --name voicevox -p 50021:50021 voicevox/voicevox_engine:latest
docker run -d --name kokoro -p 8880:8880 ghcr.io/remsky/kokoro-fastapi:latest
```

---

## Architecture

```
User Browser
    |
    v
Cloudflare Workers (Frontend: Next.js 15)
    |  Proxy: /api/* -> BACKEND_API_URL
    v
Cloud Run (Backend: FastAPI + LangGraph)
    |
    +-> Supabase PostgreSQL (pgvector, checkpointer, store)
    +-> OpenRouter API (LLM: Gemini, GPT, Claude)
    +-> OpenAI API (Embeddings: text-embedding-3-small)
    +-> VoiceVox Docker (TTS Japanese, local only)
    +-> Kokoro Docker (TTS English, local only)
    +-> Google Cloud (TTS/STT fallback)
    +-> Google Calendar ICS / Connpass API v2
```

### Frontend -> Backend Communication

Frontend API routes proxy requests to the backend:
- `BACKEND_API_URL` env var in `wrangler.jsonc` for production
- `getBackendApiUrl()` in `frontend/src/lib/api/backend-url.ts` resolves the URL
- Falls back to `http://localhost:8000` in local dev

---

## Endpoints Reference

### Backend (FastAPI) - Port 8000

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/chat` | POST | Main AI chat (LangGraph) |
| `/api/voice/tts` | POST | Text-to-Speech |
| `/api/voice/stt` | POST | Speech-to-Text |
| `/api/character` | POST | VRM character control |
| `/api/calendar/events` | GET | Calendar events |
| `/admin/knowledge` | GET/POST | Knowledge base CRUD |

### Frontend (Next.js) - Port 3000

| Endpoint | Method | Description | Backend Proxy |
|----------|--------|-------------|---------------|
| `/api/voice` | POST | Voice processing | Yes -> `/api/voice/*` |
| `/api/marp` | POST | Slide rendering | Yes -> `/api/slides` |
| `/api/slides` | POST | Slide navigation | Yes |
| `/api/character` | POST | Character control | Yes |
| `/api/qa` | POST | Q&A | Yes |
| `/api/backgrounds` | GET | Background images | Local |

### Test URLs

| Environment | URL |
|-------------|-----|
| Local Frontend | http://localhost:3000 |
| Local Backend | http://localhost:8000 |
| Local Backend Docs | http://localhost:8000/docs (Swagger UI) |
| Production Frontend | https://engineer-cafe-navigator.your-domain.workers.dev |
| Production Backend | https://engineer-cafe-backend-639959525777.asia-northeast1.run.app |
| Backend Health | `GET /api/health` |

---

## Environment Variables

### Backend (.env)

```env
# Required
OPENROUTER_API_KEY=          # LLM access (Gemini, GPT, Claude)
SUPABASE_URL=                # Supabase project URL
SUPABASE_KEY=                # Supabase service role key
SUPABASE_DB_URI=             # PostgreSQL connection string (for checkpointer/store)
OPENAI_API_KEY=              # Embeddings (text-embedding-3-small)

# TTS Provider
TTS_PROVIDER=voicevox        # "voicevox" for local & production
VOICEVOX_API_URL=http://localhost:50021  # Local: localhost, Production: Cloud Run VoiceVox service
KOKORO_API_URL=http://localhost:8880     # Local only

# Optional
GOOGLE_CLOUD_PROJECT_ID=     # Google Cloud TTS/STT fallback
GOOGLE_CALENDAR_ICAL_URL=    # Public calendar ICS feed
CONNPASS_API_KEY=            # Connpass API v2
TAVILY_API_KEY=              # Web search
```

### Frontend (.env.local)

```env
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
BACKEND_API_URL=http://localhost:8000  # For local dev
```

### Production (Cloud Run)

Environment variables are set via GCP Secret Manager. Key difference from local:
- `TTS_PROVIDER=voicevox` with `VOICEVOX_API_URL` pointing to VoiceVox Cloud Run service
- `SUPABASE_DB_URI` must be set for checkpointer/store

---

## Agent Architecture

### 7 Workflow Agents (LangGraph nodes)

| Agent | Purpose | Data Source |
|-------|---------|-------------|
| OrchestratorAgent | LLM-based routing | Supervisor Pattern |
| BusinessInfoAgent | Hours, pricing, access | Enhanced RAG |
| FacilityAgent | Equipment, basement, nearby, lost-found | Enhanced RAG |
| EventAgent | Calendar events | Google Calendar + Connpass |
| SlideAgent | Presentations | Marp slides |
| GeneralKnowledgeAgent | Web search, memory | Tavily + RAG |
| FarewellAgent | Departure flow | RAG + templates |

### 3 Support Agents

| Agent | Purpose |
|-------|---------|
| VoiceAgent | TTS (VoiceVox/Kokoro/Google) + STT |
| CharacterControlAgent | VRM avatar expressions |
| OCRAgent | Image/OCR processing |

### Routing Flow

```
User Query
  -> extract_request_type() (keyword matching in routing_constants.py)
  -> CATEGORY_TO_AGENT_MAP (category -> agent name)
  -> main_workflow.py (LangGraph node execution)
  -> format_response (output)
```

---

## Common Development Tasks

### Adding a new routing keyword

1. Add keyword to `backend/config/routing_constants.py` (appropriate `*_KEYWORDS` list)
2. Update `extract_request_type()` if new category
3. Add to `CATEGORY_TO_AGENT_MAP` if new agent mapping
4. Add tests in `backend/tests/config/`

### Adding a new agent

1. Create `backend/agents/new_agent.py` following BusinessInfoAgent pattern
2. Add node in `backend/workflows/main_workflow.py`
3. Add routing in `routing_constants.py`
4. Add tests in `backend/tests/agents/`

### Running Tests

```bash
# Backend
cd backend
pytest                           # All tests
pytest tests/agents/             # Agent tests only
pytest -x --tb=short             # Stop on first failure

# Frontend
cd frontend
pnpm lint                        # Linting
pnpm typecheck                   # TypeScript check
pnpm build                       # Build check
```

### CI Checks (must pass before PR)

```bash
# Backend
cd backend
ruff check .                     # Linting
black --check .                  # Formatting (line-length=100)
pytest                           # Tests

# Frontend
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

---

## Production Issues (2026-03-07) — ALL FIXED (PR #188, 2026-03-08)

See [PRODUCTION-DIAGNOSTIC-REPORT.md](PRODUCTION-DIAGNOSTIC-REPORT.md) for details.

| Issue | Status | Fix |
|-------|--------|-----|
| VoiceVox TTS fails on Cloud Run | FIXED | VoiceVox deployed as separate Cloud Run service |
| Checkpointer TypeError | FIXED | Context manager pattern applied in `checkpointer.py` |
| Marp API 503 | FIXED | Frontend proxies to backend `/api/slides` |
| CI/CD env var overwrite | FIXED | `--set-env-vars` → `--update-env-vars` in ci.yml |
| VRM 0.0 warnings | Cosmetic | Ignore |

---

## Troubleshooting

### "Voice not working"

1. Check `TTS_PROVIDER` env var (`voicevox` for both local and production)
2. Check VoiceVox Docker is running: `curl http://localhost:50021/version`
3. Check Google Cloud credentials if using `google` provider

### "Chat returns internal error"

1. Check `SUPABASE_DB_URI` is set and reachable
2. Check `OPENROUTER_API_KEY` is valid
3. Check Cloud Run logs: `gcloud run services logs read engineer-cafe-backend`

### "Slides not loading"

`/api/marp` proxies to backend `/api/slides`. Check backend health: `curl https://engineer-cafe-backend-639959525777.asia-northeast1.run.app/health`

### Backend Swagger UI

Visit `http://localhost:8000/docs` for interactive API documentation.
