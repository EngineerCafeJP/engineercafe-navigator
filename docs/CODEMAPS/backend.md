# Backend CODEMAP

Updated: 2026-05-18

## Entry Points

- `backend/main.py:316` creates the FastAPI app and attaches lifecycle startup/shutdown.
- `backend/main.py:360` enforces `X-API-Key` / Bearer auth for protected backend routes.
- `backend/main.py:770` serves `/api/chat` and runs the LangGraph workflow.
- `backend/main.py:1490` serves `/api/voice` metadata GETs.
- `backend/main.py:1544` serves `/api/voice` STT/TTS/interrupt/warmup POSTs.
- `backend/main.py:1527` serves `/api/calendar` from the backend-managed ICS feed.
- `backend/main.py:1973` mounts `backend/api/reception.py` at `/api/reception/*`.

## Workflow And Agents

- `backend/workflows/main_workflow.py:561` builds the main workflow and caches agent instances.
- `backend/workflows/main_workflow.py:701` defines graph nodes for reception gate, memory, orchestrator, specialist agents, and response formatting.
- `backend/workflows/main_workflow.py:1659` is the orchestrator node; it can short-circuit active reception flows before normal routing.
- `backend/agents/orchestrator_agent.py:103` owns route selection across business info, facility, event, slide, and general knowledge.
- `backend/agents/event_agent.py:153` searches spreadsheet, Google Calendar ICS, and Connpass in parallel before grounding event answers.

## Voice Stack

- `backend/main.py:1316` decodes base64 audio and calls the STT agent for `speech_to_text`.
- `backend/agents/stt_agent.py:1534` defines the Qwen3-ASR client.
- `backend/agents/stt_agent.py:1118` defines the Vosk fallback client.
- `backend/main.py:1555` handles `text_to_speech` and delegates to `VoiceAgent`.
- `backend/agents/voice_agent.py:908` selects the configured TTS provider and fallbacks.
- `backend/agents/voice_agent.py:1184` cleans text, applies emotion, checks cache, calls TTS providers, and returns base64 audio.

## Data And Persistence

- `backend/utils/reception_repository.py:54` persists reception sessions and sensor events in Supabase.
- `backend/services/sheets_event_source.py:38` fetches public event rows from the GAS Web App.
- `backend/services/event_kb_sync.py:155` plans event records for `knowledge_base`; `backend/services/event_kb_sync.py:182` upserts live records when not dry-run.
- `backend/knowledge/upload_ingestion.py` owns chunk planning for uploaded knowledge documents.
- `backend/utils/store.py` and `backend/utils/checkpointer.py` back long-term memory and LangGraph persistence.

## Observability

- `backend/observability/structured_logger.py:11` declares structured event names for chat, STT, TTS, routing, frontend telemetry, and voice round trips.
- `backend/main.py:873` emits `chat_response` latency and route metadata.
- `backend/main.py:1436` emits `stt_request_complete` after successful STT requests.
- `backend/agents/voice_agent.py:1369` emits `tts_complete` after successful TTS.
- `infra/terraform/log_metrics.tf:1` converts structured logs into Cloud Logging metrics.
- `infra/terraform/alerts.tf:1` defines Cloud Monitoring alert policies.
