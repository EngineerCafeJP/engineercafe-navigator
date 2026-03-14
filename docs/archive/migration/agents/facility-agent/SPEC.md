# Facility Agent - 技術仕様書

> 入出力仕様・API定義・データ構造

## 概要

FacilityAgentは、ユーザーからの施設、設備、特に地下施設に関する情報を提供する専門エージェントです。Enhanced RAGシステムとの統合により、エンティティ認識と優先度スコアリングを活用した高精度な情報検索を実現します。

## 入力仕様

### メイン入力: `answerFacilityQuery()`

```typescript
interface FacilityQueryInput {
  query: string;      // ユーザーからの入力テキスト
  requestType: string | null; // 具体的なリクエストタイプ (RouterAgentから継承)
  language: SupportedLanguage; // 'ja' | 'en'
}
```

#### 入力例

```typescript
// Wi-Fi関連のクエリ
{
  query: "Wi-Fiはありますか？",
  requestType: "wifi",
  language: "ja",
}

// 文脈依存クエリ
{
  query: "パスワードは？",
  requestType: "wifi",
  language: "ja",
}

// 設備関連のクエリ
{
  query: "電源は使えますか？",
  requestType: "facility",
  language: "ja",
}

// 地下施設について
{
  query: "集中スペースとは？",
  requestType: "basement",
  language: "ja",
}
```

## 出力仕様

### メイン出力: `UnifiedAgentResponse`

```typescript
interface UnifiedAgentResponse {
  text: string;                    // 施設情報を含む応答テキスト
  emotion: string;                 // 'technical' | 'guiding' | 'apologetic' | 'helpful'
  metadata: {
    agentName: string;          // "FacilityAgent"
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
// Wi-Fiの質問
{
  text: "[relaxed]はい、無料で利用可能です。パスワードは受付でお尋ねください。",
  emotion: "technical",
  metadata: {
    agentName: "FacilityAgent",
    confidence: 0.85,
    language: "ja",
    category: "facility-info",
    requestType: "wifi",
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
  text: "[relaxed]パスワードはxxxxです",
  emotion: "technical",
  metadata: {
    agentName: "FacilityAgent",
    confidence: 0.85,
    language: "ja",
    category: "facility-info",
    requestType: "wifi",
    sources: ["enhanced_rag"],
    processingInfo: {
      filtered: true,
      contextInherited: true,
      enhancedRag: true
    }
  }
}

// 地下施設の質問
{
  text: "[guiding]MTGスペースは地下1階にあり、予約不要で先着順で利用できます。",
  emotion: "guiding",
  metadata: {
    agentName: "FacilityAgent",
    confidence: 0.9,
    language: "ja",
    category: "facility-info",
    requestType: "basement",
    sources: ["enhanced_rag"],
    processingInfo: {
      filtered: true,
      contextInherited: false,
      enhancedRag: true
    }
  }
}

// 情報が見つからない場合
{
  text: "[sad]申し訳ございません。お探しの情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。",
  emotion: "apologetic",
  metadata: {
    agentName: "FacilityAgent",
    confidence: 0.3,
    language: "ja",
    category: "facility-info",
    requestType: "facility",
    sources: ["fallback"]
  }
}
```

## requestType マッピングテーブル

### requestType → Enhanced RAG Category

FacilityAgentは、RouterAgentから受け取った`requestType`をEnhanced RAGのカテゴリにマッピングします。

| requestType | Enhanced RAG Category | 説明 | キーワード例 |
|-------------|----------------------|------|------------|
| `basement` | `facility-info` | 地下施設 | 地下, basement, B1, MTGスペース |
| `facility` | `facility-info` | 一般施設 | 設備, 電源, プリンター, equipment |
| `wifi` | `facility-info` | Wi-Fi情報 | wi-fi, wifi, インターネット, ネット |
| `null` または未定義 | `general` | 一般情報 | その他 |

### emotion マッピング

応答内容に応じて適切な感情を選択します。

| requestType | 推奨 emotion | 説明 |
|-------------|--------------|------|
| `wifi` | `technical` | 事実情報の提供 |
| `basement` | `guiding` | 案内・ガイダンス |
| `facility` | `helpful` | 一般的な支援 |
| 情報見つからず | `apologetic` | 謝罪 |

### requestType値の一覧

| requestType | 説明 | キーワード例 |
|-------------|------|------------|
| `wifi` | Wi-Fi | wi-fi, wifi, インターネット, ネット |
| `facility` | 設備 | 設備, 電源, プリンター, equipment |
| `basement` | 地下施設 | 地下, basement, B1, MTGスペース, 集中スペース |
| `null` | 不明 | 特定できない場合 |

## 内部処理フロー

### 処理シーケンス

```
1. answerFacilityQuery(query, requestType, language) 呼び出し
   │
   ├─2. クエリ拡張
   │    └─ enhanceQuery(query, requestType)
   │         → Wi-Fi: "無料Wi-Fi インターネット 接続" を追加
   │         → 地下施設: "地下 B1 MTGスペース 集中スペース..." を追加
   │         → 設備: "設備 電源 コンセント プリンター" を追加
   │
   ├─3. Enhanced RAG検索
   │    └─ enhancedRagSearch.execute(query, category='facility-info')
   │         → ベクトル検索 + エンティティ認識 + スコアリング
   │
   ├─4. コンテキスト構築
   │    └─ buildContextFromSearchResult(searchResult)
   │
   ├─5. 地下施設フィルタリング (requestType === 'basement' の場合)
   │    └─ detectSpecificFacility(query)
   │         → MTG/集中/アンダー/Makers の特定
   │    └─ filterContextForSpecificFacility(context, facilityName)
   │
   ├─6. コンテキストフィルタリング (requestType が存在する場合)
   │    └─ contextFilter.execute(context, requestType, language, query)
   │         → requestTypeに応じたキーワードでフィルタ
   │
   └─7. LLM生成
        └─ buildFacilityPrompt(query, context, requestType, language)
        └─ llm.generate(prompt)
        └─ createResponseFromText(responseText, isEnhancedRag, requestType, language)
```

## キーワードパターン

### Wi-Fi関連キーワード

```typescript
// 日本語
['Wi-Fi', 'Wifi', '無線', 'インターネット', 'ネット', '接続', 'パスワード']

// 英語
['Wi-Fi', 'Wifi', 'internet', 'network', 'connection', 'wireless', 'password']
```

### 設備関連キーワード

```typescript
// 日本語
['設備', '電源', 'コンセント', 'プリンター', 'プロジェクター', '機器', '貸出']

// 英語
['facility', 'equipment', 'power outlet', 'printer', 'projector', 'device', 'loan']
```

### 地下施設キーワード

```typescript
// 日本語
['地下', 'B1', 'B1F', '地下1階', 'MTGスペース', '集中スペース', 
 'アンダースペース', 'Makersスペース', 'ミーティングスペース', '会議スペース']

// 英語
['basement', 'B1', 'MTG space', 'focus space', 'under space', 
 'makers space', 'underground', 'meeting room', 'meeting space']
```

### 特定地下施設検出パターン

```typescript
// MTGスペース
/MTG|ミーティング|meeting/i

// 集中スペース
/集中|フォーカス|focus/i

// アンダースペース
/アンダー|under/i

// Makersスペース
/Makers|メーカー|makers/i
```

## エラーハンドリング

### エラーケース

| ケース | 対応 |
|-------|------|
| Enhanced RAG検索失敗 | 標準RAGツールにフォールバック |
| RAG検索ツール未設定 | `getDefaultFacilityResponse()` を返す |
| コンテキストが空 | `getDefaultFacilityResponse()` を返す |
| コンテキストフィルタ失敗 | フィルタなしのコンテキストで続行 |
| LLM生成失敗 | デフォルト応答を返す |

### ログ出力

```typescript
// 正常系
console.log(`[FacilityAgent] Processing query: query=${query}, request_type=${requestType}, language=${language}`);
console.log(`[FacilityAgent] Filtered context for specific facility: ${facilityName}`);

// エラー系
console.error('[FacilityAgent] No RAG search tool available');
console.error('[FacilityAgent] RAG search error:', error);
console.error('[FacilityAgent] Context filter error:', error);
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal, Optional

SupportedLanguage = Literal["ja", "en"]

class UnifiedAgentResponse(TypedDict):
    text: str
    emotion: str
    agentName: str
    language: SupportedLanguage
    metadata: dict

class FacilityAgentState(TypedDict):
    query: str
    request_type: Optional[str]
    language: SupportedLanguage
    session_id: str
    metadata: dict
```

### ノード関数シグネチャ

```python
async def facility_node(state: FacilityAgentState) -> dict:
    """
    施設情報ノード: 施設・設備・Wi-Fi・地下施設に関する質問に回答

    Args:
        state: ワークフロー状態（query, request_type, language, session_id等を含む）

    Returns:
        dict: answer, emotion, metadata を含む辞書
    """
    pass
```

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-07 | Enhanced RAG統合 |
| 1.2 | 2024-07 | 地下施設検出強化 |
| 2.0 | 予定 | LangGraph移行 |
