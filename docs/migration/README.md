# LangGraph移行プロジェクト - ドキュメント一覧

## 📚 ドキュメント構成

### 🏠 基本ドキュメント

1. **[OVERVIEW.md](OVERVIEW.md)** - 移行プロジェクトの概要と目的
2. **[TEAM-ASSIGNMENTS.md](TEAM-ASSIGNMENTS.md)** - チーム担当者一覧（優先度1・2確定版）
3. **[ROADMAP.md](ROADMAP.md)** - 移行ロードマップ（12週間計画）
4. **[SUMMARY.md](SUMMARY.md)** - 準備完了サマリー

### 🔄 開発プロセス

5. **[BRANCH-STRATEGY.md](BRANCH-STRATEGY.md)** - ブランチ戦略（feature→develop→main）
6. **[INTEGRATION-GUIDE.md](INTEGRATION-GUIDE.md)** - 統合エージェント担当者向けガイド
7. **[DEVELOPMENT-STANDARDS.md](DEVELOPMENT-STANDARDS.md)** - 開発標準（コーディング規約、テスト標準等）
8. **[CODE-REVIEW-GUIDE.md](CODE-REVIEW-GUIDE.md)** - コードレビューガイド
9. **[PREPARATION-CHECKLIST.md](PREPARATION-CHECKLIST.md)** - 開発準備チェックリスト
10. **[FINAL-CHECKLIST.md](FINAL-CHECKLIST.md)** - mainブランチpush前の最終チェックリスト

### 📖 技術ドキュメント

11. **[COWORKING-SYSTEM-ANALYSIS.md](COWORKING-SYSTEM-ANALYSIS.md)** - coworking-space-systemの分析
12. **[MASTRA-AGENT-ANALYSIS.md](MASTRA-AGENT-ANALYSIS.md)** - Mastra版エージェントの責任範囲分析

### 📝 エージェント別ドキュメント

各エージェントの詳細ドキュメントは`agents/{agent-name}/`に配置されています。

#### RouterAgent（テンプレート）

- **[agents/router-agent/README.md](agents/router-agent/README.md)** - エージェント概要・役割・責任範囲
- **[agents/router-agent/MIGRATION-GUIDE.md](agents/router-agent/MIGRATION-GUIDE.md)** - Mastra→LangGraph移行手順
- **[agents/router-agent/CI-CD.md](agents/router-agent/CI-CD.md)** - CI/CD設定・ブランチ戦略
- **[agents/router-agent/TESTING.md](agents/router-agent/TESTING.md)** - テスト戦略・テストケース

他のエージェントも同様の構造でドキュメントを作成してください。

## 🚀 クイックスタート

### 新規メンバー向け

1. **[../ONBOARDING.md](../../ONBOARDING.md)** を読む（まずはここから！）
2. **[OVERVIEW.md](OVERVIEW.md)** でプロジェクトの全体像を把握
3. **[TEAM-ASSIGNMENTS.md](TEAM-ASSIGNMENTS.md)** で自分の担当を確認
4. **[BRANCH-STRATEGY.md](BRANCH-STRATEGY.md)** で開発フローを理解
5. 担当エージェントのドキュメントを読む

### 開発開始

1. **[PREPARATION-CHECKLIST.md](PREPARATION-CHECKLIST.md)** で準備を確認
2. featureブランチを作成
3. 担当エージェントの実装を開始

## 📊 ドキュメント統計

- **基本ドキュメント**: 4ファイル
- **開発プロセス**: 6ファイル
- **技術ドキュメント**: 2ファイル
- **エージェント別ドキュメント**: RouterAgentテンプレート（4ファイル）
- **合計**: 16ファイル以上

## 🔗 関連リンク

- [ルートREADME](../../README.md)
- [オンボーディングガイド](../../ONBOARDING.md)
- [開発者ガイド](../../DEVELOPER-GUIDE.md)
- [バックエンドREADME](../../backend/README.md)

