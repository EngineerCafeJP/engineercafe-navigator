# Documentation Map

> 2026-05-03 時点での現役ドキュメント案内です。まずこのページから参照してください。

## まず読む文書

- [../README.md](../README.md): プロジェクト全体の現在地
- [STATUS.md](STATUS.md): 実装済み事項と、いま残っている本当の運用リスク
- [testing/alpha-live-verification-status-2026-05-02.md](testing/alpha-live-verification-status-2026-05-02.md): 最新 alpha live verification 結果
- [plans/alpha-remediation-plan-2026-05-02.md](plans/alpha-remediation-plan-2026-05-02.md): 次実装順
- [SECURITY.md](SECURITY.md): 現在の auth 連鎖と残課題
- [DEPLOYMENT.md](DEPLOYMENT.md): Vercel + Cloud Run の現行デプロイ運用
- [plans/alpha-fast-response-implementation-2026-04-30.md](plans/alpha-fast-response-implementation-2026-04-30.md): Alpha Phase 4 の高速応答 / identity routing 実装計画
- [adr/018-alpha-fast-response-and-assistant-profile-routing.md](adr/018-alpha-fast-response-and-assistant-profile-routing.md): identity / general fallback / fast model 選定の現行 ADR
- [plans/production-readiness-followup-2026-04-19.md](plans/production-readiness-followup-2026-04-19.md): 2026-04-19 時点の production readiness follow-up
- [adr/008-operational-verification-and-deployment-guardrails.md](adr/008-operational-verification-and-deployment-guardrails.md): 2026-04-19 監査を踏まえた運用上の意思決定

## 現役ドキュメント

### 運用と現況

- [STATUS.md](STATUS.md)
- [SECURITY.md](SECURITY.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [CHANGELOG.md](CHANGELOG.md)
- [testing/alpha-live-verification-status-2026-05-02.md](testing/alpha-live-verification-status-2026-05-02.md)
- [testing/alpha-final-scenarios.md](testing/alpha-final-scenarios.md)
- [plans/alpha-remediation-plan-2026-05-02.md](plans/alpha-remediation-plan-2026-05-02.md)
- [plans/alpha-fast-response-implementation-2026-04-30.md](plans/alpha-fast-response-implementation-2026-04-30.md)
- [plans/production-readiness-followup-2026-04-19.md](plans/production-readiness-followup-2026-04-19.md)

### 実装と開発導線

- [DEVELOPER-GUIDE.md](DEVELOPER-GUIDE.md)
- [testing/TESTING-GUIDE.md](testing/TESTING-GUIDE.md)
- [../frontend/README.md](../frontend/README.md)
- [../backend/README.md](../backend/README.md)

### 現行 ADR

- [adr/005-backend-first-logic.md](adr/005-backend-first-logic.md)
- [adr/006-langgraph-workflow-redesign.md](adr/006-langgraph-workflow-redesign.md)
- [adr/007-stt-parallel-architecture.md](adr/007-stt-parallel-architecture.md)
- [adr/008-operational-verification-and-deployment-guardrails.md](adr/008-operational-verification-and-deployment-guardrails.md)
- [adr/018-alpha-fast-response-and-assistant-profile-routing.md](adr/018-alpha-fast-response-and-assistant-profile-routing.md)

## 歴史資料として読む文書

以下は履歴として残すが、現行の判断基準にはしない文書です。必要な場合は superseded 注記と
[STATUS.md](STATUS.md) を先に確認してください。

- `docs/plans/production-hardening-session-2026-03-14.md`
- `docs/plans/alpha-trial-p1-remediation-2026-04-13.md`
- `docs/plans/deployment-readiness-2026-03-15.md`
- `docs/testing/alpha-live-verification-status-2026-04-25.md`
- `docs/plans/production-readiness-followup-2026-04-19.md` は履歴ではないが、2026-04-30 以降の alpha blocker 判断では `alpha-fast-response-implementation-2026-04-30.md` を優先する

## 読むときに注意が必要な文書

以下は一部に旧構成や移行期前提が残っているため、参照時に現行コードと `STATUS.md` で確認が必要です。

- `docs/api/`
- `docs/architecture/`
- `docs/development/` 配下の多くの文書
- `docs/PRESENTATION-MODE-GUIDE.md`
- `frontend/VOICE_UI_PLAN.md`

主なズレ:

- Mastra 移行期や旧エージェント構成の説明
- 現在は閉じた blocker を open とみなす記述
- 2026-03 時点の運用前提や release 手順

## アーカイブ

- [archive/README.md](archive/README.md): 履歴資料の入口
- `archive/migration/`: Mastra -> LangGraph 移行期の詳細資料
- `archive/frontend-docs-old/`: 旧 frontend 文書群

## 2026-05-03 Alpha Remediation Snapshot

PR #674, #675, #676 を develop に merge し、Cloud Run staging
`engineer-cafe-backend-00148-82c` / `d789a2cd899779423947c40a3d65e19382f52d30`
で検証済みです。

Resolved:

- #659 B routing / slide live smoke: targeted B run `25254789937` が `64 passed, 0 warned, 0 failed`
- #660 H-UI Welcome UI live scenario
- #661 compact artifact visibility
- #662 Supabase UUID / Cloud Run log hygiene
- #671 RAGAS direct OpenAI provider secret

Still active:

- #658 STT long-tail latency
- #657 / #583 RAGAS 29-case vs 127-case coverage reconciliation
- #653 / #672 Q/C answer quality
- #670 RAGAS full-run speed / telemetry closeout

## 直近の次アクション

- #658 STT long-tail latency の fallback threshold / warmup / timeout 前 mitigation を実装する
- #657 / #583 の alpha gate coverage を launch gate と diagnostic/soak に分けて文書化・実装する
- #653 / #672 の Q/C answer quality failure を case-level telemetry で修正する
- #670 は full C/Q run の artifact で provider/model/progress が十分に残ることを確認して close 判断する
