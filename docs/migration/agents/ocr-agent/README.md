# OCR Agent

> 画像認識・文字認識を担当するエージェント（新機能）

## 担当者

| 担当者 | 役割 |
|-------|------|
| **けいてぃー** | メイン実装 |
| **たけがわ** | レビュー・サポート |

## 概要

OCR Agentは、カメラからの画像を解析し、文字認識や表情認識を行う新機能です。ユーザーがかざした番号や文字を読み取ったり、相手の表情を認識してキャラクターの応答に反映させることができます。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **文字認識(OCR)** | かざされた番号・文字を読み取る |
| **表情認識** | ユーザーの表情を分析 |
| **画像解析** | カメラ映像からの情報抽出 |

### 責任範囲外

- 音声処理（VoiceAgentの責務）
- キャラクター制御（CharacterControlAgentの責務）

## アーキテクチャ上の位置づけ

```
[カメラ入力]
      │
      ▼
┌─────────────────┐
│   OCR Agent     │ ← このエージェント
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│  OCR  │ │ 表情  │
│ 処理  │ │ 認識  │
└───────┘ └───────┘
         │
         ▼
┌─────────────────────────┐
│  Router Agent / 他Agent │
└─────────────────────────┘
```

## 想定される機能

### 1. 文字認識（OCR）

#### ユースケース

- **番号の読み取り**: ユーザーが番号をかざして選択肢を選ぶ
- **テキストの読み取り**: 名刺やドキュメントの内容を読み取る
- **QRコード**: QRコードからURLや情報を読み取る

#### 入出力

```typescript
interface OCRRequest {
  imageData: ArrayBuffer;   // 画像データ
  type: 'text' | 'number' | 'qr';  // 認識タイプ
  language?: 'ja' | 'en';   // 言語ヒント
}

interface OCRResponse {
  success: boolean;
  text?: string;            // 認識されたテキスト
  confidence: number;       // 信頼度
  boundingBox?: {           // 検出位置
    x: number;
    y: number;
    width: number;
    height: number;
  };
  error?: string;
}
```

### 2. 表情認識

#### ユースケース

- **ユーザーの感情検出**: 困っている、喜んでいる等を検出
- **応答調整**: 検出した感情に応じてキャラクターの応答を調整

#### 入出力

```typescript
interface FaceExpressionRequest {
  imageData: ArrayBuffer;   // 画像データ
}

interface FaceExpressionResponse {
  success: boolean;
  detected: boolean;        // 顔が検出されたか
  expression?: {
    emotion: 'happy' | 'sad' | 'angry' | 'neutral' | 'surprised' | 'confused';
    confidence: number;
  };
  error?: string;
}
```

## 技術選定（提案）

### OCR処理

| オプション | メリット | デメリット |
|-----------|---------|----------|
| **Google Cloud Vision** | 高精度、日本語対応 | コスト、API依存 |
| **Tesseract.js** | 無料、クライアント実行 | 精度がやや低い |
| **Azure Computer Vision** | 高精度 | コスト |

### 表情認識

| オプション | メリット | デメリット |
|-----------|---------|----------|
| **face-api.js** | 無料、クライアント実行 | モデルサイズ大 |
| **Google ML Kit** | 高精度 | モバイルアプリ向け |
| **カスタムモデル** | カスタマイズ可能 | 開発工数 |

## LangGraph移行後の設計

### ノード定義

```python
def ocr_node(state: WorkflowState) -> dict:
    """OCRノード"""
    image_data = state.get("image_data")
    ocr_type = state.get("ocr_type", "text")

    if ocr_type == "number":
        result = recognize_number(image_data)
    elif ocr_type == "qr":
        result = recognize_qr(image_data)
    else:
        result = recognize_text(image_data)

    return {
        "ocr_result": result,
        "metadata": {"agent": "OCRAgent"}
    }

def face_expression_node(state: WorkflowState) -> dict:
    """表情認識ノード"""
    image_data = state.get("image_data")

    result = recognize_expression(image_data)

    return {
        "user_emotion": result.expression.emotion if result.detected else None,
        "metadata": {"agent": "OCRAgent"}
    }
```

## 想定されるワークフロー

### 番号選択フロー

```
1. Clarification Agentが選択肢を提示
   「1. エンジニアカフェ  2. Sainoカフェ」

2. ユーザーが番号（1 or 2）をかざす

3. OCR Agentが番号を認識
   → recognized: "1"

4. Router Agentが選択を処理
   → BusinessInfoAgent（エンジニアカフェ）へルーティング
```

### 表情対応フロー

```
1. ユーザーが困った表情をしている

2. OCR Agent（表情認識）が検出
   → emotion: "confused"

3. キャラクターの応答を調整
   → より丁寧に、ゆっくり説明
```

## 実装の優先順位

| 優先度 | 機能 | 理由 |
|-------|------|------|
| **高** | 番号認識 | 選択肢の選択に直結 |
| **中** | テキストOCR | 補助的な入力手段 |
| **中** | 表情認識 | UX向上 |
| **低** | QRコード | 追加機能 |

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| 番号認識 | 「1」を表示 → "1" を認識 |
| 複数数字 | 「123」を表示 → "123" を認識 |
| 日本語OCR | 「こんにちは」→ テキスト認識 |
| 表情検出 | 笑顔 → happy を検出 |
| 顔なし | 顔が映っていない → detected: false |

## プライバシー・セキュリティ考慮

### 注意点

- **画像の保存**: 認識処理後は画像を即座に破棄
- **顔データ**: 表情のみを抽出、顔画像自体は保存しない
- **ユーザー同意**: カメラ使用前に明示的な同意を取得
- **オプトアウト**: 表情認識をオフにする設定を提供

## 担当者向けチェックリスト

- [ ] 技術選定を完了した（OCRライブラリ、表情認識ライブラリ）
- [ ] プライバシーポリシーを確認した
- [ ] カメラアクセスのUI/UXを設計した
- [ ] 番号認識の実装を完了した
- [ ] 表情認識の実装を完了した
- [ ] テストケースを確認した
- [ ] パフォーマンス（処理速度）を検証した

## 関連ドキュメント

- [Clarification Agent](../clarification-agent/README.md) - 選択肢提示
- [Router Agent](../router-agent/README.md) - ルーティング
- [Character Control Agent](../character-control-agent/README.md) - 感情反映

## 備考

このエージェントは新規機能のため、既存のMastra実装はありません。LangGraphベースで新規に設計・実装を行います。技術選定と要件定義から開始してください。
