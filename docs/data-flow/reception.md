# Data Flow: `/api/reception/*`

## Client

- Reception client helpers call `/api/reception/start`, `/api/reception/status/{id}`, and `/api/reception/sensor-status` from `frontend/src/lib/reception-api.ts:81`, `frontend/src/lib/reception-api.ts:94`, and `frontend/src/lib/reception-api.ts:108`.
- The kiosk page imports `startReception` at `frontend/src/app/page.tsx:48`.

## API Route

- Next.js start route forwards POSTs to backend `/api/reception/start` at `frontend/src/app/api/reception/start/route.ts:5`.
- Next.js status route forwards GETs to backend `/api/reception/status/{receptionSessionId}` at `frontend/src/app/api/reception/status/[receptionSessionId]/route.ts:11`.
- Next.js sensor-status route forwards GETs to backend `/api/reception/sensor-status` at `frontend/src/app/api/reception/sensor-status/route.ts:5`.
- All reception proxy calls share `proxyReceptionRequest()` at `frontend/src/app/api/reception/_shared.ts:35`, which delegates to `backendFetch()`.

## Backend

- The backend router is defined at `backend/api/reception.py:35` and mounted by `backend/main.py:1973`.
- `/sensor-trigger` stores the latest M5Stack event and optional Supabase sensor row at `backend/api/reception.py:303`.
- `/sensor-status` reads Supabase first, then in-memory fallback, at `backend/api/reception.py:341`.
- `/start` creates a `ReceptionSession`, optionally attaches visitor identity, persists it, and returns greeting/stage at `backend/api/reception.py:394`.
- `/status/{reception_session_id}` loads the persisted or cached session and verifies `session_id` at `backend/api/reception.py:448`.
- Supabase persistence is implemented by `ReceptionRepository.store_session()` at `backend/utils/reception_repository.py:65` and sensor event methods at `backend/utils/reception_repository.py:209`.

## Response

- Start responses include `reception_session_id`, greeting, and stage at `backend/api/reception.py:441`.
- Status responses include conversation `session_id`, stage, visitor type, and purpose at `backend/api/reception.py:476`.
- Sensor status returns either `triggered=false` or the event payload at `backend/api/reception.py:369` and `backend/api/reception.py:391`.
- Next.js forwards successful backend JSON unchanged at `frontend/src/app/api/reception/_shared.ts:57`.
