"""Tests for backend/utils/emotion_utils.py"""

from backend.utils.emotion_utils import (
    EMOTION_TAG_REGEX,
    strip_emotion_tags,
    extract_primary_emotion,
)


class TestStripEmotionTags:
    """Test strip_emotion_tags() function"""

    def test_strip_simple_tag(self):
        assert strip_emotion_tags("[happy]Hello") == "Hello"

    def test_strip_multiple_tags(self):
        assert strip_emotion_tags("[happy]Hi [sad]there") == "Hi there"

    def test_strip_intensity_tag(self):
        assert strip_emotion_tags("[happy:0.8]Hi") == "Hi"

    def test_strip_closing_tag(self):
        assert strip_emotion_tags("[/happy]Hi") == "Hi"

    def test_strip_empty_string(self):
        assert strip_emotion_tags("") == ""

    def test_strip_none_like(self):
        """None入力はTypeErrorになるが空文字は安全に処理"""
        assert strip_emotion_tags("") == ""

    def test_strip_no_tags(self):
        assert strip_emotion_tags("Normal text without tags") == "Normal text without tags"

    def test_strip_normalizes_whitespace(self):
        assert strip_emotion_tags("[happy]  Hi   there  ") == "Hi there"

    def test_strip_japanese_text(self):
        assert strip_emotion_tags("[relaxed]営業時間は9時からです") == "営業時間は9時からです"

    def test_strip_complex_mixed(self):
        text = (
            "[happy:0.9]エンジニアカフェへようこそ！[/happy] [relaxed]営業時間は9時から22時です。"
        )
        result = strip_emotion_tags(text)
        assert result == "エンジニアカフェへようこそ！ 営業時間は9時から22時です。"

    def test_strip_underscore_emotion(self):
        """アンダースコア付きタグ名"""
        assert strip_emotion_tags("[calm_happy]Hello") == "Hello"


class TestExtractPrimaryEmotion:
    """Test extract_primary_emotion() function"""

    def test_extract_happy(self):
        assert extract_primary_emotion("[happy]Hi") == "happy"

    def test_extract_relaxed_with_intensity(self):
        assert extract_primary_emotion("[relaxed:0.7]Hello") == "relaxed"

    def test_extract_none_no_tags(self):
        assert extract_primary_emotion("No tags here") is None

    def test_extract_empty_string(self):
        assert extract_primary_emotion("") is None

    def test_extract_first_tag_when_multiple(self):
        """複数タグがある場合、最初のタグが返される"""
        assert extract_primary_emotion("[sad]Hello [happy]World") == "sad"


class TestEmotionTagRegex:
    """Test EMOTION_TAG_REGEX pattern"""

    def test_matches_simple_tag(self):
        assert EMOTION_TAG_REGEX.search("[happy]") is not None

    def test_matches_closing_tag(self):
        assert EMOTION_TAG_REGEX.search("[/happy]") is not None

    def test_matches_intensity_tag(self):
        m = EMOTION_TAG_REGEX.search("[happy:0.8]")
        assert m is not None
        assert m.group(1) == "happy"
        assert m.group(2) == "0.8"

    def test_no_match_on_plain_text(self):
        assert EMOTION_TAG_REGEX.search("no tags here") is None
