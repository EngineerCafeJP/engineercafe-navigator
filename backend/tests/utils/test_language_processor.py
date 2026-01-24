"""
LanguageProcessor テスト（修正版）

現在の LanguageProcessor 実装（スコアベース・多言語対応）に対応
"""

import pytest
from utils.language_processor import LanguageProcessor


@pytest.fixture
def processor():
    return LanguageProcessor()


# =============================================================================
# 日本語
# =============================================================================

class TestDetectJapanese:
    def test_japanese_with_particles(self, processor):
        result = processor.detect_language("営業時間は？")
        assert result["detected_language"] == "ja"
        assert result["confidence"] == 0.9
        assert result["is_mixed"] is False

    def test_japanese_without_particles(self, processor):
        result = processor.detect_language("テスト")
        assert result["detected_language"] == "ja"
        assert result["confidence"] == 0.7

    def test_japanese_single_particle(self, processor):
        result = processor.detect_language("は")
        assert result["detected_language"] == "ja"
        assert result["confidence"] == 0.9


# =============================================================================
# 英語
# =============================================================================

class TestDetectEnglish:
    def test_english_multiple_keywords(self, processor):
        result = processor.detect_language("What are the hours?")
        assert result["detected_language"] == "en"
        assert result["confidence"] == 0.9
        assert result["is_mixed"] is False

    def test_english_minimal_sentence(self, processor):
        result = processor.detect_language("Tell me")
        assert result["detected_language"] == "en"
        assert result["confidence"] >= 0.7

    def test_single_latin_word_low_signal(self, processor):
        result = processor.detect_language("hello")
        assert result["detected_language"] == "en"
        assert result["confidence"] == 0.6


# =============================================================================
# 中国語
# =============================================================================

class TestDetectChinese:
    def test_chinese_with_keywords(self, processor):
        result = processor.detect_language("这是我的书")
        assert result["detected_language"] == "zh"
        assert result["confidence"] == 0.9

    def test_chinese_cjk_only(self, processor):
        result = processor.detect_language("福岡")
        assert result["detected_language"] == "zh"
        assert result["confidence"] == 0.7

    def test_chinese_mixed_with_english(self, processor):
        result = processor.detect_language("WiFi的密码是什么")
        assert result["detected_language"] == "zh"
        assert result["is_mixed"] is True
        assert result["languages"]["secondary"] == "en"


# =============================================================================
# 韓国語
# =============================================================================

class TestDetectKorean:
    def test_korean_with_keywords(self, processor):
        result = processor.detect_language("이것은 카페입니다")
        assert result["detected_language"] == "ko"
        assert result["confidence"] == 0.9

    def test_korean_without_keywords(self, processor):
        result = processor.detect_language("안녕")
        assert result["detected_language"] == "ko"
        assert result["confidence"] == 0.7

    def test_korean_mixed_with_english(self, processor):
        result = processor.detect_language("Engineer Cafe는 좋습니다")
        assert result["detected_language"] == "ko"
        assert result["is_mixed"] is True
        assert result["languages"]["secondary"] == "en"


# =============================================================================
# 混合言語（primary / secondary の一般化）
# =============================================================================

class TestDetectMixed:
    def test_japanese_english_mixed(self, processor):
        result = processor.detect_language("Engineer Cafeの営業時間")
        assert result["detected_language"] == "ja"
        assert result["is_mixed"] is True
        assert result["languages"]["secondary"] == "en"

    def test_japanese_chinese_mixed(self, processor):
        result = processor.detect_language("这是カフェです")
        assert result["detected_language"] in {"ja", "zh"}
        assert result["is_mixed"] is True

    def test_japanese_korean_mixed(self, processor):
        result = processor.detect_language("카페の場所")
        assert result["is_mixed"] is True


# =============================================================================
# フォールバック・エッジケース
# =============================================================================

class TestEdgeCases:
    def test_empty_string(self, processor):
        result = processor.detect_language("")
        assert result["detected_language"] == "ja"
        assert result["confidence"] == 0.5

    def test_numbers_only(self, processor):
        result = processor.detect_language("12345")
        assert result["detected_language"] == "ja"
        assert result["confidence"] == 0.5

    def test_symbols_only(self, processor):
        result = processor.detect_language("!@#$%")
        assert result["detected_language"] == "ja"
        assert result["confidence"] == 0.5


# =============================================================================
# determine_response_language
# =============================================================================

class TestDetermineResponseLanguage:
    def test_detected_language_used(self, processor):
        result = processor.detect_language("これはテストです")
        assert processor.determine_response_language(result) == "ja"

    def test_force_language(self, processor):
        result = processor.detect_language("これはテストです")
        assert processor.determine_response_language(result, force_language="en") == "en"


# =============================================================================
# 信頼度境界値
# =============================================================================

class TestConfidenceBoundaries:
    def test_confidence_0_9(self, processor):
        result = processor.detect_language("これはテストです")
        assert result["confidence"] == 0.9

    def test_confidence_0_7(self, processor):
        result = processor.detect_language("テスト")
        assert result["confidence"] == 0.7

    def test_confidence_0_6(self, processor):
        result = processor.detect_language("hello")
        assert result["confidence"] == 0.6

    def test_confidence_0_5(self, processor):
        result = processor.detect_language("xyz")
        assert result["confidence"] == 0.5
