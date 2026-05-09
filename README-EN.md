# Engineer Cafe Navigator

> A **production-grade, multilingual voice AI agent** for Engineer Cafe (Fukuoka). Not a thin "AI vtuber" stack around one chat completion: **multi-agent LangGraph, hierarchical RAG, operational gates, and evaluation tooling** behind a client-agnostic HTTP API.

**English** | **[Japanese / 日本語](README.md)**

## Current status

**Source of truth**: [docs/STATUS.md](docs/STATUS.md) (git-sync note **2026-05-05**; live baseline citations may remain **2026-05-03** until workflows re-run).

**Documentation index**: [docs/README.md](docs/README.md) · **Tooling constraints**: [CLAUDE.md](CLAUDE.md)

**OSS / license**: [LICENSE](LICENSE) (ISC) · [docs/OSS-LICENSE-POSTURE.md](docs/OSS-LICENSE-POSTURE.md) · [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)

---

## How this differs from typical avatar / single-agent stacks

| Dimension | Common pattern | Engineer Cafe Navigator |
|-----------|----------------|-------------------------|
| Intelligence placement | Logic bleeds to client or one mega-endpoint | **[Backend-first](docs/adr/005-backend-first-logic.md)** — FastAPI + LangGraph ([ADR index](docs/adr/README.md)) |
| Frontend coupling | Hard to swap UI | Next.js is **UI + proxies**; backend is **HTTP contract** for other shells (Unity, etc.) — ADR 005 |
| Agents | One prompt rules all | **LangGraph supervisor** + **reception subgraph** — [ADR 006](docs/adr/006-langgraph-workflow-redesign.md) |
| Retrieval | Flat vector only | **Enhanced RAG** — hierarchical + parent context (`backend/tools/enhanced_rag.py`), **tRAG** |
| Memory | Session-only | **Short-term** checkpointer / agent memory; **LTM** — [ADR 011](docs/adr/011-ltm-cross-session-design.md), [012](docs/adr/012-ltm-connection-pool-migration.md) |
| Quality | Manual demos | **RAGAS**, `backend/evaluation/`, [ADR 019](docs/adr/019-alpha-live-ragas-case-accounting.md), [STATUS](docs/STATUS.md) |
| Kiosk UX | Ad hoc | **[ADR 018](docs/adr/018-alpha-fast-response-and-assistant-profile-routing.md)** |

Design notes: [docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md](docs/architecture/HIERARCHICAL-RAG-ARCHITECTURE.md)

---

## Architecture (overview)

```text
Browser / Kiosk -> Next.js 15 -> FastAPI (LangGraph, RAG, reception, voice)
  -> Supabase / OpenRouter / external feeds
```

---

## Quick start

```bash
cd frontend && pnpm install && cp .env.example .env.local && pnpm dev
```

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```bash
make dev   # Docker full stack
```

---

## Documentation

| # | Doc |
|---|-----|
| 1 | [docs/STATUS.md](docs/STATUS.md) |
| 2 | [docs/README.md](docs/README.md) |
| 3 | [docs/architecture/SYSTEM-ARCHITECTURE.md](docs/architecture/SYSTEM-ARCHITECTURE.md) |
| 4 | [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md) |
| 5 | [CLAUDE.md](CLAUDE.md) |
| 6 | [frontend/README.md](frontend/README.md), [backend/README.md](backend/README.md) |

Roadmap (docs-only): [docs/plans/comprehensive-refactoring-plan-2026-05-05.md](docs/plans/comprehensive-refactoring-plan-2026-05-05.md)

Legacy: `docs/archive/`. Prefer **STATUS.md** and code.
