# Alpha Edge Case Proof Checklist 2026-05-03

Issue: #584, F edge-case / failure-tolerance validation.

This checklist maps the requested edge cases to the existing automated alpha suites and to the
remaining device or onsite checks that cannot be proven by API/browser fixtures alone.

## Coverage Map

| Case | Scenario | Existing automated coverage | Remaining proof |
| --- | --- | --- | --- |
| F-1 | Network断 / reconnect | `frontend/e2e/voice-network-recovery.spec.ts` mocks STT network failure and verifies idle recovery plus retry success. D suite and Cloud Logging gate cover backend 5xx/log hygiene, not browser reconnect UX. | Run once against Vercel/browser with DevTools offline toggled during STT or QA, then restore online and confirm next turn works. |
| F-2 | Mic permission denied | `frontend/e2e/voice-permission-denial.spec.ts` covers `NotAllowedError`, `NotFoundError`, `InvalidStateError`, and `SecurityError`. `frontend/e2e/reception-flow.spec.ts` also covers permission denial from the kiosk lane. | Real target browsers: iPad/iPhone Safari and Android Chrome permission denial/re-enable flow. |
| F-2 | Mic muted | No reliable browser automation for hardware/OS muted input. Backend `/api/voice` tests cover explicit STT failure responses, but not real muted capture. | Real device muted-mic check: UI returns idle, shows retryable STT guidance, next unmuted turn succeeds. |
| F-2 | Autoplay denied / tap-to-enable | `frontend/src/__tests__/audio/audio-user-interaction-gate.test.ts`, `frontend/src/__tests__/mobile-audio-service.test.ts`, and `frontend/src/__tests__/web-audio-player.test.ts` cover policy detection, large Android playback path, and decode timeout behavior. | Real iOS Safari tap-to-enable proof remains under #697/#698; browser automation uses `--autoplay-policy=no-user-gesture-required`, so it is not sufficient for closure. |
| F-3 | 30秒超 long utterance | Samples are defined in `docs/testing/alpha-final-scenarios.md` as `F3-LONG-JA-001` and `F3-LONG-EN-001`. A/V suites exercise normal fixture-audio STT/TTS paths but do not run 30s live utterance audio. | API-level long text `/api/chat` and `/api/voice text_to_speech` proof can be run before onsite; real 30s speech capture remains onsite/device-only. |
| F-4 | Silence / noise input | Backend `/api/voice` tests cover missing audio and STT failure response shape. Voice live fixture uses a clean sample and does not prove silence/noise. | Real device or controlled audio fixture proof for silence/noise: no unrecoverable spinner, clear retry guidance, next valid turn succeeds. |

## Existing Alpha Suite Mapping

- `stt`: log-based current-revision STT latency and timeout risk.
- `v`: live API voice pipeline with fixture TTS -> STT -> chat -> TTS.
- `a`: broader voice round-trip smoke across realistic utterances.
- `d`: state durability, adversarial prompts, backend/log hygiene; useful for failure tolerance but not UI edge UX.
- `h-ui`: Welcome -> warmup -> first voice in a browser with fixture audio; not real microphone or real autoplay policy.
- `voice-permission-denial`: browser-level mic permission error UI, outside the live alpha workflow by default.

## Manual Proof Checklist

Record browser/device, deployed frontend URL, Cloud Run revision, timestamp, and a short screen
recording or screenshot for each manual case.

1. F-1 network recovery:
   - Start a voice turn, toggle browser/network offline before STT or QA returns.
   - Confirm user-facing network error appears and the mic button is not stuck recording.
   - Restore network and complete a second voice turn successfully.
2. F-2 microphone permission:
   - Deny mic permission on first prompt.
   - Confirm clear permission guidance and idle/retryable state.
   - Re-enable permission and complete a turn.
3. F-2 muted microphone:
   - Use OS/browser/device mute or a disconnected input.
   - Confirm STT failure guidance and idle/retryable state.
   - Unmute and complete a turn.
4. F-2 autoplay/tap-to-enable:
   - On iOS Safari, trigger Welcome/TTS before the audio context is ready.
   - Confirm tap-to-enable guidance, tap once, and verify delayed TTS plays.
5. F-3 long utterance:
   - Speak or inject the JA and EN long utterance samples from `alpha-final-scenarios.md`.
   - Confirm the UI does not time out unrecoverably and the response covers the main intents.
6. F-4 silence/noise:
   - Submit silence and noisy input.
   - Confirm retry guidance, no unrecoverable loading state, and successful next valid turn.

## Recommendation For #584

Keep #584 open with this checklist until real target-device/onsite proof is attached. The automated
gap for browser network recovery is now covered, and existing tests cover permission denial and much
of audio playback policy logic. The remaining muted-mic, real autoplay-denied, 30s live utterance,
and silence/noise checks are device/onsite proof items. Split only if one of those manual checks
finds a concrete reproducible defect; otherwise close #584 after attaching the checklist results.
