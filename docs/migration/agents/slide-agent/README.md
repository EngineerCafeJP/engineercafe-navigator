# Slide Agent

> スライドプレゼンテーションのナレーションを担当するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **テリスケ** | メイン実装 |

## 概要

Slide Agent（SlideNarrator）は、Marp形式のスライドプレゼンテーションのナレーション（説明）を担当します。スライドの内容に応じた説明を提供し、スライド間のナビゲーション、質問への回答、自動再生機能をサポートします。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **スライドナレーション** | 各スライドの説明を音声で提供 |
| **スライドナビゲーション** | 次へ/前へ/特定スライドへの移動 |
| **質問対応** | スライド内容に関する質問への回答 |
| **自動再生** | タイマーによる自動スライド送り |

### 責任範囲外

- スライドのレンダリング（フロントエンドの責務）
- 音声合成（VoiceOutputAgentの責務）

## アーキテクチャ上の位置づけ

```
[ユーザー操作/自動再生]
         │
         ▼
┌─────────────────┐
│   Slide Agent   │ ← このエージェント
└────────┬────────┘
         │
    ┌────┴────┬────────────┐
    ▼         ▼            ▼
┌───────┐ ┌──────────┐ ┌──────────────┐
│ナレーション│ │ナビゲーション│ │ 質問応答     │
│ データ   │ │           │ │             │
└───────┘ └──────────┘ └──────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ VoiceOutputAgent + CharacterControl │
└─────────────────────────────────┘
```

## ナレーションデータ構造

### ナレーションJSON

```json
{
  "slides": [
    {
      "slideNumber": 1,
      "narration": {
        "auto": "エンジニアカフェへようこそ！今日は施設についてご紹介します。",
        "onDemand": {
          "料金": "基本エリアは無料でご利用いただけます。",
          "時間": "営業時間は9時から22時までです。"
        }
      },
      "transitions": {
        "next": "次のスライドでは設備についてご説明します。",
        "previous": null
      }
    }
  ]
}
```

### ナレーションファイルの場所

```
engineer-cafe-navigator-repo/src/slides/narration/
├── engineer-cafe-ja.json    # 日本語ナレーション
└── engineer-cafe-en.json    # 英語ナレーション
```

## 主要機能

### 1. スライドナレーション

```typescript
async narrateSlide(slideNumber?: number): Promise<{
  narration: string;
  slideNumber: number;
  audioBuffer: ArrayBuffer;
  characterAction: string;
  emotion?: string;
}>
```

### 2. ナビゲーション

```typescript
// 次のスライドへ
async nextSlide(): Promise<NavigationResult>

// 前のスライドへ
async previousSlide(): Promise<NavigationResult>

// 特定のスライドへ
async gotoSlide(slideNumber: number): Promise<NavigationResult>
```

### 3. 質問対応

```typescript
async answerSlideQuestion(question: string): Promise<string>
```

### 4. 自動再生

```typescript
async setAutoPlay(enabled: boolean, interval?: number): Promise<void>
async startAutoPlay(): Promise<void>
async stopAutoPlay(): Promise<void>
```

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/slide-narrator.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `loadNarration()` | ナレーションJSONの読み込み |
| `narrateSlide()` | スライドのナレーション生成 |
| `nextSlide()` | 次のスライドへ移動 |
| `previousSlide()` | 前のスライドへ移動 |
| `gotoSlide()` | 指定スライドへ移動 |
| `answerSlideQuestion()` | スライドに関する質問への回答 |
| `determineCharacterAction()` | キャラクターアクションの決定 |
| `extractEmotionFromSlideContent()` | スライド内容から感情を抽出 |

## キャラクターアクションの決定

```typescript
private determineCharacterAction(slideData: any): string {
  const narration = slideData.narration.auto.toLowerCase();

  if (narration.includes('welcome') || narration.includes('ようこそ')) {
    return 'greeting';
  } else if (narration.includes('service') || narration.includes('サービス')) {
    return 'presenting';
  } else if (narration.includes('price') || narration.includes('料金')) {
    return 'explaining';
  } else if (narration.includes('thank') || narration.includes('ありがとう')) {
    return 'bowing';
  }
  return 'neutral';
}
```

## LangGraph移行後の設計

### ノード定義

```python
def slide_narrator_node(state: WorkflowState) -> dict:
    """スライドナレーターノード"""
    action = state.get("slide_action", "narrate")
    current_slide = state.get("current_slide", 1)
    language = state["language"]

    if action == "next":
        return handle_next_slide(current_slide, language)
    elif action == "previous":
        return handle_previous_slide(current_slide, language)
    elif action == "goto":
        target = state.get("target_slide", 1)
        return handle_goto_slide(target, language)
    elif action == "question":
        question = state["query"]
        return handle_slide_question(question, current_slide, language)
    else:
        return handle_narrate_slide(current_slide, language)
```

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| ナレーション | スライド1 → 適切な説明が音声で流れる |
| 次へ移動 | スライド1で「次へ」→ スライド2に移動 |
| 最後のスライド | 最後で「次へ」→ 「最後のスライドです」 |
| 質問応答 | 「料金は？」→ onDemandから回答 |
| 自動再生 | 30秒ごとに自動で次へ |

## 感情タグの使い分け

| スライド内容 | 感情 | アクション |
|------------|------|----------|
| ウェルカム | `happy` | greeting |
| サービス紹介 | `confident` | presenting |
| 料金説明 | `explaining` | explaining |
| お礼・終了 | `grateful` | bowing |
| 一般説明 | `neutral` | neutral |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] ナレーションJSONの構造を把握した
- [ ] スライドナビゲーションロジックを理解した
- [ ] VoiceOutputAgent/CharacterControlAgentとの連携を確認した
- [ ] 自動再生機能を理解した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Voice Agent](../voice-agent/README.md) - 音声出力
- [Character Control Agent](../character-control-agent/README.md) - キャラクター制御
- [Marp Slides](../../slides/marp-format.md) - スライド形式
