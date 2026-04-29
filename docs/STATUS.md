# 現在の状態

Last updated: 2026-04-30

## 概要

このページは、`develop` 上の現行コード、2026-04-19 の live audit、2026-04-29 の実機音声 UX 確認をもとに更新しています。

確認元:

- 2026-04-16 から 2026-04-19 UTC の Cloud Run ログ
- 2026-04-19 UTC の直近 Vercel production deploy
- 2026-04-29 JST の mobile / kiosk 実地確認 screenshot と Cloud Run structured logs
- 現在 open の GitHub Issue

Supabase については、CLI で linked project の確認まではできましたが、このセッションでは recent runtime log
を同じ粒度で取得できませんでした。データ層の詳細な運用確認には、dashboard か token 付きの別フローが必要です。

現状の結論:

- キオスクのコアフロー自体は実装済み
- ただし 2026-04-29 の実地確認により、alpha release はそのまま GO できない
- 現在の主リスクは「未実装の基本機能」ではなく「会話 UX の基本品質、実測 latency、route 整合性」

特に優先度が高いのは次の 5 点です。

1. identity / help / capability 質問が provider 自己紹介や雑な general answer に落ちる問題
2. rank graph に入らない一般質問が RAG miss -> web search -> heavyweight LLM に流れる latency 問題
3. stale request type / mode により、次 turn が SlideAgent など誤 route に流れる問題
4. voice / chat / TTS の実機 p95 latency が alpha UX に達していない問題
5. deploy 時の frontend -> backend 認証ドリフト

現行の実装判断は [ADR 018](adr/018-alpha-fast-response-and-assistant-profile-routing.md) と
[Alpha Fast Response Implementation Plan](plans/alpha-fast-response-implementation-2026-04-30.md) を優先する。

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

- `#618`: daily / identity / general fallback の lightweight no-thinking model 分離
- `#617`: stale request type / mode による誤 route
- `#616`: Welcome camera/OCR-first と push-to-talk UX
- `#615`: identity / general question の回答品質
- `#613`: 実機音声 turn latency
- `#611`: Cerebras dynamic filler / fast first-response path
- `#468`: deploy-time auth drift guardrails
- `#140`: load / latency baseline
- `#458`: emotion / expression / animation alignment
- `#190`: live character validation
- `#117`: autonomous reception flow integration
- `#138`: multilingual quality improvements
- `#398`: multilingual RAGAS improvement phase 2

## 推奨する実装順

1. identity / help / capability fast path を実装する (`#615`, `#618`)
2. General fallback を daily/general light と current-info search path に分ける (`#618`, `#617`)
3. Gemini / Cerebras 候補を公式 API availability + live benchmark で選定する (`#611`, `#613`)
4. Welcome camera/OCR-first と push-to-talk UX を直す (`#616`)
5. deploy-time authenticated smoke check を維持・強化する (`#468`)
6. live latency baseline と load test を整備する (`#140`)
7. emotion -> expression -> animation の契約を一本化する (`#458`, `#190`)
8. multilingual quality を評価基準込みで閉じる (`#138`, `#398`)
9. reception の残作業を行動フロー中心に進める (`#117`)

## 参照

- [SECURITY.md](SECURITY.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [plans/alpha-fast-response-implementation-2026-04-30.md](plans/alpha-fast-response-implementation-2026-04-30.md)
- [adr/018-alpha-fast-response-and-assistant-profile-routing.md](adr/018-alpha-fast-response-and-assistant-profile-routing.md)
- [plans/production-readiness-followup-2026-04-19.md](plans/production-readiness-followup-2026-04-19.md)
- [adr/008-operational-verification-and-deployment-guardrails.md](adr/008-operational-verification-and-deployment-guardrails.md)
