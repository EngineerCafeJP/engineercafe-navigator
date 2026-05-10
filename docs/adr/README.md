# ADR 一覧（Architecture Decision Records）

> **どこから来たか**: [Documentation hub](../README.md)（`docs/README.md`）の「迷ったときの読み順」を先に確認してください。
>
> ADR は「当時の決定と理由」の記録です。**現行の運用状態**は [STATUS.md](../STATUS.md) が正本です。

## まず読む（運用・キオスク UX に直結）


| ADR                                                                                                                 | 概要                                            |
| ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| [018 — Alpha fast response / assistant profile routing](018-alpha-fast-response-and-assistant-profile-routing.md)   | identity / fast path / モデル選択（メインワークフローと一体で読む） |
| [008 — Operational verification & deployment guardrails](008-operational-verification-and-deployment-guardrails.md) | 監査・デプロイ・検証のガードレール                             |
| [019 — Alpha live RAGAS case accounting](019-alpha-live-ragas-case-accounting.md)                                   | C-127 ケース数・収集の会計                              |
| [020 — Knowledge ingestion mutation contract](020-knowledge-ingestion-mutation-contract.md)                         | RAG 投入・変更・preview の契約                           |
| [021 — Frontend/backend separation before React/Vite migration](021-frontend-backend-separation-before-react-vite.md) | Next API proxy 廃止を React/Vite 移行より先に行う判断           |
| [022 — Reception slide static assets](022-reception-slide-static-assets.md)                                         | 受付PDF/音声を frontend static asset として扱う判断             |


## ワークフロー・音声・観測


| ADR                                                                     | 概要                              |
| ----------------------------------------------------------------------- | ------------------------------- |
| [005 — Backend-first logic](005-backend-first-logic.md)                 | ロジックをバックエンドに集約                  |
| [006 — LangGraph workflow redesign](006-langgraph-workflow-redesign.md) | LangGraph 再設計・多言語・受付            |
| [007 — STT parallel architecture](007-stt-parallel-architecture.md)     | Qwen primary + Vosk fallback など |
| [009 — Slow 403 / cold-start RCA](009-slow-403-cold-start-rca.md)       | Cloud Run cold-start と 403      |
| [010 — Qwen ONNX quantization spike](010-qwen-onnx-quantization.md)     | ONNX / INT4 実験                  |
| [016 — Qwen STT phase 2 profiling](016-qwen-stt-phase2-profiling.md)    | STT プロファイル                      |


## キャラ・長期記憶・インフラ観測


| ADR                                                                         | 概要                         |
| --------------------------------------------------------------------------- | -------------------------- |
| [011 — LTM cross-session design](011-ltm-cross-session-design.md)           | 長期記憶 recall                |
| [012 — LTM connection pool migration](012-ltm-connection-pool-migration.md) | LTM コネクションプール              |
| [013 — VRM fire-and-forget](013-vrm-fire-and-forget.md)                     | `/api/character/auto` 並列生成 |
| [014 — Observability phase 1a](014-observability-phase1.md)                 | 構造化ログ                      |
| [017 — Observability phase 1b](017-observability-phase1b.md)                | Terraform メトリクス・アラート       |


## 関連ドキュメント

- [architecture/SYSTEM-ARCHITECTURE.md](../architecture/SYSTEM-ARCHITECTURE.md)
- ルート [CLAUDE.md](../../CLAUDE.md)（コマンド・API フロー制約）

## メモ

- ADR 番号は 005 以降を運用しており、**015 は欠番**です（採番のみ存在し、文書化に至らなかったため）。新しい ADR を起票する際は 023 から付番してください。
- 001–004 についても、本リポジトリでは初期から ADR 005 以降のみを保守しています。
