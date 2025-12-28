# Language Classifier - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
frontend/src/lib/
└── language-processor.ts    # 約196行
```

### 移行先（LangGraph/Python）

```
backend/
└── utils/
    └── language_processor.py    # 新規作成
```

### モジュールの役割

Language Classifier（LanguageProcessor）は、ユーザー入力テキストの言語（日本語/英語）を検出し、応答言語を決定するユーティリティモジュールです。Router Agentから呼び出され、多言語対応の基盤となるコンポーネントです。

## 移行ステップ

### Step 1: ファイル構造の準備

**新規作成ファイル**: `backend/utils/language_processor.py`

```python
# backend/utils/language_processor.py

from typing import TypedDict, Literal
import re

# 型定義とクラス実装をここに追加
```

### Step 2: 型定義の移行

#### 2.1 SupportedLanguage の移行

**TypeScript版**:
```typescript
type SupportedLanguage = 'ja' | 'en';
```

**Python版**:
```python
SupportedLanguage = Literal["ja", "en"]
```

#### 2.2 LanguageDetectionResult の移行

**TypeScript版**:
```typescript
interface LanguageDetectionResult {
  detectedLanguage: 'ja' | 'en';
  confidence: number;
  isMixed: boolean;
  languages: {
    primary: string;
    secondary?: string;
  };
}
```

**Python版**:
```python
class LanguageDetectionResult(TypedDict):
    """言語検出結果"""
    detected_language: SupportedLanguage
    confidence: float
    is_mixed: bool
    languages: dict
```

**主な変更点**:
- `detectedLanguage` → `detected_language` (snake_case)
- `isMixed` → `is_mixed` (snake_case)
- `languages` は `dict` 型として定義（`primary`/`secondary` は実行時に設定）

### Step 3: メソッドの移行

#### 3.1 detectLanguage() → detect_language()

**TypeScript版**:
```typescript
detectLanguage(text: string): LanguageDetectionResult
```

**Python版**:
```python
def detect_language(self, text: str) -> LanguageDetectionResult:
    """クエリの言語を検出"""
    pass
```

#### 3.2 determineResponseLanguage() → determine_response_language()

**TypeScript版**:
```typescript
determineResponseLanguage(
  queryLanguage: LanguageDetectionResult,
  forceLanguage?: SupportedLanguage
): SupportedLanguage
```

**Python版**:
```python
def determine_response_language(
    self,
    query_language: LanguageDetectionResult,
    force_language: SupportedLanguage | None = None
) -> SupportedLanguage:
    """応答言語を決定"""
    pass
```

### Step 4: ロジックの移行

#### 4.1 正規表現パターンの移行

**TypeScript版**:
```typescript
const japanesePattern = /[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]/;
const latinPattern = /[a-zA-Z]/;
```

**Python版**:
```python
japanese_pattern = re.compile(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]')
latin_pattern = re.compile(r'[a-zA-Z]')
```

**注意点**:
- Pythonでは `re.compile()` を使用してパターンを事前コンパイル
- 正規表現文字列は raw string (`r''`) を使用

#### 4.2 日本語文字検出ロジック

**TypeScript版**:
```typescript
const hasJapanese = japanesePattern.test(text);
```

**Python版**:
```python
has_japanese = bool(japanese_pattern.search(text))
```

**注意点**:
- Pythonの `search()` は `Match` オブジェクトまたは `None` を返すため、`bool()` で変換

#### 4.3 英語単語検出ロジック

**TypeScript版**:
```typescript
const englishWords = ['what', 'where', 'when', ...];
const normalizedText = text.toLowerCase();
const englishWordCount = englishWords.filter(word => 
  normalizedText.includes(word)
).length;
```

**Python版**:
```python
english_words = ['what', 'where', 'when', ...]
normalized_text = text.lower()
english_word_count = sum(1 for word in english_words if word in normalized_text)
```

**注意点**:
- Pythonでは `sum()` とジェネレータ式を使用してカウント

#### 4.4 混合言語検出ロジック

**TypeScript版**:
```typescript
const hasLatin = latinPattern.test(text);
const isMixed = hasJapanese && hasLatin;
```

**Python版**:
```python
has_latin = bool(re.search(r'[a-zA-Z]', text))
is_mixed = has_japanese and has_latin
```

#### 4.5 判定優先順位の実装

**TypeScript版**:
```typescript
if (hasJapanese && (hasJapaneseParticles || !hasLatin)) {
  return {
    detectedLanguage: 'ja',
    confidence: hasJapaneseParticles ? 0.9 : 0.7,
    isMixed: isMixed,
    languages: isMixed 
      ? { primary: 'ja', secondary: 'en' }
      : { primary: 'ja' }
  };
} else if (!hasJapanese && englishWordCount >= 2) {
  return {
    detectedLanguage: 'en',
    confidence: 0.9,
    isMixed: false,
    languages: { primary: 'en' }
  };
}
// デフォルト
return {
  detectedLanguage: 'ja',
  confidence: 0.5,
  isMixed: false,
  languages: { primary: 'ja' }
};
```

**Python版**:
```python
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
```

**注意点**:
- Pythonでは三項演算子の構文が異なる（`x if condition else y`）
- 辞書のキーは文字列として定義

### Step 5: 完全な実装例

```python
# backend/utils/language_processor.py

from typing import TypedDict, Literal
import re

SupportedLanguage = Literal["ja", "en"]

class LanguageDetectionResult(TypedDict):
    """言語検出結果"""
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

### Step 6: 統合方法

#### 6.1 Router Agentからの呼び出し

**TypeScript版**:
```typescript
import { LanguageProcessor } from '@/lib/language-processor';

const languageProcessor = new LanguageProcessor();
const languageResult = languageProcessor.detectLanguage(query);
const responseLanguage = languageProcessor.determineResponseLanguage(languageResult);
```

**Python版**:
```python
from backend.utils.language_processor import LanguageProcessor

language_processor = LanguageProcessor()
language_result = language_processor.detect_language(query)
response_language = language_processor.determine_response_language(language_result)
```

#### 6.2 他のエージェントからの利用

Language Processorはユーティリティモジュールとして、どのエージェントからでも利用可能です：

```python
from backend.utils.language_processor import LanguageProcessor, SupportedLanguage

# エージェント内で使用
processor = LanguageProcessor()
result = processor.detect_language(user_input)
```

## 主要な変更点

### 命名規則

| TypeScript | Python |
|-----------|--------|
| `detectLanguage()` | `detect_language()` |
| `determineResponseLanguage()` | `determine_response_language()` |
| `detectedLanguage` | `detected_language` |
| `isMixed` | `is_mixed` |
| `queryLanguage` | `query_language` |
| `forceLanguage` | `force_language` |

### 型定義

| TypeScript | Python |
|-----------|--------|
| `interface` | `TypedDict` |
| `type` (Literal) | `Literal` |
| `string` | `str` |
| `number` | `float` |
| `boolean` | `bool` |
| `?` (optional) | `| None` |

### 正規表現

| TypeScript | Python |
|-----------|--------|
| `/pattern/` | `re.compile(r'pattern')` |
| `.test(text)` | `.search(text)` または `bool(re.search(...))` |
| `.match(text)` | `.match(text)` または `.search(text)` |

### エラーハンドリング

**TypeScript版**:
```typescript
// デフォルト値を返す
return {
  detectedLanguage: 'ja',
  confidence: 0.5,
  isMixed: false,
  languages: { primary: 'ja' }
};
```

**Python版**:
```python
# デフォルト値を返す（同様のロジック）
return {
    "detected_language": "ja",
    "confidence": 0.5,
    "is_mixed": False,
    "languages": {"primary": "ja"}
}
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] `frontend/src/lib/language-processor.ts` の内容を確認した
- [ ] Pythonの依存パッケージを確認した（`typing`, `re` は標準ライブラリ）
- [ ] テスト環境を準備した

### Phase 2: 実装

- [ ] `backend/utils/language_processor.py` を作成した
- [ ] 型定義（`SupportedLanguage`, `LanguageDetectionResult`）を移行した
- [ ] `detect_language()` メソッドを実装した
- [ ] `determine_response_language()` メソッドを実装した
- [ ] 正規表現パターンを正しく移行した
- [ ] 判定ロジックを正しく実装した

### Phase 3: テスト

- [ ] 単体テストを作成した
- [ ] 正常系のテストケースを通過した
  - [ ] 純粋な日本語の検出
  - [ ] 純粋な英語の検出
  - [ ] 混合言語の検出
- [ ] エッジケースのテストを通過した
  - [ ] 空文字列
  - [ ] 特殊文字のみ
  - [ ] 数値のみ
  - [ ] 短いテキスト
- [ ] 信頼度の計算が正しいことを確認した

### Phase 4: 統合

- [ ] Router Agentから正しく呼び出せることを確認した
- [ ] 他のエージェントから利用できることを確認した
- [ ] インポートパスが正しいことを確認した
- [ ] 型チェック（mypy等）を通過した

### Phase 5: 検証

- [ ] 全テストケースを通過した
- [ ] パフォーマンスを計測した（目標: 10ms以下）
- [ ] ログ出力を確認した（debug_mode使用時）
- [ ] ドキュメントを更新した

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| 日本語が正しく検出されない | 正規表現のエンコーディング | `re.compile(r'[\u3040-\u309f]')` を使用（raw string） |
| `TypedDict` のインポートエラー | Python 3.8未満 | `from typing_extensions import TypedDict` を使用 |
| 正規表現がマッチしない | パターンの記述ミス | `re.search()` の戻り値を `bool()` で変換 |
| 型チェックエラー | `Literal` の使用方法 | `from typing import Literal` を確認 |
| 辞書のキーエラー | `languages` の構造不一致 | `{"primary": "ja"}` 形式を確認 |

### 日本語文字検出の問題

**問題**: 日本語文字が検出されない

**原因**: 正規表現パターンが正しくコンパイルされていない

**解決策**:
```python
# 正しい方法
japanese_pattern = re.compile(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]')

# 間違った方法（エスケープの問題）
japanese_pattern = re.compile('[\u3040-\u309f]')  # raw string を使用しない
```

### 正規表現のエンコーディング問題

**問題**: Unicode文字が正しく処理されない

**解決策**:
- Python 3では文字列はデフォルトでUnicode
- raw string (`r''`) を使用してエスケープを避ける
- `re.compile()` でパターンを事前コンパイル

### パフォーマンスの問題

**問題**: 言語検出が遅い

**解決策**:
- 正規表現パターンを `re.compile()` で事前コンパイル
- クラス変数として定義して再利用
- 不要な処理を削減

## テスト例

### 単体テスト

```python
# tests/test_language_processor.py

import pytest
from backend.utils.language_processor import LanguageProcessor

def test_detect_japanese():
    processor = LanguageProcessor()
    result = processor.detect_language("営業時間は？")
    assert result["detected_language"] == "ja"
    assert result["confidence"] == 0.9
    assert result["is_mixed"] == False

def test_detect_english():
    processor = LanguageProcessor()
    result = processor.detect_language("What are the hours?")
    assert result["detected_language"] == "en"
    assert result["confidence"] == 0.9

def test_detect_mixed():
    processor = LanguageProcessor()
    result = processor.detect_language("Engineer Cafeの営業時間")
    assert result["detected_language"] == "ja"
    assert result["is_mixed"] == True

def test_determine_response_language():
    processor = LanguageProcessor()
    result = processor.detect_language("営業時間は？")
    response_lang = processor.determine_response_language(result)
    assert response_lang == "ja"
```

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Python typing モジュール](https://docs.python.org/3/library/typing.html)
- [Python re モジュール](https://docs.python.org/3/library/re.html)
- [Mastra ドキュメント](https://mastra.dev)
- [元実装: language-processor.ts](../../../../frontend/src/lib/language-processor.ts)（存在する場合）
- [SPEC.md](./SPEC.md) - 技術仕様書
- [README.md](./README.md) - 概要と責任範囲

