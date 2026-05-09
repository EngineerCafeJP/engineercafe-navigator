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

## Related

- #540: Knowledge ingestion pipeline hardening for RAG quality
- #543: PDF upload chunk preview endpoint + UI
- #517: Event KB live bridge
- #668: CI Node.js runtime deprecation cleanup
