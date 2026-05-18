# Data Flow: `/api/chat`

## Client

- Browser QA submission is centralized in `submitQaQuestion()` at `frontend/src/lib/api/qa-client.ts:176`.
- Proxy mode posts to `/api/qa` through `submitViaProxy()` at `frontend/src/lib/api/qa-client.ts:151`.
- Direct mode can post to backend `/api/chat` via `directChatUrl()` at `frontend/src/lib/api/qa-client.ts:57`, falling back to proxy on auth/network failures.

## API Route

- Next.js receives QA POSTs in `frontend/src/app/api/qa/route.ts:9`.
- The route normalizes `question` / `text` into `query` at `frontend/src/app/api/qa/route.ts:14`.
- It forwards to backend `/api/chat` with `query`, `session_id`, `language`, and `visitor_id` at `frontend/src/app/api/qa/route.ts:22`.
- Shared backend proxy behavior is `frontend/src/lib/api/backend-proxy.ts:58`.

## Backend

- FastAPI handles `/api/chat` at `backend/main.py:770`.
- The endpoint sanitizes input, blocks prompt injection, tries fast general routes, then invokes `_run_workflow_with_tracking()` at `backend/main.py:824`.
- `_run_workflow_with_tracking()` gets the compiled LangGraph and calls `workflow.ainvoke()` at `backend/main.py:459`.
- `MainWorkflow` builds its graph at `backend/workflows/main_workflow.py:701`.
- The graph routes through reception check, keyword router, memory loader, orchestrator, specialist agents, and formatter at `backend/workflows/main_workflow.py:710`.
- The orchestrator node can advance active reception subgraphs before normal routing at `backend/workflows/main_workflow.py:1659`.

## Response

- The backend strips emotion tags, masks PII, attaches language/model metadata, logs `chat_response`, and returns `ChatResponse` at `backend/main.py:839`.
- Successful responses include `answer`, `emotion`, `metadata`, optional `vrm_control`, `requestId`, `phase`, and `upstreamStatus` at `backend/main.py:880`.
- Next.js returns a normalized `{ success, answer, emotion, metadata, vrm_control }` payload at `frontend/src/app/api/qa/route.ts:44`.
- Direct browser mode normalizes backend `ChatResponse` in `frontend/src/lib/api/qa-client.ts:114`.
