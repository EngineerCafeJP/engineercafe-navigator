# Frontend CODEMAP

Updated: 2026-05-18

## App Surface

- `frontend/src/app/page.tsx` is the kiosk shell and coordinates voice, OCR, reception, and presentation views.
- `frontend/src/app/components/VoiceInterface.tsx` controls microphone capture, STT, QA, TTS, playback, and VRM metadata.
- `frontend/src/app/components/KioskBottomBar.tsx` owns kiosk voice controls and lock state.
- `frontend/src/app/components/KioskVoiceStatusStack.tsx` renders voice session status.
- `frontend/src/components/reception/OcrCameraView.tsx` and `frontend/src/lib/reception-api.ts` connect OCR/member-card flow to `/api/reception/*`.

## API Routes

- `frontend/src/app/api/voice/route.ts:26` proxies voice POST actions to backend `/api/voice`.
- `frontend/src/app/api/voice/filler/route.ts` proxies static filler audio requests.
- `frontend/src/app/api/qa/route.ts:9` proxies user questions to backend `/api/chat`.
- `frontend/src/app/api/calendar/route.ts:9` proxies calendar reads to backend `/api/calendar`.
- `frontend/src/app/api/reception/_shared.ts:35` centralizes reception proxy behavior.
- `frontend/src/app/api/cron/update-knowledge-base/route.ts:50` runs the Vercel cron entry for knowledge-base refreshes.

## Client Libraries

- `frontend/src/lib/api/backend-proxy.ts:58` builds authenticated server-side backend calls using `BACKEND_API_URL` and `BACKEND_API_KEY`.
- `frontend/src/lib/api/voice-client.ts:259` sends browser STT payloads to `/api/voice`.
- `frontend/src/lib/api/voice-client.ts:283` sends browser TTS payloads to `/api/voice`.
- `frontend/src/lib/api/qa-client.ts:176` submits QA through proxy mode or direct backend mode with proxy fallback.
- `frontend/src/lib/reception-api.ts:81` starts reception sessions and `frontend/src/lib/reception-api.ts:94` polls status.

## Admin And Jobs

- `frontend/src/app/(admin)/admin/knowledge/page.tsx` is the knowledge admin list.
- `frontend/src/app/(admin)/admin/knowledge/upload/page.tsx` handles knowledge uploads.
- `frontend/src/jobs/update-knowledge-base.ts:83` runs scheduled Connpass/website knowledge refreshes.
- `frontend/src/lib/monitoring/rag-metrics.ts` records RAG and knowledge-base metrics.
- `frontend/src/lib/monitoring/cron-alerts.ts` dispatches cron failure alerts.

## Runtime Configuration

- `frontend/src/lib/env.ts` and `frontend/src/lib/env-client.ts` validate server/client runtime env.
- `frontend/vercel.json` defines Vercel route/runtime settings.
- `frontend/next.config.js` defines Next.js build behavior.
