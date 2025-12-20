# OCR Agent

> 画像認識・文字認識を担当するエージェント（新機能）

## 担当者

| 担当者 | 役割 |
|-------|------|
| **けいてぃー** | メイン実装 |
| **たけがわ** | レビュー・サポート |

## 概要

OCR Agentは、カメラからの画像を解析し、表情認識や木製会員カードの検出を行う新機能です。Phase 1ではYOLO/機械学習モデルによる高速なリアルタイム検出を実装し、Phase 2で複雑なOCR処理にマルチモーダルLLMを活用します。

## 責任範囲

### 主要責務

| 責務 | 説明 | Phase |
|------|------|-------|
| **表情認識** | ユーザーの表情をリアルタイム検出 | Phase 1 |
| **木製カード検出** | Engineer Cafe会員カードの検出 | Phase 1 |
| **複雑なOCR** | テキスト・番号の認識 | Phase 2 |
| **QRコード** | QRコードからの情報読み取り | Phase 2 |

### 責任範囲外

- 音声処理（VoiceAgentの責務）
- キャラクター制御（CharacterControlAgentの責務）

## 実装戦略

### Phase 1: YOLO/機械学習アプローチ（優先実装）

**目的**: リアルタイム性が求められる表情認識とカード検出

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 1 Architecture                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [カメラ入力] ──► [前処理] ──► [YOLOv8モデル]               │
│                                      │                       │
│                      ┌───────────────┴───────────────┐       │
│                      ▼                               ▼       │
│              ┌──────────────┐              ┌──────────────┐  │
│              │ 表情認識     │              │ カード検出   │  │
│              │ (emotion)    │              │ (card)       │  │
│              └──────────────┘              └──────────────┘  │
│                      │                               │       │
│                      └───────────────┬───────────────┘       │
│                                      ▼                       │
│                             [Router Agent]                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 表情認識モデル

| 項目 | 仕様 |
|------|------|
| **モデル** | YOLOv8-face + 表情分類器 |
| **検出クラス** | happy, neutral, confused, surprised |
| **推論速度** | < 50ms（GPU使用時） |
| **入力サイズ** | 640x640 |

```python
from ultralytics import YOLO

class EmotionDetector:
    """表情認識モデル"""

    EMOTIONS = ["happy", "neutral", "confused", "surprised"]

    def __init__(self, model_path: str = "models/emotion_yolov8.onnx"):
        self.model = YOLO(model_path)

    def detect(self, image: np.ndarray) -> dict:
        """
        表情を検出する

        Args:
            image: BGR形式の画像データ

        Returns:
            {
                "detected": bool,
                "emotion": str | None,
                "confidence": float,
                "bounding_box": {"x": int, "y": int, "w": int, "h": int} | None
            }
        """
        results = self.model(image)

        if len(results[0].boxes) == 0:
            return {"detected": False, "emotion": None, "confidence": 0.0}

        # 最も信頼度の高い検出結果を使用
        best_result = max(results[0].boxes, key=lambda x: x.conf)
        class_id = int(best_result.cls)

        return {
            "detected": True,
            "emotion": self.EMOTIONS[class_id],
            "confidence": float(best_result.conf),
            "bounding_box": {
                "x": int(best_result.xyxy[0][0]),
                "y": int(best_result.xyxy[0][1]),
                "w": int(best_result.xyxy[0][2] - best_result.xyxy[0][0]),
                "h": int(best_result.xyxy[0][3] - best_result.xyxy[0][1])
            }
        }
```

#### 木製会員カード検出モデル

| 項目 | 仕様 |
|------|------|
| **モデル** | YOLOv8 (カスタム学習) |
| **検出対象** | Engineer Cafe木製会員カード |
| **学習データ** | 現地撮影データ + データ拡張 |

```python
class CardDetector:
    """木製会員カード検出モデル"""

    def __init__(self, model_path: str = "models/card_detector.onnx"):
        self.model = YOLO(model_path)

    def detect(self, image: np.ndarray) -> dict:
        """
        会員カードを検出する

        Returns:
            {
                "detected": bool,
                "confidence": float,
                "bounding_box": dict | None
            }
        """
        results = self.model(image)

        if len(results[0].boxes) == 0:
            return {"detected": False, "confidence": 0.0, "bounding_box": None}

        best_result = max(results[0].boxes, key=lambda x: x.conf)

        return {
            "detected": True,
            "confidence": float(best_result.conf),
            "bounding_box": {
                "x": int(best_result.xyxy[0][0]),
                "y": int(best_result.xyxy[0][1]),
                "w": int(best_result.xyxy[0][2] - best_result.xyxy[0][0]),
                "h": int(best_result.xyxy[0][3] - best_result.xyxy[0][1])
            }
        }
```

### Phase 2: マルチモーダルLLMアプローチ（将来実装）

**目的**: 複雑なテキスト認識やコンテキスト理解が必要な場面

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 2 Architecture                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [カメラ入力] ──► [Phase 1で検出できない場合]                │
│                                      │                       │
│                                      ▼                       │
│                         ┌──────────────────────┐             │
│                         │  OpenRouter API      │             │
│                         │  (Gemini Vision /    │             │
│                         │   GPT-4 Vision)      │             │
│                         └──────────────────────┘             │
│                                      │                       │
│                      ┌───────────────┴───────────────┐       │
│                      ▼                               ▼       │
│              ┌──────────────┐              ┌──────────────┐  │
│              │ テキストOCR  │              │ QRコード     │  │
│              │ (text)       │              │ (qr)         │  │
│              └──────────────┘              └──────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

```python
from llm import get_llm_provider, ModelConfig, SupportedModel
from langchain_core.messages import HumanMessage

class MultimodalOCR:
    """マルチモーダルLLMによるOCR（Phase 2）"""

    def __init__(self):
        self.provider = get_llm_provider()
        self.config = ModelConfig(
            model_id=SupportedModel.GEMINI_2_5_FLASH,
            temperature=0.3,
            max_tokens=256,
        )

    async def recognize_text(self, image_base64: str, language: str = "ja") -> dict:
        """
        画像からテキストを認識する

        Args:
            image_base64: Base64エンコードされた画像
            language: 認識言語 ("ja" or "en")

        Returns:
            {
                "success": bool,
                "text": str | None,
                "confidence": float
            }
        """
        prompt = f"""
        この画像からテキストを読み取ってください。
        言語: {"日本語" if language == "ja" else "英語"}

        出力形式:
        - text: 認識されたテキスト
        - confidence: 信頼度 (0.0-1.0)
        """

        messages = [
            HumanMessage(content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ])
        ]

        response = await self.provider.generate(messages, self.config)
        # パースして返却
        return {"success": True, "text": response, "confidence": 0.9}
```

## ディレクトリ構成

```
backend/
├── agents/
│   └── ocr_agent.py          # OCRエージェント統合
├── training/                  # モデル学習用（Phase 1）
│   ├── emotion/
│   │   ├── dataset/          # 表情データセット
│   │   ├── train.py          # 学習スクリプト
│   │   └── config.yaml       # 学習設定
│   └── card/
│       ├── dataset/          # カードデータセット
│       ├── train.py          # 学習スクリプト
│       └── config.yaml       # 学習設定
├── models/                    # 学習済みモデル
│   ├── emotion_yolov8.onnx   # 表情認識モデル
│   └── card_detector.onnx    # カード検出モデル
└── services/
    ├── emotion_detector.py    # 表情認識サービス
    ├── card_detector.py       # カード検出サービス
    └── multimodal_ocr.py      # マルチモーダルOCR（Phase 2）
```

## LangGraph統合

### ノード定義

```python
from langgraph.graph import StateGraph
from typing import TypedDict, Optional

class OCRState(TypedDict):
    image_data: bytes
    emotion: Optional[str]
    card_detected: bool
    ocr_text: Optional[str]

def emotion_detection_node(state: OCRState) -> dict:
    """Phase 1: 表情認識ノード"""
    from services.emotion_detector import EmotionDetector

    detector = EmotionDetector()
    image = decode_image(state["image_data"])
    result = detector.detect(image)

    return {
        "emotion": result.get("emotion"),
        "metadata": {"agent": "OCRAgent", "phase": 1}
    }

def card_detection_node(state: OCRState) -> dict:
    """Phase 1: カード検出ノード"""
    from services.card_detector import CardDetector

    detector = CardDetector()
    image = decode_image(state["image_data"])
    result = detector.detect(image)

    return {
        "card_detected": result.get("detected", False),
        "metadata": {"agent": "OCRAgent", "phase": 1}
    }

async def multimodal_ocr_node(state: OCRState) -> dict:
    """Phase 2: マルチモーダルOCRノード"""
    from services.multimodal_ocr import MultimodalOCR

    ocr = MultimodalOCR()
    image_base64 = encode_image_base64(state["image_data"])
    result = await ocr.recognize_text(image_base64)

    return {
        "ocr_text": result.get("text"),
        "metadata": {"agent": "OCRAgent", "phase": 2}
    }
```

## 想定されるワークフロー

### 表情認識フロー（Phase 1）

```
1. カメラからフレームを取得（リアルタイム）

2. EmotionDetector で表情を検出
   → emotion: "confused", confidence: 0.85

3. 検出結果を Router Agent に送信
   → キャラクターがより丁寧な対応に切り替え

4. Character Control Agent が応答を調整
   → 表情・声のトーンを変更
```

### 会員カード検出フロー（Phase 1）

```
1. ユーザーが木製会員カードをかざす

2. CardDetector がカードを検出
   → detected: true, confidence: 0.92

3. 会員向け応答モードを有効化
   → 特別な情報や特典を案内
```

### テキスト認識フロー（Phase 2 - 将来実装）

```
1. Phase 1 の検出では対応できないテキスト

2. OpenRouter経由でマルチモーダルLLMに送信
   → Gemini Vision または GPT-4 Vision

3. テキストを認識して処理
   → 名刺、ドキュメント等の複雑なOCR
```

## 実装の優先順位

| 優先度 | 機能 | Phase | 理由 |
|-------|------|-------|------|
| **P1** | 表情認識 | 1 | UX向上、リアルタイム性重要 |
| **P1** | 木製カード検出 | 1 | 会員認識の基盤 |
| **P2** | 番号認識 | 2 | 選択肢の選択補助 |
| **P3** | テキストOCR | 2 | 補助的な入力手段 |
| **P3** | QRコード | 2 | 追加機能 |

## モデル学習ガイドライン

### 表情認識モデルの学習

1. **データ収集**: Engineer Cafeの実際の来訪者画像（許可取得済み）
2. **データ拡張**: 照明変化、角度変化、ノイズ追加
3. **クラスバランス**: 各表情クラスが均等になるよう調整
4. **評価指標**: Precision, Recall, F1-score

### カード検出モデルの学習

1. **データ収集**: 木製会員カードを様々な角度・距離で撮影
2. **ネガティブサンプル**: 類似形状のオブジェクト（財布、名刺等）
3. **背景バリエーション**: Engineer Cafe内の様々な背景
4. **評価指標**: mAP@0.5, mAP@0.5:0.95

## プライバシー・セキュリティ考慮

### 必須要件

- **画像の非保存**: 認識処理後は画像を即座に破棄
- **顔データ**: 表情ラベルのみを抽出、顔画像自体は保存しない
- **ユーザー同意**: カメラ使用前に明示的な同意を取得
- **オプトアウト**: 表情認識をオフにする設定を提供
- **ローカル推論**: Phase 1のYOLOモデルはローカル実行

## 担当者向けチェックリスト

### Phase 1（優先）

- [ ] YOLOv8の開発環境をセットアップした
- [ ] 表情データセットを収集・整理した
- [ ] 表情認識モデルを学習した
- [ ] カードデータセットを収集・整理した
- [ ] カード検出モデルを学習した
- [ ] モデルをONNX形式でエクスポートした
- [ ] 推論パフォーマンスを検証した（< 50ms目標）
- [ ] LangGraphノードに統合した

### Phase 2（将来）

- [ ] OpenRouterのマルチモーダルAPI連携を実装した
- [ ] プロンプトエンジニアリングを最適化した
- [ ] Phase 1→Phase 2のフォールバック実装

## テストケース概要

| カテゴリ | テストケース例 | Phase |
|---------|--------------|-------|
| 表情検出 | 笑顔 → happy を検出 | 1 |
| 表情検出 | 困った顔 → confused を検出 | 1 |
| 顔なし | 顔が映っていない → detected: false | 1 |
| カード検出 | 木製カード → detected: true | 1 |
| カード偽陰性 | 類似物体 → detected: false | 1 |
| テキストOCR | 日本語テキスト → 認識 | 2 |
| QRコード | URL含むQR → URL抽出 | 2 |

## 関連ドキュメント

- [Clarification Agent](../clarification-agent/README.md) - 選択肢提示
- [Router Agent](../router-agent/README.md) - ルーティング
- [Character Control Agent](../character-control-agent/README.md) - 感情反映
- [LLM Provider](../../../../backend/llm/README.md) - OpenRouter統合（Phase 2で使用）

## 備考

このエージェントは新規機能のため、既存のMastra実装はありません。

**Phase 1（YOLO/ML）から開始**することで、リアルタイム性能を確保しつつ、将来的にPhase 2（マルチモーダルLLM）で複雑なOCR機能を追加します。
