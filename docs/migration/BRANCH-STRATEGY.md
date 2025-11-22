# ブランチ戦略

## 概要

Mastra → LangGraph移行プロジェクトでは、Git Flowをベースにしたブランチ戦略を採用します。各エージェントを独立して開発し、統合エージェント担当者が全体のバランスを取ります。

## ブランチ構造

```
main (本番)
  ↑
develop (統合・テスト)
  ↑
feature/{agent-name} (各エージェント開発)
```

## ブランチの種類

### 1. mainブランチ

- **目的**: 本番環境で使用される安定版
- **保護**: 直接コミット不可、PR経由のみ
- **マージ条件**:
  - developブランチからのみマージ可能
  - すべてのテストが通過
  - コードレビュー承認済み
  - 統合エージェント担当者の承認

### 2. developブランチ

- **目的**: 統合とテストを行う開発ブランチ
- **保護**: 直接コミット可能（統合エージェント担当者のみ）
- **マージ元**: feature/{agent-name}ブランチ
- **役割**:
  - 各エージェントの統合
  - 統合テストの実行
  - コンフリクト解決
  - 全体のバランス調整

### 3. feature/{agent-name}ブランチ

- **目的**: 各エージェントの個別開発
- **命名規則**: `feature/router-agent`, `feature/memory-agent`等
- **作成元**: developブランチ
- **マージ先**: developブランチ
- **役割**:
  - エージェントの実装
  - 単体テストの作成
  - ドキュメントの作成

## 開発フロー

### 1. 新規エージェント開発の開始

```bash
# developブランチから最新を取得
git checkout develop
git pull origin develop

# featureブランチを作成
git checkout -b feature/{agent-name}

# 開発を開始
# ...
```

### 2. 開発中の作業

```bash
# 定期的にdevelopブランチの最新を取り込む
git checkout develop
git pull origin develop
git checkout feature/{agent-name}
git merge develop  # または rebase develop
```

### 3. 開発完了後のPR作成

```bash
# featureブランチをpush
git push origin feature/{agent-name}

# GitHubでPRを作成
# - base: develop
# - compare: feature/{agent-name}
```

### 4. PRレビューとマージ

- **レビュアー**: 統合エージェント担当者 + 担当エージェントの他の担当者
- **チェック項目**:
  - コード品質
  - テストカバレッジ
  - ドキュメントの更新
  - コンフリクトの有無
- **マージ**: レビュー承認後、統合エージェント担当者がマージ

### 5. developブランチでの統合テスト

- 統合エージェント担当者が統合テストを実行
- 問題があれば、該当エージェント担当者に修正依頼
- 問題がなければ、mainブランチへのマージ準備

## コンフリクト解決

### 発生タイミング

- featureブランチをdevelopにマージする際
- 複数のエージェントが同じファイルを変更した場合

### 解決手順

1. **統合エージェント担当者が確認**
   - コンフリクトの内容を確認
   - 影響範囲を評価

2. **関係者と協議**
   - 該当エージェント担当者と協議
   - 解決方針を決定

3. **解決**
   - 統合エージェント担当者が解決（または該当エージェント担当者に依頼）
   - 解決後、再度テストを実行

## ブランチ命名規則

### featureブランチ

- `feature/router-agent`
- `feature/business-info-agent`
- `feature/memory-agent`
- `feature/ocr-agent` (新規)

### その他のブランチ

- `hotfix/{issue-name}`: 緊急修正用
- `docs/{topic}`: ドキュメント専用ブランチ

## コミットメッセージ規則

### 形式

```
{type}: {subject}

{body}

{footer}
```

### type

- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `test`: テスト
- `refactor`: リファクタリング
- `chore`: その他

### 例

```
feat(router-agent): 言語検出機能を追加

- 日本語と英語の自動検出
- クエリの言語に応じたルーティング

Closes #123
```

## リリースフロー

### スプリント終了時

1. developブランチで統合テスト完了
2. mainブランチへのPR作成
3. 統合エージェント担当者がレビュー
4. 承認後、mainブランチにマージ
5. タグ付け（`v1.0.0`等）

### 緊急修正

1. mainブランチからhotfixブランチを作成
2. 修正を実装
3. mainブランチとdevelopブランチの両方にマージ
4. タグ付け

## 注意事項

- **featureブランチは1つのエージェントに1つ**
- **developブランチへの直接コミットは統合エージェント担当者のみ**
- **mainブランチへの直接コミットは禁止**
- **定期的にdevelopブランチの最新を取り込む**
- **コンフリクトは早期に解決する**

## 参考

- [Git Flow](https://nvie.com/posts/a-successful-git-branching-model/)
- [GitHub Flow](https://guides.github.com/introduction/flow/)

