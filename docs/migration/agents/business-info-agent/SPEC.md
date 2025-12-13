# Business Info Agent - 技術仕様書

> 入出力仕様・API定義・データ構造

## 概要

BusinessInfoAgentは、エンジニアカフェおよびSainoカフェの営業情報、料金、場所、アクセス情報を提供する専門エージェントです。Enhanced RAGシステムとの統合により、エンティティ認識と優先度スコアリングを活用した高精度な情報検索を実現します。

## 入力仕様

### メイン入力: `answerBusinessQuery()`

```typescript
interface BusinessQueryInput {
  query: string;              // ユーザーからの入力テキスト
  category: string;           // クエリカテゴリ (RouterAgentから継承)
  requestType: string | null; // 具体的なリクエストタイプ (RouterAgentから継承)
  language: SupportedLanguage; // 'ja' | 'en'
  sessionId?: string;         // セッション識別子 (オプション)
}
```

#### 入力例

```typescript
// 営業時間の質問
{
  query: "エンジニアカフェの営業時間を教えてください",
  category: "facility-info",
  requestType: "hours",
  language: "ja",
  sessionId: "session_abc123"
}

// 文脈依存の短いクエリ (前の会話で営業時間を聞いた後)
{
  query: "土曜日は？",
  category: "facility-info",
  requestType: null,  // ← メモリから "hours" を継承
  language: "ja",
  sessionId: "session_abc123"
}

// Sainoカフェの料金
{
  query: "sainoの料金は？",
  category: "saino-cafe",
  requestType: "price",
  language: "ja",
  sessionId: "session_xyz456"
}

// 場所の質問
{
  query: "Where is Engineer Cafe located?",
  category: "facility-info",
  requestType: "location",
  language: "en",
  sessionId: "session_def789"
}
```

## 出力仕様

### メイン出力: `UnifiedAgentResponse`

```typescript
interface UnifiedAgentResponse {
  text: string;      // 実際の応答テキスト (感情タグ付き)
  emotion: string;   // 感情 (helpful, informative, guiding, apologetic)
  metadata: {
    agentName: string;          // "BusinessInfoAgent"
    confidence: number;         // 信頼度 (0.0 - 1.0)
    language: SupportedLanguage; // 'ja' | 'en'
    category?: string;          // クエリカテゴリ
    requestType?: string | null; // リクエストタイプ
    sources?: string[];         // 情報源 ['enhanced_rag', 'knowledge_base', 'fallback']
    processingInfo?: {
      filtered: boolean;        // コンテキストフィルタリングの有無
      contextInherited: boolean; // 文脈継承の有無
      enhancedRag: boolean;     // Enhanced RAG使用の有無
    };
  };
}
```

#### 出力例

```typescript
// 営業時間の応答
{
  text: "[relaxed]エンジニアカフェの営業時間は9:00〜22:00です。",
  emotion: "informative",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.85,
    language: "ja",
    category: "facility-info",
    requestType: "hours",
    sources: ["enhanced_rag"],
    processingInfo: {
      filtered: true,
      contextInherited: false,
      enhancedRag: true
    }
  }
}

// 文脈継承後の応答
{
  text: "[relaxed]土曜日も同じ9:00〜22:00です。",
  emotion: "informative",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.85,
    language: "ja",
    category: "facility-info",
    requestType: "hours",
    sources: ["enhanced_rag"],
    processingInfo: {
      filtered: true,
      contextInherited: true,  // ← 前の会話から継承
      enhancedRag: true
    }
  }
}

// 情報が見つからない場合
{
  text: "[sad]申し訳ございません。お探しの情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。",
  emotion: "apologetic",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.3,
    language: "ja",
    category: "facility-info",
    requestType: "hours",
    sources: ["fallback"]
  }
}
```

## requestType マッピングテーブル

### requestType → Enhanced RAG Category

BusinessInfoAgentは、RouterAgentから受け取った`requestType`をEnhanced RAGのカテゴリにマッピングします。

| requestType | Enhanced RAG Category | 説明 | キーワード例 |
|-------------|----------------------|------|------------|
| `hours` | `hours` | 営業時間 | 営業時間, 何時まで, 何時から, open, close, 時間 |
| `price` | `pricing` | 料金情報 | 料金, いくら, 値段, price, cost, fee, メニュー |
| `location` | `location` | 場所情報 | 場所, どこ, where, 住所, address |
| `access` | `location` | アクセス情報 | アクセス, access, 行き方, 駅, station, 交通 |
| `basement` | `facility-info` | 地下施設 | 地下, basement, B1, MTGスペース |
| `facility` | `facility-info` | 一般施設 | 設備, 電源, プリンター, equipment |
| `wifi` | `facility-info` | Wi-Fi情報 | wi-fi, wifi, インターネット, ネット |
| `null` または未定義 | `general` | 一般情報 | その他 |

### emotion マッピング

応答内容に応じて適切な感情を選択します。

| requestType | 推奨 emotion | 説明 |
|-------------|--------------|------|
| `hours`, `price` | `informative` | 事実情報の提供 |
| `location`, `access` | `guiding` | 案内・ガイダンス |
| 情報見つからず | `apologetic` | 謝罪 |
| その他 | `helpful` | 一般的な支援 |

## 内部処理フロー

### 処理シーケンス

```
1. answerBusinessQuery(query, category, requestType, language, sessionId)
   │
   ├─2. 文脈依存チェック
   │    ├─ isShortContextQuery(query)
   │    │    → /^土曜[日]?は.*/, /^saino[のは方]?.*/ などパターンマッチ
   │    │    → query.length < 10 もチェック
   │    │
   │    └─ sessionId && isShortContextQuery → メモリから文脈取得
   │         └─ memory.getContext(query, { inheritContext: true })
   │              ├─ inheritedRequestType (前回のrequestType)
   │              └─ contextEntity (saino / engineer)
   │
   ├─3. requestType 確定
   │    └─ effectiveRequestType = requestType || inheritedRequestType
   │
   ├─4. クエリ拡張 (文脈依存の場合)
   │    └─ enhanceContextQuery(query, effectiveRequestType, language, contextEntity)
   │         ├─ contextEntity === 'saino' → "sainoカフェの営業時間"
   │         ├─ contextEntity === 'engineer' → "エンジニアカフェの営業時間"
   │         ├─ 土曜/日曜/平日 → "エンジニアカフェ 営業時間 曜日"
   │         └─ requestType based → "〜の料金", "〜の場所" など
   │
   ├─5. RAG検索
   │    ├─ Enhanced RAG優先
   │    │    └─ enhancedRagSearch.execute({
   │    │         query: searchQuery,
   │    │         category: mapRequestTypeToCategory(effectiveRequestType),
   │    │         language,
   │    │         includeAdvice: true,
   │    │         maxResults: 10
   │    │       })
   │    │
   │    └─ フォールバック: 標準RAG
   │         └─ ragSearch.execute({ query, language, limit: 10 })
   │
   ├─6. コンテキスト抽出
   │    ├─ Enhanced RAG → searchResult.data.context
   │    └─ 標準RAG → searchResult.results[].content.join('\n\n')
   │
   ├─7. コンテキストフィルタリング (requestTypeが存在する場合)
   │    └─ contextFilter.execute({ context, requestType, language, query })
   │         → 営業時間のみ、料金のみなど特定情報のみ抽出
   │
   ├─8. プロンプト構築
   │    └─ buildPrompt(query, filteredContext, requestType, language)
   │         ├─ requestType あり → 特定情報のみ抽出プロンプト (1-2文)
   │         └─ requestType なし → 簡潔な一般回答プロンプト
   │
   ├─9. LLM応答生成
   │    └─ this.generate([{ role: 'user', content: prompt }])
   │
   └─10. UnifiedAgentResponse作成
        └─ createUnifiedResponse(
             response.text,
             emotion,
             'BusinessInfoAgent',
             language,
             { confidence, category, requestType, sources, processingInfo }
           )
```

### フローチャート

```
┌────────────────────────────────────┐
│ answerBusinessQuery()              │
│ (query, category, requestType,     │
│  language, sessionId)              │
└──────────────┬─────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ 短いクエリ？          │ Yes  ┌─────────────────────┐
    │ isShortContextQuery() │─────→│ メモリから文脈取得   │
    └──────────┬───────────┘      │ - inheritedRequestType│
               │ No                │ - contextEntity       │
               │                   └──────────┬────────────┘
               │                              │
               ▼                              │
    ┌──────────────────────┐                │
    │ requestType 確定      │←───────────────┘
    │ effectiveRequestType  │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ クエリ拡張            │
    │ enhanceContextQuery() │
    │ - saino → "sainoの〜"│
    │ - 土曜 → "〜曜日"    │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ Enhanced RAG 検索         │
    │ category: hours/pricing/  │
    │           location/etc    │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ コンテキスト抽出          │
    │ - Enhanced: data.context  │
    │ - Standard: results[]     │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ コンテキストフィルタ      │ (requestType存在時)
    │ → 営業時間のみ抽出        │
    │ → 料金のみ抽出            │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ プロンプト構築            │
    │ - 特定情報抽出 (1-2文)    │
    │ - 感情タグ指定            │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ Gemini LLM 応答生成       │
    │ this.generate()           │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ UnifiedAgentResponse 作成 │
    │ - text (感情タグ付き)     │
    │ - emotion                 │
    │ - metadata                │
    └────────────────────────────┘
```

## 文脈依存クエリパターン

### 短いクエリの判定パターン (正規表現)

BusinessInfoAgentは、以下のパターンに一致するクエリを「文脈依存クエリ」として認識します。

```typescript
// 曜日パターン
/^土曜[日]?は.*/          // 土曜日は... 土曜は...
/^日曜[日]?は.*/          // 日曜日は... 日曜は...
/^平日は.*/               // 平日は...

// Sainoカフェ参照パターン
/^saino[のは方]?.*/       // sainoの方は... sainoは...

// 指示代名詞パターン
/^そっち[のは]?.*/        // そっちの方は... そっちは...
/^あっち[のは]?.*/        // あっちの方は... あっちは...
/^それ[のは]?.*/          // それの方は... それは...
/^そこ[のは]?.*/          // そこの方は... そこは...

// 長さベース判定
query.length < 10         // 10文字未満のクエリ
```

### 文脈エンティティ検出

メモリから取得した会話履歴を分析し、文脈エンティティを特定します。

```typescript
if (memoryContext.contextString.includes('サイノカフェ') ||
    memoryContext.contextString.includes('saino')) {
  contextEntity = 'saino';
} else if (memoryContext.contextString.includes('エンジニアカフェ')) {
  contextEntity = 'engineer';
}
```

### クエリ拡張ロジック

#### Sainoカフェ拡張

| 元のクエリ | requestType | 拡張後のクエリ (日本語) | 拡張後のクエリ (英語) |
|-----------|-------------|------------------------|---------------------|
| "saino" | hours | "sainoカフェの営業時間" | "saino cafe operating hours" |
| "saino" | price | "sainoカフェの料金 メニュー" | "saino cafe prices menu" |
| "saino" | null | "sainoカフェ 情報" | "saino cafe information" |

#### 曜日クエリ拡張

| 元のクエリ | requestType | 拡張後のクエリ (日本語) | 拡張後のクエリ (英語) |
|-----------|-------------|------------------------|---------------------|
| "土曜日は？" | (inherited: hours) | "エンジニアカフェ 営業時間 曜日" | "engineer cafe operating hours days" |
| "日曜は？" | (inherited: hours) | "エンジニアカフェ 営業時間 曜日" | "engineer cafe operating hours days" |
| "平日は？" | (inherited: price) | "エンジニアカフェ 料金 価格" | "engineer cafe price cost" |

#### エンティティ + requestType拡張

| contextEntity | requestType | query.length < 10 | 拡張後のクエリ (日本語) |
|---------------|-------------|-------------------|------------------------|
| saino | hours | Yes | "sainoカフェの営業時間" |
| engineer | price | Yes | "エンジニアカフェの料金 価格" |
| saino | location | Yes | "sainoカフェの場所 アクセス" |

## ツール依存関係

### 必須ツール

#### 1. Enhanced RAG Search Tool

**ツール名**: `enhancedRagSearch`

**機能**: エンティティ認識と優先度スコアリングを活用した高精度検索

**実行インターフェース**:
```typescript
await enhancedRagSearch.execute({
  query: string,          // 検索クエリ
  category: string,       // hours, pricing, location, facility-info, general
  language: SupportedLanguage,
  includeAdvice: boolean, // 実用的なアドバイス生成
  maxResults: number      // 最大結果数 (通常10)
})
```

**返却データ**:
```typescript
{
  success: boolean,
  data: {
    context: string,      // 統合されたコンテキスト文字列
    results: Array<{
      content: string,
      category: string,
      subcategory: string,
      score: number,
      priority: number    // エンティティ認識による優先度
    }>,
    advice?: string       // 実用的なアドバイス (オプション)
  }
}
```

#### 2. Standard RAG Search Tool (フォールバック)

**ツール名**: `ragSearch`

**機能**: 標準的なベクトル検索

**実行インターフェース**:
```typescript
await ragSearch.execute({
  query: string,
  language: SupportedLanguage,
  limit: number  // 最大結果数 (通常10)
})
```

**返却データ**:
```typescript
{
  success: boolean,
  results: Array<{
    content: string,
    metadata: {
      category: string,
      subcategory: string,
      language: string
    }
  }>
}
```

#### 3. Context Filter Tool

**ツール名**: `contextFilter`

**機能**: requestTypeに基づいた特定情報のみの抽出

**実行インターフェース**:
```typescript
await contextFilter.execute({
  context: string,        // フィルタ対象のコンテキスト
  requestType: string,    // hours, price, location, etc.
  language: SupportedLanguage,
  query: string          // 元のユーザークエリ
})
```

**返却データ**:
```typescript
{
  success: boolean,
  data: {
    filteredContext: string  // フィルタリング後のコンテキスト
  }
}
```

**フィルタリング例**:

```typescript
// 入力コンテキスト (複数情報が含まれる)
`エンジニアカフェは東京都千代田区にあります。
営業時間は9:00〜22:00です。
料金は1時間500円、1日2000円です。`

// requestType: "hours" でフィルタ
↓
`営業時間は9:00〜22:00です。`

// requestType: "price" でフィルタ
↓
`料金は1時間500円、1日2000円です。`
```

### オプショナルツール

#### SimplifiedMemorySystem

**機能**: 会話履歴とrequestType継承

**使用メソッド**:
```typescript
// 文脈とrequestType継承を取得
const memoryContext = await memory.getContext(query, {
  includeKnowledgeBase: false,
  language,
  inheritContext: true
});

// 返却値
{
  recentMessages: Message[],
  knowledgeResults: [],
  contextString: string,          // 会話履歴文字列
  inheritedRequestType: string | null  // 前回のrequestType
}
```

## プロンプトテンプレート

### requestType指定時 (特定情報抽出)

#### 日本語プロンプト

```
次の情報から{requestTypePrompt}のみを抽出して質問に答えてください。

質問: {query}
情報: {context}

{requestTypePrompt}のみを答えてください。最大1-2文。他の情報は含めないでください。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。
```

**requestTypePrompt マッピング**:
- `hours` → "営業時間"
- `price` → "料金情報"
- `location` → "場所情報"
- `access` → "アクセス情報"
- `basement` → "地下施設情報"

#### 英語プロンプト

```
Extract ONLY the {requestTypePrompt} from the following information to answer the question.

Question: {query}
Information: {context}

Answer with ONLY the {requestTypePrompt}. Maximum 1-2 sentences. Do not include any other information.
IMPORTANT: Start your response with [relaxed] for information or [happy] for positive news.
```

**requestTypePrompt マッピング**:
- `hours` → "operating hours"
- `price` → "pricing information"
- `location` → "location information"
- `access` → "access information"
- `basement` → "basement facility information"

### requestType未指定時 (一般回答)

#### 日本語プロンプト

```
提供された情報を使って質問に答えてください。簡潔で直接的に答えてください。

質問: {query}
情報: {context}

関連する情報のみを簡潔に（1-2文）答えてください。
重要: 感情タグで回答を始めてください: 情報提供は[relaxed]、良いニュースは[happy]、利用できないサービスは[sad]。
```

#### 英語プロンプト

```
Answer the question using the provided information. Be concise and direct.

Question: {query}
Information: {context}

Answer briefly (1-2 sentences) with only the relevant information.
IMPORTANT: Start your response with an emotion tag: [relaxed] for information, [happy] for positive news, [sad] for unavailable services.
```

## エラーハンドリング

### エラーケース

| エラーケース | 対応 | confidence | emotion |
|------------|------|-----------|---------|
| RAG検索失敗 | getDefaultResponse() | 0.3 | apologetic |
| RAG結果が空 | getDefaultResponse() | 0.3 | apologetic |
| コンテキストが空 | getDefaultResponse() | 0.3 | apologetic |
| コンテキストフィルタ失敗 | フィルタなしで継続 | 0.85 | 元のemotion |
| メモリアクセス失敗 | inheritedRequestType = null で継続 | 0.85 | 元のemotion |

### デフォルトレスポンス

```typescript
// 日本語
{
  text: "[sad]申し訳ございません。お探しの情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。",
  emotion: "apologetic",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.3,
    language: "ja",
    category: category,
    requestType: requestType,
    sources: ["fallback"]
  }
}

// 英語
{
  text: "[sad]I'm sorry, I couldn't find the specific information you're looking for. Please try rephrasing your question or contact the staff for assistance.",
  emotion: "apologetic",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.3,
    language: "en",
    category: category,
    requestType: requestType,
    sources: ["fallback"]
  }
}
```

### ログ出力

#### デバッグログ

```typescript
// クエリ処理開始
console.log('[BusinessInfoAgent] Processing query:', {
  query,
  category,
  requestType,
  language,
  sessionId
});

// 文脈継承
console.log('[BusinessInfoAgent] Inherited request type:', effectiveRequestType);

// 文脈エンティティ検出
console.log('[BusinessInfoAgent] Context entity detected:', contextEntity);

// クエリ拡張
console.log('[BusinessInfoAgent] Enhanced context query:', searchQuery);

// RAG検索
console.log('[BusinessInfoAgent] Using Enhanced RAG with category:', category);

// コンテキストフィルタリング
console.log('[BusinessInfoAgent] Filtered context:', {
  originalLength,
  filteredLength
});

// プロンプト構築
console.log('[BusinessInfoAgent] Building prompt with:', {
  queryLength,
  contextLength,
  requestType,
  language
});
```

#### エラーログ

```typescript
// RAG検索エラー
console.error('[BusinessInfoAgent] RAG search error:', error);

// コンテキストフィルタエラー
console.error('[BusinessInfoAgent] Context filter error:', error);

// RAGツールが見つからない
console.error('[BusinessInfoAgent] No RAG search tool available');
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal, Optional
from pydantic import BaseModel

class BusinessQueryInput(BaseModel):
    """ビジネス情報クエリの入力"""
    query: str
    category: str
    request_type: Optional[str]
    language: Literal["ja", "en"]
    session_id: Optional[str] = None

class UnifiedAgentResponse(TypedDict):
    """統一エージェント応答"""
    text: str
    emotion: str
    metadata: dict

class ProcessingInfo(TypedDict):
    """処理情報"""
    filtered: bool
    context_inherited: bool
    enhanced_rag: bool

class ResponseMetadata(TypedDict):
    """応答メタデータ"""
    agent_name: Literal["BusinessInfoAgent"]
    confidence: float
    language: Literal["ja", "en"]
    category: Optional[str]
    request_type: Optional[str]
    sources: list[str]
    processing_info: ProcessingInfo
```

### ノード関数シグネチャ

```python
from langgraph.graph import StateGraph
from typing import Annotated

def business_info_node(state: WorkflowState) -> dict:
    """
    ビジネス情報エージェントノード

    Args:
        state: ワークフロー状態
            - query: ユーザークエリ
            - category: クエリカテゴリ
            - request_type: リクエストタイプ
            - language: 言語
            - session_id: セッションID

    Returns:
        dict: response, emotion, metadata を含む辞書
    """
    # 1. 文脈依存チェック
    if is_short_context_query(state["query"]) and state.get("session_id"):
        memory_context = get_memory_context(
            state["query"],
            session_id=state["session_id"],
            language=state["language"]
        )
        effective_request_type = (
            state["request_type"] or memory_context.get("inherited_request_type")
        )
        context_entity = detect_context_entity(memory_context)
    else:
        effective_request_type = state["request_type"]
        context_entity = None

    # 2. クエリ拡張
    search_query = enhance_context_query(
        state["query"],
        effective_request_type,
        state["language"],
        context_entity
    )

    # 3. Enhanced RAG検索
    rag_category = map_request_type_to_category(effective_request_type)
    search_result = enhanced_rag_search(
        query=search_query,
        category=rag_category,
        language=state["language"],
        include_advice=True,
        max_results=10
    )

    # 4. コンテキスト抽出 & フィルタリング
    context = extract_context(search_result)
    if effective_request_type:
        context = filter_context_by_request_type(
            context,
            effective_request_type,
            state["language"],
            state["query"]
        )

    # 5. プロンプト構築 & LLM応答
    prompt = build_prompt(
        state["query"],
        context,
        effective_request_type,
        state["language"]
    )
    response = llm_generate(prompt)

    # 6. 統一応答作成
    return create_unified_response(
        text=response.text,
        emotion=determine_emotion(effective_request_type),
        agent_name="BusinessInfoAgent",
        language=state["language"],
        metadata={
            "confidence": 0.85,
            "category": state["category"],
            "request_type": effective_request_type,
            "sources": ["enhanced_rag"],
            "processing_info": {
                "filtered": bool(effective_request_type),
                "context_inherited": effective_request_type != state["request_type"],
                "enhanced_rag": True
            }
        }
    )
```

### LangGraphグラフ定義

```python
from langgraph.graph import StateGraph, END

# ワークフローグラフ構築
workflow = StateGraph(WorkflowState)

# ビジネス情報ノード追加
workflow.add_node("business_info", business_info_node)

# エッジ定義
workflow.add_edge("router", "business_info")
workflow.add_edge("business_info", "voice_output")
workflow.add_edge("business_info", "character_control")

# コンパイル
app = workflow.compile()
```

## パフォーマンス指標

### 目標値

| 指標 | 目標値 | 測定方法 |
|------|--------|---------|
| 応答精度 | 85%+ | RAG検索のconfidence |
| 応答時間 | < 3秒 | クエリ受信から応答生成まで |
| 文脈継承率 | 90%+ | 短いクエリでの継承成功率 |
| Enhanced RAG使用率 | 95%+ | enhancedRagTool使用比率 |
| コンテキストフィルタ適用率 | 80%+ | requestType存在時のフィルタ適用率 |

### モニタリングメトリクス

```typescript
// 応答メタデータに含まれるメトリクス
{
  processingInfo: {
    filtered: boolean,           // フィルタ適用の有無
    contextInherited: boolean,   // 文脈継承の有無
    enhancedRag: boolean         // Enhanced RAG使用の有無
  }
}
```

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-07 | 文脈依存クエリ処理追加 |
| 1.2 | 2024-07 | Enhanced RAG統合 |
| 1.3 | 2024-12 | コンテキストフィルタリング強化 |
| 1.4 | 2025-01 | エンティティ認識と優先度スコアリング追加 |
| 2.0 | 予定 | LangGraph移行 |

## 関連ドキュメント

- [RouterAgent SPEC.md](../router-agent/SPEC.md) - クエリルーティング仕様
- [Enhanced RAG System](../../../mastra/tools/enhanced-rag-search.ts) - RAG検索実装
- [SimplifiedMemorySystem](../../../lib/simplified-memory.ts) - メモリシステム実装
- [UnifiedAgentResponse](../../../mastra/types/unified-response.ts) - 応答型定義

## 付録: テストケース例

### 基本営業時間クエリ

```typescript
// 入力
{
  query: "営業時間は？",
  category: "facility-info",
  requestType: "hours",
  language: "ja"
}

// 期待出力
{
  text: "[relaxed]エンジニアカフェの営業時間は9:00〜22:00です。",
  emotion: "informative",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.85,
    language: "ja",
    requestType: "hours",
    sources: ["enhanced_rag"],
    processingInfo: {
      filtered: true,
      contextInherited: false,
      enhancedRag: true
    }
  }
}
```

### 文脈継承クエリ

```typescript
// 前提: 直前に "エンジニアカフェの営業時間は？" を質問済み

// 入力
{
  query: "土曜日は？",
  category: "facility-info",
  requestType: null,
  language: "ja",
  sessionId: "session_123"
}

// 期待出力
{
  text: "[relaxed]土曜日も同じ9:00〜22:00です。",
  emotion: "informative",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.85,
    language: "ja",
    requestType: "hours",  // ← 継承された
    sources: ["enhanced_rag"],
    processingInfo: {
      filtered: true,
      contextInherited: true,  // ← 継承フラグ
      enhancedRag: true
    }
  }
}
```

### Sainoカフェクエリ

```typescript
// 入力
{
  query: "sainoの料金は？",
  category: "saino-cafe",
  requestType: "price",
  language: "ja"
}

// 期待出力
{
  text: "[relaxed]Sainoカフェの料金は、コーヒー1杯500円からです。",
  emotion: "informative",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.85,
    language: "ja",
    requestType: "price",
    sources: ["enhanced_rag"],
    processingInfo: {
      filtered: true,
      contextInherited: false,
      enhancedRag: true
    }
  }
}
```

### エラーケース

```typescript
// 入力 (情報が見つからない場合)
{
  query: "深夜営業はしていますか？",
  category: "facility-info",
  requestType: "hours",
  language: "ja"
}

// 期待出力
{
  text: "[sad]申し訳ございません。お探しの情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。",
  emotion: "apologetic",
  metadata: {
    agentName: "BusinessInfoAgent",
    confidence: 0.3,
    language: "ja",
    requestType: "hours",
    sources: ["fallback"]
  }
}
```
