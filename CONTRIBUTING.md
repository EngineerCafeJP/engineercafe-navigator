# Contributing Guide

このドキュメントでは、Engineer Cafe Navigator プロジェクトへの貢献方法について説明します。

## ブランチ戦略

このプロジェクトでは **GitHub Flow** をベースとしたブランチ戦略を採用しています。

### ブランチ構成

```
main          # 本番環境用（保護されたブランチ）
  │
  ├── develop        # 開発統合ブランチ
  │     │
  │     ├── feature/xxx    # 機能開発
  │     ├── fix/xxx        # バグ修正
  │     └── docs/xxx       # ドキュメント
  │
  └── hotfix/xxx     # 緊急修正（mainから直接分岐）
```

### ブランチの役割

| ブランチ | 用途 | マージ先 |
|---------|------|---------|
| `main` | 本番環境。常にデプロイ可能な状態を維持 | - |
| `develop` | 開発統合。次回リリースに向けた開発を統合 | `main` |
| `feature/*` | 新機能開発 | `develop` |
| `fix/*` | バグ修正 | `develop` |
| `docs/*` | ドキュメント更新 | `develop` |
| `hotfix/*` | 緊急の本番バグ修正 | `main` と `develop` |

### main ブランチの保護ルール

`main` ブランチには以下の保護ルールが設定されています：

- **Restrict deletions**: ブランチの削除を禁止
- **Require a pull request before merging**: 直接プッシュを禁止、PRが必須
- **Block force pushes**: 強制プッシュを禁止

## 開発フロー

### 1. 新機能の開発

```bash
# develop から feature ブランチを作成
git checkout develop
git pull origin develop
git checkout -b feature/your-feature-name

# 開発作業
# ...

# コミット
git add .
git commit -m "feat: Add your feature description"

# プッシュ
git push origin feature/your-feature-name
```

### 2. Pull Request の作成

1. GitHub で PR を作成
2. `develop` ブランチをターゲットに設定
3. レビュアーをアサイン
4. CI チェックがパスすることを確認
5. レビュー後にマージ

### 3. リリース

```bash
# develop から main へ PR を作成
# レビュー後にマージ
```

## コミットメッセージ規約

[Conventional Commits](https://www.conventionalcommits.org/) に従います。

### フォーマット

```
<type>: <description>

[optional body]

[optional footer]
```

### Type 一覧

| Type | 説明 |
|------|------|
| `feat` | 新機能 |
| `fix` | バグ修正 |
| `docs` | ドキュメントのみの変更 |
| `style` | コードの意味に影響しない変更（空白、フォーマット等） |
| `refactor` | バグ修正や機能追加を伴わないコード変更 |
| `perf` | パフォーマンス改善 |
| `test` | テストの追加・修正 |
| `chore` | ビルドプロセスや補助ツールの変更 |

### 例

```bash
# 新機能
git commit -m "feat: Add voice input support for mobile devices"

# バグ修正
git commit -m "fix: Resolve memory leak in lip-sync analyzer"

# ドキュメント
git commit -m "docs: Update API documentation for voice endpoint"

# リファクタリング
git commit -m "refactor: Simplify router agent logic"
```

## コードレビュー

### レビュアーの責任

1. コードの品質とスタイルの確認
2. ロジックの正確性の検証
3. セキュリティ上の問題がないかチェック
4. テストが十分かの確認
5. ドキュメントが更新されているかの確認

### レビュー時のチェックリスト

- [ ] コードが目的を達成しているか
- [ ] エラーハンドリングが適切か
- [ ] パフォーマンスに問題がないか
- [ ] セキュリティリスクがないか
- [ ] テストが書かれているか
- [ ] ドキュメントが更新されているか

## 開発環境のセットアップ

詳細は [LOCAL-DEVELOPMENT-SETUP.md](./docs/LOCAL-DEVELOPMENT-SETUP.md) を参照してください。

### クイックスタート

```bash
# リポジトリのクローン
git clone https://github.com/EngineerCafeJP/engineercafe-navigator.git
cd engineercafe-navigator

# Frontend
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev

# Backend (LangGraph開発時)
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.main:app --reload
```

## Issue と PR のリンク

Issue を解決する PR を作成する場合、コミットメッセージまたは PR の説明に以下を含めてください：

```
Closes #123
Fixes #123
Resolves #123
```

## 質問・サポート

- GitHub Issues で質問を作成
- Discord でチームメンバーに連絡

## ライセンス

このプロジェクトへの貢献は、プロジェクトのライセンスに従います。
