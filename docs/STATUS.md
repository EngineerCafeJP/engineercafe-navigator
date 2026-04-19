# 現在の状態

Last updated: 2026-04-19

## 概要

このページは、`develop` 上の現行コードと 2026-04-19 に実施した live audit をもとに更新しています。

確認元:

- 2026-04-16 から 2026-04-19 UTC の Cloud Run ログ
- 2026-04-19 UTC の直近 Vercel production deploy
- 現在 open の GitHub Issue

Supabase については、CLI で linked project の確認まではできましたが、このセッションでは recent runtime log
を同じ粒度で取得できませんでした。データ層の詳細な運用確認には、dashboard か token 付きの別フローが必要です。

現状の結論:

- キオスクのコアフロー自体は実装済み
- 現在の主リスクは「未実装の基本機能」ではなく「運用と整合性」

特に優先度が高いのは次の 4 点です。

1. deploy 時の frontend -> backend 認証ドリフト
2. voice / chat 系の本番レイテンシ悪化
3. 感情タグと VRM / VRMA 契約の不整合
4. 多言語品質の未完了部分

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

### Critical: live latency が production 水準としてはまだ弱い

同じ 3 日間の Cloud Run ログで slow request を確認:

- `/api/voice`: slow request 15 件、最大 `62.68s`
- `/api/character`: slow threshold 超過が 8 件
- `/api/chat`: slow threshold 超過が 7 件

解釈:

- 現在のサービスは利用可能だが、production latency baseline を主張できる状態ではない
- 既存の backend test だけでは不十分で、live latency を release 判断に組み込む必要がある

関連 Issue:

- `#140`: 負荷テストとパフォーマンス検証

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

- `#468`: deploy-time auth drift guardrails
- `#140`: load / latency baseline
- `#458`: emotion / expression / animation alignment
- `#190`: live character validation
- `#117`: autonomous reception flow integration
- `#138`: multilingual quality improvements
- `#398`: multilingual RAGAS improvement phase 2

## 推奨する実装順

1. deploy-time authenticated smoke check を入れる (`#468`)
2. live latency baseline と load test を整備する (`#140`)
3. emotion -> expression -> animation の契約を一本化する (`#458`, `#190`)
4. multilingual quality を評価基準込みで閉じる (`#138`, `#398`)
5. reception の残作業を行動フロー中心に進める (`#117`)

## 参照

- [SECURITY.md](SECURITY.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [plans/production-readiness-followup-2026-04-19.md](plans/production-readiness-followup-2026-04-19.md)
- [adr/008-operational-verification-and-deployment-guardrails.md](adr/008-operational-verification-and-deployment-guardrails.md)
