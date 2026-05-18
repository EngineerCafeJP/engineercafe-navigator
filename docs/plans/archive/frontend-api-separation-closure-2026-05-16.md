> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Frontend API Separation Closure Note

作成日: 2026-05-16

## 結論

Frontend API 分離 Issue は、このセッションで close 可能。

close 条件は「React 全面置換・Voice UI 全面再設計」ではなく、現行 UI を維持したまま、
音声ターンの通信責務を `VoiceInterface.tsx` から型付き API client へ分離することとする。

## 実装済み範囲

- `/api/voice` の `speech_to_text`, `text_to_speech`, `interrupt`, `client_telemetry` を `frontend/src/lib/api/voice-client.ts` に分離。
- `/api/voice/filler` を `requestVoiceFiller()` に分離。
- `/api/character` の `auto`, `supported_features`, status を `frontend/src/lib/api/character-client.ts` に分離。
- `VoiceInterface.tsx` から音声系の direct `fetch('/api/voice')`, `fetch('/api/voice/filler')`, `fetch('/api/character')` を撤去。
- 既存の `submitQaQuestion()` は維持し、QA の proxy/direct/fallback 境界は変更しない。
- `AbortSignal`, `keepalive`, HTTP status, normalized error payload を client boundary に集約。
- voice turn timing の client telemetry を追加し、`sttMs`, `qaMs`, `ttsMs`, `status`, `requestMode`, `usedProxyFallback` を `/api/voice` proxy log に残せるようにした。

## Close とする理由

- 1824行の `VoiceInterface.tsx` から、通信の生 fetch と JSON/HTTP error handling を外した。
- UI の録音、再生、iOS audio unlock、filler enqueue、lip-sync、VRM merge はまだ UI 側に残るが、これは現時点では presentation/runtime 制御であり API 分離の close blocker ではない。
- `page.tsx` / `VoiceInterface.tsx` の全面分割や React runtime の置き換えは、効果が大きい一方でこの Issue の成功条件を曖昧にするため、別 Issue に分離する。

## 残課題

### P2: VoiceInterface component split

目的: `VoiceInterface.tsx` を、録音制御、音声ターン制御、再生制御、表示 UI に分ける。

判断基準:

- `VoiceInterface.tsx` から audio playback と lip-sync scheduling を hook/service へ移す。
- 既存 kiosk UI の見た目と iPad Safari audio unlock を壊さない。
- 主要 voice tests と TypeScript が通る。

### P2: Turn API / streaming spike

目的: `STT -> QA -> TTS` の複数 round-trip を減らす余地を測る。

判断基準:

- `/api/voice/turn` または SSE は spike として実装し、現行 route と並走できる。
- p50/p95 の改善が API 分離後 telemetry で確認できる。
- 失敗時に既存 `speech_to_text` + `submitQaQuestion` + `text_to_speech` へ戻せる。

### P3: Frontend architecture replacement

目的: UI 層の長期保守性を改善する。

判断基準:

- React/Next の全面置換や大規模 UI shell rewrite は、速度 Issue や API 分離 Issue の close blocker にしない。
- 置換する場合は kiosk 操作、音声権限、iPad Safari、VRM rendering、OCR overlay を含む別 epic とする。

## Issue コメント案

Frontend API 分離 Issue は close します。

- `voice-client.ts` と `character-client.ts` を追加し、音声/STT/TTS/filler/character 通信を型付き client に集約
- `VoiceInterface.tsx` から音声系 direct fetch を撤去
- `AbortSignal`, `keepalive`, status, normalized error を client boundary に移動
- 音声ターンの `sttMs`, `qaMs`, `ttsMs` telemetry を追加

残る `VoiceInterface.tsx` のコンポーネント分割、統合 `/api/voice/turn`、UI shell rewrite は P2/P3 follow-up として扱います。
