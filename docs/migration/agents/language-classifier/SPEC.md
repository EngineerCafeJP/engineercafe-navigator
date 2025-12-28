# Language Classifier - 技術仕様書

> 入出力仕様・API定義・データ構造

## 概要

Language Classifier（LanguageProcessor）は、ユーザー入力テキストの言語を検出し、応答言語を決定するユーティリティモジュールです。Router Agentから呼び出され、多言語対応の基盤となるコンポーネントです。

## 入力仕様

### メイン入力: 'detectLanguage()'

```typescript
interface LanguageDetectionInput {
  text: string;  // 検出対象のテキスト
}
```

#### 入力例

```typescript
// 日本語のクエリ
"エンジニアカフェの営業時間は？"

// 英語のクエリ
"What are the hours?"

// 混合言語のクエリ
"Engineer Cafeの営業時間"

// 短いテキスト
"Wi-Fi password"

// 判定困難なテキスト
"こんにちは"
```

### 応答言語決定: `determineResponseLanguage()`

```typescript
interface ResponseLanguageInput {
  queryLanguage: LanguageDetectionResult;  // 検出結果
  forceLanguage?: SupportedLanguage;       // 強制指定言語（オプショナル）
}
```

## 出力仕様

### メイン出力: `LanguageDetectionResult`

```typescript
interface LanguageDetectionResult {
  detectedLanguage: 'ja' | 'en';  // 検出された言語
  confidence: number;              // 信頼度 (0.0 - 1.0)
  isMixed: boolean;               // 混合言語かどうか
  languages: {
    primary: string;              // 主要言語
    secondary?: string;           // 副言語（混合時）
  };
}
```

#### 出力例

```typescript
// 純粋な日本語（高信頼度）
{
  detectedLanguage: 'ja',
  confidence: 0.9,
  isMixed: false,
  languages: { primary: 'ja' }
}

// 純粋な日本語（中信頼度）
{
  detectedLanguage: 'ja',
  confidence: 0.7,
  isMixed: false,
  languages: { primary: 'ja' }
}

// 混合（日英）
{
  detectedLanguage: 'ja',  // 日本語優先
  confidence: 0.7,
  isMixed: true,
  languages: { primary: 'ja', secondary: 'en' }
}

// 純粋な英語
{
  detectedLanguage: 'en',
  confidence: 0.9,
  isMixed: false,
  languages: { primary: 'en' }
}

// 判定困難（デフォルト）
{
  detectedLanguage: 'ja',
  confidence: 0.5,
  isMixed: false,
  languages: { primary: 'ja' }
}
```

### 応答言語出力: `SupportedLanguage`

```typescript
type SupportedLanguage = 'ja' | 'en';
```

#### 出力例

```typescript
// 日本語
'ja'

// 英語
'en'
```

## 検出ロジック

### 日本語判定パターン

#### 日本語文字パターン

```typescript
// Unicode範囲による日本語文字の検出
const japanesePattern = /[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]/;

// ひらがな: \u3040-\u309f
// カタカナ: \u30a0-\u30ff
// 漢字: \u4e00-\u9faf
```

#### 日本語の助詞・文末表現

```typescript
const japaneseParticles = [
  'は', 'が', 'を', 'に', 'で', 'の', 'か', 
  'です', 'ます', 'だ', 'である'
];
```

### 英語判定パターン

#### 英語の一般的な単語

```typescript
const englishWords = [
  'what', 'where', 'when', 'how', 'why',
  'is', 'are', 'was', 'were',
  'the', 'a', 'an',
  'engineer', 'cafe', 'about', 'tell', 'me', 
  'please', 'hours', 'open', 'close', 'price',
  'location', 'wifi', 'facility'
];
```

### ラテン文字パターン

```typescript
// アルファベットの検出
const latinPattern = /[a-zA-Z]/;
```

### 判定優先順位

1. **日本語文字あり + 助詞あり**
   - 判定: 日本語
   - 信頼度: 0.9
   - 混合: ラテン文字があれば `true`

2. **日本語文字あり + 助詞なし**
   - 判定: 日本語
   - 信頼度: 0.7
   - 混合: ラテン文字があれば `true`

3. **英単語2つ以上 + 日本語なし**
   - 判定: 英語
   - 信頼度: 0.9
   - 混合: `false`

4. **判定困難**
   - 判定: 日本語（デフォルト）
   - 信頼度: 0.5
   - 混合: `false`

### 混合言語の検出

```typescript
// 混合言語の判定条件
const isMixed = hasJapanese && hasLatin;

// hasJapanese: 日本語文字パターンにマッチ
// hasLatin: ラテン文字（a-zA-Z）が含まれる
```

## 内部処理フロー

### 処理シーケンス

```
1. detectLanguage(text) 呼び出し
   │
   ├─2. テキスト正規化
   │    └─ text.toLowerCase() で小文字化
   │
   ├─3. 日本語文字の検出
   │    └─ japanesePattern.test(text)
   │
   ├─4. 日本語助詞の検出
   │    └─ japaneseParticles.some(particle => text.includes(particle))
   │
   ├─5. ラテン文字の検出
   │    └─ latinPattern.test(text)
   │
   ├─6. 英語単語のカウント
   │    └─ englishWords.filter(word => normalizedText.includes(word)).length
   │
   ├─7. 混合言語の判定
   │    └─ hasJapanese && hasLatin
   │
   └─8. 判定ロジック適用
        └─ 優先順位に従って判定
```

### 処理の詳細

#### Step 1: メソッド呼び出し
- detectLanguage(text: string)
- Router Agentから呼び出される

#### Step 2: テキスト正規化
- 英語単語の検出のために小文字化
- 日本語文字の検出は元のテキストを使用

#### Step 3-6: パターン検出
- 日本語文字、助詞、ラテン文字、英語単語を検出

#### Step 7: 混合言語判定
- 日本語文字とラテン文字の両方が存在する場合、混合言語と判定

#### Step 8: 判定ロジック
- 優先順位に従って言語を判定
- 信頼度と混合言語フラグを設定

### 応答言語決定フロー

1. determineResponseLanguage(queryLanguage, forceLanguage?) 呼び出し
   │
   ├─2. forceLanguage チェック
   │    └─ 指定されていればそれを返す
   │
   └─3. 検出言語を返す
        └─ queryLanguage.detectedLanguage

## エラーハンドリング

### エラーケース

| ケース | 対応 |
|-------|------|
| 空文字列 | デフォルト（日本語、信頼度: 0.5）を返す |
| 特殊文字のみ | デフォルト（日本語、信頼度: 0.5）を返す |
| 数値のみ | デフォルト（日本語、信頼度: 0.5）を返す |
| 判定不能 | デフォルト（日本語、信頼度: 0.5）を返す |

### ログ出力

```typescript
// 正常系（ログなし - シンプルな処理のため）

// エラー系（必要に応じて）
console.warn('[LanguageProcessor] Unable to detect language, using default');
```

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal
import re

SupportedLanguage = Literal["ja", "en"]

class LanguageDetectionResult(TypedDict):
    """言語検出結果"""
    detected_language: SupportedLanguage
    confidence: float
    is_mixed: bool
    languages: dict
```

### 関数シグネチャ

```python
def detect_language(text: str) -> LanguageDetectionResult:
    """
    テキストの言語を検出

    Args:
        text: 検出対象のテキスト

    Returns:
        LanguageDetectionResult: 検出結果
    """
    pass

def determine_response_language(
    query_language: LanguageDetectionResult,
    force_language: SupportedLanguage | None = None
) -> SupportedLanguage:
    """
    応答言語を決定

    Args:
        query_language: クエリの言語検出結果
        force_language: 強制指定言語（オプショナル）

    Returns:
        SupportedLanguage: 応答言語 ('ja' | 'en')
    """
    pass
```

### 実装例

```python
# backend/utils/language_processor.py

from typing import TypedDict, Literal
import re

SupportedLanguage = Literal["ja", "en"]

class LanguageDetectionResult(TypedDict):
    detected_language: SupportedLanguage
    confidence: float
    is_mixed: bool
    languages: dict

class LanguageProcessor:
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def detect_language(self, text: str) -> LanguageDetectionResult:
        """クエリの言語を検出"""
        normalized_text = text.lower()

        # 日本語文字のパターン
        japanese_pattern = re.compile(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]')
        has_japanese = bool(japanese_pattern.search(text))

        # 英語の一般的な単語
        english_words = [
            'what', 'where', 'when', 'how', 'why', 'is', 'are', 'the',
            'engineer', 'cafe', 'about', 'tell', 'me', 'please', 'hours'
        ]
        english_word_count = sum(1 for word in english_words if word in normalized_text)

        # 日本語の助詞・文末表現
        japanese_particles = ['は', 'が', 'を', 'に', 'で', 'の', 'か', 'です', 'ます']
        has_japanese_particles = any(p in text for p in japanese_particles)

        # 混合言語の検出
        has_latin = bool(re.search(r'[a-zA-Z]', text))
        is_mixed = has_japanese and has_latin

        # 判定ロジック
        if has_japanese and (has_japanese_particles or not has_latin):
            return {
                "detected_language": "ja",
                "confidence": 0.9 if has_japanese_particles else 0.7,
                "is_mixed": is_mixed,
                "languages": {"primary": "ja", "secondary": "en"} if is_mixed else {"primary": "ja"}
            }
        elif not has_japanese and english_word_count >= 2:
            return {
                "detected_language": "en",
                "confidence": 0.9,
                "is_mixed": False,
                "languages": {"primary": "en"}
            }

        # デフォルト
        return {
            "detected_language": "ja",
            "confidence": 0.5,
            "is_mixed": False,
            "languages": {"primary": "ja"}
        }

    def determine_response_language(
        self,
        query_language: LanguageDetectionResult,
        force_language: SupportedLanguage | None = None
    ) -> SupportedLanguage:
        """応答言語を決定"""
        if force_language:
            return force_language
        return query_language["detected_language"]
```

## テストケース

### 正常系

| 入力 | 期待される言語 | 信頼度 | 混合 |
|-----|--------------|--------|------|
| "営業時間は？" | ja | 0.9 | false |
| "What are the hours?" | en | 0.9 | false |
| "Engineer Cafeの営業時間" | ja | 0.7 | true |
| "Wi-Fi password" | en | 0.9 | false |
| "こんにちは" | ja | 0.7 | false |
| "エンジニアカフェについて教えて" | ja | 0.9 | false |
| "Tell me about the cafe" | en | 0.9 | false |
| "カフェのhoursは？" | ja | 0.7 | true |

### エッジケース

| 入力 | 期待される言語 | 信頼度 | 混合 |
|-----|--------------|--------|------|
| "" | ja | 0.5 | false |
| "123" | ja | 0.5 | false |
| "!@#$%" | ja | 0.5 | false |
| "a" | ja | 0.5 | false |
| "は" | ja | 0.9 | false |
| "the" | ja | 0.5 | false |

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-07 | 混合言語検出の改善 |
| 2.0 | 予定 | LangGraph移行 |