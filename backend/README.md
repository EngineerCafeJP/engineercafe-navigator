# Backend

FastAPI + LangGraph backend for Engineer Cafe Navigator.

This service is the authoritative runtime for chat, voice, slides, character control, knowledge APIs, and the reception flow. The frontend should be treated as a UI/proxy layer, not as a second AI runtime.

## Current Role

- `backend/main.py`: FastAPI app and core endpoints
- `backend/workflows/`: LangGraph orchestration
- `backend/agents/`: domain agents and support agents
- `backend/api/`: knowledge, reception, STT vocabulary
- `backend/services/`: reception handoff, seat availability, visitor identification, translation
- `backend/tests/`: main automated verification surface

## Runtime Notes

Current important endpoints:

- `GET /health`
- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/voice`
- `POST /api/slides`
- `POST /api/character`
- `POST /api/interrupt`
- `/api/knowledge/*`
- `/api/stt-vocabulary/*`
- `/api/reception/*`

Notable implementation details:

- API-key protection exists, but becomes optional if `API_SECRET_KEY` is missing.
- Rate limiting depends on `slowapi`; without it, the decorators become no-ops.
- Reception session state is currently stored in process memory, not durable storage.
- Recent STT fixes added WebM-to-WAV conversion, which means ffmpeg/runtime availability matters for some environments.

## Environment

The exact contract should be validated against code before deploy, but the main backend-side variables currently include:

- `ENVIRONMENT`
- `API_SECRET_KEY`
- `ALLOWED_ORIGINS`
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_DB_URI`
- `TTS_PROVIDER`
- `VOICEVOX_API_URL`
- `GOOGLE_CLOUD_PROJECT_ID`
- `GOOGLE_CLOUD_CREDENTIALS`
- `GOOGLE_GENERATIVE_AI_API_KEY`

Do not rely on old migration-era docs for env setup. Use [docs/STATUS.md](../docs/STATUS.md) plus the actual code paths.

## Local Run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

As of 2026-03-14:

- `pytest --collect-only -q` collects `2868` tests

Useful commands:

```bash
cd backend
pytest -m "not ragas and not slow and not e2e" --tb=short -q
pytest tests/api -q
pytest tests/services -q
pytest tests/workflows -q
```

## Production Concerns

Before calling the backend production-ready:

- Make `API_SECRET_KEY` mandatory in production
- Make rate limiting mandatory
- Move reception sessions off in-memory storage
- Add deploy-time secret/config validation
- Keep kiosk/browser/device smoke verification in the release flow

See [docs/STATUS.md](../docs/STATUS.md) for the current audit and linked risks.
