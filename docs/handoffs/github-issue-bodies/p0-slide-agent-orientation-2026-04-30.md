## Summary

Fix the slide-mode UX for kiosk phones by gating portrait mode with a rotate instruction and auto-starting the slide tour when the viewport becomes landscape.

## Evidence

- The supplied slide PDFs are horizontal 16:9.
- Current PDF panel is fitted into portrait, making the deck small and visually secondary.
- `startPresentation()` emits `autoStartPresentation`, but `ReceptionPdfGuide` does not subscribe to it.

## Scope

- Detect landscape with `matchMedia('(orientation: landscape)')`, with `innerWidth > innerHeight` fallback.
- Listen to `change`, `resize`, and `orientationchange`.
- In portrait, show a full-screen rotate instruction and do not start narration.
- In landscape, show the slide deck full-screen or nearly full-screen and auto-start slide 1 once.
- Close button must remain reachable.

## Acceptance criteria

- Portrait slide mode shows only the rotate instruction and close affordance.
- Switching to landscape starts slide 1 automatically.
- Returning to portrait pauses/stops narration or prevents hidden continuing playback.
- Close returns to idle.
- Playwright covers portrait and emulated landscape behavior.

## Out of scope

- Generating narration audio.
- Rewriting SlideAgent routing.
