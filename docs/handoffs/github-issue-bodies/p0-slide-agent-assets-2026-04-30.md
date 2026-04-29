## Summary

Ingest the new 5-page reception PDF/Markdown slide assets into the runtime narration format so SlideAgent/PDF playback no longer uses stale 10-slide narration.

## Evidence

- New PDFs are 5 pages.
- New narration Markdown files are 5 sections.
- Existing `backend/slides/narration/engineer-cafe-{ja,en}.json` is 10 slides and no longer matches the new deck.

## Scope

- Parse or convert:
  - `frontend/public/reception/engineer-cafe-narration-ja.md`
  - `frontend/public/reception/engineer-cafe-narration-en.md`
- Produce deterministic runtime data with:
  - `slideNumber`
  - `narration.auto`
  - empty or minimal `onDemand`
  - minimal transitions
- Make language selection explicit for Japanese and English.
- Add a check that PDF page count equals narration entry count.

## Acceptance criteria

- JA runtime narration has exactly 5 slides.
- EN runtime narration has exactly 5 slides.
- The renderer can select JA/EN based on kiosk language.
- A test fails if PDF pages and narration count diverge.
- Normal narration playback does not call LLM/search.

## Out of scope

- Welcome/OCR/PTT changes.
- General chat route changes.
