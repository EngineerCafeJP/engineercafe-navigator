# Documentation hub（`docs/`）

> **運用状態の正本**は [STATUS.md](STATUS.md) です（live の run ID はそこに集約。**2026-05-05** に git 由来の「同期メモ」を追記済み。ワークフローを再実行していない限り NO-GO 記録の日付は 05-03 のまま）。
>
> このページは `docs/` 以下とルート README を繋ぐ**索引**です。
>
> 最終整理: 2026-05-05 — README・開発ガイドの重複を削り、スナップショットは STATUS に一本化。

## 言語方針

`docs/` 配下のドキュメントおよびモノレポ内の補助ドキュメント（`frontend/README.md`・`backend/README.md` を含む）は **本文を日本語で統一**します（コード・識別子・環境変数名・公式サービス名・ADR ファイル名は英語のままで構いません）。

リポジトリ全体の英語入口はルートの [README.md](../README.md) と [README-EN.md](../README-EN.md) のみとします。

## 迷ったときの読み順

1. [STATUS.md](STATUS.md) … alpha・ゲート・残リスク
2. [adr/018-alpha-fast-response-and-assistant-profile-routing.md](adr/018-alpha-fast-response-and-assistant-profile-routing.md) … fast path / identity まわりの現行 ADR
3. [DEVELOPER-GUIDE.md](DEVELOPER-GUIDE.md) … コミュニケーション規約・クイックスタート・開発タスク
4. [architecture/SYSTEM-ARCHITECTURE.md](architecture/SYSTEM-ARCHITECTURE.md) … システム構成（詳細はコード・ADR と突合）
5. [setup-guide.md](setup-guide.md) / [DEPLOYMENT.md](DEPLOYMENT.md) … セットアップ・デプロイ運用

ルートの [CLAUDE.md](../CLAUDE.md) は Cursor / Claude Code 向けの **コマンド・CI・硬性制約**（Frontend は Tailwind v3 固定など）です。

## 運用・セキュリティ・デプロイ

| 文書 | 内容 |
| --- | --- |
| [STATUS.md](STATUS.md) | 現在状態・証跡付きサマリ（**ここだけがスナップショットの正本**） |
| [SECURITY.md](SECURITY.md) | 認証連鎖と論点 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Vercel + Cloud Run |
| [CHANGELOG.md](CHANGELOG.md) | リポジトリレベルの変更ログ |

## 開発・テスト

| 文書 | 内容 |
| --- | --- |
| [DEVELOPER-GUIDE.md](DEVELOPER-GUIDE.md) | **現行の開発者入口**（言語ルール・テスト・CI） |
| [development/ENVIRONMENT-VARIABLES.md](development/ENVIRONMENT-VARIABLES.md) | env 一覧（冒頭の注意どおり STATUS・コードと突合） |
| [development/AGENTS.md](development/AGENTS.md) | 開発モード記録（一部は旧情報あり） |
| [testing/TESTING-GUIDE.md](testing/TESTING-GUIDE.md) | テスト運用 |
| [../frontend/README.md](../frontend/README.md) | フロントの環境変数・API プロキシ |
| [../backend/README.md](../backend/README.md) | バックエンドのエンドポイント早見表 |

長文かつ Mastra 時代の記述が残る `development/DEVELOPER-GUIDE.md` は [§歴史資料](#歴史資料) に退け、入口としては使わないでください。

## アーキテクチャ・API

| 文書 | 内容 |
| --- | --- |
| [architecture/SYSTEM-ARCHITECTURE.md](architecture/SYSTEM-ARCHITECTURE.md) | レイヤ・データフロー |
| [architecture/HIERARCHICAL-RAG-ARCHITECTURE.md](architecture/HIERARCHICAL-RAG-ARCHITECTURE.md) | 階層 RAG の設計議論（実装はコードと突合） |
| [api/API-ja.md](api/API-ja.md) | API 説明（OpenAPI と乖離がある場合は **コード優先**） |

## 計画（plans）

| 文書 | メモ |
| --- | --- |
| [plans/comprehensive-refactoring-plan-2026-05-05.md](plans/comprehensive-refactoring-plan-2026-05-05.md) | 構造リファクタの計画のみ（実装は別 PR） |
| [plans/alpha-reset-plan-2026-05-03.md](plans/alpha-reset-plan-2026-05-03.md) | Alpha reset（STATUS と対応） |
| [plans/alpha-ui-e2e-hardening-2026-04-12.md](plans/alpha-ui-e2e-hardening-2026-04-12.md) | Voice E2E ワークフロー関連 |

## ルート README

[../README.md](../README.md) … リポジトリ全体の最短入口（詳細は本ページと STATUS へ）。

## 参照時に注意が必要な文書

一部に旧アーキテクチャ・移行期前提が残ります。**判断は [STATUS.md](STATUS.md) と現行コードを優先**してください。

## 歴史資料

| 入口 | 内容 |
| --- | --- |
| [archive/README.md](archive/README.md) | アーカイブ索引 |
| [development/DEVELOPER-GUIDE.md](development/DEVELOPER-GUIDE.md) | **旧長文開発ガイド**（参照用のみ） |
| [archive/migration/](archive/migration/) | Mastra → LangGraph 移行期資料 |

## Alpha / verification の結果ログ

- [testing/alpha-live-verification-status-2026-05-03.md](testing/alpha-live-verification-status-2026-05-03.md)
- [testing/alpha-final-scenarios.md](testing/alpha-final-scenarios.md)

