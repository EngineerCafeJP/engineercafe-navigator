# Business Info Agent

> 営業情報・料金・場所に関する質問に回答するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **テリスケ** | メイン実装 |

## 概要

Business Info Agentは、エンジニアカフェおよびSainoカフェの基本情報（営業時間、料金、場所、アクセス方法など）に関する質問に回答します。Enhanced RAGシステムと連携し、高精度な情報検索と回答生成を行います。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **営業時間回答** | エンジニアカフェ・Sainoカフェの営業時間を回答 |
| **料金情報提供** | 利用料金、会員プランなどの料金情報を提供 |
| **場所・アクセス** | 所在地、最寄り駅、アクセス方法を案内 |
| **基本情報全般** | 上記以外の基本的な施設情報を提供 |

### 責任範囲外

- 設備・Wi-Fi詳細（FacilityAgentの責務）
- イベント情報（EventAgentの責務）
- 会議室の詳細（FacilityAgentの責務）

## アーキテクチャ上の位置づけ

```
[Router Agent]
       │
       ▼ requestType: hours/price/location
┌─────────────────────┐
│ Business Info Agent │ ← このエージェント
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Enhanced RAG      │
│  (Priority Scorer)  │
└─────────────────────┘
```

## 対応するリクエストタイプ

| requestType | キーワード例 | 説明 |
|-------------|-------------|------|
| `hours` | 営業時間, 何時まで, open | 営業時間に関する質問 |
| `price` | 料金, いくら, price | 料金に関する質問 |
| `location` | 場所, どこ, access | 場所・アクセスに関する質問 |

## 依存関係

### 入力依存

| コンポーネント | 用途 |
|--------------|------|
| `Enhanced RAG` | ナレッジベースからの情報検索 |
| `RAGPriorityScorer` | エンティティ認識・結果優先順位付け |
| `SimplifiedMemorySystem` | 文脈継承（前回の質問情報） |

### 出力

```typescript
interface BusinessInfoResponse {
  answer: string;           // 回答テキスト
  emotion: string;          // 感情タグ
  confidence: number;       // 信頼度
  sources: string[];        // 情報ソース
  category: string;         // カテゴリ
}
```

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/business-info-agent.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `answerBusinessQuery()` | メインの質問回答処理 |
| `buildPrompt()` | RAG結果からプロンプト構築 |
| `formatResponse()` | 応答のフォーマット処理 |

## Enhanced RAG統合

### エンティティ認識

- **Engineer Cafe**: エンジニアカフェ関連のコンテンツを優先
- **Saino Cafe**: サイノカフェ関連のコンテンツを優先
- **自動判定**: クエリからエンティティを自動検出

### カテゴリマッピング

```python
# requestType → Enhanced RAGカテゴリ
{
    "hours": "hours",
    "price": "pricing",
    "location": "access"
}
```

## LangGraph移行後の設計

### ノード定義

```python
def business_info_node(state: WorkflowState) -> dict:
    """ビジネス情報ノード"""
    query = state["query"]
    request_type = state["metadata"]["routing"]["request_type"]

    # Enhanced RAGで検索
    rag_results = enhanced_rag_search(
        query=query,
        category=map_request_type_to_category(request_type),
        entity=detect_entity(query)
    )

    # 回答生成
    answer = generate_business_answer(query, rag_results)

    return {
        "response": answer,
        "metadata": {
            "agent": "BusinessInfoAgent",
            "confidence": calculate_confidence(rag_results)
        }
    }
```

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| 営業時間 | 「エンジニアカフェの営業時間は？」→ 9:00〜22:00 |
| 料金 | 「利用料金はいくら？」→ 無料（基本エリア） |
| 場所 | 「場所はどこ？」→ 福岡市中央区天神... |
| Saino | 「Sainoの営業時間は？」→ 11:00〜20:30 |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] Enhanced RAGの統合方法を把握した
- [ ] エンティティ認識（Engineer Cafe/Saino）を理解した
- [ ] テストケースを確認した
- [ ] LangGraph版の設計方針を理解した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - ルーティング元
- [Facility Agent](../facility-agent/README.md) - 設備関連
- [Enhanced RAG](../../tools/enhanced-rag.md) - RAGシステム
