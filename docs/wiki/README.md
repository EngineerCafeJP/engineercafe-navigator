# Engineer Cafe Navigator - Wiki Templates

このディレクトリには、Backlog Wikiへコピー可能なドキュメントテンプレートが含まれています。

## ディレクトリ構成

```
docs/wiki/
├── README.md                           # このファイル
├── api-management/
│   └── openrouter-setup.md             # OpenRouter API設定ガイド
├── development/
│   ├── branch-strategy.md              # ブランチ戦略
│   └── local-setup.md                  # ローカル開発セットアップ
└── agents/
    └── overview.md                     # エージェントアーキテクチャ概要
```

## 使い方

1. 対象のマークダウンファイルを開く
2. 内容をコピー
3. Backlog Wikiに新規ページを作成
4. 内容を貼り付け

## Backlog Wiki への展開

各ファイルは以下のBacklog Wikiページに対応します:

| ファイル | Backlog Wiki パス |
|---------|------------------|
| `api-management/openrouter-setup.md` | API管理/OpenRouter設定 |
| `development/branch-strategy.md` | 開発/ブランチ戦略 |
| `development/local-setup.md` | 開発/ローカルセットアップ |
| `agents/overview.md` | アーキテクチャ/エージェント概要 |

## 更新ルール

- Gitリポジトリを正として管理
- Backlog Wikiへは定期的に同期
- 大きな変更時はPRでレビュー後にWikiを更新
