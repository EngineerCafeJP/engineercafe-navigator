# Production Readiness Follow-up Plan

Date: 2026-04-19

## 目的

2026-04-19 の live audit をもとに、現行コードと recent runtime evidence に基づく
production follow-up plan を整理する。

## 根拠

この plan の根拠:

- `develop` 上の repository state
- 2026-04-16 から 2026-04-19 UTC の Cloud Run logs
- 2026-04-19 UTC の recent Vercel production deploy
- 現在 open の GitHub Issues

Supabase CLI は linked project の確認まではできたが、同じ粒度の recent runtime log までは取得できなかった。
data-layer observability は follow-up のままです。

## すでに閉じている項目

- admin / cron / monitoring route 用 frontend middleware
- `API_SECRET_KEY` 未設定時の backend fail-closed startup
- production 相当環境での `slowapi` 必須化
- `ReceptionRepository` 経由の reception persistence
- voice / character capability discovery route

## 現在の優先順位

### P0: frontend -> backend auth drift 用の release guardrail

Issue:

- `#468`

理由:

- recent Cloud Run logs で `POST /api/character` の `403` が繰り返し出た
- その後の最新 production frontend validation は `200` で、恒常不具合というより deploy drift を示している

完了条件:

- production frontend route 用 authenticated smoke script がある
- deploy / promotion 手順に smoke gate が組み込まれている
- `BACKEND_API_KEY` と `API_SECRET_KEY` の ownership が文書化されている

### P1: live latency baseline と load testing

Issue:

- `#140`

理由:

- `/api/voice` は recent Cloud Run logs で最大 `62.68s`
- `/api/chat` と `/api/character` も slow threshold を繰り返し超過

完了条件:

- 再現可能な load script がある
- text / STT / TTS の p50 / p95 / p99 が文書化されている
- alpha / production の practical limit が書かれている

### P1: emotion / expression / animation contract の一本化

Issues:

- `#458`
- `#190`

理由:

- backend が partial emotion intensity を返している
- frontend に独自正規化が残っている
- live response verification でも mismatch が見えている

完了条件:

- shared emotion vocabulary が 1 つに定まっている
- intensity handling が explicit かつ consistent
- target-device validation で PASS / FAIL evidence が残る

### P1: multilingual quality の残件を閉じる

Issues:

- `#138`
- `#398`

理由:

- query 側の multilingual translation は改善済み
- ただし response consistency は全言語で target bar に達していない

完了条件:

- 英語 / 韓国語 / 中国語の evaluation target が current behavior に合わせて更新されている
- response-language correctness が可能な範囲で automated に確認されている
- 残課題が retrieval / generation / prompt-quality に切り分けられている

### P1: autonomous reception flow の継続実装

Issue:

- `#117`

理由:

- persistence base は強くなっているため、残作業は session durability ではなく behavior integration に寄せるべき

完了条件:

- 新規 / リピーター分岐が明示実装されている
- slide handoff が統合フローで検証されている
- autonomous flow 専用の verification path がある

## 運用ルール

1. runtime-sensitive な production readiness claim には live verification を添える
2. 過去の plan と矛盾する場合は superseded を明示する
3. frontend-authenticated smoke check が通るまで新 deploy を healthy とみなさない

## 参照

- [../STATUS.md](../STATUS.md)
- [../SECURITY.md](../SECURITY.md)
- [../DEPLOYMENT.md](../DEPLOYMENT.md)
- [../adr/008-operational-verification-and-deployment-guardrails.md](../adr/008-operational-verification-and-deployment-guardrails.md)
