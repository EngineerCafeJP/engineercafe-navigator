# Contributing to Engineer Cafe Navigator

Thanks for your interest in contributing. Engineer Cafe Navigator is the reception system of a free public coworking space operated by **Fukuoka City**, built in the open by the facility's own users (ISC licensed).

This guide links to existing docs rather than duplicating them. If you find contradictions between files, please call them out in your PR description instead of guessing — some docs may be older than the code.

## 1. Getting it running

```bash
make setup     # mise install + deps + Docker build
make dev       # docker-compose up (frontend:3000 + backend:8000)
```

See [README-EN.md](README-EN.md), [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md), and [Makefile](Makefile) for more options.

**External credentials:** a full local run needs external credentials (e.g. Supabase, OpenRouter, Google Cloud STT/TTS). **You do not need them for:**
- Documentation changes (`docs/`, README/CONTRIBUTING edits)
- i18n strings/copy and content updates
- Frontend-only UI/component/styling work that can be developed and reviewed without a working backend
- Backend code changes that you can validate with linting, type checks, and unit tests (`pytest -m "not ragas and not slow" --tb=short -q`) without calling external services

Running the full voice/RAG/calendar/reception flows end-to-end does require the relevant credentials configured (see `.env.example` and deployment/docs for details).

## 2. Checks that must pass before a PR

```bash
cd frontend && pnpm lint && pnpm typecheck && pnpm build
cd backend && ruff check . && black --check .
pytest -m "not ragas and not slow" --tb=short -q
```

Notes:
- Line length is **100** for both `black` and `ruff` (`backend/pyproject.toml`).
- Tailwind CSS is pinned to **v3.4.17** — do not upgrade to v4.

More context: [CLAUDE.md](CLAUDE.md), [docs/DEVELOPER-GUIDE.md](docs/DEVELOPER-GUIDE.md).

## 3. Branch and PR conventions

- Base branch for PRs is **`develop`**, not `main`.
- Branch naming: `feat/<desc>`, `fix/<desc>`, `refactor/<desc>`, `chore/<desc>`, `docs/<desc>`
- Commit format: `<type>(<scope>): <subject>` (Conventional Commits)
- One PR = one intent

## 4. Where things live

- `backend/agents/` — the 12 agents
- `backend/workflows/` — LangGraph graphs
- `frontend/src/app/` — Next.js App Router (pages and API routes/proxies)
- `docs/adr/` — architecture decision records (ADRs)
- `supabase/` — migrations and config

For architecture and current status, start with [docs/README.md](docs/README.md), [docs/STATUS.md](docs/STATUS.md), and [docs/architecture/SYSTEM-ARCHITECTURE.md](docs/architecture/SYSTEM-ARCHITECTURE.md).

## 5. How to pick something to work on

- Look for issues labeled [`good first issue`](https://github.com/EngineerCafeJP/engineercafe-navigator/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
- **Please comment on the issue before starting work** to avoid duplicate effort and to confirm scope/approach with maintainers.

## License

By contributing, you agree that your contributions will be licensed under the [ISC License](LICENSE).
