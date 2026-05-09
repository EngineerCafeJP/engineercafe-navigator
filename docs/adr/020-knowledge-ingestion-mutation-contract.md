# ADR 020: Knowledge Ingestion Mutation Contract

## Status

Accepted, 2026-05-09.

## Context

Issue #540 tracks the gap between the YAML knowledge seed path and the admin
upload path. Before this decision, YAML ingestion used category-specific
hierarchical chunks, while the admin upload path used a flat `chunk_text()`
helper. That made RAG quality depend on the ingestion route.

The same area had a second reliability issue: CRUD and upload paths could
produce retrieval-invisible rows when embedding generation returned no vector.
Those rows were successfully stored in `knowledge_base`, but Enhanced RAG could
not retrieve them.

The admin UI also had no deterministic proof that PDF/Markdown preview,
upload, update, and delete mutations affected the same rows that RAG consumes.

## Decision

Knowledge mutations must satisfy these contracts:

1. Text CRUD must reject create/update operations before storage if a required
   embedding cannot be generated.
2. File upload must use the same category-aware hierarchical chunking primitives
   as YAML seeding.
3. Uploaded chunks must carry stable document-level identity in metadata:
   `entry_id`, `document_id`, `chunk_level`, `chunk_index`, and `total_chunks`.
4. Preview remains a dry run: parse and chunk only, no embedding or DB writes.
5. Mutation tests must share one Supabase fake between the admin API and
   `EnhancedRAGSearch` so tests prove retrieval-visible behavior, not just API
   response shape.
6. Live release evidence must include post-deploy RAG mutation checks against
   production API paths before closing the relevant issue.

## Consequences

- Upload and YAML knowledge now use compatible chunk levels and category
  strategies.
- A failed embedding service no longer creates rows that silently miss RAG.
- Multi-chunk uploaded documents can be reasoned about as one document via
  `metadata.document_id`.
- #543 preview acceptance can be verified without introducing side effects.
- #540 Phase 0 and Phase 1 are implemented for Markdown/PDF upload. Bilingual
  ingestion and metadata schema validation remain future work under #540 or a
  follow-up issue.

## Verification

Required local gates:

- `pytest tests/api/test_knowledge_api.py`
- `pytest tests/integration/test_knowledge_rag_mutation_contract.py`
- `pytest tests/knowledge/test_upload_ingestion.py`
- `pnpm exec playwright test --config=playwright.config.ts e2e/knowledge.spec.ts --project=chromium`

Required production gates after merge:

- `/health` returns OK on the new Cloud Run revision.
- Admin preview accepts Markdown/PDF and rejects too-large files without writes.
- Admin upload inserts retrieval-visible rows with embeddings.
- Text create/update reject null embeddings and do not mutate stored rows.
- Updated uploaded knowledge is observable through the live RAG/chat path or a
  direct live RAG verification script.

### 2026-05-09 Production Evidence

The contract was deployed by PR #790 after PR #787, #788, and #789 were merged.
The production backend served 100% traffic from Cloud Run revision
`engineer-cafe-backend-00192-bzt` with image
`engineer-cafe-backend:a9e85d3d7896aded7be0021649538b303a2cd34e`.

Observed results:

- GitHub Actions develop run `25588854013` passed, including
  `backend-test`, `backend-test-ragas`, and `backend-deploy-staging`.
- The deploy job used `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`, Node.js 24
  action versions, `google-github-actions/setup-gcloud@v3.0.1`, and produced no
  Node.js 20 action deprecation warnings.
- `/health` returned `status=ok` with `supabase=ok`.
- Live Markdown preview, upload, get, update, delete, and cleanup passed against
  `/api/knowledge/*`.
- Live `/api/chat` retrieved the uploaded token before update and retrieved the
  updated token after update, proving retrieval-visible mutation behavior.
- Live filler API returned audio for 12 samples; backend upstream latency max
  was 7 ms.
- Voice pipeline retry report
  `backend/tests/reports/voice-pipeline-live-post-alpha-rag-node24-deploy-retry-20260509024048.md`
  recorded `14 PASS / 4 WARN / 0 FAIL`.
- Frontend production voice-live Playwright retry passed: `1 passed`.
- Cloud Logging error gate report
  `backend/tests/reports/cloud-logging-check-post-alpha-rag-node24-logs-20260509024521.md`
  passed with zero `/api/chat` 5xx, memory helper errors, UUID hygiene errors,
  or reception persistence errors. A direct Cloud Run log query also found zero
  `ERROR`, `Traceback`, `Timeout`, or `routing error` rows for the verification
  window.

Residual risk:

- STT latency remains outside the target for #529. In the same verification
  window, STT logs on revision `engineer-cafe-backend-00192-bzt` showed 9
  `stt_winner` rows, winners `qwen=4` and `vosk=5`, p50 `6877 ms`, p90
  `9000 ms`, max `10006 ms`, and `stt_qwen_rejected=0`. The STT live latency
  gate report
  `backend/tests/reports/stt-live-preflight-post-alpha-rag-node24-stt-20260509024521.md`
  failed on p95/over-10s ratio, so STT latency remains tracked by #529 and does
  not close under this ADR.

## Related

- #540: Knowledge ingestion pipeline hardening for RAG quality
- #543: PDF upload chunk preview endpoint + UI
- #517: Event KB live bridge
- #668: CI Node.js runtime deprecation cleanup
