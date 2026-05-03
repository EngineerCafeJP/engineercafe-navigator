# 現在の状態

Last updated: 2026-05-03

## 概要

このページは、`develop` 上の現行コード、2026-04-19 の live audit、2026-04-29 の実機音声 UX 確認、
2026-05-02 の alpha-live-verification full run / targeted C run、2026-05-03 の PR #674/#675/#676
deploy verification、PR #692/#693/#695/#699/#700/#701/#702/#703/#705/#707/#709 merge 後の alpha issue 状態をもとに更新しています。

確認元:

- 2026-04-16 から 2026-04-19 UTC の Cloud Run ログ
- 2026-04-19 UTC の直近 Vercel production deploy
- 2026-04-29 JST の mobile / kiosk 実地確認 screenshot と Cloud Run structured logs
- 2026-05-02 JST の `alpha-live-verification` run `25244933308` / `25247945549`
- 2026-05-03 JST の targeted B run `25254789937` と Cloud Run revision `engineer-cafe-backend-00148-82c`
- 2026-05-03 JST の post-#692 C-127 run `25270459825`
- 2026-05-03 JST の post-#709 Cloud Run deploy revision `engineer-cafe-backend-00162-mlr`
- 2026-05-03 JST の SHA-matched full alpha-live-verification run `25272361091`
- 現在 open の GitHub Issue

Supabase については、CLI で linked project の確認まではできましたが、このセッションでは recent runtime log
を同じ粒度で取得できませんでした。データ層の詳細な運用確認には、dashboard か token 付きの別フローが必要です。

現状の結論:

- キオスクのコアフロー自体は実装済み
- alpha live verification workflow は Cloud Run SHA match 付きで end-to-end 実行できる
- RAGAS evaluator は direct OpenAI で動くことを確認済み
- PR #674/#675/#676 により、B routing / slide live smoke、Welcome UI、compact artifacts、Supabase UUID log hygiene は解消済み
- PR #692 により C-127 manifest accounting は解消済み。run `25270459825` で `requested=127` になったが、
  live `/api/chat` 429 により `evaluated=35`, `collection_errors=92` だった
- PR #693 は Q quality 修正、PR #695/#701 は C-127 pacing / coverage 修正、PR #699/#700/#702/#703 は C source / live harness / log hygiene hardening として merge 済み
- PR #705/#709 は voice backend timeout / Vercel budget 修正、PR #707 は iOS/Android mobile audio 修正として merge 済み
- 最新 full suite run `25272361091` は Cloud Run revision `engineer-cafe-backend-00162-mlr` / SHA `6ce1ac81983c7ae53ddfdfc58eba1ee043a83fa8` で実行中
- ただし latest `suites=all` の green proof はまだなく、alpha release はまだ GO できない
- 現在の主リスクは「未実装の基本機能」ではなく「会話 UX の基本品質、実測 latency、route 整合性、評価 gate の透明性」

特に優先度が高いのは次の 5 点です。

1. 最新 full suite run `25272361091` の outcome / artifact を確認する
2. C-127 が live `/api/chat` 429 なしで `127/127` collect/evaluate できることの証明
3. Q suite の残 failure が #693 後に解消されたことの証明
4. #697/#698 の mobile playback live-device proof
5. RAGAS full-run speed / telemetry の operational closeout

現行の実装判断は [ADR 018](adr/018-alpha-fast-response-and-assistant-profile-routing.md) と
[Alpha Remediation Plan 2026-05-02](plans/alpha-remediation-plan-2026-05-02.md) を優先する。

## 2026-05-03 Alpha Remediation Snapshot

最新の deployed staging / harness 状態:

- develop SHA: `6ce1ac81983c7ae53ddfdfc58eba1ee043a83fa8`
- Cloud Run revision: `engineer-cafe-backend-00162-mlr`
- Traffic: latest revision 100%
- Health: `/health` OK
- develop CI after PR #709: `25271932807`, success including frontend voice-live and `ci-success`
- Targeted B run: `25254789937`
- B result: `64 passed, 0 warned, 0 failed`
- B1-BIZ-003: `土日祝日も利用できますか。` -> `business_info`, `1258ms`
- Cloud Logging UUID / reception persistence errors during B run window: 0 rows
- PR #692 merge SHA: `d74264e808e9b2a0244d3a1a9e5dfe12671530ea`
- Post-#692 C-127 run: `25270459825`, `requested=127`, `evaluated=35`, `collection_errors=92`
- PR #693 merge SHA: `14cb8e5b3c4f9711a77c634d3db80f8bf4f80efd`
- PR #695 merge SHA: `ed25199e4c7104ac0f6e2f027c4fdadd72280182`
- PR #699/#700/#701/#702/#703/#705/#707/#709 are all included in deployed Cloud Run SHA `6ce1ac81983c7ae53ddfdfc58eba1ee043a83fa8`
- Full alpha-live-verification run `25272361091` is in progress with `suites=all`, `c_ragas_suite=alpha-127`, and SHA match required

Resolved or implemented in the 2026-05-03 remediation pass:

- #659: B routing / slide live smoke
- #660: Welcome UI live scenario
- #661: compact artifact visibility
- #662: Supabase UUID / Cloud Run log hygiene
- #671: RAGAS provider secret issue
- #691: C-127 manifest accounting
- #694: C-127 `/api/chat` 429 collection blocker implementation merged in PR #695; live proof pending
- #700: Welcome camera-flow guard
- #702: alpha Cloud Run log-noise reduction
- #703: STT warmup before voice live

Still blocking or important:

- #583: C-127 completion remains P0 until post-#695/#701 run collects/evaluates `127/127` with `collection_errors=0`.
- #696: voice backend timeout / warmup UX is closed after post-#705/#709 live proof.
- #697: iOS delayed TTS playback remains P0 until post-#707 iPad/iPhone Safari proof.
- #698: Android large-audio playback remains P1 until post-#707 Android phone proof or explicit alpha demotion.
- #653: Q quality remains P1 until post-#693 `suites=q` rerun has 0 failures.
- #672: C answer/source quality remains P1, but current C metrics are not release-proof until C-127 collection completes.
- #670: RAGAS telemetry is implemented, but post-#695/#701 C-127 artifact still needs operational proof before close.

## 2026-05-02 Alpha Live Verification Snapshot

最新の正本は [Alpha Live Verification Status 2026-05-02](testing/alpha-live-verification-status-2026-05-02.md)。

- Full run: `25244933308`
- Targeted C/RAGAS run: `25247945549`
- Cloud Run revision: `engineer-cafe-backend-00144-q85`
- develop SHA: `fa7745b7420c0709fcff950ed3bf4c090f0dfc55`
- SHA match: pass
- Full run conclusion: failure
- Direct OpenAI RAGAS: confirmed after GitHub Secret `OPENAI_API_KEY` sync

Resolved in the 2026-05-02 / 2026-05-03 remediation pass:

- #671: RAGAS provider secret issue. `OPENAI_API_KEY` is now available to the workflow, and C uses direct OpenAI.
- #659: B routing / slide live smoke.
- #660: H-UI Welcome UI live scenario.
- #661: compact artifact visibility.
- #662: Supabase UUID/log hygiene.

Still blocking:

- #583: C-127 completion proof after #695
- #653 / #672: Q/C answer quality
- #670: full-run RAGAS speed / telemetry closeout

## 実装済みとして確認できたこと

### Frontend

- Next.js 15 App Router が現行 frontend
- `frontend/src/lib/api/backend-proxy.ts` の `backendFetch()` 経由で backend proxy を実施
- `backendFetch()` は server-side で `BACKEND_API_KEY` を `X-API-Key` として付与
- `frontend/src/middleware.ts` で `/api/admin/*`, `/api/cron/*`, `/api/monitoring/*` を保護
- `GET /api/voice?action=supported_languages` は実装済み
- `GET /api/character?action=supported_features` は実装済み

### Backend

- `backend/main.py` は `ENVIRONMENT=production` かつ `API_SECRET_KEY` 未設定時に起動失敗
- `verify_api_key` は fail-open ではなく fail-closed
- `slowapi` は production 相当環境で必須
- 受付セッションは `ReceptionRepository` 経由で永続化される
- OCR / reception / voice / character / slides / admin knowledge API は存在し、現行構成に接続されている

### ドキュメント基準

- `docs/STATUS.md`, `docs/SECURITY.md`, `docs/DEPLOYMENT.md` は 2026-04-19 の監査結果に合わせて更新済み
- 2026-03-14 と 2026-04-13 の計画文書は履歴として残すが、現行計画ではないことを明示した

## 本番運用で確認した事実

### P0: identity / help / capability 質問は deterministic fast path が必要

2026-04-29 JST の実地確認で、`あなたの名前は` に対して provider 自己紹介に寄った回答が返った。
これは施設案内 kiosk として誤りであり、LLM provider の変更だけでは再発を防げない。

現在の判断:

- `あなたの名前は`, `あなたは誰`, `何ができますか`, `help` は LLM / RAG / web search に渡さない
- Engineer Cafe Navigator としての canonical response を返す
- provider self-disclosure は alpha blocker として 0 件にする

関連 Issue:

- `#615`: identity / general question の回答品質
- `#618`: daily / identity / general fallback の lightweight no-thinking model 分離

### P0: general fallback は search path と fast path を分ける

2026-04-29 JST の Cloud Run logs では、`あなたの名前は` の chat が約 10s かかり、
`general_knowledge` route で knowledge cache / web search が絡んだ。RAG graph に入らないだけで
web search に落ちる設計は、一般質問と日常会話の UX に向かない。

現在の判断:

- `assistant_profile`: deterministic
- `daily_conversation`: lightweight / no-search
- `general_light`: lightweight / no-search
- `current_info`: calendar / Tavily / web search が必要な場合だけ search

関連 Issue:

- `#618`
- `#611`: Cerebras dynamic filler / fast first-response path
- `#613`: 実機音声 turn latency

### P0: stale request type / mode は route の根拠にしない

2026-04-29 JST の実地確認で、`明日のイベントについて教えて` が SlideAgent の説明へ流れた。
ログ上も previous request type が残っていることが確認された。前 turn の request type は context であって、
current turn の high-confidence intent なしに route を固定してはいけない。

関連 Issue:

- `#617`: stale request type / mode による誤 route

### Critical: frontend -> backend auth drift により一時的な 403 が出る可能性がある

2026-04-16 から 2026-04-19 UTC の Cloud Run ログで確認したこと:

- `403` 応答: 145 件
- 該当 protected route: `POST /api/character`

一方、2026-04-19 08:17 UTC の最新 production frontend 経由の確認では:

- `/api/character` は `200`
- `/api/voice?action=supported_languages` は `200`

解釈:

- 常時故障ではない
- `BACKEND_API_KEY` と `API_SECRET_KEY` の不整合、または deploy / promotion 時の検証不足が本質的なリスク

関連 Issue:

- `#468`: deploy smoke gate による auth drift 防止

### Critical: live latency が alpha 水準としてまだ弱い

同じ 3 日間の Cloud Run ログで slow request を確認:

- `/api/voice`: slow request 15 件、最大 `62.68s`
- `/api/character`: slow threshold 超過が 8 件
- `/api/chat`: slow threshold 超過が 7 件

解釈:

- 現在のサービスは利用可能だが、alpha kiosk latency baseline を主張できる状態ではない
- 既存の backend test だけでは不十分で、live latency を release 判断に組み込む必要がある
- 2026-04-29 の実測では STT / chat / TTS のどれも blocker になりうるため、区間別に p50 / p95 を追う

関連 Issue:

- `#140`: 負荷テストとパフォーマンス検証
- `#613`: 実機音声 turn latency

### High: 感情タグとアニメーション契約はまだずれている

現在のコードと live response の両方で、Issue `#458` の症状を確認:

- backend emotion mapping は `happy: 0.8` のような partial intensity を返す
- frontend 側に独自正規化が残っている
- production 確認時の `/api/character` 応答でも mixed intensity を返した

関連 Issue:

- `#458`: emotion / expression / animation の整合
- `#190`: target-device での character validation

### High: 多言語品質は改善済みだが未完了

現状:

- query 側の multilingual tRAG translation は en / ko / zh に入っている
- response language の安定性は ja / en が中心
- ko / zh は response translation より multilingual generation 依存がまだ大きい

関連 Issue:

- `#138`: 多言語品質改善
- `#398`: multilingual RAGAS / response stabilization

### Medium: frontend env validation は補助的で authoritative ではない

- `frontend/src/lib/env.ts` は useful な contract を示している
- ただし実行時はなお `process.env` の直接参照が多く、単独で authoritative とは言えない

### Medium: Supabase observability は CLI だけでは不足

- `supabase projects list` は成功
- ただし authenticated な remote inspect / recent log まではこのセッションで取得できなかった

## いま重要な Open Issues

- `#583`: C-127 completion proof
- `#653`: Q-content quality
- `#672`: Direct OpenAI C/RAGAS JA target miss
- `#670`: C/RAGAS runtime and telemetry
- `#611`: Cerebras dynamic filler / fast first-response path

## 推奨する実装順

1. run `25272361091` または targeted `suites=c-127` rerun で #583 / #670 / #672 の判断材料を取る
2. PR #693 後の `suites=q` rerun で #653 を close できるか判断する
3. C-127 が `127/127` 完走してから C answer/source quality を直す (`#672`)
4. RAGAS full-run telemetry / runtime を close 判断する (`#670`)
5. #611 / #584 / #585 の live-only proof を収集するか、alpha GO から demote / waive する

## 参照

- [SECURITY.md](SECURITY.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [testing/alpha-live-verification-status-2026-05-02.md](testing/alpha-live-verification-status-2026-05-02.md)
- [plans/alpha-remediation-plan-2026-05-02.md](plans/alpha-remediation-plan-2026-05-02.md)
- [plans/alpha-fast-response-implementation-2026-04-30.md](plans/alpha-fast-response-implementation-2026-04-30.md)
- [adr/018-alpha-fast-response-and-assistant-profile-routing.md](adr/018-alpha-fast-response-and-assistant-profile-routing.md)
- [plans/production-readiness-followup-2026-04-19.md](plans/production-readiness-followup-2026-04-19.md)
- [adr/008-operational-verification-and-deployment-guardrails.md](adr/008-operational-verification-and-deployment-guardrails.md)
