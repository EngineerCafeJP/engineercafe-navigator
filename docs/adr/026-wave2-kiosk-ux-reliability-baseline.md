# ADR-026: Wave 2 Kiosk UX Reliability Baseline

## Status

Accepted (2026-05-18) — PR #852 / #874 / #875 で実装・follow-up・CI reachability を完了し、develop CI/CD と Cloud Run live verification 済み。

## Context

2026-05-17 の Wave 2 では、受付 kiosk の実地 UX に直結する 3 系統の P0/P1 問題を同時に閉じた。PR #852 で本体を実装し、その後 PR #874 で live E2E follow-up gap、PR #875 で GitHub runner から direct Postgres に到達できない CI 環境差を修復した。

1. Date determinism: 「今日は何月何日ですか」のような日付確認が calendar / web search / LLM に流れ、現在日時の回答が不安定になる。
2. Audio playback reliability: iPad / mobile Safari を含むブラウザ音声再生で、再生終了の二重発火、ユーザー操作 gate 停止、thinking 状態滞留、失敗時の無音が起きる。
3. Calendar modernization: Google Calendar だけでは Engineer Cafe curated event の source of truth として弱く、キャンセル・過去日・曖昧な範囲解釈が混入する。

また PR #852 以降の Vercel Preview deploy が失敗しており、原因は repository code ではなく Vercel project の Preview 全体に `NEXT_PUBLIC_SUPABASE_URL` と `NEXT_PUBLIC_SUPABASE_ANON_KEY` が存在しないことだった。Production には存在していたため production smoke は通ったが、PR Preview の信頼性としては不健全だった。

## Decision

### D1: Date-only questions bypass LLM and search

日付だけを尋ねる query は deterministic system-clock path に固定する。

- `query_classifier` は date-only phrase を `general_knowledge` / current-time fast path に分類する。
- `web_search` は bare `今日`, `明日`, `昨日`, `今週` を検索 trigger として扱わない。
- `GeneralKnowledgeAgent` は JST system clock で回答し、metadata に `sources=["system_clock"]`, `provider_called=false` を残す。
- 天気、ニュース、latest、search、trend など現在情報が必要な query は従来どおり current-info path に流す。

### D2: Cloud Run and scheduled jobs use JST explicitly

Cloud Run service と `event-kb-sync` Cloud Run Job は `TZ=Asia/Tokyo` を持つ。Docker image も `tzdata` を含める。

### D3: Event source priority is spreadsheet > connpass > Google Calendar

Engineer Cafe curated events は、GAS Web App 経由の spreadsheet source を最優先にする。

- `SheetsEventSource` は `EVENT_SHEET_GAS_URL` と `EVENT_SHEET_GAS_TOKEN` を Secret Manager から読む。
- Apps Script の 302 redirect を前提に `follow_redirects=True` を使う。
- spreadsheet response は allowlist された公開項目だけを取り込み、PII columns は backend に流さない。
- EventAgent は spreadsheet / Google Calendar / Connpass を並列取得し、重複を正規化 title + date で dedupe する。
- Google Calendar は cancelled / noise prefix / 過去日を除外する。

### D4: Voice state machine must fail back to audible or idle

ブラウザ音声再生は、失敗時に無音で止まらないことを baseline とする。

- audio queue は playback settlement を一度だけ発火させる。
- user interaction gate は timeout と `sessionStorage` bypass persistence を持つ。
- voice controller は processing / thinking が watchdog window を超えた場合に idle へ戻す。
- 音声再生失敗時は session 内で回数制限つきの browser fallback speech を出す。
- state transition telemetry を送る。

### D5: Preview deploy env must be unified across Vercel, GitHub Secrets, and Secret Manager

Public Supabase env は secret value を出力せずに以下へ揃える。

- local `frontend/.env.local`
- GitHub Actions repository secrets
- Google Secret Manager
- Vercel Production
- Vercel Preview (all branches)
- Vercel Development

Production だけに env がある状態は、PR Preview の deploy gate を壊すため不可とする。

## Verification

### Implementation PRs

- PR: [#852](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/852) — Wave 2 Date / Audio / Calendar implementation
- Merge commit: `2866921b06dd705c8b39dcf0ae6e2c8e97a3abd4`
- Merged: 2026-05-17 16:07:00 UTC
- develop CI: `25995874994`, conclusion `success`
- Frontend Production Smoke: `25995874988`, conclusion `success`
- PR: [#874](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/874) — live E2E follow-up gaps
- Merge commit: `f7582f1a5e99360b86d57735fa4fcb6a8d9736cf`
- Merged: 2026-05-17 20:37:37 UTC
- PR CI: `26001835735`, conclusion `success`
- post-merge develop CI: `26002065329`, conclusion `success`
- PR: [#875](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/875) — direct DB E2E reachability guard
- Merge commit: `eee8c0b19f459dcd25ccc5aad211895b037514c6`
- Merged: 2026-05-17 21:11:05 UTC
- PR CI: `26002651705`, conclusion `success`
- post-merge develop CI: `26002826450`, conclusion `success`

### Cloud Run

- Service: `engineer-cafe-backend`
- Region: `asia-northeast1`
- Revision: `engineer-cafe-backend-00218-8zv`
- Traffic: latest revision 100%
- Secret bindings verified: `API_SECRET_KEY`, `GOOGLE_CALENDAR_ICAL_URL`, `EVENT_SHEET_GAS_URL`, `EVENT_SHEET_GAS_TOKEN`, `LANGSMITH_API_KEY`, `CEREBRAS_API_KEY`

### Event KB sync

- Job: `event-kb-sync`
- Args: `python -m backend.scripts.sync_event_kb --include-spreadsheet`
- Image: same merge SHA image as Cloud Run service
- Latest execution: `event-kb-sync-92wns`
- Completion: `EXECUTION_SUCCEEDED`
- Completed at: 2026-05-17 16:29:36 UTC
- Scheduler: `event-kb-sync-daily`, `0 9 * * *`, `Asia/Tokyo`, `ENABLED`

### Live API

Health check:

```text
GET /health -> 200
status=ok
checks: api=ok, supabase=ok, llm_provider=configured
```

Date deterministic check:

```text
POST /api/chat "今日は何月何日ですか？" -> 200
answer: 今日は2026年5月18日（月曜日）です。
metadata.sources: ["system_clock"]
metadata.provider_called: false
metadata.route: general_knowledge
```

Weekly event source check:

```text
POST /api/chat "今週のエンジニアカフェのイベントを教えてください。" -> 200
metadata.route: event
metadata.sources: ["spreadsheet", "google_calendar", "connpass"]
answer includes 2026-05-19, 2026-05-20, and 2026-05-23 events.
```

Post-#875 live route smoke against `engineer-cafe-backend-00218-8zv`:

```text
POST /api/chat "メインホールはどこにありますか？" -> 200
route=facility-info, agent=FacilityAgent
answer mentions 1階メインホール, event-priority coworking, Wi-Fi, power.

POST /api/chat "営業時間とWi-Fiのパスワードを教えてください" -> 200
route=facility-info, agent=FacilityAgent
answer mentions 9:00〜22:00, engnecf-guest-2.4GHz/5GHz, akarenga-112years.

POST /api/chat "3Dプリンターの使い方を教えてください" -> 200
route=facility-info, agent=FacilityAgent
answer mentions MAKER'sスペース, free training, web reservation by previous day.

POST /api/chat "サイノカフェのランチは？" -> 200
route=saino-cafe, agent=BusinessInfoAgent
answer mentions sandwiches, waffles, prices, and drink-set discount.

POST /api/chat "ハッカソンの開催予定は？" -> 200
route=event, agent=EventAgent
answer mentions Connpass and https://engineercafe.connpass.com/.

POST /api/chat "コーヒーはいくらですか？" -> 200
route=saino-cafe, agent=BusinessInfoAgent
answer mentions blend coffee 380円 and single origin 460円.
```

### Vercel Preview

Original PR #852 preview deployment failed:

```text
[env-check] Missing required env var(s): NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
```

After syncing Preview / Development envs, redeploying the same PR preview succeeded:

```text
Deployment: dpl_BaPptKnk1KgRWn6TDyXGj6vBBdcD
Target: preview
Status: Ready
[env-check] Vercel production env check passed (4 required vars checked).
Build Completed in /vercel/output
Deployment completed
```

Production frontend smoke also returned HTTP 200 at `https://frontend-delta-six-20.vercel.app`.

PR #874 Vercel Preview also completed successfully after env parity was repaired:

```text
Deployment: GGugatUfdthE34EsnzBedLDFeZ2Q
Target: preview
Status: Ready
```

## Consequences

### Positive

- Date-only questions are deterministic and cheap.
- EventAgent now uses the Cafe-maintained spreadsheet as the curated source without requiring staff workflow changes.
- Google Calendar is still used, but it is no longer the only or highest-priority source.
- Audio failure modes now have bounded state recovery instead of indefinite thinking / silence.
- Preview deploys no longer fail just because a branch does not have branch-scoped public Supabase env.

### Negative

- `SheetsEventSource` depends on the GAS Web App availability and token binding.
- Browser fallback speech is less natural than primary TTS, so it is a reliability fallback, not a UX target.
- Direct DB E2E depends on runner network reachability to Supabase Postgres. PR #875 skips those tests when the runner cannot reach Postgres directly, while HTTP/Cloud Run live proof remains mandatory.
- Existing React hook dependency warnings remain in `VoiceInterface.tsx`; they are not introduced by this ADR but remain cleanup debt.

## Follow-up

- Keep Vercel Preview env in sync when adding any production-required frontend env.
- Add a scheduled env parity check if more Preview-only failures appear.
- Use a network-reachable runner or Cloud SQL/Auth Proxy style path before requiring direct DB E2E as a hard gate.
- Capture iPad Safari audio proof when the next onsite device window is available; CI proves browser flow, not physical speaker behavior.

## Approvals

- Proposed: Codex (2026-05-18) — Wave 2 implementation and live verification closeout.
- Accepted: Terada Kousuke (terisuke, 2026-05-18) — requested PR → merge → CI/CD → Google Cloud verification → issue close → ADR/docs closeout.

## References

- [PR #852](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/852)
- [PR #874](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/874)
- [PR #875](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/875)
- [Issue #855](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/855)
- [Issue #856](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/856)
- [Issue #857](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/857)
- [Issue #858](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/858)
- [Issue #770](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/770)
- [Issue #851](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/851)
