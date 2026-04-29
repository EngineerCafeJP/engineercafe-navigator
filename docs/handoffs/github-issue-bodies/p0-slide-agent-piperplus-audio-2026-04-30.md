## Summary

Wire per-slide PiperPlus narration for the reception PDFs without involving an LLM during normal slide playback.

## Preferred alpha path

Pre-generate static audio from the Markdown narration:

```text
frontend/public/reception/audio/ja/01.mp3
frontend/public/reception/audio/en/01.mp3
frontend/public/reception/lipsync/ja/01.json
frontend/public/reception/lipsync/en/01.json
```

This is preferred because the narration text is static and alpha needs predictable first-audio latency.

## Acceptable fallback

Use live PiperPlus TTS per slide only if:

- the result is cached for the session;
- the next slide is prefetched while current narration plays;
- latency logs record first-audio and next-slide timings.

## Acceptance criteria

- Normal slide narration uses no LLM.
- First slide audio starts under 1s when precomputed/cached.
- Next slide narration starts within 500ms after previous narration completes when cached.
- Missing audio does not dead-end the presentation.
- Stopping/closing slide mode aborts playback and lipsync.
- JA and EN audio paths are separate.

## Out of scope

- Changing chat model routing.
- Welcome/OCR/PTT changes.
