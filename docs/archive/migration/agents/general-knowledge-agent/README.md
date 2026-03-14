# General Knowledge Agent

> 一般的な質問・Web検索に対応するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **テリスケ** | メイン実装 |

## 概要

General Knowledge Agentは、エンジニアカフェに直接関係しない一般的な質問に回答します。ナレッジベースとWeb検索を組み合わせて、幅広い質問に対応します。AI・テクノロジー、福岡のテックシーン、スタートアップ情報などが主な対象です。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **一般情報回答** | エンジニアカフェ以外の一般的な質問への回答 |
| **Web検索** | 最新情報が必要な場合のWeb検索 |
| **テック情報** | AI、プログラミング、技術トレンドの情報提供 |
| **福岡情報** | 福岡のテックシーン、スタートアップ情報 |

### 責任範囲外

- エンジニアカフェの具体的な情報（専門エージェントの責務）
- イベント情報（EventAgentの責務）

## アーキテクチャ上の位置づけ

```
[Router Agent]
       │
       ▼ category: general
┌──────────────────────────┐
│ General Knowledge Agent  │ ← このエージェント
└───────────┬──────────────┘
            │
       ┌────┴────┐
       ▼         ▼
┌──────────┐ ┌──────────┐
│Knowledge │ │   Web    │
│   Base   │ │  Search  │
└──────────┘ └──────────┘
```

## Web検索の判定

### 検索が必要なキーワード

```typescript
// 日本語
['最新', '現在', '今', 'ニュース', 'トレンド', 'スタートアップ', 'ベンチャー',
 '技術', 'AI', '人工知能', '機械学習', 'プログラミング']

// 英語
['latest', 'current', 'now', 'news', 'trend', 'startup', 'venture',
 'technology', 'ai', 'artificial intelligence', 'machine learning', 'programming']
```

### 判定ロジック

```typescript
private shouldUseWebSearch(query: string): boolean {
  const lowerQuery = query.toLowerCase();
  return webSearchKeywords.some(keyword => lowerQuery.includes(keyword));
}
```

## 依存関係

### ツール

| ツール | 用途 |
|-------|------|
| `ragSearch` | ナレッジベース検索 |
| `generalWebSearch` | Web検索 |

### 情報ソースの優先順位

1. **ナレッジベース** → 常に最初に検索
2. **Web検索** → キーワードに該当 or ナレッジベースに情報なし

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/general-knowledge-agent.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `answerGeneralQuery()` | 一般質問への回答処理 |
| `shouldUseWebSearch()` | Web検索が必要か判定 |
| `buildGeneralPrompt()` | プロンプト構築 |
| `getDefaultGeneralResponse()` | 情報なし時のフォールバック |

## LangGraph移行後の設計

### ノード定義

```python
def general_knowledge_node(state: WorkflowState) -> dict:
    """一般知識ノード"""
    query = state["query"]
    language = state["language"]

    sources = []
    context = ""

    # ナレッジベース検索
    kb_results = await rag_search(query, language)
    if kb_results:
        context += kb_results
        sources.append("knowledge_base")

    # Web検索（必要な場合）
    if should_use_web_search(query) or not context:
        web_results = await web_search(query, language)
        if web_results:
            context += "\n\n" + web_results
            sources.append("web_search")

    if not context:
        return fallback_response(language)

    answer = generate_answer(query, context, sources, language)

    return {
        "response": answer,
        "metadata": {
            "agent": "GeneralKnowledgeAgent",
            "sources": sources
        }
    }
```

### 信頼度計算

```python
def calculate_confidence(sources: list[str]) -> float:
    if "knowledge_base" in sources and "web_search" in sources:
        return 0.9
    elif "knowledge_base" in sources:
        return 0.8
    elif "web_search" in sources:
        return 0.6
    else:
        return 0.3
```

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| 一般質問 | 「福岡のおすすめスポットは？」→ Web検索結果 |
| テック質問 | 「AIの最新トレンドは？」→ Web検索結果 |
| 情報なし | 「月面基地の設計」→ フォールバック応答 |

## 感情タグの使い分け

| 状況 | 感情タグ | 理由 |
|-----|---------|------|
| 一般情報 | `[relaxed]` | 落ち着いた説明 |
| テックニュース | `[happy]` | 興味深い情報 |
| 情報なし | `[sad]` | 申し訳なさを表現 |
| 意外な発見 | `[surprised]` | 驚きを表現 |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] Web検索の判定ロジックを把握した
- [ ] ナレッジベースとWeb検索の統合方法を理解した
- [ ] フォールバック応答を確認した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - ルーティング元
- [RAG Search](../../tools/rag-search.md) - ナレッジベース検索
- [Web Search](../../tools/web-search.md) - Web検索
