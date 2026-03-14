# Router Agent - 技術仕様書

> 入出力仕様・API定義・データ構造

## 入力仕様

### メイン入力: `routeQuery()`

```typescript
interface RouterInput {
  query: string;      // ユーザーからの入力テキスト
  sessionId: string;  // セッション識別子
}
```

#### 入力例

```typescript
// 通常のクエリ
{
  query: "エンジニアカフェの営業時間を教えてください",
  sessionId: "session_abc123"
}

// 文脈依存クエリ
{
  query: "土曜日も同じ時間ですか？",
  sessionId: "session_abc123"
}

// メモリ関連クエリ
{
  query: "さっき何を聞いたか覚えてる？",
  sessionId: "session_abc123"
}
```

## 出力仕様

### メイン出力: `RouteResult`

```typescript
interface RouteResult {
  agent: string;              // ルーティング先エージェント名
  category: string;           // クエリカテゴリ
  requestType: string | null; // 具体的なリクエストタイプ
  language: SupportedLanguage; // 'ja' | 'en'
  confidence: number;         // 信頼度 (0.0 - 1.0)
  debugInfo: {
    languageDetection: LanguageDetectionResult;
    classification: QueryClassificationResult;
  };
}
```

#### 出力例

```typescript
// 営業時間の質問
{
  agent: "BusinessInfoAgent",
  category: "facility-info",
  requestType: "hours",
  language: "ja",
  confidence: 0.9,
  debugInfo: {
    languageDetection: {
      detectedLanguage: "ja",
      confidence: 0.9,
      isMixed: false
    },
    classification: {
      reason: "Hours keywords detected"
    }
  }
}

// 曖昧なカフェの質問
{
  agent: "ClarificationAgent",
  category: "cafe-clarification-needed",
  requestType: null,
  language: "ja",
  confidence: 0.7,
  debugInfo: {
    languageDetection: { ... },
    classification: {
      reason: "Ambiguous cafe query"
    }
  }
}
```

## エージェントマッピング

### agent値の一覧

| agent値 | 説明 | 対応カテゴリ |
|---------|------|------------|
| `BusinessInfoAgent` | 営業情報エージェント | facility-info, saino-cafe, hours, price, location |
| `FacilityAgent` | 施設エージェント | facility-info (wifi/basement) |
| `EventAgent` | イベントエージェント | calendar, events |
| `MemoryAgent` | メモリエージェント | memory |
| `GeneralKnowledgeAgent` | 一般知識エージェント | general |
| `ClarificationAgent` | 曖昧性解消エージェント | cafe-clarification-needed, meeting-room-clarification-needed |
| `TimeAgent` | 時刻エージェント | current-time |

### category値の一覧

| category | 説明 | トリガー条件 |
|----------|------|------------|
| `facility-info` | 施設情報 | エンジニアカフェ関連 |
| `saino-cafe` | Sainoカフェ | Saino/サイノ明示 |
| `calendar` | カレンダー | イベント/予定関連 |
| `events` | イベント | イベント/勉強会 |
| `current-time` | 現在時刻 | 今何時？ |
| `general` | 一般 | 上記以外 |
| `memory` | メモリ | 会話履歴関連 |
| `cafe-clarification-needed` | カフェ曖昧 | カフェ特定必要 |
| `meeting-room-clarification-needed` | 会議室曖昧 | 会議室特定必要 |
| `pricing` | 料金 | 料金/price |
| `facilities` | 設備 | 設備/facility |
| `access` | アクセス | アクセス/access |
| `hours` | 営業時間 | 時間/営業/hours |

### requestType値の一覧

| requestType | 説明 | キーワード例 |
|-------------|------|------------|
| `wifi` | Wi-Fi | wi-fi, wifi, インターネット, ネット |
| `hours` | 営業時間 | 営業時間, 何時まで, 何時から, open, close |
| `price` | 料金 | 料金, いくら, 値段, price, cost, fee |
| `location` | 場所 | 場所, どこ, where, アクセス, 住所 |
| `facility` | 設備 | 設備, 電源, プリンター, equipment |
| `basement` | 地下施設 | 地下, basement, B1, MTGスペース, 集中スペース |
| `meeting-room` | 会議室 | 会議室, ミーティングルーム (地下以外) |
| `event` | イベント | イベント, 勉強会, セミナー, workshop |
| `null` | 不明 | 特定できない場合 |

## 内部処理フロー

### 処理シーケンス

```
1. routeQuery(query, sessionId) 呼び出し
   │
   ├─2. 言語検出
   │    └─ languageProcessor.detectLanguage(query)
   │
   ├─3. メモリ関連チェック
   │    └─ isMemoryRelatedQuestion(query)
   │         → true の場合: MemoryAgent へルーティング
   │
   ├─4. クエリ分類
   │    └─ queryClassifier.classifyWithDetails(query)
   │
   ├─5. リクエストタイプ抽出
   │    └─ extractRequestType(query)
   │
   ├─6. 文脈依存チェック (requestType が null の場合)
   │    └─ isContextDependentQuery(query)
   │         → true の場合: memory.getPreviousRequestType(sessionId)
   │
   └─7. エージェント選択
        └─ selectAgent(category, requestType, query)
```

## キーワードパターン

### メモリ関連キーワード

```typescript
// 日本語
['さっき', '前に', '覚えて', '記憶', '質問', '聞いた', '話した',
 'どんな', '何を', '言った', '会話', '履歴', '先ほど']

// 英語
['remember', 'recall', 'earlier', 'before', 'previous', 'asked',
 'said', 'mentioned', 'conversation', 'history', 'what did i']
```

### 文脈依存パターン（正規表現）

```typescript
/^土曜[日]?[はも].*/        // 土曜日は... 土曜も...
/^日曜[日]?[はも].*/        // 日曜日は... 日曜も...
/^平日[はも].*/             // 平日は... 平日も...
/^saino[のは方も]?.*/       // sainoの方は... sainoも...
/^そっち[のはも]?.*/        // そっちの方は... そっちも...
/^あっち[のはも]?.*/        // あっちの方は... あっちも...
/^それ[のはも]?.*/          // それは... それも...
/^そこ[のはも]?.*/          // そこは... そこも...
```

### 除外パターン（メモリ判定から除外）

```typescript
// ビジネス関連（メモリと誤判定されやすい）
['メニュー', 'menu', '料金', 'price', '営業時間', 'hours',
 '場所', 'location', '設備', 'facility', 'サイノカフェ', 'saino']

// 施設関連
['地下', 'basement', 'スペース', 'space', 'mtg', '会議室', 'makers']
```

## エラーハンドリング

### エラーケース

| ケース | 対応 |
|-------|------|
| 言語検出失敗 | デフォルト `ja` を使用 |
| 分類失敗 | `general` カテゴリにフォールバック |
| メモリアクセス失敗 | requestType を `null` のまま継続 |
| 不明なエージェント | `GeneralKnowledgeAgent` にルーティング |

### ログ出力

```typescript
// 正常系
console.log(`[RouterAgent] Context inheritance: ${query} -> ${requestType}`);

// エラー系
console.error('[RouterAgent] Failed to get previous request type:', error);
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal

class RouteResult(TypedDict):
    agent: Literal[
        "BusinessInfoAgent",
        "FacilityAgent",
        "EventAgent",
        "MemoryAgent",
        "GeneralKnowledgeAgent",
        "ClarificationAgent",
        "TimeAgent"
    ]
    category: str
    request_type: str | None
    language: Literal["ja", "en"]
    confidence: float
    debug_info: dict
```

### ノード関数シグネチャ

```python
def router_node(state: WorkflowState) -> dict:
    """
    ルーターノード: クエリを適切なエージェントにルーティング

    Args:
        state: ワークフロー状態（query, session_id, context等を含む）

    Returns:
        dict: routed_to, request_type, metadata を含む辞書
    """
    pass
```

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-07 | 文脈依存ルーティング追加 |
| 1.2 | 2024-07 | 地下施設検出強化 |
| 2.0 | 予定 | LangGraph移行 |
