> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Alpha Parallel Blocker Plan

Last updated: 2026-04-30 JST

## 結論

次に潰す alpha blocker は、主線を `#616 -> #611/#610 -> #617 live validation` に置く。
ただし SlideAgent は、画面上の主要導線として `スライド案内` ボタンが存在し、2026-04-30 に日本語/英語 PDF と対応ナレーション Markdown が投入済みであるため、alpha 現地テスト対象に含めるなら P0 として並列実装する。

## 優先順位

1. `#616` Welcome UX / Push-to-talk clarity
   - Welcome が会話開始ではなくカメラ/OCRを先に開くため、受付体験の初回導線を壊している。
   - `frontend/src/app/page.tsx` は Welcome 実行時に `setWelcomeMemberOcrOpen(true)` を呼んでいる。
   - `frontend/e2e/reception-flow.spec.ts` も現状の camera-first を期待しており、仕様とテストの両方を直す必要がある。

2. `#611/#610` Fast first response / filler
   - `#620` で Cerebras fast QA first-pass は入ったが、フロント側の first audible feedback はまだ未実装。
   - `frontend/src/lib/audio-queue.ts` は priority queue を持っているため、短い filler/prepared audio を優先再生する土台はある。
   - `/api/voice/filler` は未実装なので、最短は静的 filler audio + 既存 audio queue priority で始める。

3. SlideAgent deterministic tour
   - `frontend/public/reception/engineer-cafe-ja.pdf` と `engineer-cafe-en.pdf` は 5 pages / 16:9。
   - `frontend/public/reception/engineer-cafe-narration-ja.md` と `engineer-cafe-narration-en.md` は各 5 slides。
   - 既存 `backend/slides/narration/engineer-cafe-{ja,en}.json` は 10 slides で、投入済み PDF/Markdown と一致しない。
   - `ReceptionPdfGuide` は日本語 PDF/audio prefix 固定で、英語 PDF と Markdown narration を読まない。
   - `startPresentation()` は `autoStartPresentation` を発火するが、PDF renderer 側は購読していない。自動開始は Marp viewer 側だけ。

4. `#617` stale route validation
   - `#620` の routing 改善後も、live/e2e で「地下について」直後の「明日のイベント」が SlideAgent に入らないことを証明する必要がある。

5. `#583/#584/#585` final gates
   - 127-case RAGAS、edge/live fault、2h kiosk は実装後の GO/NO-GO gate として残す。

## 並列分担

### Primary lane

Owner: main engineer

Scope:

- `#616` Welcome should enter voice-first, not OCR-first.
- Member card button should be the only path that opens member-card OCR.
- Push-to-talk must expose pressed/listening/released states clearly.
- Then `#611/#610` first audible feedback path.

Why:

- `#616` touches first-run kiosk UX and existing reception e2e expectations.
- `#611/#610` touches voice timing, audio queue behavior, and alpha latency metrics.

### Parallel lane

Owner: second engineer

Scope:

- New SlideAgent P0 issue set.
- PDF/Markdown assets to deterministic slide tour.
- Landscape gate and auto-start.
- Per-slide PiperPlus narration playback/prefetch, no LLM for narration.

Why:

- The work is mostly isolated to `frontend/src/app/components/ReceptionPdfGuide.tsx`, `frontend/src/lib/reception/reception-pdf-constants.ts`, slide narration assets, and slide e2e tests.
- It should not conflict with Welcome and voice first-response implementation.

## SlideAgent acceptance criteria

- `スライド案内` tap in portrait shows a full-screen rotate instruction, not a cramped bottom-half slide panel.
- When viewport becomes landscape, slide 1 starts automatically without a second tap.
- Japanese UI uses `engineer-cafe-ja.pdf` and Japanese narration.
- English UI uses `engineer-cafe-en.pdf` and English narration.
- PDF page count and narration count must match: 5 pages / 5 narration entries.
- Narration is deterministic. LLM is not called for ordinary slide playback.
- First slide audible start is under 1s when audio is precomputed/cached, or the implementation must show measured reason if live PiperPlus TTS is used.
- Next slide starts within 500ms after the previous narration completes when audio is cached.
- Close/finish returns to idle and stops audio/lipsync.
- E2E covers portrait rotate gate, landscape auto-start, language switching, next/previous, completion, and close.

## Implementation note

For alpha reliability, prefer pre-generated PiperPlus audio and optional lipsync JSON under:

```text
frontend/public/reception/audio/ja/01.mp3
frontend/public/reception/audio/en/01.mp3
frontend/public/reception/lipsync/ja/01.json
frontend/public/reception/lipsync/en/01.json
```

Live PiperPlus generation is acceptable only if it prefetches the next slide and records latency. Since the source text is static, pre-generation is the lower-risk alpha path.

## Current CI note

After PR #620 merge, CI run `25121216454` had core jobs green at 2026-04-30 JST: backend tests, frontend typecheck/lint/build, Playwright e2e, and Playwright voice-live. Staging deploy was still in progress at the last check and should be rechecked before live validation.
