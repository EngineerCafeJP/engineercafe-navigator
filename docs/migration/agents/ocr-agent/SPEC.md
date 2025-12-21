# OCR Agent - 技術仕様書

> 入出力仕様・API定義・データ構造

## 入力仕様<!---->

### メイン入力: `OCRQuery()`

```typescript
interface OCRInput {
  image: Image;      // 画像　mageかnumpyかここは要検討
  sessionId: string;  // セッション識別子
}
```

#### 入力例

```typescript
{
  image: 画像1 //1と書かれた画像,
  sessionId: "engineer-cafe"
}

{
  image: 画像2 //2と書かれた画像,
  sessionId: "saino-cafe"
}

{
  image: 画像3//"'イベント'と書かれた画像'",
  sessionId: "event-info"
}

{
  query: 顔1//"困った顔",
  sessionId: "confuse"
}

{
  query: 顔2"//顔が認識できない",
  sessionId: ""
}
```

## 出力仕様

### メイン出力: `OCRResult`

```typescript
interface OCRRoutingResult {
  agent: string;               // 次に呼び出す Agent
  category: string;            // 分類カテゴリ
  requestType: string | null;  // 追加情報（存在する場合のみ）
  language: 'ja' | 'en' | null;
  confidence: number;          // 総合信頼度 (0.0 - 1.0)

  debugInfo: {
    recognitionType: 'number' | 'text' | 'qr' | 'face_expression';
    recognizedText?: string;
    emotion?: string;
    rawConfidence: number;
    reason: string;
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

//数字を判定
{
  agent: "FacilityAgent",
  category: "saino-info",
  requestType: null,
  language: "ja",
  confidence: 0.7,
  debugInfo: {
    languageDetection: { ... },
    classification: {
      reason: "recognise '1'"
    }
  }
}

//表情認識
{
  "agent": "ClarificationAgent",
  "category": "emotion",
  "requestType": "confused",
  "language": null,
  "confidence": 0.85,
  "debugInfo": {
    "recognitionType": "face_expression",
    "emotion": "confused",
    "rawConfidence": 0.88,
    "reason": "User looks confused"
  }
}

```

## エージェントマッピング

### agent値の一覧

| agent値 | 説明 | 対応カテゴリ |
|---------|------|------------|
| `BusinessInfoAgent` | 営業情報エージェント | facility-info,  hours, price, location |
| `FacilityAgent` | 施設エージェント | facility-info (wifi/basement), saino-cafe |
| `EventAgent` | イベントエージェント | calendar, events |<!--必要かいまいちわからん-->
|`ClarificationAgent`|何か書く|何か書く|

### category値の一覧

| category | 説明 | トリガー条件 |
|----------|------|------------|
| `engineer-cafe` | エンジニアカフェ | エンジニアカフェ関連 |
| `saino-cafe` | Sainoカフェ | Saino/サイノ明示 |
| `calendar` | カレンダー | イベント/予定関連 |
| `event` | イベント | イベント/勉強会 |
| `facilities` | 設備 | 設備/facility |
|`emotion`|表情|困った顔とか| <!--困った顔も変更するやろ-->

### requestType値の一覧

| requestType | 説明 | キーワード例 |
|-------------|------|------------|
| `number-1` | 番号1 | 1と書かれたホワイトボード |
| `number-2` | 番号2 | 2と書かれたホワイトボード |
| `confused` | 困惑顔 | 困った顔 |
| `null` | 不明 | 特定できない場合 |

## 内部処理フロー

### 処理シーケンス

```
1. OCRInput(image, sessionId)
   │
   ├─2. Image Type 判定
   │    ├─ 数字
   │    ├─ 文字
   │    ├─ QR
   │    └─ 顔
   │
   ├─3. 各認識モデル実行
   │
   ├─4. 認識結果の正規化
   │
   ├─5. Routing Metadata 生成
   │
   └─6. Router Agent に返却
```


## エラーハンドリング

### エラーケース

| ケース | 対応 |
|-------|------|
|検出不可	| ClarificationAgent |
|1 or 2 判定不可	| 音声 or UI で再入力要求 |
|顔未検出	| detected=false |
|複数候補	| confidence 低下＋ Clarification |
### ログ出力

```typescript
// 正常系
console.log(`[OCRAgent] Context inheritance: ${query} -> ${requestType}`);

// エラー系
console.error('[OCRAgent] Failed to get previous request type:', error);
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal, Optional


class OCRResult(TypedDict, total=False):
    text: str
    confidence: float


class FaceExpression(TypedDict):
    emotion: Literal[
        "happy", "sad", "angry",
        "neutral", "surprised", "confused"
    ]
    confidence: float


class ImageRecognitionResult(TypedDict):
    agent: Literal["OCRAgent"]

    recognition_type: Literal[
        "number",
        "text",
        "qr",
        "face_expression"
    ]

    ocr_result: Optional[OCRResult]
    face_expression: Optional[FaceExpression]

    detected: bool
    language: Optional[Literal["ja", "en"]]
    confidence: float

    routing_hint: dict
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
| 0.0 | 2025-01 | 新規実装|
