# Parallel Worker Handoff: SlideAgent Alpha Readiness

Last updated: 2026-04-30 JST

## Goal

Complete the reception SlideAgent flow for alpha onsite testing using the new static PDF and narration assets:

- `frontend/public/reception/engineer-cafe-ja.pdf`
- `frontend/public/reception/engineer-cafe-en.pdf`
- `frontend/public/reception/engineer-cafe-narration-ja.md`
- `frontend/public/reception/engineer-cafe-narration-en.md`

The slide tour must be deterministic. Do not use an LLM for normal slide playback.

## Current findings

- Both PDFs are 5 pages, 16:9, 720 x 405 pt.
- Both Markdown narration files describe 5 slides.
- Existing backend narration JSON has 10 slides, so it is stale for the new deck.
- `ReceptionPdfGuide` currently hardcodes Japanese PDF/audio prefixes.
- `startPresentation()` dispatches `autoStartPresentation`, but `ReceptionPdfGuide` does not listen to it. The PDF path does not auto-start today.
- The current PDF panel is sized to fit portrait, so the horizontal deck appears too small for kiosk use.

## Files likely owned by this task

- `frontend/src/app/page.tsx`
- `frontend/src/app/components/ReceptionPdfGuide.tsx`
- `frontend/src/lib/reception/reception-pdf-constants.ts`
- `frontend/e2e/reception-flow.spec.ts`
- `frontend/e2e/marp-viewer.spec.ts` or a new `frontend/e2e/reception-pdf-guide.spec.ts`
- optional script: `scripts/build-reception-narration.py` or `frontend/src/jobs/...`
- optional generated JSON/audio assets if the team decides to commit them

Do not change Welcome/OCR/PTT implementation in this branch unless coordinating with the primary lane.

## Recommended implementation

1. Add language-aware reception deck constants.

```ts
export const RECEPTION_GUIDE_PDFS = {
  ja: '/reception/engineer-cafe-ja.pdf',
  en: '/reception/engineer-cafe-en.pdf',
} as const;
```

Add language-aware audio/lipsync prefixes for `ja` and `en`.

2. Make `ReceptionPdfGuide` accept `language`, `autoStart`, and `landscapeReady` props.

Expected behavior:

- reset to page 1 when language changes;
- use the correct PDF and audio prefix;
- start playback once when `autoStart && landscapeReady && totalPages > 0`;
- stop playback when leaving slide mode.

3. Add a slide-mode orientation gate.

Use viewport detection instead of trying to force orientation. iOS Safari cannot reliably lock orientation from a web page.

Suggested detection:

- `window.matchMedia('(orientation: landscape)')`
- fallback to `window.innerWidth > window.innerHeight`
- listen to `change`, `resize`, and `orientationchange`

Portrait behavior:

- show a full-screen instruction to rotate the device;
- do not show the small slide panel;
- do not start narration.

Landscape behavior:

- hide the rotate instruction;
- show the PDF full-screen or nearly full-screen;
- auto-start slide 1 once.

4. Convert narration Markdown to the runtime format.

Lowest-risk alpha option:

- parse `## スライドN:` / `## Slide N:` sections;
- emit 5-entry JSON with `slideNumber`, `narration.auto`, empty `onDemand`, and simple transitions;
- assert PDF page count equals narration count in a test or build check.

Alternatively, make the frontend read Markdown directly, but keep parsing deterministic and tested.

5. Use PiperPlus narration without LLM.

Preferred alpha path:

- pre-generate audio per slide and language;
- commit or deploy assets under `frontend/public/reception/audio/{ja,en}/NN.mp3`;
- optionally precompute lipsync JSON under `frontend/public/reception/lipsync/{ja,en}/NN.json`.

Acceptable fallback:

- call existing TTS once per slide and cache/prefetch results;
- prefetch next slide while current slide is playing;
- expose measured first-audio and next-slide timings in logs.

## Acceptance checks

- Portrait `スライド案内` shows rotate instruction.
- Landscape change auto-starts slide 1.
- Japanese deck uses Japanese PDF and narration.
- English deck uses English PDF and narration.
- 5 PDF pages and 5 narration entries are verified.
- No LLM/network search is used for normal narration.
- Close returns to idle and stops audio/lipsync.
- Completion returns to idle after the configured completion delay.
- Playwright covers portrait, landscape, language, next/previous, close, and completion.

## Suggested local commands

```bash
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend test:e2e -- reception-flow.spec.ts
pnpm --dir frontend test:e2e -- reception-pdf-guide.spec.ts
```

If the repo uses wrapper scripts on the active branch, prefer the existing package scripts over adding new tooling.

## GitHub issue split

Epic:

- P0 SlideAgent landscape PDF tour and deterministic narration readiness

Sub-issues:

- P0 Slide narration asset ingestion: 5-page PDF/Markdown to runtime narration data
- P0 Slide mode landscape gate and orientation auto-start
- P0 PiperPlus per-slide narration playback/prefetch without LLM
- P0 SlideAgent e2e/live validation gate
