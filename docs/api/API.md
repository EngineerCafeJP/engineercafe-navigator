# API Documentation - Engineer Cafe Navigator

[日本語版](./API-ja.md) | English

Updated for the current Vercel + Cloud Run deployment.

## Overview

Engineer Cafe Navigator uses a two-tier API architecture:

- Public clients usually call the frontend routes at `https://frontend-delta-six-20.vercel.app/api`.
- Those frontend `/api/*` routes proxy to the FastAPI backend and attach `X-API-Key` automatically via `BACKEND_API_KEY`.
- Admin, cron, and monitoring routes are protected at the frontend edge with `Authorization: Bearer <ADMIN_API_SECRET>`.
- Core backend application routes such as `/api/chat` are not meant to be called directly from browsers.

## Base URLs

```text
Frontend production: https://frontend-delta-six-20.vercel.app/api
Frontend local:      http://localhost:3000/api
Backend local:       http://localhost:8000
```

## Authentication

| Surface | Auth |
| --- | --- |
| Public frontend proxy routes | No client-side secret required |
| Direct backend application routes | `X-API-Key: <API_SECRET_KEY>` |
| Frontend admin, cron, monitoring routes | `Authorization: Bearer <ADMIN_API_SECRET>` |

Notes:

- `BACKEND_API_KEY` is a server-side secret used by the Next.js frontend when proxying requests to the backend.
- `ADMIN_API_SECRET` is enforced by frontend middleware on `/api/admin/*`, `/api/cron/*`, and `/api/monitoring/*`.
- The backend also restricts CORS to `https://frontend-delta-six-20.vercel.app` plus local development origins.

## Architecture Note

Frontend `/api/*` routes are not the backend itself. They are a proxy and integration layer:

- `/api/voice`, `/api/qa`, `/api/slides`, `/api/character`, `/api/ocr`, and `/api/reception/*` forward requests to backend routes.
- `/api/marp` is a frontend-only render endpoint. It fetches backend slide markdown from `/api/slides/content`, then renders it with `MarpProcessor`.
- Admin routes under `/api/admin/*` are edge-protected frontend routes. Some proxy to backend APIs, and some use frontend-side admin utilities directly.

## Frontend API

### POST /api/voice

Frontend proxy for backend `POST /api/voice`.

Typical request:

```json
{
  "action": "speech_to_text",
  "audioData": "base64-encoded-audio",
  "sessionId": "session-123",
  "language": "ja"
}
```

Supported actions in the current backend:

- `speech_to_text`
- `text_to_speech`
- `set_language`
- `interrupt`

Typical response:

```json
{
  "success": true,
  "transcript": "エンジニアカフェについて教えてください",
  "audioResponse": "base64-audio",
  "emotion": "neutral",
  "sessionId": "session-123"
}
```

### GET /api/backgrounds

Returns image filenames from the frontend backgrounds manifest.

Example response:

```json
{
  "images": ["IMG_5573.JPG", "placeholder.svg"],
  "total": 2
}
```

### POST /api/marp

Frontend-only Marp render endpoint.

Current flow:

1. Accepts `{ "language": "ja" }` or `{ "language": "en" }`
2. Calls backend `POST /api/slides/content`
3. Processes returned markdown with `MarpProcessor`
4. Returns rendered HTML, parsed slide data, and narration data

Example request:

```json
{
  "language": "ja"
}
```

Example response:

```json
{
  "success": true,
  "html": "<!DOCTYPE html><html>...</html>",
  "slideData": {
    "slides": [
      {
        "slideNumber": 1,
        "title": "Engineer Cafe"
      }
    ]
  },
  "narrationData": {
    "metadata": {
      "title": "Engineer Cafe"
    }
  },
  "slideCount": 12,
  "metadata": {
    "language": "ja",
    "title": "Engineer Cafe"
  }
}
```

`GET /api/marp` returns a simple status payload:

```json
{
  "status": "ok",
  "backend": "connected"
}
```

### POST /api/slides

Frontend proxy for backend `POST /api/slides`.

This route is for slide navigation, narration, and slide-specific questions. It is not the Marp render path.

Supported actions in the current backend:

- `narrate`
- `narrate_current` (alias of `narrate`)
- `next`
- `previous`
- `goto`
- `question`
- `answer_question` (alias of `question`)

Example request:

```json
{
  "action": "next",
  "slideNumber": 2,
  "language": "ja",
  "sessionId": "session-123"
}
```

Example response:

```json
{
  "success": true,
  "answer": "次のスライドでは施設をご案内します。",
  "emotion": "neutral",
  "slideNumber": 3,
  "metadata": {
    "language": "ja"
  }
}
```

### POST /api/qa

Frontend proxy for backend `POST /api/chat`.

Important behavior:

- The frontend accepts `question` or `text`.
- It forwards that value to the backend as `query`.
- The historical `ask_question` description is stale. The backend route it actually uses is `/api/chat`.

Example request:

```json
{
  "question": "What are the opening hours?",
  "sessionId": "session-123",
  "language": "en",
  "visitorId": "visitor-123"
}
```

Forwarded backend payload:

```json
{
  "query": "What are the opening hours?",
  "session_id": "session-123",
  "language": "en",
  "visitor_id": "visitor-123"
}
```

Example response:

```json
{
  "success": true,
  "answer": "Engineer Cafe is open during its published business hours.",
  "emotion": "neutral",
  "metadata": {
    "session_id": "session-123"
  }
}
```

`GET /api/qa` supports frontend helper actions:

- `action=question_categories`
- `action=sample_questions&language=ja|en`
- `action=health`

### POST /api/ocr

Frontend proxy for backend `POST /api/chat` with image data.

This route accepts an image and optional query, then forwards it to the backend chat endpoint with `image_data` for OCR/vision processing.

Example request:

```json
{
  "image_data": "base64-encoded-image",
  "query": "Analyze this image",
  "session_id": "session-123",
  "language": "en"
}
```

Example response:

```json
{
  "success": true,
  "answer": "The image shows a business card with ...",
  "emotion": "neutral",
  "metadata": {
    "session_id": "session-123"
  }
}
```

Note: The frontend validates that `image_data` is present before proxying. The backend processes the image through its existing chat pipeline with vision capabilities.

### POST /api/character

Frontend proxy for backend `POST /api/character`.

Example request:

```json
{
  "action": "setExpression",
  "emotion": "happy",
  "animation": "greeting"
}
```

Example response:

```json
{
  "success": true,
  "message": "{\"emotion\":\"happy\"}"
}
```

`GET /api/character` currently returns a simple frontend status payload:

```json
{
  "status": "ok"
}
```

## Backend API

These are the main FastAPI routes behind the frontend proxies.

### POST /api/chat

Main LangGraph chat endpoint.

- Requires `X-API-Key`
- Request body uses `query`, `session_id`, `language`, optional `context`, and optional `visitor_id`
- Returns `answer`, `emotion`, `metadata`, and optional `vrm_control`

Example request:

```http
POST /api/chat
X-API-Key: your-api-secret
Content-Type: application/json
```

```json
{
  "query": "Tell me about Engineer Cafe",
  "session_id": "session-123",
  "language": "en"
}
```

### POST /api/chat/stream

SSE version of the chat endpoint.

- Requires `X-API-Key`
- Uses the same request schema as `/api/chat`
- Returns `text/event-stream`

### POST /api/agent/invoke

Direct LangGraph invocation endpoint.

- Requires `X-API-Key`
- Uses the same request schema as `/api/chat`
- Returns `{ "status": "success", "result": ... }`

### POST /api/interrupt

Interrupt endpoint for active sessions.

- Requires `X-API-Key`
- Request body:

```json
{
  "session_id": "session-123"
}
```

### GET /health

Backend health endpoint.

- Returns backend service and dependency health information
- Used for operational health checks
- Current implementation does not attach the same `X-API-Key` dependency used by `/api/chat`

Example response:

```json
{
  "status": "ok",
  "service": "engineer-cafe-navigator-backend",
  "checks": {
    "api": "ok",
    "supabase": "ok",
    "llm_provider": "configured"
  }
}
```

### Internal slide content helper

`POST /api/slides/content` is an internal backend helper used by frontend `/api/marp`.

- Request body: `{ "language": "ja" }`
- Returns raw markdown plus narration data
- It is not the public Marp render endpoint

## Admin API

All frontend admin routes live under `/api/admin/*` and require:

```http
Authorization: Bearer <ADMIN_API_SECRET>
```

### /api/admin/knowledge

Supported methods:

- `GET`: list knowledge entries
- `POST`: create a knowledge entry

Current behavior:

- Proxies to backend `/api/knowledge`
- The frontend normalizes `search` to `keyword` on list requests

### /api/admin/knowledge/[id]

Supported methods:

- `GET`: fetch a single knowledge entry
- `PUT`: update a knowledge entry
- `DELETE`: delete a knowledge entry

This is an edge-protected frontend admin route for single-entry CRUD.

### /api/admin/knowledge/categories

Supported methods:

- `GET`: fetch category, subcategory, source, and language metadata

### /api/admin/stt

Supported methods:

- `GET`: list vocabulary entries or fetch one item with `?id=...`
- `POST`: create a vocabulary entry
- `PUT`: update a vocabulary entry using `?id=...`
- `DELETE`: delete a vocabulary entry using `?id=...`

Current behavior:

- Proxies to backend `/api/stt/vocabulary`
- Validates `id` format before proxying single-item requests

## OCR API

### POST /api/ocr

Frontend proxy for backend `POST /api/ocr`. Identifies visitors via camera image.

Supported modes:

- `member_card` — scan a membership card barcode or ID
- `handwriting` — extract handwritten text from a form

Example request:

```json
{
  "mode": "member_card",
  "imageData": "base64-encoded-image",
  "sessionId": "session-123"
}
```

Example response:

```json
{
  "success": true,
  "visitorIdentity": {
    "memberId": "M-12345",
    "name": "Taro Engineer"
  },
  "rawText": "M-12345 Taro Engineer",
  "sessionId": "session-123"
}
```

Rate limiting applies. Returns `429 Too Many Requests` when the limit is exceeded.

The OCR backend is implemented in `backend/api/ocr.py` and delegates to OCRAgent for processing.

## Reception API

Frontend reception routes proxy to backend `/api/reception/*`.

### POST /api/reception/start

Starts a reception session. Accepts an optional `visitor_identity` field for pre-identified visitors (e.g. via OCR).

Example request:

```json
{
  "session_id": "session-123",
  "language": "ja",
  "trigger_type": "button_press",
  "visitor_identity": {
    "memberId": "M-12345",
    "name": "Taro Engineer"
  }
}
```

`visitor_identity` is optional. Omit it when identity has not been established before reception starts.

### POST /api/reception/respond

Continues the reception conversation.

Example request:

```json
{
  "session_id": "session-123",
  "reception_session_id": "reception-123",
  "message": "I am here for a tour."
}
```

### POST /api/reception/complete

Completes reception and invokes the main workflow via `ainvoke_from_reception()`. The backend generates an agent response using the full visitor context collected during reception.

Example request:

```json
{
  "session_id": "session-123",
  "reception_session_id": "reception-123"
}
```

### GET /api/reception/status/[id]

Returns current reception state.

Optional query parameter:

- `session_id`

Example response:

```json
{
  "session_id": "session-123",
  "stage": "routing",
  "visitor_type": "new",
  "purpose": "tour"
}
```

## Monitoring And Scheduled Routes

### /api/monitoring/dashboard

- `GET`
- Requires `Authorization: Bearer <ADMIN_API_SECRET>`
- Returns frontend-side operational metrics

### /api/monitoring/migration-success

- `GET`
- Requires `Authorization: Bearer <ADMIN_API_SECRET>`
- Returns migration dashboard data

### /api/cron/update-knowledge-base

- `POST`
- Requires `Authorization: Bearer <ADMIN_API_SECRET>`

### /api/cron/update-slides

- `POST`
- Requires `Authorization: Bearer <ADMIN_API_SECRET>`

## Embeddings

Current canonical embedding setup:

- Model: `text-embedding-3-small`
- Provider path used by the backend embedding service: `openai/text-embedding-3-small`
- Dimensions: `1536`

When documenting RAG, admin knowledge ingestion, or backend search behavior, treat OpenAI `text-embedding-3-small` at 1536 dimensions as the source of truth.

## Error Handling

Typical error responses:

```json
{
  "error": "Internal server error"
}
```

Backend validation and auth failures commonly use:

- `400 Bad Request`
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`
- `409 Conflict`
- `422 Unprocessable Entity`
- `429 Too Many Requests`
- `500 Internal Server Error`
- `503 Service Unavailable`

## Operational Notes

- Required frontend secrets: `NEXT_PUBLIC_BACKEND_API_URL`, `BACKEND_API_URL`, `BACKEND_API_KEY`, `ADMIN_API_SECRET`
- Required backend secrets: `API_SECRET_KEY`
- Backend health and CORS are configured for the Vercel production domain
- Older Cloudflare references are legacy-only and should not be used for current operations
