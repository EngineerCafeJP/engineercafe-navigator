# Clarification Agent - 技術仕様書

> 入出力仕様・API定義・データ構造

## 入力仕様

### メイン入力: `handleClarification()`

```typescript
interface ClarificationInput {
  query: string;                    // ユーザーからの入力テキスト
  category: ClarificationCategory;   // 曖昧性の種類
  language: SupportedLanguage;       // 応答言語 ('ja' | 'en')
}

type ClarificationCategory =
  | 'cafe-clarification-needed'
  | 'meeting-room-clarification-needed'
  | 'general-clarification-needed';

```

#### 入力例

```typescript
// カフェの曖昧性解消
{
  query: "カフェの営業時間は？",
  category: "cafe-clarification-needed",
  language: "ja"
}

// 会議室の曖昧性解消
{
  query: "会議室の予約方法は？",
  category: "meeting-room-clarification-needed",
  language: "ja"
}

// 英語でのカフェの曖昧性解消
{
  query: "What are the cafe hours?",
  category: "cafe-clarification-needed",
  language: "en"
}

// デフォルトの曖昧性解消
{
  query: "詳しく教えて",
  category: "general-clarification-needed",
  language: "ja"
}
```

## 出力仕様

### メイン出力: `UnifiedAgentResponse`

```typescript
interface UnifiedAgentResponse {
  text: string;              // 感情タグ付きの応答テキスト
  emotion: string;            // 感情（常に 'surprised'）
  metadata: {
    agentName: string;        // 'ClarificationAgent'
    confidence: number;        // 信頼度 (0.7 - 0.9)
    language: SupportedLanguage; // 'ja' | 'en'
    category?: string;         // 曖昧性の種類（オプショナル）
    requestType?: string | null; // リクエストタイプ（Clarification Agentでは通常 null）
    sources?: string[];        // ['clarification_system']（オプショナル）
    processingInfo?: {         // 処理情報（オプショナル）
      filtered?: boolean;
      contextInherited?: boolean;
      enhancedRag?: boolean;
    };
  };
}
```

#### 出力例

```typescript
// カフェの曖昧性解消（日本語）
{
  text: "[surprised]お手伝いさせていただきます！どちらについてお聞きでしょうか：\n1. **エンジニアカフェ**（コワーキングスペース）- 営業時間、設備、利用方法\n2. **サイノカフェ**（併設のカフェ＆バー）- メニュー、営業時間、料金\n\nお聞かせください！",
  emotion: "surprised",
  metadata: {
    agentName: "ClarificationAgent",
    confidence: 0.9,
    language: "ja",
    category: "cafe-clarification-needed",
    sources: ["clarification_system"]
  }
}

// 会議室の曖昧性解消（英語）
{
  text: "[surprised]I'd be happy to help! We have two types of meeting spaces:\n1. **Paid Meeting Rooms (2F)** - Private rooms with advance booking required (fees apply)\n2. **Basement Meeting Spaces (B1)** - Free open spaces for casual meetings\n\nWhich one would you like to know about?",
  emotion: "surprised",
  metadata: {
    agentName: "ClarificationAgent",
    confidence: 0.9,
    language: "en",
    category: "meeting-room-clarification-needed",
    sources: ["clarification_system"]
  }
}

// デフォルトの曖昧性解消（日本語）
{
  text: "[surprised]お手伝いさせていただきます！もう少し詳しくお聞かせいただけますか？",
  emotion: "surprised",
  metadata: {
    agentName: "ClarificationAgent",
    confidence: 0.7,
    language: "ja",
    category: "general-clarification-needed",
    sources: ["clarification_system"]
  }
}

```

## category値の一覧

### ClarificationCategory

| category | 説明 | 信頼度 | トリガー条件 |
|----------|------|--------|------------|
| `cafe-clarification-needed` | カフェ曖昧 | 0.9 | 「カフェ」という単語が含まれるが、エンジニアカフェかSainoカフェか特定できない |
| `meeting-room-clarification-needed` | 会議室曖昧 | 0.9 | 「会議室」という単語が含まれるが、有料会議室(2F)か地下MTGスペースか特定できない |
| `general-clarification-needed` | 一般的な曖昧 | 0.7 | 上記以外の曖昧な質問 |

## 内部処理フロー

### 処理シーケンス

```
1. handleClarification(query, category, language) 呼び出し
   │
   ├─2. EmotionTaggerの動的インポート
   │    └─ await import('@/lib/emotion-tagger')
   │
   ├─3. category判定
   │    │
   │    ├─ "cafe-clarification-needed"
   │    │ └─ カフェの曖昧性解消メッセージを取得（言語別）
   │    │
   │    ├─ "meeting-room-clarification-needed"
   │    │ └─ 会議室の曖昧性解消メッセージを取得（言語別）
   │    │
   │    └─ その他
   │       └─ デフォルトの曖昧性解消メッセージを取得（言語別）
   │
   ├─4. 感情タグの付与
   │    └─ EmotionTagger.addEmotionTag(message, 'surprised')
   │
   └─5. UnifiedAgentResponseの生成
        └─ createUnifiedResponse(taggedMessage, 'surprised', ...)
```


### 処理の詳細

#### Step 1: メソッド呼び出し
- `handleClarification(query: string, category: string, language: SupportedLanguage)`
- Router Agentから呼び出される（categoryは既に判定済み）

#### Step 2: 動的インポート
- `EmotionTagger`を動的にインポート（28行目）
- 必要になった時点で読み込む

#### Step 3: category別メッセージ取得
- **カフェの曖昧性**（31-34行目）:
  - 日本語: "お手伝いさせていただきます！どちらについてお聞きでしょうか：..."
  - 英語: "I'd be happy to help! Are you asking about:..."
  
- **会議室の曖昧性**（53-56行目）:
  - 日本語: "お手伝いさせていただきます！会議スペースは2種類ございます：..."
  - 英語: "I'd be happy to help! We have two types of meeting spaces:..."
  
- **デフォルト**（75-77行目）:
  - 日本語: "お手伝いさせていただきます！もう少し詳しくお聞かせいただけますか？"
  - 英語: "I'd be happy to help! Could you please provide more details..."

#### Step 4: 感情タグ付与
- すべてのメッセージに`[surprised]`タグを付与（37行目、59行目、80行目）

#### Step 5: レスポンス生成
- `createUnifiedResponse()`で`UnifiedAgentResponse`を生成
- confidence: 0.9（カフェ/会議室）または 0.7（デフォルト）
- sources: `['clarification_system']`


## エラーハンドリング

### エラーケース

| ケース | 対応 |
|-------|------|
| categoryが未定義 | `general-clarification-needed` として処理 |
| languageが未定義 | デフォルト `ja` を使用 |
| EmotionTaggerの読み込み失敗 | 感情タグなしでメッセージを返す |
| メッセージ生成失敗 | デフォルトメッセージを返す（confidence: 0.5）

### ログ出力

```typescript
// 正常系（ログなし - シンプルな処理のため）

// エラー系
console.error('[ClarificationAgent] Failed to generate clarification message:', error);
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal

SupportedLanguage = Literal["ja", "en"]

ClarificationCategory = Literal[
    "cafe-clarification-needed",
    "meeting-room-clarification-needed",
    "general-clarification-needed",
]

class ClarificationResult(TypedDict):
    """Clarificationノードの出力結果"""
    response: str                # 感情タグ付きテキスト
    emotion: Literal["surprised"]
    metadata: dict               # agent名, clarification_type など

```

### ノード関数シグネチャ

```python
def clarification_node(state: WorkflowState) -> dict:
    """
    Clarificationノード: 曖昧なクエリを明確化するための選択肢を提示

    Args:
        state: ワークフロー状態（少なくとも次を含む想定）
            - query: ユーザーの入力テキスト
            - language: 応答言語 ('ja' | 'en')
            - metadata.routing.category: ClarificationCategory

    Returns:
        dict: ClarificationResult相当の情報を含む差分
            - response: 感情タグ付きの応答テキスト
            - emotion: 'surprised'
            - metadata: {
                "agent": "ClarificationAgent",
                "requires_followup": True,
                "clarification_type": category,
                ... 既存のmetadataにマージ ...
              }
    """
    ...
```

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-07 | UnifiedAgentResponse対応 |
| 1.2 | 2024-07 | 感情タグ統合 |
| 2.0 | 予定 | LangGraph移行 |