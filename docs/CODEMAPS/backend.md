# Backend CODEMAP

Updated: 2026-05-19

## Entry Points

- `backend/main.py:319` creates the FastAPI app and attaches lifecycle startup/shutdown.
- `backend/main.py:363` enforces `X-API-Key` / Bearer auth for protected backend routes.
- `backend/api/chat.py:562` creates `/api/chat`, `/api/chat/stream`, `/api/interrupt`, and `/api/agent/invoke` routes; `backend/main.py:557` mounts them with API-key protection.
- `backend/api/voice.py:748` creates `/api/voice` and `/api/voice/filler` routes; `backend/main.py:558` mounts them with API-key protection.
- `backend/api/calendar.py:38` creates `/api/calendar` routes; `backend/main.py:559` mounts them with API-key protection.
- `backend/main.py:586` mounts `backend/api/reception.py` at `/api/reception/*`.

## Workflow And Agents

- `backend/workflows/main_workflow.py:151` defines `MainWorkflow` and caches specialist agent instances.
- `backend/workflows/main_workflow.py:308` builds the LangGraph graph for reception gate, keyword routing, memory, orchestrator, specialist agents, and response formatting.
- `backend/workflows/main/orchestration.py:239` is the orchestrator node; `backend/workflows/main/routing.py:375` owns the keyword-router node.
- `backend/agents/orchestrator_agent.py:105` owns route selection across business info, facility, event, slide, and general knowledge.
- `backend/agents/event_agent.py:162` searches spreadsheet, Google Calendar ICS, and Connpass in parallel before grounding event answers.

## Voice Stack

- `backend/api/voice.py:343` decodes base64 audio, calls the STT agent for `speech_to_text`, and logs `stt_request_complete`.
- `backend/agents/stt_agent.py:98` selects STT providers and keeps the public `STTAgent` facade.
- `backend/agents/stt/qwen_primary.py:50` implements Qwen-primary plus hedged Vosk fallback winner selection.
- `backend/agents/stt/qwen_client.py:47` defines the Qwen3-ASR client family, including `Qwen06BCpuSTTClient`.
- `backend/agents/stt/local_client.py:47` defines the Vosk fallback client.
- `backend/api/voice.py:634` handles `text_to_speech` and delegates to `VoiceAgent`.
- `backend/agents/voice_agent.py:63` selects the configured TTS provider and fallbacks.
- `backend/agents/voice_agent.py:374` cleans text, applies emotion, checks cache, calls TTS providers, and returns base64 audio.

## Data And Persistence

- `backend/utils/reception_repository.py:54` persists reception sessions and sensor events in Supabase.
- `backend/services/sheets_event_source.py:38` fetches public event rows from the GAS Web App.
- `backend/services/event_kb_sync.py:155` plans event records for `knowledge_base`; `backend/services/event_kb_sync.py:182` upserts live records when not dry-run.
- `backend/knowledge/upload_ingestion.py` owns chunk planning for uploaded knowledge documents.
- `backend/utils/store.py` and `backend/utils/checkpointer.py` back long-term memory and LangGraph persistence.

## Observability

- `backend/observability/structured_logger.py:12` declares structured event names for chat, STT, TTS, routing, frontend telemetry, and voice round trips.
- `backend/api/chat.py:460` emits `chat_response` latency and route metadata for normal chat responses.
- `backend/api/voice.py:464` emits `stt_request_complete` after successful STT requests.
- `backend/agents/voice_agent.py:468` emits `tts_complete` for cached TTS responses; provider paths emit the same event before returning audio.
- `infra/terraform/log_metrics.tf:1` converts structured logs into Cloud Logging metrics.
- `infra/terraform/alerts.tf:1` defines Cloud Monitoring alert policies.
