# Engineer Cafe Navigator 開発者ガイド

> 注意: この文書には Mastra 移行期の記述が多く残っています。現行の入口は `docs/STATUS.md`、`docs/DEVELOPER-GUIDE.md`、ルートの `README.md` を優先してください。

最終更新日: 2026年2月7日（LangGraph バックエンド + 共有インフラストラクチャ整備済み）

## 📋 目次

1. [プロジェクト概要](#プロジェクト概要)
2. [現在の状況](#現在の状況)
3. [クイックスタート](#クイックスタート)
4. [アーキテクチャ](#アーキテクチャ)
5. [実装ガイド](#実装ガイド)
6. [テスト戦略](#テスト戦略)
7. [トラブルシューティング](#トラブルシューティング)
8. [今後の開発計画](#今後の開発計画)

---

## プロジェクト概要

Engineer Cafe Navigator は、福岡市中央区天神にあるエンジニアカフェの AI アシスタントシステムです。

### 主な機能
- 多言語対応（日本語・英語）
- 音声インターフェース（Google Cloud Speech-to-Text/Text-to-Speech）
- 3D VRM キャラクター表示
- RAG (Retrieval-Augmented Generation) による知識ベース検索
- 短期記憶機能（3分間の会話コンテキスト保持）
- カレンダー統合
- Web検索統合

### 技術スタック

#### Frontend
- **Framework**: Next.js 15.3 + React 19 + TypeScript
- **AI Framework**: Mastra 0.10.5 (マルチエージェントオーケストレーション)
- **3D Graphics**: Three.js + @pixiv/three-vrm

#### Backend (LangGraph)
- **言語**: Python 3.12+
- **AI Framework**: LangGraph (Supervisor Pattern)
- **LLM Provider**: OpenRouter with ADR 018 fast model resolver
- **テスト**: pytest（406件パス）+ LangChain Evaluation

#### 共通
- **Database**: PostgreSQL + pgvector (Supabase)
- **Voice**: Google Cloud Speech/TTS
- **Embeddings**: OpenAI text-embedding-3-small (1536次元)

---

## 現在の状況

### デュアルスタックアーキテクチャ

本プロジェクトは **Frontend (Next.js + Mastra)** と **Backend (LangGraph)** のデュアルスタック構成です。
2026年2月時点で、バックエンドの LangGraph 移行が進行中であり、結合テストフェーズに入っています。

#### Backend: LangGraph エージェントシステム（開発中）
- **構成**: 10+ エージェント（Supervisor Pattern）
  - **OrchestratorAgent**: Supervisor Pattern によるルーティング・ワークフロー制御
  - **RouterAgent**: キーワードベースクエリルーティング（28/28テストケースパス）
  - **BusinessInfoAgent**: 営業時間・料金・場所（RAG統合）
  - **FacilityAgent**: 設備・Wi-Fi情報（地下施設対応）
  - **EventAgent**: イベント・カレンダー連携
  - **MemoryAgent**: 会話履歴管理（Supabase統合）
  - **ClarificationAgent**: 曖昧さ解消
  - **GeneralKnowledgeAgent**: Web 検索
  - **SlideAgent**: スライドナレーション
  - **VoiceAgent**: STT/TTS
  - **CharacterControlAgent**: VRM キャラクター制御
  - **OCRAgent**: 画像認識（新規）

#### 共有インフラストラクチャ（2026年2月整備）
- `config/routing_constants.py`: ルーティングキーワード・マッピング・ヘルパー集約
- `config/prompts/`: エージェント固有プロンプトテンプレート
- `utils/input_sanitizer.py`: 入力バリデーション・サニタイズ
- `utils/exceptions.py`: カスタム例外階層

#### パフォーマンス指標
- **バックエンドテスト**: 406件パス、2件スキップ
- **ルーティング精度**: 28/28テストケース全パス
- **LangChain Evaluation**: LLM Judge + ルーティング精度評価統合済み

#### Frontend: Next.js + Mastra エージェントシステム（本番稼働中）
- **構成**: 8つの専門エージェント + ワークフロー（Mastra によるオーケストレーション）
- **テスト成功率**: 100%（セマンティック評価）
- **RouterAgent精度**: 94.1%

---

## クイックスタート

### 1. 環境セットアップ（10分）

```bash
# リポジトリをクローン
git clone [repository-url]
cd engineer-cafe-navigator

# 環境変数の設定
cp .env.example .env.local
# .env.local を編集して必要な API キーを設定

# 依存関係のインストール
pnpm install

# データベースのセットアップ
pnpm db:migrate
pnpm seed:knowledge
```

### 2. 開発サーバー起動（5分）

```bash
# 開発サーバー起動
pnpm dev

# 別ターミナルで動作確認
curl -X POST http://localhost:3000/api/qa \
  -H "Content-Type: application/json" \
  -d '{"action": "ask_question", "question": "エンジニアカフェの営業時間は？", "language": "ja"}'
```

### 3. バックエンド（LangGraph）セットアップ

```bash
cd backend

# 依存関係インストール（uv 推奨）
uv sync
# または
pip install -r requirements.txt

# テスト実行
pytest -v --tb=short

# コード品質チェック
ruff check . && black --check .
```

### 4. テスト実行

```bash
# Frontend テスト
pnpm tsx scripts/tests/run-tests.ts

# Backend テスト（406件）
cd backend && pytest -v --tb=short

# Backend ルーティング精度評価
pytest backend/tests/evaluation/test_routing_accuracy.py -v
```

---

## アーキテクチャ

### ディレクトリ構造

```
src/
├── app/                    # Next.js App Router
│   └── api/               # API エンドポイント
├── components/            # React コンポーネント
├── lib/                   # ユーティリティ
│   ├── audio/            # 音声処理
│   ├── simplified-memory.ts  # メモリシステム
│   └── query-classifier.ts   # クエリ分類
└── mastra/               # AI エージェント
    ├── agents/           # エージェント実装
    ├── tools/            # ツール実装
    └── workflows/        # ワークフロー

scripts/
├── tests/                 # テストスクリプト
│   ├── integrated-test-suite.ts
│   ├── router-agent-test.ts
│   ├── calendar-integration-test.ts
│   ├── run-tests.ts      # テストランナー
│   └── utils/            # テストユーティリティ
├── check-knowledge-base.ts  # 知識ベース確認
├── migrate-to-openai-embeddings.ts  # 移行スクリプト
└── seed-knowledge-base.ts   # データシード
```

### データフロー

```
[ユーザー入力]
    ↓
[RouterAgent] → クエリ分析・ルーティング
    ↓
[専門エージェント] → 情報処理
    ↓
[MainQAWorkflow] → レスポンス生成
    ↓
[ユーザーへ返答]
```

---

## 実装ガイド

### 最重要：ツール管理パターン

```typescript
// ❌ 間違った実装（直接インポート）
import { ragSearchTool } from '@/mastra/tools/rag-search';
const result = await ragSearchTool.execute({ ... });

// ✅ 正しい実装（ツールマップから取得）
export class MyAgent extends Agent {
  private _tools: Map<string, any> = new Map();

  addTool(name: string, tool: any) {
    this._tools.set(name, tool);
  }

  async processQuery() {
    const ragTool = this._tools.get('ragSearch');
    if (!ragTool) {
      return this.getDefaultResponse();
    }
    
    try {
      const result = await ragTool.execute({ ... });
      // 結果の処理
    } catch (error) {
      console.error('[MyAgent] Tool error:', error);
      return this.getDefaultResponse();
    }
  }
}
```

### RAG検索結果の処理

```typescript
// 両方の形式に対応する必要がある
let context = '';
if (searchResult.results && Array.isArray(searchResult.results)) {
  // 標準RAGツールの形式
  context = searchResult.results
    .map(r => r.content)
    .join('\n\n');
} else if (searchResult.data && searchResult.data.context) {
  // エンハンスドRAGツールの形式
  context = searchResult.data.context;
}

if (!context) {
  return this.getDefaultResponse(language);
}
```

### 新しいエージェントの追加手順

1. **エージェントクラスの作成**
```typescript
// src/mastra/agents/my-new-agent.ts
export class MyNewAgent extends Agent {
  private _tools: Map<string, any> = new Map();
  
  // 実装...
}
```

2. **RouterAgentに追加**
```typescript
// src/mastra/agents/router-agent.ts
private selectAgent(category: string, requestType: string | null): string {
  const agentMap: Record<string, string> = {
    // ... 既存のマッピング
    'my-category': 'MyNewAgent',  // 追加
  };
}
```

3. **MainQAWorkflowに統合**
```typescript
// src/mastra/workflows/main-qa-workflow.ts
// コンストラクタで初期化
this.myNewAgent = new MyNewAgent(config);

// switch文に追加
case 'MyNewAgent':
  answer = await this.myNewAgent.processQuery(query, language);
  break;
```

---

## テスト戦略

### テストスクリプト一覧

#### 統合テストスイート
- `scripts/tests/run-tests.ts` - すべてのテストを実行するテストランナー
- `scripts/tests/integrated-test-suite.ts` - 主要機能の統合テスト（セマンティック評価採用）
- `scripts/tests/router-agent-test.ts` - ルーティング精度テスト
- `scripts/tests/calendar-integration-test.ts` - カレンダー統合テスト

#### テストユーティリティ
- `scripts/tests/utils/test-evaluation.ts` - セマンティック評価システム（同義語認識・概念グループ）

#### デバッグツール
- `scripts/check-knowledge-base.ts` - 知識ベースの内容確認
- `scripts/migrate-to-openai-embeddings.ts` - 埋め込みベクトルの移行

#### テスト実行方法
```bash
pnpm test              # 全テスト実行
pnpm test:integrated   # 統合テストのみ
pnpm test:router       # ルーターテストのみ
pnpm test:calendar     # カレンダーテストのみ
```

### 成功基準と現在の達成状況
- **テスト成功率**: ✅ 100%達成（セマンティック評価）
- **平均応答時間**: ✅ 2.9秒（目標3秒以内を達成）
- **ルーティング精度**: ✅ 94.1%（ほぼ目標達成）
- **地下施設検索**: ✅ 完全対応
- **文脈依存クエリ**: ✅ 対応済み

---

## トラブルシューティング

### よくある問題と解決方法

#### 1. RAG検索結果が0件
```bash
# デバッグコマンド
pnpm tsx scripts/check-knowledge-base.ts
```
**原因**: カテゴリフィルタリングの問題
**解決**: カテゴリパラメータを削除、またはlimitパラメータを使用

#### 2. ツールが見つからない
```typescript
// エラー: Cannot read property 'execute' of undefined
```
**原因**: ツールが正しく登録されていない
**解決**: MainQAWorkflowの`initializeTools()`を確認

#### 3. 日本語/英語の混在
**原因**: 言語検出の問題
**解決**: LanguageProcessorの動作を確認

#### 4. メモリー機能が動作しない
**原因**: SessionIdが正しく伝播されていない
**解決**: SimplifiedMemorySystemのログを確認

---

## 今後の開発計画

### Phase 1: 短期目標（1-2週間）

#### ✅ 完了済み
- **テスト評価システム改革**: セマンティック評価により成功率28.6%→100%
- **Enhanced RAG統合**: BusinessInfoAgent、FacilityAgent、RealtimeAgentで完全統合
- **RouterAgent精度向上**: 文脈依存ルーティング対応（「土曜日も同じ時間？」等）

#### 🚀 次のステップ
1. **テストカバレッジ拡張**: 新機能特有のテストケース追加
2. **カレンダー統合の最適化**: EventAgentのカレンダーツール統合強化
3. **パフォーマンス最適化**: 平均応答時間を2秒以内に

### Phase 2: 中期目標（1ヶ月）

#### 1. エンティティ拡張
- 周辺施設情報の追加
- より詳細な施設案内

#### 2. 高度なメモリシステム
- 長期記憶の検討
- ユーザー個別の嗜好学習

### Phase 3: 長期目標（3ヶ月）

#### 1. 機械学習統合
- 学習ベースの応答改善
- ユーザー行動分析

#### 2. マルチモーダル対応
- 画像認識統合
- 音声感情認識

---

## 環境変数

```bash
# Google Cloud
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json

# AI Models
OPENROUTER_API_KEY=your-openrouter-api-key
OPENAI_API_KEY=your-openai-api-key
FAST_LLM_PRIMARY_MODEL=google/gemini-3.1-flash-lite-preview
FAST_LLM_FALLBACK_MODEL=google/gemini-2.5-flash-lite

# Supabase
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Calendar (Optional)
GOOGLE_CALENDAR_CLIENT_ID=your-calendar-client-id
GOOGLE_CALENDAR_CLIENT_SECRET=your-calendar-client-secret

# CRON Jobs
CRON_SECRET=your-cron-secret
```

---

## コマンドリファレンス

### 開発
```bash
pnpm dev                    # 開発サーバー起動
pnpm build                  # プロダクションビルド
pnpm start                  # プロダクションサーバー起動
pnpm lint                   # ESLint実行
pnpm typecheck              # TypeScriptの型チェック
```

### データベース
```bash
pnpm db:migrate             # マイグレーション実行
pnpm seed:knowledge         # 知識ベースの初期データ投入
pnpm db:reset               # データベースリセット（開発環境のみ）
```

### テスト
```bash
pnpm tsx scripts/tests/run-tests.ts  # 全テスト実行
pnpm tsx scripts/tests/integrated-test-suite.ts  # 統合テスト
pnpm tsx scripts/tests/router-agent-test.ts  # ルーティングテスト
pnpm tsx scripts/tests/calendar-integration-test.ts  # カレンダーテスト
```

---

## 参考リンク

- [Mastra Documentation](https://mastra.dev)
- [Next.js Documentation](https://nextjs.org/docs)
- [Supabase Documentation](https://supabase.com/docs)
- [Google Cloud Speech-to-Text](https://cloud.google.com/speech-to-text/docs)
- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)

---

## お問い合わせ

技術的な質問や提案がある場合は、GitHubのIssueを作成してください。

---

*このドキュメントは継続的に更新されます。最新版は常にリポジトリのmainブランチを参照してください。*
