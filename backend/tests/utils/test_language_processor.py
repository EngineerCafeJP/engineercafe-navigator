"""
LanguageProcessor のユニットテスト
"""

from backend.utils.language_processor import LanguageProcessor, LanguageDetectionResult


class TestLanguageProcessor:
    """LanguageProcessor のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.processor = LanguageProcessor()

    def test_detect_japanese_text(self):
        """日本語テキストの検出"""
        result = self.processor.detect_language("エンジニアカフェの営業時間は?")

        assert result.detected == "ja"
        assert result.confidence == 0.95

    def test_detect_japanese_with_hiragana(self):
        """ひらがなを含む日本語テキストの検出"""
        result = self.processor.detect_language("こんにちは、今日は良い天気ですね")

        assert result.detected == "ja"
        assert result.confidence == 0.95

    def test_detect_japanese_with_katakana(self):
        """カタカナを含む日本語テキストの検出"""
        result = self.processor.detect_language("カフェのメニューは何ですか")

        assert result.detected == "ja"
        assert result.confidence == 0.95

    def test_detect_japanese_with_kanji(self):
        """漢字を含む日本語テキストの検出"""
        result = self.processor.detect_language("営業時間を教えて下さい")

        assert result.detected == "ja"
        assert result.confidence == 0.95

    def test_detect_japanese_mixed_with_english(self):
        """日本語と英語が混在したテキストの検出"""
        result = self.processor.detect_language("Engineer Cafeの場所はどこですか")

        assert result.detected == "ja"
        assert result.confidence == 0.95

    def test_detect_english_text(self):
        """英語テキストの検出"""
        result = self.processor.detect_language("What are the business hours?")

        assert result.detected == "en"
        assert result.confidence == 0.8

    def test_detect_english_with_numbers(self):
        """数字を含む英語テキストの検出"""
        result = self.processor.detect_language("Open from 9:00 to 22:00")

        assert result.detected == "en"
        assert result.confidence == 0.8

    def test_detect_empty_string(self):
        """空文字列の検出"""
        result = self.processor.detect_language("")

        # 空文字列はデフォルトで英語と判定
        assert result.detected == "en"
        assert result.confidence == 0.8

    def test_determine_response_language_japanese(self):
        """日本語応答言語の決定"""
        detection_result = LanguageDetectionResult(detected="ja", confidence=0.95)
        response_lang = self.processor.determine_response_language(detection_result)

        assert response_lang == "ja"

    def test_determine_response_language_english(self):
        """英語応答言語の決定"""
        detection_result = LanguageDetectionResult(detected="en", confidence=0.8)
        response_lang = self.processor.determine_response_language(detection_result)

        assert response_lang == "en"

    def test_japanese_pattern_regex(self):
        """日本語パターン正規表現のテスト"""
        # ひらがな範囲
        assert self.processor.JAPANESE_PATTERN.search("あ")
        assert self.processor.JAPANESE_PATTERN.search("ん")

        # カタカナ範囲
        assert self.processor.JAPANESE_PATTERN.search("ア")
        assert self.processor.JAPANESE_PATTERN.search("ン")

        # 漢字範囲
        assert self.processor.JAPANESE_PATTERN.search("漢")
        assert self.processor.JAPANESE_PATTERN.search("字")

        # 英語はマッチしない
        assert not self.processor.JAPANESE_PATTERN.search("Hello")
        assert not self.processor.JAPANESE_PATTERN.search("123")

    def test_language_detection_result_structure(self):
        """LanguageDetectionResultの構造テスト"""
        result = LanguageDetectionResult(detected="ja", confidence=0.95)

        assert hasattr(result, "detected")
        assert hasattr(result, "confidence")
        assert result.detected in ["ja", "en"]
        assert 0.0 <= result.confidence <= 1.0
