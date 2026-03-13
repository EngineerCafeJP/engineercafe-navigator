# Router Agent

> クエリルーティングを担当する中央振り分けエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **テリスケ** | メイン実装 |
| **YukitoLyn** | レビュー・サポート |

## 概要

Router Agentは、ユーザーからの入力を分析し、適切な専門エージェントにルーティングする役割を担います。マルチエージェントアーキテクチャの「交通整理役」として機能し、システム全体の応答品質と効率性を左右する重要なコンポーネントです。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **言語検出** | ユーザー入力が日本語か英語かを判定 |
| **クエリ分類** | 質問のカテゴリ（営業時間、設備、イベント等）を特定 |
| **エージェント選択** | 最適な専門エージェントを決定 |
| **コンテキスト継承** | 文脈依存クエリの場合、前回の情報を引き継ぐ |
| **メモリ関連判定** | 「さっき何を聞いた？」等のメモリ系質問を識別 |

### 責任範囲外

- 実際の質問への回答生成（専門エージェントの責務）
- 音声処理（Voice Agentの責務）
- データベースアクセス（各専門エージェントの責務）

## アーキテクチャ上の位置づけ

```
[ユーザー入力]
       │
       ▼
┌─────────────────┐
│  Router Agent   │  ← このエージェント
└────────┬────────┘
         │
    ┌────┴────┬────────┬────────┬────────┬────────┐
    ▼         ▼        ▼        ▼        ▼        ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│Business│ │Facility│ │ Event │ │Memory │ │General│ │Clarify│
│ Info  │ │       │ │       │ │       │ │Knowledge│ │      │
└───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘
```

## 依存関係

### 入力依存

| コンポーネント | 用途 |
|--------------|------|
| `QueryClassifier` | クエリのカテゴリ分類ロジック |
| `LanguageProcessor` | 言語検出・応答言語決定 |
| `SimplifiedMemorySystem` | 文脈継承時の前回情報取得 |

### 出力先

| エージェント | ルーティング条件 |
|------------|-----------------|
| `BusinessInfoAgent` | 営業時間、料金、場所に関する質問 |
| `FacilityAgent` | 設備、Wi-Fi、地下施設に関する質問 |
| `EventAgent` | イベント、カレンダーに関する質問 |
| `MemoryAgent` | 会話履歴に関する質問 |
| `GeneralKnowledgeAgent` | 上記に該当しない一般的な質問 |
| `ClarificationAgent` | 曖昧な質問（カフェ/会議室の特定が必要） |

## ルーティングロジック

### 優先順位

1. **メモリ関連チェック** - 「さっき」「覚えてる」等のキーワード → `MemoryAgent`
2. **文脈依存チェック** - 「土曜日も同じ？」等 → 前回のエージェントへ
3. **曖昧性チェック** - カフェ・会議室の特定が必要 → `ClarificationAgent`
4. **リクエストタイプ判定** - 具体的なキーワードから判定
5. **カテゴリマッピング** - 分類結果に基づくエージェント選択

### リクエストタイプ一覧

| タイプ | キーワード例 | ルーティング先 |
|-------|-------------|---------------|
| `hours` | 営業時間、何時まで、open | BusinessInfoAgent |
| `price` | 料金、いくら、price | BusinessInfoAgent |
| `location` | 場所、どこ、アクセス | BusinessInfoAgent |
| `wifi` | Wi-Fi、インターネット | FacilityAgent |
| `facility` | 設備、電源、プリンター | FacilityAgent |
| `basement` | 地下、B1、MTGスペース | FacilityAgent |
| `event` | イベント、勉強会、セミナー | EventAgent |

## パフォーマンス指標

| 指標 | 目標値 | 現在値（Mastra版） |
|-----|-------|-------------------|
| ルーティング精度 | 95%以上 | 94.1% |
| 処理時間 | 100ms以下 | 約50ms |
| 文脈継承成功率 | 90%以上 | 実装済み |

## 現在の実装（Mastra）

### ファイル構成

```
engineer-cafe-navigator-repo/src/
├── mastra/agents/router-agent.ts    # メインロジック
├── lib/query-classifier.ts          # クエリ分類
└── lib/language-processor.ts        # 言語処理
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `routeQuery()` | メインルーティング処理 |
| `selectAgent()` | エージェント選択ロジック |
| `extractRequestType()` | リクエストタイプ抽出 |
| `isMemoryRelatedQuestion()` | メモリ関連判定 |
| `isContextDependentQuery()` | 文脈依存判定 |

## LangGraph移行後の設計

### ノード構成

```python
# LangGraphワークフロー内でのノード
workflow.add_node("router", router_node)
workflow.add_conditional_edges(
    "router",
    route_decision,
    {
        "business_info": "business_info",
        "facility": "facility",
        "event": "event",
        "memory": "memory",
        "general_knowledge": "general_knowledge",
        "clarification": "clarification",
    }
)
```

### 状態定義

```python
class RouterState(TypedDict):
    query: str
    session_id: str
    language: str  # 'ja' | 'en'
    routed_to: str | None
    request_type: str | None
    confidence: float
    context: dict
```

## 関連ドキュメント

- [SPEC.md](./SPEC.md) - 入出力仕様の詳細
- [MIGRATION-GUIDE.md](./MIGRATION-GUIDE.md) - Mastra→LangGraph移行手順
- [TESTING.md](./TESTING.md) - テスト戦略とテストケース

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] ルーティングロジックの優先順位を把握した
- [ ] 各エージェントへの振り分け条件を確認した
- [ ] LangGraph版の設計方針を理解した
- [ ] テストケースを確認した
