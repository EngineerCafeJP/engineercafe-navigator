"""
Tests for backend/utils/clarification_templates.py

Clarification テンプレートの固定応答メッセージとメタデータ生成をテスト。
"""

from backend.utils.clarification_templates import get_clarification_response


class TestClarificationResponseStructure:
    """レスポンス構造のテスト"""

    def test_returns_dict_with_required_keys(self):
        """必須キー（response, emotion, metadata）を含む辞書を返す"""
        result = get_clarification_response("cafe-clarification-needed", "ja")

        assert "response" in result
        assert "emotion" in result
        assert "metadata" in result

    def test_response_is_string(self):
        """response フィールドは文字列"""
        result = get_clarification_response("cafe-clarification-needed", "ja")
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0

    def test_emotion_is_surprised(self):
        """emotion フィールドは常に "surprised" """
        result = get_clarification_response("cafe-clarification-needed", "ja")
        assert result["emotion"] == "surprised"

    def test_metadata_contains_required_fields(self):
        """metadata に agent, confidence, category, sources が含まれる"""
        result = get_clarification_response("cafe-clarification-needed", "ja")
        metadata = result["metadata"]

        assert "agent" in metadata
        assert "confidence" in metadata
        assert "category" in metadata
        assert "sources" in metadata

        assert metadata["agent"] == "ClarificationAgent"
        assert isinstance(metadata["confidence"], float)
        assert metadata["category"] == "cafe-clarification-needed"
        assert isinstance(metadata["sources"], list)


class TestCafeClarificationMessages:
    """カフェ曖昧性のテンプレートメッセージをテスト"""

    def test_cafe_clarification_ja_contains_expected_keywords(self):
        """日本語メッセージに「エンジニアカフェ」「サイノカフェ」が含まれる"""
        result = get_clarification_response("cafe-clarification-needed", "ja")
        response = result["response"]

        # 感情タグを除去してチェック
        assert "エンジニアカフェ" in response
        assert "サイノカフェ" in response

    def test_cafe_clarification_en_contains_expected_keywords(self):
        """英語メッセージに "Engineer Cafe" が含まれる"""
        result = get_clarification_response("cafe-clarification-needed", "en")
        response = result["response"]

        assert "Engineer Cafe" in response

    def test_cafe_clarification_confidence_is_high(self):
        """カフェ曖昧性の confidence は 0.9"""
        result = get_clarification_response("cafe-clarification-needed", "ja")
        assert result["metadata"]["confidence"] == 0.9


class TestMeetingRoomClarificationMessages:
    """会議室曖昧性のテンプレートメッセージをテスト"""

    def test_meeting_room_clarification_ja_contains_info(self):
        """日本語メッセージに会議室情報が含まれる"""
        result = get_clarification_response("meeting-room-clarification-needed", "ja")
        response = result["response"]

        # 有料会議室と地下MTGスペースの両方が言及される
        assert "有料会議室" in response or "会議室" in response
        assert "地下" in response or "MTG" in response

    def test_meeting_room_clarification_en_contains_info(self):
        """英語メッセージに会議室情報が含まれる"""
        result = get_clarification_response("meeting-room-clarification-needed", "en")
        response = result["response"]

        assert "meeting" in response.lower()

    def test_meeting_room_clarification_confidence_is_high(self):
        """会議室曖昧性の confidence は 0.9"""
        result = get_clarification_response("meeting-room-clarification-needed", "ja")
        assert result["metadata"]["confidence"] == 0.9


class TestGeneralClarificationMessages:
    """一般的な曖昧性のテンプレートメッセージをテスト"""

    def test_general_clarification_ja(self):
        """日本語の一般的なclarificationメッセージ"""
        result = get_clarification_response("general-clarification-needed", "ja")
        response = result["response"]

        # 「もう少し詳しく」のような表現が含まれる
        assert len(response) > 0
        assert isinstance(response, str)

    def test_general_clarification_en(self):
        """英語の一般的なclarificationメッセージ"""
        result = get_clarification_response("general-clarification-needed", "en")
        response = result["response"]

        assert len(response) > 0
        assert isinstance(response, str)

    def test_general_clarification_confidence_is_lower(self):
        """一般的な曖昧性の confidence は 0.7（他より低い）"""
        result = get_clarification_response("general-clarification-needed", "ja")
        assert result["metadata"]["confidence"] == 0.7


class TestUnknownCategoryFallback:
    """未知のカテゴリに対するフォールバック動作をテスト"""

    def test_unknown_category_falls_back_to_general(self):
        """未知のカテゴリは general clarification にフォールバック"""
        # Type error を回避するため、関数自体は any category を受け入れるが
        # 実際には general にフォールバックする
        result = get_clarification_response("unknown-category", "ja")  # type: ignore

        # general と同じ confidence になる
        assert result["metadata"]["confidence"] == 0.7
        assert result["metadata"]["category"] == "unknown-category"

    def test_unknown_language_falls_back_to_japanese(self):
        """未知の言語は日本語にフォールバック"""
        result = get_clarification_response("cafe-clarification-needed", "fr")  # type: ignore

        # 日本語メッセージになる（エンジニアカフェが含まれる）
        assert "エンジニアカフェ" in result["response"]


class TestEmotionTagging:
    """感情タグが付与されることをテスト"""

    def test_response_starts_with_emotion_tag(self):
        """レスポンスが感情タグ [surprised] で始まる"""
        result = get_clarification_response("cafe-clarification-needed", "ja")
        response = result["response"]

        assert response.startswith("[surprised]")

    def test_all_categories_have_emotion_tag(self):
        """すべてのカテゴリで感情タグが付与される"""
        categories = [
            "cafe-clarification-needed",
            "meeting-room-clarification-needed",
            "general-clarification-needed",
        ]

        for category in categories:
            result = get_clarification_response(category, "ja")  # type: ignore
            assert result["response"].startswith("[surprised]")
