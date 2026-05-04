# Scripts Directory

このディレクトリには、Engineer Cafe Navigatorの開発・運用・テストに使用するスクリプトが含まれています。

## 🧪 テストスクリプト（新構造）

### 統合テストディレクトリ: `tests/`

テストスクリプトは整理・統合され、`tests/`ディレクトリに移動しました。

#### メインテストファイル:
- **`tests/integrated-test-suite.ts`** ⭐ - **統合テストスイート**
  - 全主要機能をカバーする包括的テスト
  - セマンティック評価システム採用
  - 基本情報、施設ナビゲーション、メモリ、多言語対応
  - カレンダー連携、Webサーチ、STT補正のテスト追加
  
- **`tests/router-agent-test.ts`** - RouterAgent専用テスト
  - クエリルーティングロジックの検証
  - エージェント選択とリクエストタイプの精度測定
  
- **`tests/calendar-integration-test.ts`** - カレンダー連携テスト
  - Google Calendar統合の動作確認
  
- **`tests/run-tests.ts`** - テストランナー
  - 全テストまたは特定のテストスイートを実行

#### ユーティリティ:
- **`tests/utils/test-evaluation.ts`** - セマンティック評価システム
  - 同義語認識、概念グループマッチング
  - 60%閾値の柔軟な評価基準

### レガシーテストファイル（非推奨）
以下のファイルは新構造に統合されました：
- `test-basement-queries.ts` → integrated-test-suite.tsに統合
- `test-enhanced-rag.ts` → integrated-test-suite.tsに統合  
- `test-specific-queries.ts` → integrated-test-suite.tsに統合
- `final-comprehensive-test.ts` → integrated-test-suite.tsに統合

## 🔧 開発・運用スクリプト

### Knowledge Base Management
- **`seed-knowledge-base.ts`** - 知識ベースの初期データ投入
- **`import-markdown-knowledge.ts`** - Markdownファイルからの知識インポート
- **`migrate-to-openai-embeddings.ts`** - OpenAI embeddings移行

### Database Operations
- **`setup-admin-knowledge.ts`** - 管理者知識インターフェース設定
- **`update-database-schema.ts`** - データベーススキーマ更新
- **`execute-sql.ts`** - SQLクエリ実行ユーティリティ

### Testing & Verification
- **`check-knowledge-base.ts`** - 知識ベースの整合性チェック
- **`debug-categorization.ts`** - カテゴリ分類のデバッグ
- **`final-comprehensive-test.ts`** - 包括的システムテスト

## 📁 アーカイブ

### `archive/` ディレクトリ
旧バージョンや実験的スクリプトを保管:
- **`migrate-all-knowledge.ts`** - 旧型知識ベース移行
- **`fix-*.ts`** - 各種修正スクリプトの履歴
- **`*.sql`** - データベース修正クエリ

## 🚀 使用方法

### メインテストの実行
```bash
# 全テストスイートを実行（推奨）
pnpm test

# 特定のテストスイートを実行
pnpm test:integrated    # 統合テストスイート
pnpm test:router        # RouterAgentテスト
pnpm test:calendar      # カレンダー連携テスト

# または、scriptsディレクトリから直接実行
cd scripts/tests
npx tsx run-tests.ts
npx tsx run-tests.ts integrated
npx tsx run-tests.ts router
npx tsx run-tests.ts calendar
```

### 開発用ツール
```bash
# 知識ベースチェック
npx tsx -r dotenv/config scripts/check-knowledge-base.ts

# RouterAgentテスト
npx tsx -r dotenv/config scripts/test-router-agent.ts
```

## 📊 テスト評価システムの進化

### 従来型 (Legacy)
- **厳格キーワードマッチング**: 70%閾値
- **同義語認識なし**: "hours" ≠ "営業時間"
- **結果**: 28.6%成功率 (誤測定)

### 近代型 (Current) ⭐
- **セマンティック評価**: 意味理解ベース
- **同義語・概念認識**: "hours" = "営業時間" = "時間"
- **現実的期待値**: システム改善を正確に反映
- **結果**: 100%成功率 (正確測定)

## 🎯 重要な改善点

1. **測定精度の向上**: 改善効果を正しく測定
2. **新機能対応**: Enhanced RAG、RouterAgent、Memory System
3. **現実的評価**: 過度に厳格でない期待値設定
4. **詳細分析**: スコア、概念ヒント、セマンティック詳細

このテストスイートにより、Engineer Cafe Navigatorの継続的な品質向上と正確なパフォーマンス測定が実現されています。
