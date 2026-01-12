# Slide Agent (SlideNarrator) - 技術仕様書

> 入出力仕様・API定義・データ構造

## 入力仕様

### メイン入力: スライド操作

```typescript
interface LoadNarrationInput {
  slideFile: string;           // スライドファイル名 (例: 'engineer-cafe')
  language: SupportedLanguage; // 'ja' | 'en'
}

interface SlideNavigationInput {
  slideNumber?: number;  // 特定のスライド番号（オプション）
}

interface SlideQuestionInput {
  question: string;      // スライド内容に関する質問
}

interface AutoPlayInput {
  enabled: boolean;      // 自動再生の有効/無効
  interval?: number;     // 自動進行の間隔（ミリ秒、デフォルト30秒）
}
```

#### 入力例

```typescript
// ナレーション読み込み
{
  slideFile: "engineer-cafe",
  language: "ja"
}

// スライド移動
{
  slideNumber: 3  // 3枚目のスライドへ移動
}

// スライドに関する質問
{
  question: "集中スペースはいくつありますか？"
}

// 自動再生設定
{
  enabled: true,
  interval: 45000  // 45秒間隔
}
```

## 出力仕様

### メイン出力: `NarrationResult`

```typescript
interface NarrationResult {
  narration: string;              // ナレーションテキスト
  slideNumber: number;            // 現在のスライド番号
  audioBuffer: ArrayBuffer;       // 音声データ
  characterAction: string;        // キャラクターアクション
  characterControlData?: any;     // キャラクター制御データ
  emotion?: string;               // 感情タグ
}

interface NavigationResult {
  success: boolean;               // 成功/失敗
  narration?: string;             // ナレーションテキスト
  slideNumber?: number;           // スライド番号
  audioBuffer?: ArrayBuffer;      // 音声データ
  characterAction?: string;       // キャラクターアクション
  characterControlData?: any;     // キャラクター制御データ
  emotion?: string;               // 感情タグ
  transitionMessage?: string;     // トランジションメッセージ
}

interface SlideInfo {
  currentSlide: number;           // 現在のスライド番号
  totalSlides: number;            // 総スライド数
  slideData: any;                 // スライドデータ
}
```

#### 出力例

```typescript
// ナレーション実行結果
{
  narration: "皆さん、エンジニアカフェへようこそ。ここはエンジニアが学び、交流し、成長できる無料の公共スペースです。",
  slideNumber: 1,
  audioBuffer: ArrayBuffer(12345),
  characterAction: "greeting",
  characterControlData: {
    emotion: "happy",
    lipSyncData: [...]
  },
  emotion: "happy"
}

// 次スライド移動結果
{
  success: true,
  narration: "エンジニアカフェは福岡市と市民の協力で生まれました...",
  slideNumber: 2,
  audioBuffer: ArrayBuffer(23456),
  characterAction: "presenting",
  emotion: "confident",
  transitionMessage: "それでは、エンジニアカフェについて詳しくご説明いたします。"
}

// 最終スライドでの次スライド試行
{
  success: false,
  transitionMessage: "最後のスライドです。最初に戻りますか、それとも何かご質問はございますか？"
}
```

## ナレーションデータ構造

### JSON Schema

```json
{
  "metadata": {
    "title": "string",           // プレゼンテーションタイトル
    "language": "ja | en",       // 言語
    "speaker": "string",         // TTS音声の種類
    "version": "string"          // データバージョン
  },
  "slides": [
    {
      "slideNumber": "number",   // スライド番号（1から開始）
      "narration": {
        "auto": "string",        // 自動ナレーション（スライド表示時）
        "onEnter": "string",     // 進入時の短いメッセージ
        "onDemand": {
          "keyword": "response"  // キーワードに対する応答
        }
      },
      "transitions": {
        "next": "string | null",     // 次スライドへの遷移メッセージ
        "previous": "string | null"  // 前スライドへの遷移メッセージ
      }
    }
  ]
}
```

### 実データ例

```json
{
  "metadata": {
    "title": "エンジニアカフェ案内",
    "language": "ja",
    "speaker": "ja-JP-Neural2-B",
    "version": "2.0"
  },
  "slides": [
    {
      "slideNumber": 1,
      "narration": {
        "auto": "皆さん、エンジニアカフェへようこそ。ここはエンジニアが学び、交流し、成長できる無料の公共スペースです。",
        "onEnter": "エンジニアカフェへようこそ。こちらは施設案内の最初のスライドです。",
        "onDemand": {
          "詳しく": "エンジニアカフェは2019年8月に福岡市の「エンジニアフレンドリーシティ福岡」の一環として誕生した公共のコワーキングスペースです。",
          "無料": "完全無料でご利用いただける公共施設です。",
          "場所": "福岡市の赤煉瓦文化館内に位置し、重要文化財である歴史ある建物の中でお仕事していただけます。"
        }
      },
      "transitions": {
        "next": "それでは、エンジニアカフェについて詳しくご説明いたします。",
        "previous": null
      }
    },
    {
      "slideNumber": 4,
      "narration": {
        "auto": "地下には4つの特徴的なスペースがあります。ミーティングスペースは2名以上でホームページから予約が必要です。",
        "onEnter": "地下スペースの詳細についてご説明します。",
        "onDemand": {
          "ミーティングスペース": "2名以上から利用可能で、ホームページから事前予約が必要です。",
          "集中スペース": "6ブース完備で予約不要ですが、おしゃべりは完全禁止です。",
          "Makersスペース": "3Dプリンタやレーザーカッターが利用できます。初回利用時は講習が必須です。"
        }
      },
      "transitions": {
        "next": "利用時間と延長についてご説明します。",
        "previous": "コワーキングスペースに戻ります。"
      }
    }
  ]
}
```

## キャラクターアクションマッピング

### アクション決定ロジック

`determineCharacterAction(slideData)` メソッドはスライドのナレーション内容からキャラクターアクションを決定します。

| ナレーション内容（キーワード） | アクション | 説明 |
|-------------------------|----------|------|
| `welcome`, `ようこそ` | `greeting` | 挨拶のジェスチャー |
| `service`, `サービス` | `presenting` | プレゼンテーションの動作 |
| `price`, `料金` | `explaining` | 説明する動作 |
| `thank`, `ありがとう` | `bowing` | お辞儀 |
| その他 | `neutral` | 通常の姿勢 |

### 実装例

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
  } else {
    return 'neutral';
  }
}
```

## 感情抽出マッピング

### 感情決定ロジック

`extractEmotionFromSlideContent(slideData)` メソッドはスライド内容から感情タグを抽出します。

| ナレーション内容（キーワード） | 感情タグ | 説明 |
|-------------------------|---------|------|
| `welcome`, `ようこそ`, `hello` | `happy` | 歓迎・喜び |
| `price`, `料金`, `cost` | `explaining` | 説明的 |
| `service`, `サービス`, `feature` | `confident` | 自信 |
| `thank`, `ありがとう`, `appreciate` | `grateful` | 感謝 |
| `question`, `質問`, `help` | `curious` | 好奇心 |
| その他 | `neutral` | 中立 |

### エージェント指示における感情タグ

エージェントの指示文には以下の感情タグが使用されます：

```typescript
// 質問回答時の感情タグ
const emotionTags = [
  '[happy]',      // 興奮する機能や利点を説明する時
  '[sad]',        // 情報が見つからない時
  '[angry]',      // （通常は使用しない）
  '[relaxed]',    // 情報的な回答をする時（デフォルト）
  '[surprised]'   // 予期しない質問を受けた時
];
```

## メソッド一覧

### ナレーション管理

| メソッド | 説明 | 戻り値 |
|---------|------|-------|
| `loadNarration(slideFile, language)` | ナレーションJSONを読み込む | `Promise<void>` |
| `narrateSlide(slideNumber?)` | スライドをナレーションする | `Promise<NarrationResult>` |
| `answerSlideQuestion(question)` | スライドに関する質問に回答 | `Promise<string>` |

### ナビゲーション

| メソッド | 説明 | 戻り値 |
|---------|------|-------|
| `nextSlide()` | 次のスライドへ移動 | `Promise<NavigationResult>` |
| `previousSlide()` | 前のスライドへ移動 | `Promise<NavigationResult>` |
| `gotoSlide(slideNumber)` | 指定スライドへ移動 | `Promise<NavigationResult>` |
| `getCurrentSlideInfo()` | 現在のスライド情報を取得 | `Promise<SlideInfo>` |

### 自動再生

| メソッド | 説明 | 戻り値 |
|---------|------|-------|
| `setAutoPlay(enabled, interval?)` | 自動再生設定 | `Promise<void>` |
| `startAutoPlay()` | 自動再生開始 | `Promise<void>` |
| `stopAutoPlay()` | 自動再生停止 | `Promise<void>` |

### 内部メソッド

| メソッド | 説明 | 戻り値 |
|---------|------|-------|
| `determineCharacterAction(slideData)` | キャラクターアクション決定 | `string` |
| `extractEmotionFromSlideContent(slideData)` | 感情タグ抽出 | `string` |

## 内部処理フロー

### ナレーション実行フロー

```
1. narrateSlide(slideNumber?) 呼び出し
   │
   ├─2. スライド番号検証
   │    └─ targetSlide が範囲内か確認
   │
   ├─3. ナレーションデータ取得
   │    └─ slides配列から該当スライドを検索
   │
   ├─4. 言語取得
   │    └─ memory.get('language')
   │
   ├─5. キャラクター制御決定
   │    ├─ determineCharacterAction(slideData) → アクション
   │    └─ extractEmotionFromSlideContent(slideData) → 感情
   │
   ├─6. 音声・キャラクター処理（並列）
   │    ├─ voiceOutputAgent.convertTextToSpeech()
   │    └─ characterControlAgent.processCharacterControl()
   │
   ├─7. リップシンク処理
   │    └─ characterControlAgent.processCharacterControl({audioData})
   │
   └─8. 結果返却
        └─ {narration, slideNumber, audioBuffer, characterAction, emotion}
```

### スライドナビゲーションフロー

```
1. nextSlide() / previousSlide() / gotoSlide() 呼び出し
   │
   ├─2. 境界チェック
   │    ├─ nextSlide: currentSlide >= totalSlides → エラーメッセージ
   │    ├─ previousSlide: currentSlide <= 1 → エラーメッセージ
   │    └─ gotoSlide: 範囲外 → エラーメッセージ
   │
   ├─3. トランジションメッセージ取得
   │    └─ slideData.transitions.next/previous
   │
   ├─4. スライド番号更新
   │    └─ currentSlide を更新
   │
   ├─5. ナレーション実行
   │    └─ narrateSlide(新しいslideNumber)
   │
   └─6. 結果返却
        └─ {success, narration, slideNumber, audioBuffer, transitionMessage}
```

### 質問応答フロー

```
1. answerSlideQuestion(question) 呼び出し
   │
   ├─2. 現在のスライドデータ取得
   │    └─ slides.find(s => s.slideNumber === currentSlide)
   │
   ├─3. onDemand応答チェック
   │    ├─ slideData.narration.onDemand を確認
   │    └─ キーワードマッチ → 定義済み応答を返す
   │
   ├─4. 動的応答生成（onDemandに該当なし）
   │    ├─ スライドコンテキストを作成
   │    ├─ プロンプト生成（言語に応じて）
   │    └─ this.generate() でLLM応答生成
   │
   └─5. 応答返却
        └─ 文字列応答
```

## エージェント統合

### VoiceOutputAgent統合

```typescript
// 音声出力エージェントとの連携
setVoiceOutputAgent(agent: any): void

// 音声生成
const voiceResult = await this.voiceOutputAgent.convertTextToSpeech({
  text: narration,
  language,
  emotion,
  agentName: 'SlideNarrator'
});
```

### CharacterControlAgent統合

```typescript
// キャラクター制御エージェントとの連携
setCharacterControlAgent(agent: any): void

// キャラクター制御
const characterResult = await this.characterControlAgent.processCharacterControl({
  emotion,
  text: narration,
  agentName: 'SlideNarrator'
});

// リップシンク生成
const lipSyncResult = await this.characterControlAgent.processCharacterControl({
  audioData: audioBuffer,
  agentName: 'SlideNarrator'
});
```

## メモリ管理

### メモリ保存データ

| キー | 値の型 | 説明 |
|-----|-------|------|
| `currentSlide` | `number` | 現在のスライド番号 |
| `totalSlides` | `number` | 総スライド数 |
| `narrationData` | `object` | ナレーションデータ全体 |
| `autoPlay` | `boolean` | 自動再生の有効/無効 |
| `autoPlayInterval` | `number` | 自動再生間隔（ミリ秒） |
| `language` | `SupportedLanguage` | 言語設定 |

## エラーハンドリング

### エラーケース

| ケース | エラーメッセージ | 対応 |
|-------|--------------|------|
| ナレーション未読み込み | `No narration data loaded` | loadNarration()を先に呼び出す |
| 無効なスライド番号 | `Invalid slide number: ${number}` | 1〜totalSlidesの範囲を指定 |
| スライドデータ不在 | `No narration data for slide ${number}` | ナレーションJSONを確認 |
| 音声生成失敗 | `Text-to-Speech failed: ${error}` | voiceServiceの設定を確認 |
| 音声出力エージェント失敗 | `Voice output failed: ${error}` | voiceOutputAgentの設定を確認 |

### ログ出力

```typescript
// 正常系
console.log(`[SlideNarrator] Loaded narration for ${slideFile} (${language})`);
console.log(`[SlideNarrator] Narrating slide ${slideNumber}`);

// エラー系
console.error('Failed to load narration:', error);
console.error(`Text-to-Speech failed: ${error}`);
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal, Optional
from dataclasses import dataclass

SupportedLanguage = Literal["ja", "en"]

@dataclass
class NarrationResult:
    narration: str
    slide_number: int
    audio_buffer: bytes
    character_action: str
    character_control_data: Optional[dict] = None
    emotion: Optional[str] = None

@dataclass
class NavigationResult:
    success: bool
    narration: Optional[str] = None
    slide_number: Optional[int] = None
    audio_buffer: Optional[bytes] = None
    character_action: Optional[str] = None
    character_control_data: Optional[dict] = None
    emotion: Optional[str] = None
    transition_message: Optional[str] = None

@dataclass
class SlideInfo:
    current_slide: int
    total_slides: int
    slide_data: dict
```

### ノード関数シグネチャ

```python
async def slide_narrator_node(state: WorkflowState) -> dict:
    """
    スライドナレーターノード: プレゼンテーションスライドのナレーションを実行

    Args:
        state: ワークフロー状態（slide_action, slide_number, question等を含む）

    Returns:
        dict: narration_result, audio_data, character_control を含む辞書
    """
    pass
```

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-06 | VoiceOutputAgent/CharacterControlAgent統合 |
| 1.2 | 2024-09 | 自動再生機能追加 |
| 1.3 | 2024-11 | onDemand応答機能強化 |
| 2.0 | 予定 | LangGraph移行 |
