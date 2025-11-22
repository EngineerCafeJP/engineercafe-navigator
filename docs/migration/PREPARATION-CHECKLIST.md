# 開発準備チェックリスト

## 概要

LangGraph移行プロジェクトを開始する前に、このチェックリストを確認してください。

## ✅ 完了済み項目

### 1. ドキュメント整備
- [x] 移行概要ドキュメント（OVERVIEW.md）
- [x] チーム担当者一覧（TEAM-ASSIGNMENTS.md）
- [x] ブランチ戦略（BRANCH-STRATEGY.md）
- [x] ロードマップ（ROADMAP.md）
- [x] 統合ガイド（INTEGRATION-GUIDE.md）
- [x] 参考実装分析（COWORKING-SYSTEM-ANALYSIS.md）
- [x] Mastra版エージェント分析（MASTRA-AGENT-ANALYSIS.md）
- [x] オンボーディングガイド（ONBOARDING.md）
- [x] 開発標準（DEVELOPMENT-STANDARDS.md）
- [x] コードレビューガイド（CODE-REVIEW-GUIDE.md）

### 2. バックエンド基盤
- [x] ディレクトリ構造の作成（agents/, workflows/, tools/, utils/, models/, config/, tests/）
- [x] 共通型定義（models/types.py）
- [x] 共通ユーティリティ（utils/logger.py, utils/error_handler.py, utils/language_processor.py）
- [x] 設定管理（config/settings.py）
- [x] 環境変数テンプレート（.env.example）
- [x] 依存関係の定義（requirements.txt, pyproject.toml）
- [x] OCR関連の依存関係追加

### 3. テスト環境
- [x] pytest設定（pytest.ini）
- [x] テストフィクスチャ（tests/conftest.py）
- [x] テストディレクトリ構造（tests/agents/, tests/workflows/, tests/integration/）

### 4. CI/CD
- [x] GitHub Actionsワークフロー（.github/workflows/backend-ci.yml）

### 5. 実装例
- [x] 基本的なエージェント実装例（examples/basic_agent_example.py）

### 6. 参考リポジトリ
- [x] langgraph-referenceの追加（git submodule）

## 📋 開発開始前の確認事項

### 環境セットアップ

- [ ] Python 3.11+がインストールされている
- [ ] 仮想環境が作成されている
- [ ] 依存関係がインストールされている（`pip install -r requirements.txt`）
- [ ] 環境変数が設定されている（`.env`ファイルを作成）

### 開発ツール

- [ ] Blackがインストールされている
- [ ] Ruffがインストールされている
- [ ] mypyがインストールされている
- [ ] pytestがインストールされている

### リポジトリ

- [ ] リポジトリがクローンされている
- [ ] 参考リポジトリ（langgraph-reference）が取得されている
- [ ] developブランチが最新になっている

### ドキュメント

- [ ] オンボーディングガイドを読んだ
- [ ] 自分の担当エージェントを確認した
- [ ] 担当エージェントのドキュメントを読んだ
- [ ] 開発標準を理解した
- [ ] ブランチ戦略を理解した

## 🚀 開発開始

準備が整ったら、以下の手順で開発を開始してください：

1. **featureブランチを作成**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/{agent-name}
   ```

2. **実装を開始**
   - 担当エージェントのドキュメントを参照
   - 参考実装（langgraph-reference/coworking-space-system）を確認
   - 実装例（backend/examples/basic_agent_example.py）を参考

3. **テストを作成**
   - 単体テストを追加
   - カバレッジ80%以上を目標

4. **PRを作成**
   - コードレビューガイドに従う
   - CI/CDが通過することを確認

## 📞 サポート

質問や問題がある場合は：
- 統合エージェント担当者（寺田@terisuke, YukitoLyn）に連絡
- GitHub Issuesで質問

