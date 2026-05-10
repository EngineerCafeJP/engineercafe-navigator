# ADR 022: Reception slide PDFs as checked-in frontend static assets

## Status

Accepted, 2026-05-10.

## Context

The reception guide uses two five-page PDFs with pre-generated PiperPlus
narration audio:

- `frontend/public/reception/engineer-cafe-ja.pdf`
- `frontend/public/reception/engineer-cafe-en.pdf`
- `frontend/public/reception/audio/{ja,en}/01.mp3` through `05.mp3`

The 2026-05-10 deck refresh replaced QR/image data in the PDFs while preserving
page count and extracted text. The project also has Google Cloud Run for backend
voice/RAG APIs, which can make slide deployment ownership ambiguous.

## Decision

Reception slide PDFs and matching static narration audio remain checked-in
frontend assets under `frontend/public/reception`.

The live kiosk loads the PDFs from the frontend origin at `/reception/*.pdf`.
Google Cloud Storage is not the runtime source for these files. If a future
operator wants a GCS or CDN source of truth, that must be introduced as a
separate runtime change with explicit URL contracts and cache invalidation.

## Consequences

- A reception deck update is a frontend asset PR, not a Cloud Run deploy.
- Merge to `develop` must be followed by frontend deployment verification.
- A PDF-only refresh may keep existing narration MP3 files only when page count
  and extracted text are unchanged.
- If extracted text changes, the same PR must update narration Markdown,
  backend narration JSON, and PiperPlus MP3 files.
- Every checked-in PDF, image, or audio refresh must include provenance evidence
  or explicit release gaps.

## Verification

For each deck refresh:

- confirm both PDFs have 5 pages unless the code/tests are intentionally updated;
- compare extracted text with the previous deck using `pdftotext`;
- run `frontend/src/__tests__/reception-narration-assets.test.ts`;
- after deploy, verify the frontend production URLs for both PDFs;
- record checksums and provenance in a docs asset record.

## Related

- #810: Reception slide PDF QR refresh and asset provenance
- `docs/architecture/stt-tts-stack-and-slide-audio-2026-05-09.md`
- `docs/assets/reception-slide-assets-2026-05-10.md`
