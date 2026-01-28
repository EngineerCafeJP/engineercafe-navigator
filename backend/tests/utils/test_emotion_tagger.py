"""
EmotionTagger のユニットテスト

感情タグ付与機能のテストケース
"""

import pytest
from backend.utils.emotion_tagger import add_emotion_tag


class TestEmotionTagger:
    """EmotionTagger のテストクラス"""

    def test_add_emotion_tag_happy(self):
        """happy感情タグの付与テスト"""
        result = add_emotion_tag("こんにちは", "happy")
        assert result == "[happy]こんにちは"

    def test_add_emotion_tag_surprised(self):
        """surprised感情タグの付与テスト"""
        result = add_emotion_tag("どちらですか？", "surprised")
        assert result == "[surprised]どちらですか？"

    def test_add_emotion_tag_sad(self):
        """sad感情タグの付与テスト"""
        result = add_emotion_tag("申し訳ありません", "sad")
        assert result == "[sad]申し訳ありません"

    def test_add_emotion_tag_relaxed(self):
        """relaxed感情タグの付与テスト"""
        result = add_emotion_tag("営業時間は9時からです", "relaxed")
        assert result == "[relaxed]営業時間は9時からです"

    def test_add_emotion_tag_empty_message(self):
        """空のメッセージに対するテスト"""
        result = add_emotion_tag("", "happy")
        assert result == "[happy]"

    def test_add_emotion_tag_multiline_message(self):
        """複数行メッセージに対するテスト"""
        message = "お手伝いさせていただきます！\nどちらについてお聞きでしょうか？"
        result = add_emotion_tag(message, "surprised")
        assert result == "[surprised]お手伝いさせていただきます！\nどちらについてお聞きでしょうか？"

    def test_add_emotion_tag_with_special_characters(self):
        """特殊文字を含むメッセージに対するテスト"""
        message = "営業時間は9:00-22:00です。"
        result = add_emotion_tag(message, "relaxed")
        assert result == "[relaxed]営業時間は9:00-22:00です。"