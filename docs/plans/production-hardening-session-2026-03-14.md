# Production Hardening Session Plan

Last updated: 2026-03-14

## Goal

次セッションで、現在確認できている production blocker をまとめて潰せるようにするための実行計画。

この文書は次の 2 つを目的にしています。

1. 実装・運用・ドキュメントのズレを 1 本の修正セッションに集約する
2. ローカルの監査結果と GitHub 上の tracking issue を同期する

Tracking issue:

- GitHub Issue [#232](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/232): `stabilization: production hardening sprint from 2026-03-14 audit`

## Scope

今回の監査で優先度が高いと判断した対象:

- frontend admin / monitoring / cron route の認証不足
- backend API auth の fail-open 挙動
- reception session の in-memory 管理
- frontend と backend の API 契約不整合
- STT vocabulary の browser-direct backend call
- env / deployment / security / architecture docs の stale 状態

## Confirmed Findings

### A. Auth / Exposure

- `frontend/src/app/api/admin/knowledge/route.ts` は認証なしで KB 読み書き可能
- `frontend/src/app/api/cron/update-slides/route.ts` は無認証実行可能
- `frontend/src/app/api/alerts/webhook/route.ts` の `GET` は recent alerts を無認証で返す
- `frontend/src/middleware.ts` は未実装
- `backend/main.py` は `API_SECRET_KEY` 未設定時に auth が no-op

### B. Backend Reliability

- `backend/api/reception.py` は `_active_sessions` の in-memory store を使用
- reception router は他の protected API と同等の保護を受けていない
- rate limiting は `slowapi` 不在時に no-op

### C. Frontend / Backend Contract Mismatch

- `GET /api/voice?action=supported_languages` を UI が要求するが backend は `POST /api/voice` のみ
- `GET /api/character?action=supported_features` を UI が期待するが route は stub を返す
- STT vocabulary 管理は proxy を通さない経路が残る

### D. Documentation / Operational Drift

- top-level README は更新したが、`docs/api/`, `docs/architecture/`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `docs/development/` に stale 記述が多い
- Vercel / Mastra / RouterAgent / MemoryAgent / ClarificationAgent 前提の記述が現役文書に残っている
- 重複ファイル `docs/spaces/spaces/basement-spaces.md` は削除済み

## Execution Order For Next Session

### 1. Security and auth hardening

- add frontend middleware or equivalent route guard
- protect admin / monitoring / cron / alerts routes
- make backend production auth fail-closed
- add tests for unauthorized access

### 2. Reception hardening

- move reception session state to repository-backed persistence
- align reception endpoints with backend auth policy
- add restart / multi-instance tolerant behavior

### 3. Contract alignment

- unify voice supported-languages discovery
- unify character supported-features discovery
- route STT vocabulary through authenticated server-side proxy
- expand E2E / smoke coverage for these flows

### 4. Documentation cleanup phase 2

- rewrite API docs from actual routes
- rewrite deployment/security docs from actual infra
- either archive or clearly downgrade old development guides

## Suggested Acceptance Checks

- unauthorized access to admin / cron / alerts / monitoring returns `401` or `403`
- production startup fails when required backend secret is absent
- reception flow survives restart or uses durable recovery path
- frontend no longer depends on browser-direct backend admin calls
- `voice` and `character` feature-discovery paths reflect real backend behavior
- docs entrypoints point to only current-safe references

## Session Notes

- Existing related GitHub issues should be referenced rather than duplicated where possible
- Existing local modifications in `backend/main.py` and `backend/utils/structured_logging.py` are unrelated to this documentation pass and should be handled carefully in implementation work
