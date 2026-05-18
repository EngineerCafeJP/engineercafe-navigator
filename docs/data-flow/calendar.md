# Data Flow: `/api/calendar`

## Client

- Calendar consumers call the Next.js route `/api/calendar` with optional `timeRange`.
- The route reads `timeRange` from `request.nextUrl.searchParams` at `frontend/src/app/api/calendar/route.ts:11`.

## API Route

- Next.js handles the GET route at `frontend/src/app/api/calendar/route.ts:9`.
- It forwards a backend GET to `/api/calendar` with the same `timeRange` at `frontend/src/app/api/calendar/route.ts:17`.
- Auth, base URL, timeout, and response JSON parsing are handled by `frontend/src/lib/api/backend-proxy.ts:58`.

## Backend

- FastAPI handles `/api/calendar` at `backend/main.py:1527`.
- It validates `timeRange` against `_CALENDAR_TIME_RANGES` at `backend/main.py:1524`.
- It calls `CalendarService().search_events()` at `backend/main.py:1534`.
- `CalendarService` reads `GOOGLE_CALENDAR_ICAL_URL` at `backend/tools/calendar_service.py:81`, calculates the window at `backend/tools/calendar_service.py:117`, fetches ICS at `backend/tools/calendar_service.py:167`, parses VEVENT blocks at `backend/tools/calendar_service.py:205`, and filters by time at `backend/tools/calendar_service.py:193`.

## Response

- `CalendarService.search_events()` returns `{ success: true, data: { events, timeRange, eventCount } }` at `backend/tools/calendar_service.py:104`.
- Backend returns that service result directly at `backend/main.py:1541`.
- Backend service failures become HTTP 502 at `backend/main.py:1535`.
- Next.js returns backend data and status at `frontend/src/app/api/calendar/route.ts:26`.
