# Language Classifier

> 言語検出・言語処理を担当するモジュール

## 担当者

| 担当者 | 役割 |
|-------|------|
| **Chie** | メイン実装 |
| **Jun** | レビュー・サポート |

## 概要

Language Classifierは、ユーザー入力の言語（日本語/英語）を検出し、応答言語を決定する機能を提供します。Router Agentから呼び出され、多言語対応の基盤となるコンポーネントです。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **言語検出** | 入力テキストが日本語か英語かを判定 |
| **応答言語決定** | 回答をどの言語で行うか決定 |
| **混合言語検出** | 日英混合のテキストを識別 |
| **信頼度算出** | 言語検出の確実性をスコア化 |

### 責任範囲外

- クエリの分類（QueryClassifierの責務）
- 翻訳（将来の機能）

## アーキテクチャ上の位置づけ

```
[ユーザー入力]
       │
       ▼
┌──────────────────────┐
│  Language Classifier │ ← このモジュール
└──────────┬───────────┘
           │
           ▼ 検出結果
┌──────────────────────┐
│    Router Agent      │
└──────────────────────┘
```

## 出力仕様

### LanguageDetectionResult

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

### 出力例

```typescript
// 純粋な日本語
{
  detectedLanguage: 'ja',
  confidence: 0.9,
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
```

## 検出ロジック

### 日本語判定

```typescript
// 日本語文字パターン
const japanesePattern = /[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]/;

// 日本語の助詞・文末表現
const japaneseParticles = ['は', 'が', 'を', 'に', 'で', 'の', 'か', 'です', 'ます'];
```

### 英語判定

```typescript
// 英語の一般的な単語
const englishWords = [
  'what', 'where', 'when', 'how', 'why', 'is', 'are', 'the',
  'engineer', 'cafe', 'about', 'tell', 'me', 'please', 'hours'
];
```

### 優先順位

1. **日本語文字あり + 助詞あり** → 日本語（信頼度: 0.9）
2. **日本語文字あり + 助詞なし** → 日本語（信頼度: 0.7）
3. **英単語2つ以上 + 日本語なし** → 英語（信頼度: 0.9）
4. **判定困難** → 日本語（デフォルト、信頼度: 0.5）

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/lib/language-processor.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `detectLanguage()` | 言語検出のメイン処理 |
| `determineResponseLanguage()` | 応答言語の決定 |

### 使用例

```typescript
import { LanguageProcessor } from '@/lib/language-processor';

const processor = new LanguageProcessor();

// 言語検出
const result = processor.detectLanguage('エンジニアカフェの営業時間は？');
// { detectedLanguage: 'ja', confidence: 0.9, isMixed: false, ... }

// 応答言語決定
const responseLanguage = processor.determineResponseLanguage(result);
// 'ja'
```

## LangGraph移行後の設計

### ユーティリティ関数

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

def detect_language(text: str) -> LanguageDetectionResult:
    """言語を検出"""
    # 日本語文字パターン
    japanese_pattern = re.compile(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]')
    has_japanese = bool(japanese_pattern.search(text))

    # 日本語の助詞
    japanese_particles = ['は', 'が', 'を', 'に', 'で', 'の', 'か', 'です', 'ます']
    has_particles = any(p in text for p in japanese_particles)

    if has_japanese:
        return {
            "detected_language": "ja",
            "confidence": 0.9 if has_particles else 0.7,
            "is_mixed": bool(re.search(r'[a-zA-Z]', text)),
            "languages": {"primary": "ja"}
        }

    # 英語判定...
    return {"detected_language": "ja", "confidence": 0.5, ...}
```

## テストケース概要

| 入力 | 期待される言語 | 信頼度 |
|-----|--------------|--------|
| 「営業時間は？」 | ja | 0.9 |
| "What are the hours?" | en | 0.9 |
| "Engineer Cafeの営業時間" | ja（混合） | 0.7 |
| "Wi-Fi password" | en | 0.9 |
| "こんにちは" | ja | 0.7 |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] 言語検出パターンを把握した
- [ ] 混合言語の処理を理解した
- [ ] 信頼度の計算ロジックを確認した
- [ ] Router Agentとの連携を理解した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - 呼び出し元
- [Clarification Agent](../clarification-agent/README.md) - 曖昧性解消
- [Query Classifier](../../utils/query-classifier.md) - クエリ分類
