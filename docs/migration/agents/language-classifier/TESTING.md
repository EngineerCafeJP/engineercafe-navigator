# Language Classifier - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

Language Classifier（LanguageProcessor）は、多言語対応の基盤となるユーティリティモジュールです。全てのクエリの言語検出を担当するため、高い精度とパフォーマンスが求められます。

### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | 各メソッド | 個別機能の検証 |
| パフォーマンステスト | 処理速度 | レスポンスタイムの検証 |
| 回帰テスト | 全検出パターン | 既存機能の維持確認 |

### テストカバレッジ目標

- **単体テストカバレッジ**: 95%以上
- **言語検出精度**: 98%以上
- **パフォーマンス**: 平均10ms以下、最大20ms以下

## 単体テストケース

### 1. 言語検出テスト

#### 1.1 日本語検出（高信頼度）

```python
# tests/test_language_processor.py

import pytest
from backend.utils.language_processor import LanguageProcessor

class TestLanguageDetection:
    """言語検出のテスト"""

    @pytest.fixture
    def processor(self):
        return LanguageProcessor()

    @pytest.mark.parametrize("text,expected_lang,expected_confidence,expected_mixed", [
        # 日本語（高信頼度 - 助詞あり）
        ("営業時間は？", "ja", 0.9, False),
        ("エンジニアカフェについて教えて", "ja", 0.9, False),
        ("Wi-Fiのパスワードは何ですか？", "ja", 0.9, False),
        ("料金を教えてください", "ja", 0.9, False),
        ("場所はどこですか？", "ja", 0.9, False),
    ])
    def test_detect_japanese_high_confidence(self, processor, text, expected_lang, expected_confidence, expected_mixed):
        """日本語検出（高信頼度）のテスト"""
        result = processor.detect_language(text)
        assert result["detected_language"] == expected_lang
        assert result["confidence"] == expected_confidence
        assert result["is_mixed"] == expected_mixed
        assert result["languages"]["primary"] == "ja"
```

#### 1.2 日本語検出（中信頼度）

```python
    @pytest.mark.parametrize("text,expected_lang,expected_confidence,expected_mixed", [
        # 日本語（中信頼度 - 助詞なし）
        ("こんにちは", "ja", 0.7, False),
        ("ありがとう", "ja", 0.7, False),
        ("は", "ja", 0.9, False),  # 助詞単体は高信頼度
    ])
    def test_detect_japanese_medium_confidence(self, processor, text, expected_lang, expected_confidence, expected_mixed):
        """日本語検出（中信頼度）のテスト"""
        result = processor.detect_language(text)
        assert result["detected_language"] == expected_lang
        assert result["confidence"] == expected_confidence
        assert result["is_mixed"] == expected_mixed
```

#### 1.3 英語検出

```python
    @pytest.mark.parametrize("text,expected_lang,expected_confidence,expected_mixed", [
        # 英語
        ("What are the hours?", "en", 0.9, False),
        ("Tell me about the cafe", "en", 0.9, False),
        ("Wi-Fi password", "en", 0.9, False),
        ("Where is the location?", "en", 0.9, False),
        ("How much does it cost?", "en", 0.9, False),
    ])
    def test_detect_english(self, processor, text, expected_lang, expected_confidence, expected_mixed):
        """英語検出のテスト"""
        result = processor.detect_language(text)
        assert result["detected_language"] == expected_lang
        assert result["confidence"] == expected_confidence
        assert result["is_mixed"] == expected_mixed
        assert result["languages"]["primary"] == "en"
```

#### 1.4 混合言語検出

```python
    @pytest.mark.parametrize("text,expected_lang,expected_confidence,expected_mixed", [
        # 混合言語（日本語優先）
        ("Engineer Cafeの営業時間", "ja", 0.7, True),
        ("カフェのhoursは？", "ja", 0.7, True),
        ("Wi-Fi passwordは何ですか？", "ja", 0.9, True),  # 助詞ありで高信頼度
    ])
    def test_detect_mixed_language(self, processor, text, expected_lang, expected_confidence, expected_mixed):
        """混合言語検出のテスト"""
        result = processor.detect_language(text)
        assert result["detected_language"] == expected_lang
        assert result["confidence"] == expected_confidence
        assert result["is_mixed"] == expected_mixed
        assert result["languages"]["primary"] == "ja"
        if expected_mixed:
            assert result["languages"].get("secondary") == "en"
```

### 2. エッジケーステスト

```python
class TestEdgeCases:
    """エッジケースのテスト"""

    @pytest.fixture
    def processor(self):
        return LanguageProcessor()

    @pytest.mark.parametrize("text,expected_lang,expected_confidence,expected_mixed", [
        # エッジケース（デフォルト: 日本語、信頼度0.5）
        ("", "ja", 0.5, False),
        ("123", "ja", 0.5, False),
        ("!@#$%", "ja", 0.5, False),
        ("a", "ja", 0.5, False),
        ("the", "ja", 0.5, False),  # 単語1つでは英語と判定されない
    ])
    def test_edge_cases(self, processor, text, expected_lang, expected_confidence, expected_mixed):
        """エッジケースのテスト"""
        result = processor.detect_language(text)
        assert result["detected_language"] == expected_lang
        assert result["confidence"] == expected_confidence
        assert result["is_mixed"] == expected_mixed
        assert result["languages"]["primary"] == "ja"
```

### 3. 応答言語決定テスト

```python
class TestResponseLanguageDetermination:
    """応答言語決定のテスト"""

    @pytest.fixture
    def processor(self):
        return LanguageProcessor()

    def test_determine_response_language_from_detection(self, processor):
        """検出結果から応答言語を決定"""
        # 日本語検出
        result_ja = processor.detect_language("営業時間は？")
        response_lang = processor.determine_response_language(result_ja)
        assert response_lang == "ja"

        # 英語検出
        result_en = processor.detect_language("What are the hours?")
        response_lang = processor.determine_response_language(result_en)
        assert response_lang == "en"

    def test_determine_response_language_with_force(self, processor):
        """強制言語指定のテスト"""
        result = processor.detect_language("営業時間は？")
        
        # 強制で英語を指定
        response_lang = processor.determine_response_language(result, force_language="en")
        assert response_lang == "en"

        # 強制で日本語を指定
        result_en = processor.detect_language("What are the hours?")
        response_lang = processor.determine_response_language(result_en, force_language="ja")
        assert response_lang == "ja"
```

### 4. 信頼度テスト

```python
class TestConfidence:
    """信頼度のテスト"""

    @pytest.fixture
    def processor(self):
        return LanguageProcessor()

    def test_confidence_values(self, processor):
        """信頼度値の範囲とパターンのテスト"""
        test_cases = [
            ("営業時間は？", 0.9),  # 日本語 + 助詞
            ("こんにちは", 0.7),    # 日本語のみ（助詞なし）
            ("What are the hours?", 0.9),  # 英語（2単語以上）
            ("", 0.5),  # デフォルト
            ("Engineer Cafeの営業時間", 0.7),  # 混合（助詞なし）
            ("Wi-Fi passwordは何ですか？", 0.9),  # 混合（助詞あり）
        ]

        for text, expected_confidence in test_cases:
            result = processor.detect_language(text)
            assert result["confidence"] == expected_confidence, f"Text: {text}"
            assert 0.0 <= result["confidence"] <= 1.0, "Confidence must be between 0 and 1"
```

### 5. 統合テスト

```python
class TestIntegration:
    """統合テスト"""

    @pytest.fixture
    def processor(self):
        return LanguageProcessor()

    def test_full_workflow(self, processor):
        """完全なワークフローのテスト"""
        # 1. 言語検出
        result = processor.detect_language("エンジニアカフェの営業時間は？")
        assert result["detected_language"] == "ja"
        assert result["confidence"] == 0.9

        # 2. 応答言語決定
        response_lang = processor.determine_response_language(result)
        assert response_lang == "ja"

        # 3. 混合言語のケース
        mixed_result = processor.detect_language("Engineer Cafeの営業時間")
        assert mixed_result["is_mixed"] == True
        assert mixed_result["languages"]["primary"] == "ja"
        assert mixed_result["languages"]["secondary"] == "en"

    def test_multiple_detections(self, processor):
        """複数の検出を連続で実行"""
        texts = [
            "営業時間は？",
            "What are the hours?",
            "Engineer Cafeの営業時間",
            "Wi-Fi password",
            "こんにちは",
        ]

        results = [processor.detect_language(text) for text in texts]
        
        # 各結果が正しい形式であることを確認
        for result in results:
            assert "detected_language" in result
            assert "confidence" in result
            assert "is_mixed" in result
            assert "languages" in result
            assert result["detected_language"] in ["ja", "en"]
            assert 0.0 <= result["confidence"] <= 1.0
```

## パフォーマンステスト

### レスポンスタイム計測

```python
import time

class TestPerformance:
    """パフォーマンステスト"""

    @pytest.fixture
    def processor(self):
        return LanguageProcessor()

    def test_detection_performance(self, processor):
        """言語検出の処理時間テスト"""
        test_texts = [
            "営業時間は？",
            "What are the hours?",
            "Engineer Cafeの営業時間",
            "Wi-Fi password",
            "こんにちは",
            "Tell me about the cafe",
            "カフェのhoursは？",
            "エンジニアカフェについて教えて",
        ]

        times = []
        for text in test_texts:
            start = time.perf_counter()
            processor.detect_language(text)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 目標: 平均10ms以下、最大20ms以下
        assert avg_time < 10, f"Average time {avg_time:.2f}ms exceeds 10ms"
        assert max_time < 20, f"Max time {max_time:.2f}ms exceeds 20ms"

    def test_response_language_performance(self, processor):
        """応答言語決定の処理時間テスト"""
        result = processor.detect_language("営業時間は？")

        times = []
        for _ in range(100):
            start = time.perf_counter()
            processor.determine_response_language(result)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 応答言語決定は非常に高速であるべき
        assert avg_time < 1, f"Average time {avg_time:.2f}ms exceeds 1ms"
        assert max_time < 5, f"Max time {max_time:.2f}ms exceeds 5ms"

    def test_concurrent_detection(self, processor):
        """同時リクエストのテスト"""
        import concurrent.futures

        texts = ["営業時間は？"] * 100

        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(processor.detect_language, texts))
        elapsed = (time.perf_counter() - start) * 1000

        assert len(results) == 100
        assert all(r["detected_language"] == "ja" for r in results)
        # 100件の同時処理が200ms以内
        assert elapsed < 200, f"Concurrent processing took {elapsed:.2f}ms"
```

## 回帰テストマトリクス

### 言語検出精度テスト

SPEC.mdで定義された全テストケースを網羅的にテストします。

| カテゴリ | テストケース数 | 目標精度 |
|---------|--------------|---------|
| 日本語（高信頼度） | 8 | 100% |
| 日本語（中信頼度） | 3 | 100% |
| 英語 | 8 | 100% |
| 混合言語 | 3 | 100% |
| エッジケース | 6 | 100% |
| **合計** | **28** | **100%** |

### テストケース一覧

SPEC.mdのテストケースに基づく完全なテストマトリクス：

```python
# tests/test_regression.py

import pytest
from backend.utils.language_processor import LanguageProcessor

class TestRegression:
    """回帰テスト"""

    @pytest.fixture
    def processor(self):
        return LanguageProcessor()

    @pytest.mark.parametrize("text,expected_lang,expected_confidence,expected_mixed", [
        # SPEC.mdの正常系テストケース
        ("営業時間は？", "ja", 0.9, False),
        ("What are the hours?", "en", 0.9, False),
        ("Engineer Cafeの営業時間", "ja", 0.7, True),
        ("Wi-Fi password", "en", 0.9, False),
        ("こんにちは", "ja", 0.7, False),
        ("エンジニアカフェについて教えて", "ja", 0.9, False),
        ("Tell me about the cafe", "en", 0.9, False),
        ("カフェのhoursは？", "ja", 0.7, True),

        # SPEC.mdのエッジケース
        ("", "ja", 0.5, False),
        ("123", "ja", 0.5, False),
        ("!@#$%", "ja", 0.5, False),
        ("a", "ja", 0.5, False),
        ("は", "ja", 0.9, False),
        ("the", "ja", 0.5, False),
    ])
    def test_spec_test_cases(self, processor, text, expected_lang, expected_confidence, expected_mixed):
        """SPEC.mdで定義された全テストケース"""
        result = processor.detect_language(text)
        assert result["detected_language"] == expected_lang, f"Text: {text}"
        assert result["confidence"] == expected_confidence, f"Text: {text}"
        assert result["is_mixed"] == expected_mixed, f"Text: {text}"
```

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_language_processor.py -v

# 特定のテストクラスのみ
pytest tests/test_language_processor.py::TestLanguageDetection -v

# パフォーマンステストのみ
pytest tests/test_language_processor.py::TestPerformance -v

# 回帰テストのみ
pytest tests/test_regression.py -v

# カバレッジレポート付き
pytest tests/test_language_processor.py --cov=backend/utils/language_processor --cov-report=html

# カバレッジ閾値チェック（95%以上）
pytest tests/test_language_processor.py --cov=backend/utils/language_processor --cov-report=term-missing --cov-fail-under=95
```

### CI/CD連携

```yaml
# .github/workflows/test-language-processor.yml

name: Language Processor Tests

on:
  push:
    paths:
      - 'backend/utils/language_processor.py'
      - 'tests/test_language_processor.py'
  pull_request:
    paths:
      - 'backend/utils/language_processor.py'
      - 'tests/test_language_processor.py'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      - name: Run tests
        run: |
          pytest tests/test_language_processor.py -v --cov=backend/utils/language_processor --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: language_processor
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 95%以上 |
| 言語検出精度 | 98%以上 |
| 平均処理時間 | 10ms以下 |
| 最大処理時間 | 20ms以下 |
| 回帰テスト | 全パス（28/28） |

### リリース前チェックリスト

- [ ] 全単体テストがパス
- [ ] パフォーマンステストが基準を満たす
- [ ] 回帰テストマトリクスの全ケースがパス（28/28）
- [ ] テストカバレッジが95%以上
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了（SPEC.md、README.md、MIGRATION-GUIDE.md）

## テストデータ

### テスト用サンプルテキスト

```python
# tests/fixtures/language_test_data.py

JAPANESE_TEXTS = [
    "営業時間は？",
    "エンジニアカフェについて教えて",
    "Wi-Fiのパスワードは何ですか？",
    "料金を教えてください",
    "場所はどこですか？",
    "こんにちは",
    "ありがとう",
]

ENGLISH_TEXTS = [
    "What are the hours?",
    "Tell me about the cafe",
    "Wi-Fi password",
    "Where is the location?",
    "How much does it cost?",
]

MIXED_TEXTS = [
    "Engineer Cafeの営業時間",
    "カフェのhoursは？",
    "Wi-Fi passwordは何ですか？",
]

EDGE_CASE_TEXTS = [
    "",
    "123",
    "!@#$%",
    "a",
    "the",
    "は",
]
```

## 参考リンク

- [SPEC.md](./SPEC.md) - 技術仕様書（テストケース定義）
- [MIGRATION-GUIDE.md](./MIGRATION-GUIDE.md) - 移行ガイド（テスト例）
- [README.md](./README.md) - 概要と責任範囲
- [pytest ドキュメント](https://docs.pytest.org/)
- [Python unittest ドキュメント](https://docs.python.org/3/library/unittest.html)

