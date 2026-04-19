# Documentation Map

> 2026-04-19 時点での現役ドキュメント案内です。まずこのページから参照してください。

## まず読む文書

- [../README.md](../README.md): プロジェクト全体の現在地
- [STATUS.md](STATUS.md): 実装済み事項と、いま残っている本当の運用リスク
- [SECURITY.md](SECURITY.md): 現在の auth 連鎖と残課題
- [DEPLOYMENT.md](DEPLOYMENT.md): Vercel + Cloud Run の現行デプロイ運用
- [plans/production-readiness-followup-2026-04-19.md](plans/production-readiness-followup-2026-04-19.md): 直近の実装計画
- [adr/008-operational-verification-and-deployment-guardrails.md](adr/008-operational-verification-and-deployment-guardrails.md): 2026-04-19 監査を踏まえた運用上の意思決定

## 現役ドキュメント

### 運用と現況

- [STATUS.md](STATUS.md)
- [SECURITY.md](SECURITY.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [CHANGELOG.md](CHANGELOG.md)
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

## 歴史資料として読む文書

以下は履歴として残すが、現行の判断基準にはしない文書です。必要な場合は superseded 注記と
[STATUS.md](STATUS.md) を先に確認してください。

- `docs/plans/production-hardening-session-2026-03-14.md`
- `docs/plans/alpha-trial-p1-remediation-2026-04-13.md`
- `docs/plans/deployment-readiness-2026-03-15.md`

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

## 直近の次アクション

- deploy smoke gate を実装し、`docs/DEPLOYMENT.md` の手順を自動化へ寄せる
- API / architecture / development 文書の stale 記述を段階的に更新または archive に移す
- Supabase の運用ログ確認手順を別途整備する
