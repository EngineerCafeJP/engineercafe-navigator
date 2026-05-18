# Cloud Logging Structured Event Check

- Timestamp: wave3_postmetrics_cloud_20260518T0432Z
- Project: aipartner-426616
- Service: engineer-cafe-backend
- Region: asia-northeast1
- Window start: 2026-05-18T04:30:00Z
- Window end: now
- Lookback minutes: 120
- Error gate only: no
- STT generation threshold: 99.00%
- Overall passed: yes

## Summary

| Check | Result | Detail |
| --- | --- | --- |
| `stt_qwen_start` generation | PASS | 100.00% across 4 STT trace(s); raw structured events: 4; missing traces: 0 |
| `stt_qwen_complete` generation | PASS | 100.00% across 4 STT trace(s); raw structured events: 4; missing traces: 0 |
| `stt_winner` generation | PASS | 100.00% across 4 STT trace(s); raw structured events: 4; missing traces: 0 |
| `chat_response` required fields | PASS | 4 structured log(s); required: latency_ms, route, language, rag_fallback, ltm_store_write |
| `/api/chat` 5xx rows | PASS | 0 matching log row(s) |
| critical API ERROR/5xx rows | PASS | 0 matching /api/voice, /api/chat, /api/slides, or /api/error log row(s) |
| `ltm_store_write=failed` rows | PASS | 0 matching chat_response log row(s) |
| `memory_helper` ERROR samples | PASS | 0 error log(s) found; samples listed below if present |
| LTM connection/timeout errors | PASS | 0 matching log row(s) |
| `invalid input syntax for type uuid` hygiene | PASS | 0 matching log row(s) |
| `Reception session persistence failed` hygiene | PASS | 0 matching log row(s) |

## STT Events

| Event | Structured count | Trace generation rate | Missing trace count |
| --- | ---: | ---: | ---: |
| `stt_qwen_start` | 4 | 100.00% | 0 |
| `stt_qwen_complete` | 4 | 100.00% | 0 |
| `stt_winner` | 4 | 100.00% | 0 |

## chat_response Schema

- Rows checked: 4
- Required fields: latency_ms, route, language, rag_fallback, ltm_store_write

## Cloud Run Error Rows

- `/api/chat` 5xx rows: 0
- Critical API ERROR/5xx rows: 0
- `ltm_store_write=failed` rows: 0

## memory_helper Error Samples

- Error rows found: 0
- No memory_helper error samples in the lookback window.

## LTM Connection Error Samples

- Error rows found: 0
- No LTM connection error samples in the lookback window.

## Alpha Log Hygiene

- `invalid input syntax for type uuid` rows: 0
- `Reception session persistence failed` rows: 0
- No alpha log hygiene matches in the lookback window.
