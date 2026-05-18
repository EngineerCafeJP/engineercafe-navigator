# Data Flow: GAS Web App -> `EVENT_SHEET_GAS_URL` -> `SheetsEventSource` -> KB

## Client

- The external client is the Google Apps Script Web App configured by `EVENT_SHEET_GAS_URL` and `EVENT_SHEET_GAS_TOKEN`.
- Backend CLI sync can include the sheet source with `--include-spreadsheet` at `backend/scripts/sync_event_kb.py:37`.
- Runtime event answers also instantiate `SheetsEventSource` in `EventAgent.__init__()` at `backend/agents/event_agent.py:49`.

## API Route

- There is no local HTTP API route for the GAS fetch; the backend service calls the GAS Web App directly.
- `SheetsEventSource` reads `EVENT_SHEET_GAS_URL` and `EVENT_SHEET_GAS_TOKEN` at `backend/services/sheets_event_source.py:41`.
- It sends `GET <EVENT_SHEET_GAS_URL>?token=<EVENT_SHEET_GAS_TOKEN>` at `backend/services/sheets_event_source.py:61`.
- Cloud Run secret binding for `EVENT_SHEET_GAS_URL` is configured in CI deploy logic at `.github/workflows/ci.yml:619`.

## Backend

- `SheetsEventSource.fetch_events()` validates configuration, fetches JSON, rejects GAS errors, extracts items, and normalizes rows at `backend/services/sheets_event_source.py:50`.
- `_to_record()` filters non-approved rows, validates title/date, normalizes time, and returns `EventSourceRecord` at `backend/services/sheets_event_source.py:104`.
- `search_events()` exposes the same response shape as `CalendarService` and applies time-window filtering at `backend/services/sheets_event_source.py:83`.
- `EventAgent.answer_event_query()` searches spreadsheet, ICS calendar, and Connpass in parallel at `backend/agents/event_agent.py:153`.
- KB sync plans event rows through `plan_event_kb_records()` at `backend/services/event_kb_sync.py:155` and writes with `sync_event_kb_records()` at `backend/services/event_kb_sync.py:182`.

## Response

- Runtime event search returns `{ success: true, data: { events, timeRange, eventCount } }` from `SheetsEventSource.search_events()` at `backend/services/sheets_event_source.py:92`.
- `EventAgent` merges spreadsheet, calendar, and Connpass events at `backend/agents/event_agent.py:188`, then returns answer/emotion/metadata at `backend/agents/event_agent.py:257`.
- KB sync returns `planned_count`, `written_count`, `skipped_count`, and written records via `EventKbSyncResult` at `backend/services/event_kb_sync.py:49`.
- The CLI prints planned/written/skipped counts and titles at `backend/scripts/sync_event_kb.py:81`.
