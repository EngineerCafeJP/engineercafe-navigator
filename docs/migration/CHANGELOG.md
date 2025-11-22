# 変更履歴 - LangGraph移行プロジェクト

## [0.1.0] - 2025-11-22

### 追加

#### ドキュメント
- 移行概要ドキュメント（OVERVIEW.md）
- チーム担当者一覧（TEAM-ASSIGNMENTS.md）
- ブランチ戦略（BRANCH-STRATEGY.md）
- ロードマップ（ROADMAP.md）
- 統合ガイド（INTEGRATION-GUIDE.md）
- 参考実装分析（COWORKING-SYSTEM-ANALYSIS.md）
- Mastra版エージェント分析（MASTRA-AGENT-ANALYSIS.md）
- 開発標準（DEVELOPMENT-STANDARDS.md）
- コードレビューガイド（CODE-REVIEW-GUIDE.md）
- 準備チェックリスト（PREPARATION-CHECKLIST.md）
- 最終チェックリスト（FINAL-CHECKLIST.md）
- サマリー（SUMMARY.md）
- オンボーディングガイド（ONBOARDING.md）

#### エージェント別ドキュメント
- RouterAgentの完全なドキュメントセット（テンプレート）
  - README.md
  - MIGRATION-GUIDE.md
  - CI-CD.md
  - TESTING.md

#### バックエンド基盤
- ディレクトリ構造（agents/, workflows/, tools/, utils/, models/, config/, tests/, examples/）
- 共通型定義（models/types.py）
- 共通ユーティリティ（utils/logger.py, utils/error_handler.py, utils/language_processor.py）
- 設定管理（config/settings.py）
- 環境変数テンプレート（.env.example）
- 依存関係の定義（requirements.txt, pyproject.toml）
- OCR関連の依存関係（Tesseract, EasyOCR, Google Vision API）
- 実装例（examples/basic_agent_example.py）

#### テスト環境
- pytest設定（pytest.ini）
- テストフィクスチャ（tests/conftest.py）
- テストディレクトリ構造

#### CI/CD
- GitHub Actionsワークフロー（.github/workflows/backend-ci.yml）

#### 参考リポジトリ
- langgraph-reference（git submodule）

### 変更

- README.md: LangGraph移行プロジェクト情報を追加
- DEVELOPER-GUIDE.md: 移行プロジェクトセクションを追加
- docs/README.md: 移行プロジェクトドキュメントセクションを追加
- backend/workflows/main_workflow.py: WorkflowStateをmodels/types.pyからインポートするように変更

### 修正

- WorkflowStateの重複定義を修正（models/types.pyに統一）
- インポートパスの統一
- 型定義の一貫性を確保

### 削除

- langgraph-repo/（langgraph-referenceに統一）

---

## 次のバージョン予定

### [0.2.0] - 予定

- RouterAgentの実装
- MemoryAgentの実装
- 統合テストの追加

