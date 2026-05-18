# Architecture CODEMAP

Updated: 2026-05-18

## Runtime Shape

The production app is split into a Next.js frontend and a FastAPI backend. Browser requests hit Next.js route handlers first for server-side proxying, auth header attachment, timeout control, and response normalization. The backend owns LangGraph routing, voice providers, event sources, persistence, and structured observability.

## Core Request Paths

- Voice: browser `VoiceInterface` -> `frontend/src/app/api/voice/route.ts:26` -> `backend/main.py:1544` -> STT/TTS agents -> `VoiceResponse`.
- Chat: browser QA client -> `frontend/src/app/api/qa/route.ts:9` -> `backend/main.py:770` -> `MainWorkflow` -> specialist agents -> `ChatResponse`.
- Calendar: browser/admin caller -> `frontend/src/app/api/calendar/route.ts:9` -> `backend/main.py:1527` -> `CalendarService`.
- Reception: kiosk/OCR/M5Stack caller -> `frontend/src/app/api/reception/*` -> `backend/api/reception.py:35` router -> Supabase-backed reception repository.
- Event sheet sync: GAS Web App -> `SheetsEventSource` -> `event_kb_sync` -> `knowledge_base`.

## Graphs And Routing

- Main LangGraph starts at `backend/workflows/main_workflow.py:727` and routes text through reception check, keyword routing, memory loading, orchestrator, agent nodes, and formatter.
- Reception subgraph starts at `backend/workflows/reception_workflow.py:562` and advances one reception stage per invocation.
- Orchestrator routing rules live in `backend/agents/orchestrator_agent.py:113`; fast-path and reception bypass rules are in `backend/workflows/main_workflow.py:1659`.

## Persistence Boundaries

- Supabase stores reception sessions/sensor events through `backend/utils/reception_repository.py:65` and `backend/utils/reception_repository.py:209`.
- Knowledge-base event sync uses `backend/services/event_kb_sync.py:155` for planning and `backend/services/event_kb_sync.py:182` for writes.
- Long-term memory and checkpointer setup happen during FastAPI startup in `backend/main.py:244` and are closed during shutdown in `backend/main.py:286`.

## Observability Boundary

- Application code emits structured events with `backend/observability/structured_logger.py`.
- Terraform maps logs to metrics in `infra/terraform/log_metrics.tf`.
- Terraform alert policies in `infra/terraform/alerts.tf` cover chat fallback, STT failures, p95 latency, TTS failures, memory helper errors, critical API errors, and LTM connection errors.
