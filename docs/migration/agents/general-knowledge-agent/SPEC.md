# General Knowledge Agent - 技術仕様書

> 入出力仕様・API定義・データ構造

## 入力仕様

### メイン入力: `answerGeneralQuery()`

```typescript
interface GeneralQueryInput {
  query: string;              // ユーザーからの入力テキスト
  language: SupportedLanguage; // 'ja' | 'en'
}
```

#### 入力例

```typescript
// 一般情報クエリ
{
  query: "エンジニアカフェについて教えて",
  language: "ja"
}

// 技術トレンドクエリ
{
  query: "最新のAI技術について教えて",
  language: "ja"
}

// 福岡のスタートアップ情報
{
  query: "Tell me about Fukuoka's tech scene",
  language: "en"
}

// 情報が見つからない場合
{
  query: "明日の天気は？",
  language: "ja"
}
```

## 出力仕様

### メイン出力: `UnifiedAgentResponse`

```typescript
interface UnifiedAgentResponse {
  text: string;              // 生成された回答テキスト（感情タグ付き）
  emotion: EmotionType;      // 'helpful' | 'apologetic'
  agentName: string;         // 'GeneralKnowledgeAgent'
  language: SupportedLanguage; // 'ja' | 'en'
  metadata: {
    confidence: number;      // 信頼度 (0.3 - 0.9)
    category: string;        // 'general_knowledge'
    sources: string[];       // データソース配列
    processingInfo: {
      enhancedRag: boolean;  // false (Enhanced RAG不使用)
    };
  };
}
```

#### 出力例

```typescript
// ナレッジベースと検索の両方を使用
{
  text: "[relaxed]エンジニアカフェは福岡市中央区にあるコワーキングスペースです。最新のWeb検索によると、現在多くのスタートアップ企業が利用しています。",
  emotion: "helpful",
  agentName: "GeneralKnowledgeAgent",
  language: "ja",
  metadata: {
    confidence: 0.9,
    category: "general_knowledge",
    sources: ["knowledge base", "web search"],
    processingInfo: {
      enhancedRag: false
    }
  }
}

// ナレッジベースのみ
{
  text: "[relaxed]Engineer Cafe is a coworking space located in Fukuoka City. It provides a collaborative environment for engineers and entrepreneurs.",
  emotion: "helpful",
  agentName: "GeneralKnowledgeAgent",
  language: "en",
  metadata: {
    confidence: 0.8,
    category: "general_knowledge",
    sources: ["knowledge base"],
    processingInfo: {
      enhancedRag: false
    }
  }
}

// ウェブ検索のみ
{
  text: "[happy]最新のAI技術については、2025年現在、生成AIやマルチモーダルモデルが急速に発展しています。",
  emotion: "helpful",
  agentName: "GeneralKnowledgeAgent",
  language: "ja",
  metadata: {
    confidence: 0.6,
    category: "general_knowledge",
    sources: ["web search"],
    processingInfo: {
      enhancedRag: false
    }
  }
}

// 情報が見つからない場合
{
  text: "[sad]申し訳ございません。ご質問に答えるための具体的な情報が見つかりませんでした。質問を言い換えていただくか、別のことについてお尋ねください。",
  emotion: "apologetic",
  agentName: "GeneralKnowledgeAgent",
  language: "ja",
  metadata: {
    confidence: 0.3,
    category: "general_knowledge",
    sources: ["fallback"],
    processingInfo: {
      enhancedRag: false
    }
  }
}
```

## データソース仕様

### ウェブ検索判定キーワード

#### 日本語キーワード

```typescript
const japaneseWebSearchKeywords = [
  '最新',        // Latest
  '現在',        // Current
  '今',          // Now
  'ニュース',    // News
  'トレンド',    // Trend
  'スタートアップ', // Startup
  'ベンチャー',  // Venture
  '技術',        // Technology
  'AI',
  '人工知能',    // Artificial Intelligence
  '機械学習',    // Machine Learning
  'プログラミング' // Programming
];
```

#### 英語キーワード

```typescript
const englishWebSearchKeywords = [
  'latest',
  'current',
  'now',
  'news',
  'trend',
  'startup',
  'venture',
  'technology',
  'ai',
  'artificial intelligence',
  'machine learning',
  'programming'
];
```

### データソース優先順位

| データソース組み合わせ | 信頼度 | 使用条件 |
|---------------------|-------|---------|
| Knowledge Base + Web Search | 0.9 | 両方のソースで情報が見つかった場合 |
| Knowledge Base のみ | 0.8 | ナレッジベースのみで情報が見つかった場合 |
| Web Search のみ | 0.6 | ウェブ検索のみで情報が見つかった場合 |
| Fallback | 0.3 | どのソースでも情報が見つからない場合 |

## 感情タグ仕様

### 感情マッピング

```typescript
interface EmotionMapping {
  situation: string;
  tag: string;
  examples: string[];
}

const emotionRules: EmotionMapping[] = [
  {
    situation: "一般情報の提供",
    tag: "[relaxed]",
    examples: [
      "エンジニアカフェについて教えて",
      "福岡の情報を知りたい"
    ]
  },
  {
    situation: "技術ニュース・ポジティブ情報",
    tag: "[happy]",
    examples: [
      "最新のAI技術について教えて",
      "福岡のスタートアップシーンについて"
    ]
  },
  {
    situation: "革新的・驚きの情報",
    tag: "[surprised]",
    examples: [
      "画期的な技術について",
      "予想外の発見について"
    ]
  },
  {
    situation: "情報が見つからない・課題について",
    tag: "[sad]",
    examples: [
      "情報が見つかりませんでした",
      "現在は対応していません"
    ]
  }
];
```

### emotion プロパティマッピング

| 感情タグ | emotion値 | 使用場面 |
|---------|----------|---------|
| `[relaxed]` | `helpful` | 一般的な情報提供 |
| `[happy]` | `helpful` | ポジティブな技術情報 |
| `[surprised]` | `helpful` | 革新的な情報 |
| `[sad]` | `apologetic` | 情報なし・エラー |

## ツール仕様

### ragSearch ツール

**入力:**
```typescript
{
  query: string;     // 検索クエリ
  language: SupportedLanguage; // 言語
  limit: number;     // 取得件数（デフォルト: 10）
}
```

**出力:**
```typescript
{
  success: boolean;
  results?: Array<{
    content: string;
    similarity: number;
  }>;
  data?: {
    context: string;
  };
}
```

### generalWebSearch ツール

**入力:**
```typescript
{
  query: string;     // 検索クエリ
  language: SupportedLanguage; // 言語
}
```

**出力:**
```typescript
{
  success: boolean;
  text?: string;     // 検索結果テキスト
  data?: {
    context: string;
  };
}
```

## 内部処理フロー

### 処理シーケンス

```
1. answerGeneralQuery(query, language) 呼び出し
   │
   ├─2. ウェブ検索判定
   │    └─ shouldUseWebSearch(query)
   │         → キーワードマッチング
   │
   ├─3. ナレッジベース検索（常に実行）
   │    └─ ragSearch.execute({ query, language, limit: 10 })
   │         → 成功: context += KB results
   │         → 失敗: エラーログ
   │
   ├─4. ウェブ検索（条件付き実行）
   │    └─ if (needsWebSearch || !context)
   │         → generalWebSearch.execute({ query, language })
   │              → 成功: context += web results
   │              → 失敗: エラーログ
   │
   ├─5. コンテキスト評価
   │    └─ if (!context)
   │         → getDefaultGeneralResponse(language)
   │
   ├─6. プロンプト構築
   │    └─ buildGeneralPrompt(query, context, sources, language)
   │
   ├─7. LLM生成
   │    └─ generate([{ role: 'user', content: prompt }])
   │
   └─8. レスポンス構築
        └─ createUnifiedResponse(text, emotion, agentName, language, metadata)
```

## プロンプト構築仕様

### 英語プロンプト

```typescript
`Answer the following question using the provided information from ${sourceInfo}.

Question: ${query}

Information:
${context}

Provide a comprehensive but concise answer. If the information is from web search, mention that it's current information. Be helpful and informative.`
```

### 日本語プロンプト

```typescript
`${sourceInfo}から提供された情報を使用して、次の質問に答えてください。

質問: ${query}

情報:
${context}

包括的だが簡潔な回答を提供してください。情報がウェブ検索からのものである場合は、それが最新の情報であることを述べてください。役立つ情報を提供してください。`
```

## エラーハンドリング

### エラーケース

| ケース | 対応 | 信頼度 |
|-------|------|-------|
| RAG検索エラー | エラーログ、処理継続 | 0.6（Web検索成功時） |
| Web検索エラー | エラーログ、処理継続 | 0.8（KB検索成功時） |
| 両方エラー | デフォルトレスポンス | 0.3 |
| コンテキストなし | デフォルトレスポンス | 0.3 |

### ログ出力

```typescript
// 正常系
console.log('[GeneralKnowledgeAgent] Processing general query:', { query, language });

// エラー系
console.error('[GeneralKnowledgeAgent] RAG search error:', error);
console.error('[GeneralKnowledgeAgent] Web search error:', error);
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal
from enum import Enum

class SupportedLanguage(str, Enum):
    JA = "ja"
    EN = "en"

class EmotionType(str, Enum):
    HELPFUL = "helpful"
    APOLOGETIC = "apologetic"

class GeneralQueryInput(TypedDict):
    query: str
    language: SupportedLanguage

class GeneralKnowledgeMetadata(TypedDict):
    confidence: float
    category: str
    sources: list[str]
    processing_info: dict

class UnifiedAgentResponse(TypedDict):
    text: str
    emotion: EmotionType
    agent_name: str
    language: SupportedLanguage
    metadata: GeneralKnowledgeMetadata
```

### ノード関数シグネチャ

```python
def general_knowledge_node(state: WorkflowState) -> dict:
    """
    General Knowledgeノード: 一般的な質問に対する回答を生成

    Args:
        state: ワークフロー状態（query, language, context等を含む）

    Returns:
        dict: response, metadata を含む辞書
    """
    pass

def should_use_web_search(query: str) -> bool:
    """
    ウェブ検索が必要かどうかを判定

    Args:
        query: ユーザークエリ

    Returns:
        bool: ウェブ検索が必要な場合True
    """
    pass
```

## 信頼度計算ロジック

### 計算アルゴリズム

```typescript
function calculateConfidence(sources: string[]): number {
  const hasKnowledgeBase = sources.includes('knowledge_base');
  const hasWebSearch = sources.includes('web_search');

  if (hasKnowledgeBase && hasWebSearch) {
    return 0.9;  // 両方のソース
  } else if (hasKnowledgeBase) {
    return 0.8;  // ナレッジベースのみ
  } else if (hasWebSearch) {
    return 0.6;  // ウェブ検索のみ
  } else {
    return 0.3;  // フォールバック
  }
}
```

### 信頼度区分

| 信頼度範囲 | 評価 | データソース |
|-----------|------|-------------|
| 0.9 | 非常に高い | KB + Web |
| 0.8 | 高い | KB のみ |
| 0.6 - 0.7 | 中程度 | Web のみ |
| 0.3 - 0.5 | 低い | Fallback |

## パフォーマンス目標

### 応答時間目標

| 処理段階 | 目標時間 |
|---------|---------|
| KB検索 | 500ms以下 |
| Web検索 | 2000ms以下 |
| LLM生成 | 1500ms以下 |
| **合計** | **4000ms以下** |

### リソース使用制限

| リソース | 制限 |
|---------|------|
| KB検索結果 | 10件まで |
| Web検索結果 | 1ページ分 |
| コンテキスト長 | 4000文字以内 |
| LLM生成トークン | 500トークン以内 |

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-07 | Web検索統合 |
| 1.2 | 2024-12 | 感情タグ強化 |
| 2.0 | 予定 | LangGraph移行 |
