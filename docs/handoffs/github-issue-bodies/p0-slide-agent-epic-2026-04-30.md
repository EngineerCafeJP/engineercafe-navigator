## Summary

Make the reception SlideAgent flow alpha-ready by using the newly supplied 5-page Japanese/English PDFs and matching narration Markdown as a deterministic, no-LLM slide tour.

This should be treated as a P0 alpha blocker if `スライド案内` remains in the first-screen kiosk controls for onsite testing.

## Evidence

- `frontend/public/reception/engineer-cafe-ja.pdf`: 5 pages, 16:9, 720 x 405 pt.
- `frontend/public/reception/engineer-cafe-en.pdf`: 5 pages, 16:9, 720 x 405 pt.
- `frontend/public/reception/engineer-cafe-narration-ja.md`: 5 slide narration sections.
- `frontend/public/reception/engineer-cafe-narration-en.md`: 5 slide narration sections.
- Existing `backend/slides/narration/engineer-cafe-{ja,en}.json` has 10 slides and is stale for the new deck.
- `frontend/src/app/components/ReceptionPdfGuide.tsx` currently hardcodes Japanese PDF/audio prefixes.
- `frontend/src/app/page.tsx` dispatches `autoStartPresentation`, but the PDF renderer does not subscribe to it. Auto-start currently applies to Marp only.
- The current portrait panel makes a horizontal deck too small for kiosk use.

## Scope

- Use the supplied PDF and Markdown narration assets.
- Add language-aware deck/narration/audio selection.
- Add portrait rotate instruction and landscape auto-start.
- Use PiperPlus/precomputed audio per slide, or live TTS with caching/prefetch as a fallback.
- Do not use an LLM for normal narration playback.
- Add e2e coverage for the full slide tour path.

## Acceptance criteria

- `スライド案内` tap in portrait shows a rotate instruction, not a cramped bottom-half panel.
- When the viewport becomes landscape, slide 1 starts automatically without another tap.
- Japanese language uses Japanese PDF and narration.
- English language uses English PDF and narration.
- PDF page count and narration count match: 5 pages / 5 narration entries.
- Normal narration path calls no LLM and no web search.
- First slide audio starts under 1s when cached/precomputed.
- Next slide begins within 500ms after previous narration completes when cached.
- Close/finish returns to idle and stops audio/lipsync.
- Playwright covers portrait gate, landscape auto-start, language switching, navigation, close, and completion.

## Suggested split

- Asset ingestion: PDF/Markdown -> runtime narration data.
- Orientation UX: landscape gate and auto-start.
- Audio playback: PiperPlus per-slide narration and prefetch.
- Validation: e2e/live gate and issue close evidence.

## References

- `docs/plans/alpha-parallel-blocker-plan-2026-04-30.md`
- `docs/handoffs/alpha-slide-agent-parallel-worker-2026-04-30.md`
