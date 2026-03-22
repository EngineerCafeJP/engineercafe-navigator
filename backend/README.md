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
- `GET /api/calendar`
- `POST /api/chat` (also handles OCR/vision when `image_data` is provided)
- `POST /api/chat/stream`
- `POST /api/voice`
- `POST /api/slides`
- `POST /api/character`
- `POST /api/ocr` — member card and handwriting OCR; implemented in `backend/api/ocr.py`
- `POST /api/interrupt`
- `/api/knowledge/*`
- `/api/stt-vocabulary/*`
- `/api/reception/*`

Notable implementation details:

- API-key protection exists, but becomes optional only in local/dev environments without `API_SECRET_KEY`; `staging`, `preview`, and `production` fail closed.
- Rate limiting depends on `slowapi`; without it, the decorators become no-ops.
- Reception session state is currently stored in process memory, not durable storage.
- Agent prompts include oral/conversational style instructions for natural TTS output.
- `clean_text_for_tts` in `utils/text_utils.py` strips Markdown artifacts (headers, bold, lists, links, code blocks) before speech synthesis.
- Recent STT fixes added WebM-to-WAV conversion, which means ffmpeg/runtime availability matters for some environments.
- OrchestratorAgent gates on reception status before LLM routing — sessions with an active reception are handled by the reception workflow first.
- `POST /api/reception/complete` invokes `ainvoke_from_reception()` in the main workflow to generate an agent response using the full visitor context.
- `POST /api/reception/start` accepts an optional `visitor_identity` field for OCR-pre-identified visitors.
- `backend/utils/reception_status.py` provides the reception status checker used by the orchestrator gate.

## Environment

Use the checked-in example files as the first source of truth:

- `backend/.env.example`: local development and shared defaults
- `backend/.env.staging.example`: Cloud Run staging shape
- `backend/.env.production.example`: production-only additions and hardening

The shared backend contract across those examples includes:

- `ENVIRONMENT`, `PORT`, `APP_URL`
- `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY`
- `GOOGLE_CALENDAR_ICAL_URL`, `CONNPASS_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_DB_URI`
- `API_SECRET_KEY`, `ALLOWED_ORIGINS` for non-dev fail-closed deployments
- `TTS_PROVIDER`, `VOICEVOX_API_URL`, `KOKORO_API_URL` for voice runtime selection
- `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `DISCORD_WEBHOOK_URL` when tracing/alerts are enabled

Additional optional Google voice credentials are still code-backed when using Google-powered STT/TTS paths:

- `GOOGLE_CLOUD_PROJECT_ID`
- `GOOGLE_CLOUD_CREDENTIALS`

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
