# AGENTS.md - Engineer Cafe Navigator

## 開発モード: 2-Agent (Cursor PM + Claude Code Worker)

---

## 役割分担

| 役割 | 担当 | 責任範囲 |
|------|------|---------|
| **PM (計画・レビュー)** | Cursor | 要件定義、プラン作成、コードレビュー、本番デプロイ |
| **Worker (実装)** | Claude Code | 実装、テスト、staging デプロイ、CI/CD 修正 |

---

## ワークフロー

```
[ユーザー] 「〇〇を作りたい」
    ↓
[Cursor PM] 要件ヒアリング → Plans.md 作成
    ↓
[Cursor PM] /handoff-to-claude → タスク依頼
    ↓
[Claude Code] 実装 + テスト + CI/CD グリーン確認
    ↓
[Claude Code] /handoff-to-cursor → 完了報告
    ↓
[Cursor PM] レビュー → 本番デプロイ or 修正依頼
```

---

## マーカー凡例

| マーカー | 状態 | 説明 |
|---------|------|------|
| `cc:TODO` | 未着手 | Claude Code が実行予定 |
| `cc:WIP` | 作業中 | Claude Code が実装中 |
| `cc:DONE` | 完了 | Claude Code が完了 |
| `cc:BLOCKED` | ブロック中 | 依存タスク待ち |
| `pm:依頼中` | PM から依頼 | Cursor からの依頼 |
| `pm:確認済` | PM 確認済み | Cursor がレビュー完了 |

---

## プロジェクト構成

```
engineer-cafe-navigator2025/
├── frontend/                 # Next.js 15 + Mastra (TypeScript)
│   ├── src/
│   │   ├── app/             # App Router
│   │   ├── mastra/          # AI Agents (12エージェント)
│   │   ├── lib/             # ユーティリティ
│   │   └── slides/          # Marp スライド
│   └── supabase/            # マイグレーション
├── backend/                  # Python + LangGraph
│   ├── agents/              # エージェント実装（10種）
│   ├── config/              # 設定（routing_constants, prompts/）
│   ├── utils/               # ユーティリティ（input_sanitizer, exceptions等）
│   ├── workflows/           # LangGraphワークフロー
│   └── tests/               # テスト（406件）
├── docs/                     # ドキュメント
│   ├── development/         # 開発ガイド
│   │   ├── AGENTS.md        # このファイル
│   │   └── CLAUDE.md        # Claude Code 設定
│   ├── api/                 # API仕様
│   ├── architecture/        # アーキテクチャ
│   ├── migration/agents/    # エージェント移行仕様
│   └── archive/             # 古いドキュメント
└── Plans.md                  # タスク管理（ルートに保持）
```

---

## エージェント一覧 (LangGraph 実装)

| エージェント | 担当者 | 役割 | ステータス |
|-------------|--------|------|-----------|
| OrchestratorAgent | テリスケ | Supervisor Pattern ルーティング | LangGraph 実装済 |
| RouterAgent | テリスケ | クエリルーティング（キーワードベース） | LangGraph 実装済 |
| BusinessInfoAgent | テリスケ | 営業時間・料金 | LangGraph 実装済 |
| FacilityAgent | Natsumi | 設備・地下施設 | LangGraph 実装済 |
| EventAgent | テリスケ | イベント・カレンダー | LangGraph 実装済 |
| MemoryAgent | takegg0311 | 会話履歴管理 | LangGraph 実装済 |
| ClarificationAgent | Chie | 曖昧さ解消 | LangGraph 実装済 |
| GeneralKnowledgeAgent | テリスケ | Web 検索 | LangGraph 実装済 |
| CharacterControlAgent | takegg0311 | VRM キャラクター | LangGraph 実装済 |
| VoiceAgent | Chie | STT/TTS | LangGraph 実装済 |
| SlideAgent | テリスケ | スライドナレーション | LangGraph 実装済 |
| OCRAgent | けいてぃー | 画像認識 | **新規** (LangGraph のみ) |

### 共有インフラストラクチャ

| モジュール | 目的 |
|-----------|------|
| `config/routing_constants.py` | ルーティングキーワード・エージェントマッピング・ヘルパー関数を集約 |
| `config/prompts/` | エージェント固有のプロンプトテンプレート（facility, event, memory） |
| `utils/input_sanitizer.py` | プロンプトインジェクション検出・入力バリデーション |
| `utils/exceptions.py` | ドメイン固有カスタム例外階層 |

---

## CI/CD 要件

- **すべての PR で CI がグリーンであること**
- Claude Code は CI 失敗時に自動修正を試みる
- 修正不可の場合は PM に報告

---

## 権限とセキュリティ

### 外部サービス統合の権限設定

Claude Code と Cursor は以下の操作で bash コマンド実行が許可されています:

#### データベーステスト (Supabase 統合)
- 外部データベースサービスに接続する Supabase 統合テストの実行
- データベース接続が必要なテストスクリプトの実行 (例: `pnpm test:integration`)
- データベースマイグレーションとセットアップコマンド (例: `pnpm db:migrate`, `pnpm db:setup-admin`)

#### コンテナ操作 (Docker)
- Docker イメージのビルド (例: `docker build`, `docker-compose build`)
- テスト用コンテナ化サービスの実行 (例: `docker-compose up`)
- コンテナ管理コマンド (例: `docker ps`, `docker logs`)

#### CI/CD 操作
- リントと型チェックコマンドの実行 (例: `pnpm lint`, `pnpm typecheck`)
- テストスイートの実行 (例: `pnpm test`, `pytest`)
- 本番成果物のビルド (例: `pnpm build`)

**セキュリティ注記**: これらの操作にはユーザー入力処理と外部サービス接続が含まれます。すべてのコマンドは適切な入力検証とサニタイゼーションを伴って実行されます。

---

## 関連ファイル

- `../../Plans.md` - タスク管理（ルートディレクトリ）
- `CLAUDE.md` - Claude Code 詳細設定（同じディレクトリ）
- `../../.cursor/commands/` - Cursor コマンド
- `../../.claude/memory/` - 意思決定記録
