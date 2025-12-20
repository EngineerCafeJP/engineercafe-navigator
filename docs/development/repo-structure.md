# リポジトリ構成ガイド

## 概要

このリポジトリには、Engineer Cafe Navigator 2025の新実装と、旧実装の参照コードが含まれています。

## ディレクトリ構成

```
engineer-cafe-navigator2025/
├── frontend/                        # 新Frontend実装
│   └── src/
│       └── mastra/                  # Mastra AIエージェント
│           └── agents/              # 12エージェント実装
│
├── backend/                         # 新Backend実装（LangGraph）
│   ├── agents/                      # LangGraphエージェント
│   ├── llm/                         # OpenRouter LLMプロバイダー
│   └── workflows/                   # LangGraphワークフロー
│
├── docs/                            # ドキュメント
│   ├── migration/                   # 移行関連ドキュメント
│   │   └── agents/                  # エージェント別移行ガイド
│   ├── wiki/                        # Backlog Wiki テンプレート
│   └── development/                 # 開発ガイド
│
├── supabase/                        # Supabase設定
│
└── engineer-cafe-navigator-repo/    # 旧実装（参照用）
    ├── src/                         # 旧Mastra実装
    └── docs/                        # 旧ドキュメント
```

## 各ディレクトリの役割

### 本番コード

| ディレクトリ | 用途 | 技術スタック |
|-------------|------|-------------|
| `frontend/` | 新Frontend | Next.js 15.3 + Mastra 0.10.5 |
| `backend/` | 新Backend | Python + LangGraph + OpenRouter |
| `supabase/` | DB設定 | PostgreSQL + pgvector |

### ドキュメント

| ディレクトリ | 用途 |
|-------------|------|
| `docs/migration/` | MastraからLangGraphへの移行ガイド |
| `docs/wiki/` | Backlog Wiki向けテンプレート |
| `docs/development/` | 開発者向けガイド |

### 参照コード（編集禁止）

| ディレクトリ | 用途 | 注意事項 |
|-------------|------|---------|
| `engineer-cafe-navigator-repo/` | 旧実装の参照 | **編集禁止** |

## engineer-cafe-navigator-repo について

### 目的

- 旧Mastra実装のロジックを参照するため
- 新LangGraph実装への移行時の参考資料
- エージェントのルーティングロジック等のポート元

### 重要な参照ファイル

| ファイル | 内容 |
|---------|------|
| `src/mastra/agents/router-agent.ts` | RouterAgentの完全実装（290行） |
| `src/mastra/agents/` | 12エージェントのMastra実装 |
| `src/lib/simplified-memory.ts` | メモリシステム実装 |
| `CLAUDE.md` | 旧プロジェクトのAI向け指示書 |

### 使い方

```bash
# 参照時
cat engineer-cafe-navigator-repo/src/mastra/agents/router-agent.ts

# 検索時
grep -r "memoryKeywordsJa" engineer-cafe-navigator-repo/src/
```

### 禁止事項

- `engineer-cafe-navigator-repo/`内のファイルを編集しない
- このディレクトリに新規ファイルを追加しない
- ネストされた`.git`を復元しない

## Git管理

### 統一リポジトリ

```
リポジトリ: https://github.com/EngineerCafeJP/engineercafe-navigator
ブランチ:
- main: 本番
- develop: 開発統合
- feature/*: 機能開発
```

### .gitignore

`engineer-cafe-navigator-repo/`は追跡対象ですが、内部の`.git`は除外されています:

```gitignore
# Nested git directories are removed, not ignored
# engineer-cafe-navigator-repo/ is tracked as reference code
```

## 移行完了後

LangGraph移行が完全に完了した後:

1. `engineer-cafe-navigator-repo/`は削除可能
2. 移行完了をチームで確認
3. 必要に応じてアーカイブを作成

## 関連ドキュメント

- [ブランチ戦略](../wiki/development/branch-strategy.md)
- [ローカルセットアップ](../wiki/development/local-setup.md)
- [エージェントアーキテクチャ](../wiki/agents/overview.md)
