# リポジトリ構成ガイド

> 注意: この文書には現在存在しないパスや migration-era の記述が含まれる可能性があります。現行構成は実ディレクトリと `docs/STATUS.md` を優先してください。

> 最終更新: 2026-02-07（参照コード削除、クリーンモノレポ化）

## 概要

Engineer Cafe Navigator 2025 のモノレポ構成です。
Frontend (Next.js) + Backend (Python/LangGraph) + DB (Supabase) の3層アーキテクチャ。

## ディレクトリ構成

```
engineer-cafe-navigator2025/
├── README.md                        # プロジェクト概要
├── README-EN.md                     # 英語版README
├── Plans.md                         # タスク管理（ルートに保持）
│
├── frontend/                        # Frontend（Next.js）
│   └── src/
│       ├── app/                     # App Router + API Routes
│       ├── components/              # React コンポーネント
│       └── lib/                     # ユーティリティ
│
├── backend/                         # Backend（Python + LangGraph）
│   ├── agents/                      # LangGraph エージェント（12種）
│   ├── config/                      # 設定・定数
│   │   ├── routing_constants.py     # ルーティングキーワード・型定義・ヘルパー
│   │   ├── settings.py              # アプリケーション設定
│   │   └── prompts/                 # 共有プロンプトテンプレート
│   │       ├── facility_prompts.py
│   │       ├── event_prompts.py
│   │       └── memory_prompts.py
│   ├── llm/                         # OpenRouter LLM プロバイダー
│   ├── tools/                       # ツール実装（agent_tools, web_search）
│   ├── utils/                       # ユーティリティ
│   │   ├── input_sanitizer.py       # 入力バリデーション・サニタイズ
│   │   ├── exceptions.py            # カスタム例外階層
│   │   ├── memory_helper.py         # Supabase メモリシステム
│   │   ├── language_processor.py    # 言語検出
│   │   └── query_classifier.py      # クエリ分類
│   ├── workflows/                   # LangGraph ワークフロー
│   ├── tests/                       # テスト（406件）
│   │   ├── agents/                  # 単体テスト
│   │   ├── integration/             # 統合テスト
│   │   └── evaluation/              # LangChain Evaluation
│   ├── slides/                      # スライドファイル
│   └── supabase/                    # Supabase 設定・マイグレーション
│
└── docs/                            # ドキュメント
    ├── development/                 # 開発ガイド
    ├── api/                         # API仕様
    ├── architecture/                # アーキテクチャ
    ├── migration/                   # 移行ガイド（完了済み・履歴）
    ├── archive/                     # 古いドキュメント
    ├── blog/                        # ブログ記事
    ├── wiki/                        # Backlog Wiki テンプレート
    └── CHANGELOG.md                 # 変更履歴
```

## 各ディレクトリの役割

### 本番コード

| ディレクトリ | 用途 | 技術スタック |
|-------------|------|-------------|
| `frontend/` | Frontend | Next.js 15.3 + React 19 + TypeScript |
| `backend/` | Backend | Python 3.12 + LangGraph + OpenRouter |
| `backend/supabase/` | DB設定・マイグレーション | PostgreSQL + pgvector |

### ドキュメント

| ディレクトリ | 用途 |
|-------------|------|
| `docs/development/` | 開発ガイド、CLAUDE.md、AGENTS.md 等 |
| `docs/api/` | API仕様（API.md, API-ja.md） |
| `docs/architecture/` | システムアーキテクチャドキュメント |
| `docs/migration/` | Mastra→LangGraph 移行ガイド（完了済み・履歴として保持） |
| `docs/archive/` | 古いドキュメント・完了レポート |
| `docs/blog/` | ブログ記事 |
| `docs/wiki/` | Backlog Wiki 向けテンプレート |

## Git管理

### 統一リポジトリ

```
リポジトリ: https://github.com/EngineerCafeJP/engineercafe-navigator
ブランチ:
- main: 本番
- develop: 開発統合
- feature/*: 機能開発
```

## 移行履歴

Mastra (TypeScript) → LangGraph (Python) への移行は 2026年2月に完了しました。

- 旧参照コード（`engineer-cafe-navigator-repo/`）は削除済み
- 旧 LangGraph リファレンス（`langgraph-reference/` submodule）は削除済み
- 旧 Mastra エージェントアーカイブ（`frontend/src/_reference/mastra/`）は削除済み
- 移行ガイド（`docs/migration/agents/`）は履歴として保持

## 関連ドキュメント

- [開発ガイド](DEVELOPER-GUIDE.md)
- [エージェント一覧](AGENTS.md)
- [LangGraph開発ガイド](LANGGRAPH-DEVELOPMENT-GUIDE.md)
- [エージェント開発クイックスタート](AGENT-QUICKSTART.md)
