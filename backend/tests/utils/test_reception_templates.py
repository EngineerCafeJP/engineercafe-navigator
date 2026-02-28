"""
Tests for backend/utils/reception_templates.py

Reception テンプレートの固定応答メッセージとメタデータ生成をテスト。
"""

from backend.utils.reception_templates import get_reception_response


class TestReceptionResponseStructure:
    """レスポンス構造のテスト"""

    def test_returns_dict_with_required_keys(self):
        """必須キー（response, emotion, metadata）を含む辞書を返す"""
        result = get_reception_response("ja")

        assert "response" in result
        assert "emotion" in result
        assert "metadata" in result

    def test_response_is_string(self):
        """response フィールドは文字列"""
        result = get_reception_response("ja")
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0

    def test_emotion_is_happy(self):
        """emotion フィールドは常に "happy" """
        result = get_reception_response("ja")
        assert result["emotion"] == "happy"

    def test_metadata_contains_required_fields(self):
        """metadata に agent, confidence, category, sources が含まれる"""
        result = get_reception_response("ja")
        metadata = result["metadata"]

        assert "agent" in metadata
        assert "confidence" in metadata
        assert "category" in metadata
        assert "sources" in metadata

        assert metadata["agent"] == "ReceptionAgent"
        assert isinstance(metadata["confidence"], float)
        assert metadata["category"] == "reception"
        assert isinstance(metadata["sources"], list)


class TestFirstTimeReception:
    """初回利用案内のテスト"""

    def test_first_time_ja_contains_welcome(self):
        """日本語初回メッセージにウェルカム情報が含まれる"""
        result = get_reception_response("ja", "first_time")
        response = result["response"]

        assert "ようこそ" in response
        assert "無料" in response
        assert "受付" in response or "利用登録" in response

    def test_first_time_en_contains_welcome(self):
        """英語初回メッセージにwelcome情報が含まれる"""
        result = get_reception_response("en", "first_time")
        response = result["response"]

        assert "Welcome" in response
        assert "free" in response.lower()
        assert "register" in response.lower() or "reception" in response.lower()

    def test_first_time_confidence_is_high(self):
        """初回利用案内の confidence は 0.95"""
        result = get_reception_response("ja", "first_time")
        assert result["metadata"]["confidence"] == 0.95

    def test_first_time_reception_type_in_metadata(self):
        """metadata に reception_type が含まれる"""
        result = get_reception_response("ja", "first_time")
        assert result["metadata"]["reception_type"] == "first_time"


class TestReturningReception:
    """リピーター案内のテスト"""

    def test_returning_ja_contains_welcome_back(self):
        """日本語リピーターメッセージにおかえりが含まれる"""
        result = get_reception_response("ja", "returning")
        response = result["response"]

        assert "おかえり" in response

    def test_returning_en_contains_welcome_back(self):
        """英語リピーターメッセージにwelcome backが含まれる"""
        result = get_reception_response("en", "returning")
        response = result["response"]

        assert "Welcome back" in response

    def test_returning_confidence(self):
        """リピーター案内の confidence は 0.9"""
        result = get_reception_response("ja", "returning")
        assert result["metadata"]["confidence"] == 0.9


class TestGeneralReception:
    """一般受付案内のテスト"""

    def test_general_ja_contains_basic_info(self):
        """日本語一般案内に基本情報が含まれる"""
        result = get_reception_response("ja", "general")
        response = result["response"]

        assert "Wi-Fi" in response or "wifi" in response.lower()
        assert "9:00" in response or "営業時間" in response

    def test_general_en_contains_basic_info(self):
        """英語一般案内に基本情報が含まれる"""
        result = get_reception_response("en", "general")
        response = result["response"]

        assert "Wi-Fi" in response
        assert "9:00" in response

    def test_general_is_default_reception_type(self):
        """引数なしはgeneralになる"""
        result = get_reception_response("ja")
        assert result["metadata"]["reception_type"] == "general"

    def test_general_confidence(self):
        """一般案内の confidence は 0.85"""
        result = get_reception_response("ja", "general")
        assert result["metadata"]["confidence"] == 0.85


class TestEmotionTagging:
    """感情タグが付与されることをテスト"""

    def test_response_starts_with_emotion_tag(self):
        """レスポンスが感情タグ [happy] で始まる"""
        result = get_reception_response("ja")
        assert result["response"].startswith("[happy]")

    def test_all_types_have_emotion_tag(self):
        """すべての受付タイプで感情タグが付与される"""
        for reception_type in ["first_time", "returning", "general"]:
            result = get_reception_response("ja", reception_type)
            assert result["response"].startswith("[happy]")


class TestLanguageFallback:
    """未知の言語に対するフォールバック動作をテスト"""

    def test_unknown_language_falls_back_to_japanese(self):
        """未知の言語は日本語にフォールバック"""
        result = get_reception_response("fr")  # type: ignore

        # 日本語メッセージになる
        assert "エンジニアカフェ" in result["response"] or "ようこそ" in result["response"]
