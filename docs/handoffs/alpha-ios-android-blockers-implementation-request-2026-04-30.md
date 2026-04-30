# Alpha iOS/Android blockers implementation request (2026-04-30)

## Scope

Open alpha-gate issues:

- #632 VRM character drifts left across responses.
- #633 Intermittent unexpected error from Vercel function timeout.
- #634 iOS Safari Welcome / voice button does not start recording reliably.
- #635 Slide header overlap and silent narration.
- #636 /api/character 403 noise is lower priority; avoid making it worse and prefer local character controls where possible.

## Evidence

- WebKit MediaRecorder documentation demonstrates `getUserMedia()` and `MediaRecorder.start()` from a button handler and confirms Safari records MP4/AAC (`https://webkit.org/blog/11353/mediarecorder-api/`).
- MDN Autoplay guide states Web Audio playback started outside user input is subject to autoplay blocking (`https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay`).
- MDN `AudioContext.state` documents iOS Safari `interrupted` recovery via `resume()` (`https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/state`).
- WebKit bug 237878 tracks iOS `AudioContext` suspension when a page is backgrounded (`https://bugs.webkit.org/show_bug.cgi?id=237878`).
- Vercel duration docs state functions return 504 on max duration and Fluid Compute defaults to 300s, with legacy projects using shorter defaults (`https://vercel.com/docs/functions/configuring-functions/duration`, `https://vercel.com/docs/functions/limitations`).

## Implementation split

### Worker A: VRM position stability (#632)

Owned files:

- `frontend/src/app/components/CharacterAvatar.tsx`
- Optional focused tests if practical.

Requirements:

- Remove the hard-coded idle `+0.15` root scene X offset.
- Stop resetting `vrm.scene.position` every animation frame during sequences.
- Apply root position from `modelPositionOffset + sessionPose.position` consistently only in controlled effects / explicit position changes.
- Do not touch audio, Vercel config, or page z-index files.
- You are not alone in the codebase; do not revert unrelated edits or files owned by other workers.

Acceptance:

- Repeated `sessionState` changes do not produce cumulative position drift.
- Idle/listening/processing/speaking preserve the configured model offset.

### Main implementation: audio, timeout, z-index, observability (#633/#634/#635)

Owned files:

- `frontend/src/app/components/VoiceInterface.tsx`
- `frontend/src/lib/audio/*`
- `frontend/src/app/components/ReceptionPdfGuide.tsx`
- `frontend/src/app/components/MarpViewer.tsx`
- `frontend/src/app/page.tsx`
- `frontend/vercel.json`
- `frontend/src/middleware.ts`
- Tests under `frontend/e2e` or `frontend/src/__tests__` as needed.

Requirements:

- Voice start must mark/listen synchronously inside the user gesture path so Safari does not clean up the recorder before `MediaRecorder.start()`.
- Audio unlock must create/resume AudioContext and play a silent buffer in the gesture path; handle `suspended` and `interrupted`.
- Slide narration must explicitly ensure audio context is resumed before playback and expose a tap-to-enable fallback instead of silent failure.
- Slide modal must sit above header/settings/bottom chrome on both iOS and Android.
- Vercel function duration must be increased for voice/qa/character/slides, with frontend proxy timeout below Vercel max duration.
- Add low-volume UA logging for relevant API paths so Vercel logs can distinguish iOS/Android/desktop.

Acceptance:

- iOS Safari and Android Chrome both use the same push-to-talk user gesture path.
- Voice button tap enters recording rather than showing generic unexpected error.
- Slide narration has an unlock path and no silent success state.
- Vercel timeout hierarchy is coherent.
