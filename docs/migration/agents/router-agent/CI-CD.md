# RouterAgent CI/CD設定

## 概要

RouterAgentのCI/CDパイプライン設定を説明します。

## ブランチ戦略

### featureブランチ

- **ブランチ名**: `feature/router-agent`
- **作成元**: `develop`
- **マージ先**: `develop`

### 開発フロー

```bash
# 1. developブランチからfeatureブランチを作成
git checkout develop
git pull origin develop
git checkout -b feature/router-agent

# 2. 開発とコミット
git add .
git commit -m "feat(router-agent): implement router node"

# 3. featureブランチをpush
git push origin feature/router-agent

# 4. PRを作成（base: develop, compare: feature/router-agent）
```

## CI/CDパイプライン

### GitHub Actions設定

`.github/workflows/router-agent.yml`:

```yaml
name: RouterAgent CI

on:
  pull_request:
    branches:
      - develop
    paths:
      - 'backend/agents/router_agent.py'
      - 'backend/tests/agents/test_router_agent.py'
  push:
    branches:
      - feature/router-agent

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: Run tests
        run: |
          cd backend
          pytest tests/agents/test_router_agent.py -v --cov=backend/agents/router_agent --cov-report=html
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./backend/coverage.xml
```

## テスト戦略

### 単体テスト

- **ファイル**: `backend/tests/agents/test_router_agent.py`
- **カバレッジ目標**: 80%以上

### 統合テスト

- **ファイル**: `backend/tests/integration/test_router_integration.py`
- **内容**: ワークフロー全体でのルーティングテスト

## コードレビュー

### レビュアー

- 統合エージェント担当者（寺田@terisuke, YukitoLyn）
- 他のRouterAgent担当者

### レビューチェックリスト

- [ ] コードが仕様を満たしている
- [ ] テストが通過している
- [ ] コードカバレッジが目標を満たしている
- [ ] ドキュメントが更新されている
- [ ] エラーハンドリングが適切
- [ ] パフォーマンスが基準を満たしている

## デプロイ

### 開発環境

- **ブランチ**: `develop`
- **自動デプロイ**: developブランチへのマージ時に自動デプロイ

### 本番環境

- **ブランチ**: `main`
- **デプロイ方法**: mainブランチへのマージ時に手動デプロイ

## モニタリング

### メトリクス

- ルーティング成功率
- ルーティング精度
- レスポンスタイム
- エラー率

### ログ

- ルーティング決定のログ
- エラーログ
- パフォーマンスログ

## 参考

- [BRANCH-STRATEGY.md](../../BRANCH-STRATEGY.md): ブランチ戦略の詳細
- [TESTING.md](./TESTING.md): テスト戦略の詳細

