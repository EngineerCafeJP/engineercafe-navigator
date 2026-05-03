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

PR #674, #675, #676 に加えて、#692, #693, #695, #699, #700, #701, #702, #703, #705, #707, #709 を develop に merge 済みです。
#692 は C-127 accounting を修正し、run `25270459825` で `requested=127` を確認しました。
ただし同 run は live `/api/chat` 429 により `evaluated=35`, `collection_errors=92`
で、C-127 completion proof にはなっていません。#695 は 429 pacing / retry 修正として merge 済みで、
post-#695/#701 C-127 proof は run `25272361091` で確認中です。#693 は Q suite 残 failure 修正として merge 済みで、
同 run で post-deploy proof を確認中です。#705/#709 は voice timeout budget、#707 は mobile audio playback の
実装修正として merge/deploy 済みです。#696 は live proof 後に close 済み、#697/#698 は live/device proof まで open 維持です。

Resolved:

- #658 STT / voice preflight: run `25258764528` が `suites=stt,v` PASS
- #659 B routing / slide live smoke: targeted B run `25254789937` が `64 passed, 0 warned, 0 failed`
- #660 H-UI Welcome UI live scenario
- #661 compact artifact visibility
- #662 Supabase UUID / Cloud Run log hygiene
- #671 RAGAS direct OpenAI provider secret
- #691 C-127 manifest accounting: PR #692
- #694 C-127 `/api/chat` 429 collection blocker: PR #695 merged, live proof pending
- #700 Welcome camera-flow guard
- #702 alpha Cloud Run log-noise reduction
- #703 STT warmup before voice live
- #696 voice backend timeout budget: PR #705/#709 merged/deployed and closed after live proof
- #697 iOS delayed TTS playback: PR #707 merged, device proof pending
- #698 Android large-audio playback: PR #707 merged, device proof pending

Still active:

- #583 C-127 completion proof: run `25272361091` must collect/evaluate `127/127`
- #653 / #672 Q/C answer quality
- #670 RAGAS full-run speed / telemetry closeout
- #697 / #698 live/device proof
- #611 / #584 / #585 live-only proof / issue-scope decisions

## 直近の次アクション

- run `25272361091` を監視し、full suite の outcome / artifact を正本として確認する
- C-127 で `requested=127`, `evaluated=127`, `collection_errors=0` を確認する
- Q suite で #653 の残 failure が 0 になったか確認する
- C-127 が完走してから #672 の answer/source quality を case-level telemetry で修正する
- #670 は post-#695/#701 C-127 artifact で provider/model/progress と compact report が十分に残ることを確認して close 判断する
