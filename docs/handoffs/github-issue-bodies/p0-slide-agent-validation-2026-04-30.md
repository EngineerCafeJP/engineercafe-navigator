## Summary

Add the validation gate needed to close the SlideAgent alpha blocker after asset ingestion, orientation UX, and narration playback are implemented.

## Scope

- Add or update Playwright coverage for:
  - portrait rotate instruction;
  - landscape auto-start;
  - Japanese deck/narration;
  - English deck/narration;
  - next/previous/reset;
  - close/finish returns to idle;
  - audio stop on close.
- Add backend/frontend unit coverage for narration count if conversion is implemented.
- Run local and CI checks.
- Attach results to the epic before close.

## Acceptance criteria

- `pnpm --dir frontend lint` passes.
- `pnpm --dir frontend typecheck` passes.
- `pnpm --dir frontend build` passes.
- Relevant Playwright slide/reception specs pass.
- Evidence includes measured first-audio latency and next-slide transition latency.
- Evidence includes a statement that normal narration used no LLM/search.

## Out of scope

- Implementing the feature itself.
- Closing unrelated P0/P1 issues.
