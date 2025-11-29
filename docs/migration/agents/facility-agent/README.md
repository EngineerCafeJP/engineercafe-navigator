# Facility Agent

> 施設・設備・Wi-Fi・地下施設に関する質問に回答するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **Natsumi** | メイン実装 |
| **けいてぃー** | レビュー・サポート |

## 概要

Facility Agentは、エンジニアカフェの設備（Wi-Fi、電源、プリンターなど）および地下施設（MTGスペース、集中スペース、アンダースペース、Makersスペース）に関する質問に回答します。Enhanced RAGと連携し、詳細な施設情報を提供します。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **Wi-Fi情報** | Wi-Fiの有無、接続方法、パスワードなど |
| **電源・設備** | 電源コンセント、プリンター、その他設備 |
| **地下施設案内** | B1Fの各スペース（MTG、集中、Under、Makers） |
| **利用方法** | 各設備・スペースの利用方法・予約方法 |

### 責任範囲外

- 営業時間・料金（BusinessInfoAgentの責務）
- イベント情報（EventAgentの責務）
- カフェメニュー（BusinessInfoAgentの責務）

## アーキテクチャ上の位置づけ

```
[Router Agent]
       │
       ▼ requestType: wifi/facility/basement
┌─────────────────┐
│  Facility Agent │ ← このエージェント
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│   Enhanced RAG      │
│  (地下施設優先検出) │
└─────────────────────┘
```

## 対応するリクエストタイプ

| requestType | キーワード例 | 説明 |
|-------------|-------------|------|
| `wifi` | Wi-Fi, インターネット, ネット | Wi-Fi関連の質問 |
| `facility` | 設備, 電源, プリンター | 設備全般の質問 |
| `basement` | 地下, B1, MTGスペース | 地下施設の質問 |

## 地下施設の種類

| スペース名 | 説明 | 予約 |
|-----------|------|------|
| **MTGスペース** | カジュアルな打ち合わせ用 | 不要（先着順） |
| **集中スペース** | 静かな作業環境 | 不要（先着順） |
| **アンダースペース** | イベント・セミナー用 | 要予約 |
| **Makersスペース** | モノづくり・工作用 | 要予約 |

## 依存関係

### 入力依存

| コンポーネント | 用途 |
|--------------|------|
| `Enhanced RAG` | 施設情報の検索 |
| `地下施設検出` | basement関連クエリの優先処理 |

### クエリ拡張

```typescript
// 地下施設検索時のクエリ拡張
const basementKeywords = [
  '地下', 'basement', 'B1', 'MTGスペース',
  '集中スペース', 'アンダースペース', 'Makersスペース',
  'ミーティングスペース', '会議スペース'
];
```

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/facility-agent.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `answerFacilityQuery()` | メインの質問回答処理 |
| `expandBasementQuery()` | 地下施設クエリの拡張 |
| `buildFacilityPrompt()` | 施設情報プロンプト構築 |

## LangGraph移行後の設計

### ノード定義

```python
def facility_node(state: WorkflowState) -> dict:
    """施設情報ノード"""
    query = state["query"]
    request_type = state["metadata"]["routing"]["request_type"]

    # 地下施設クエリの場合は拡張
    if request_type == "basement":
        query = expand_basement_query(query)

    # Enhanced RAGで検索
    rag_results = enhanced_rag_search(
        query=query,
        category="facility-info"
    )

    return {
        "response": generate_facility_answer(query, rag_results),
        "metadata": {"agent": "FacilityAgent"}
    }
```

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| Wi-Fi | 「Wi-Fiはありますか？」→ はい、無料で利用可能 |
| 電源 | 「電源は使えますか？」→ 各席に電源あり |
| 地下MTG | 「地下の会議室について」→ MTGスペースは予約不要... |
| 集中スペース | 「集中スペースとは？」→ 静かな作業環境... |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] 地下施設の4種類（MTG/集中/Under/Makers）を把握した
- [ ] 地下施設検出の優先処理を理解した
- [ ] クエリ拡張のロジックを理解した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - ルーティング元
- [Business Info Agent](../business-info-agent/README.md) - 基本情報
- [Enhanced RAG](../../tools/enhanced-rag.md) - RAGシステム
