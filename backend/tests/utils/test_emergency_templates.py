"""
Tests for backend/utils/emergency_templates.py

Emergency テンプレートの固定応答メッセージとメタデータ生成をテスト。
"""

from backend.utils.emergency_templates import (
    classify_emergency_subtype,
    get_emergency_response,
)


class TestEmergencySubtypeClassification:
    """緊急サブタイプ分類のテスト"""

    def test_earthquake_ja_keyword(self):
        """日本語「地震」キーワードで earthquake に分類される"""
        result = classify_emergency_subtype("地震が起きました")
        assert result == "earthquake"

    def test_earthquake_en_keyword(self):
        """英語 "earthquake" キーワードで earthquake に分類される"""
        result = classify_emergency_subtype("There is an earthquake!")
        assert result == "earthquake"

    def test_fire_ja_keyword(self):
        """日本語「火事」キーワードで fire に分類される"""
        result = classify_emergency_subtype("火事です！")
        assert result == "fire"

    def test_fire_en_keyword(self):
        """英語 "fire" キーワードで fire に分類される"""
        result = classify_emergency_subtype("There is a fire!")
        assert result == "fire"

    def test_medical_emergency_aed_keyword(self):
        """「AED」キーワードで medical_emergency に分類される"""
        result = classify_emergency_subtype("AEDはどこですか")
        assert result == "medical_emergency"

    def test_medical_emergency_ambulance_keyword(self):
        """英語 "ambulance" キーワードで medical_emergency に分類される"""
        result = classify_emergency_subtype("call an ambulance")
        assert result == "medical_emergency"

    def test_general_emergency_fallback(self):
        """認識できないクエリは general_emergency にフォールバックする"""
        result = classify_emergency_subtype("緊急事態です")
        assert result == "general_emergency"

    def test_unrecognized_query_falls_back_to_general(self):
        """キーワードが一致しないクエリは general_emergency にフォールバックする"""
        result = classify_emergency_subtype("助けてください")
        assert result == "general_emergency"


class TestEarthquakeResponse:
    """地震テンプレートのテスト"""

    def test_earthquake_ja_response(self):
        """地震クエリで日本語避難指示が返される"""
        result = get_emergency_response("地震が起きました", "ja")
        response = result["response"]

        assert "地震" in response
        assert "机の下" in response
        assert "1階正面玄関" in response

    def test_earthquake_en_response(self):
        """地震クエリで英語避難指示が返される"""
        result = get_emergency_response("There is an earthquake", "en")
        response = result["response"]

        assert "Earthquake" in response
        assert "desk" in response
        assert "1F main entrance" in response

    def test_earthquake_subtype_in_metadata(self):
        """メタデータに subtype=earthquake が含まれる"""
        result = get_emergency_response("地震", "ja")
        assert result["metadata"]["subtype"] == "earthquake"

    def test_earthquake_confidence_is_high(self):
        """地震テンプレートの confidence は 0.95"""
        result = get_emergency_response("地震", "ja")
        assert result["metadata"]["confidence"] == 0.95


class TestFireResponse:
    """火事テンプレートのテスト"""

    def test_fire_ja_response(self):
        """火事クエリで日本語避難指示が返される"""
        result = get_emergency_response("火事です", "ja")
        response = result["response"]

        assert "火事" in response
        assert "119" in response
        assert "出口" in response

    def test_fire_en_response(self):
        """火事クエリで英語避難指示が返される"""
        result = get_emergency_response("There is a fire", "en")
        response = result["response"]

        assert "Fire" in response
        assert "119" in response
        assert "exit" in response.lower()

    def test_fire_subtype_in_metadata(self):
        """メタデータに subtype=fire が含まれる"""
        result = get_emergency_response("火事", "ja")
        assert result["metadata"]["subtype"] == "fire"

    def test_fire_confidence_is_high(self):
        """火事テンプレートの confidence は 0.95"""
        result = get_emergency_response("火事", "ja")
        assert result["metadata"]["confidence"] == 0.95


class TestMedicalEmergencyResponse:
    """医療緊急テンプレートのテスト"""

    def test_medical_emergency_ja_response(self):
        """医療緊急クエリで日本語応急処置情報が返される"""
        result = get_emergency_response("AEDはどこですか", "ja")
        response = result["response"]

        assert "119" in response
        assert "AED" in response
        assert "1階受付" in response

    def test_medical_emergency_en_response(self):
        """医療緊急クエリで英語応急処置情報が返される"""
        result = get_emergency_response("call an ambulance", "en")
        response = result["response"]

        assert "119" in response
        assert "AED" in response
        assert "reception" in response.lower()

    def test_medical_emergency_subtype_in_metadata(self):
        """メタデータに subtype=medical_emergency が含まれる"""
        result = get_emergency_response("AED", "ja")
        assert result["metadata"]["subtype"] == "medical_emergency"

    def test_medical_emergency_confidence_is_high(self):
        """医療緊急テンプレートの confidence は 0.95"""
        result = get_emergency_response("AED", "ja")
        assert result["metadata"]["confidence"] == 0.95


class TestGeneralEmergencyResponse:
    """一般緊急テンプレートのテスト"""

    def test_general_emergency_ja_response(self):
        """一般緊急クエリで日本語緊急案内が返される"""
        result = get_emergency_response("緊急事態です", "ja")
        response = result["response"]

        assert "緊急事態" in response
        assert "119" in response
        assert "110" in response

    def test_general_emergency_en_response(self):
        """一般緊急クエリで英語緊急案内が返される"""
        result = get_emergency_response("emergency", "en")
        response = result["response"]

        assert "Emergency" in response
        assert "119" in response
        assert "110" in response

    def test_general_emergency_subtype_in_metadata(self):
        """メタデータに subtype=general_emergency が含まれる"""
        result = get_emergency_response("緊急事態", "ja")
        assert result["metadata"]["subtype"] == "general_emergency"

    def test_general_emergency_confidence_is_lower(self):
        """一般緊急テンプレートの confidence は 0.85（他より低い）"""
        result = get_emergency_response("緊急事態", "ja")
        assert result["metadata"]["confidence"] == 0.85


class TestEmergencyResponseStructure:
    """レスポンス構造のテスト"""

    def test_returns_dict_with_required_keys(self):
        """必須キー（response, emotion, metadata）を含む辞書を返す"""
        result = get_emergency_response("地震", "ja")

        assert "response" in result
        assert "emotion" in result
        assert "metadata" in result

    def test_response_is_string(self):
        """response フィールドは文字列"""
        result = get_emergency_response("地震", "ja")
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0

    def test_emotion_is_serious(self):
        """emotion フィールドは常に "serious" """
        result = get_emergency_response("地震", "ja")
        assert result["emotion"] == "serious"

    def test_metadata_contains_required_fields(self):
        """metadata に agent, confidence, subtype, sources が含まれる"""
        result = get_emergency_response("地震", "ja")
        metadata = result["metadata"]

        assert "agent" in metadata
        assert "confidence" in metadata
        assert "subtype" in metadata
        assert "sources" in metadata

        assert metadata["agent"] == "EmergencyAgent"
        assert isinstance(metadata["confidence"], float)
        assert isinstance(metadata["sources"], list)


class TestEmotionTagging:
    """感情タグが付与されることをテスト"""

    def test_earthquake_response_starts_with_serious_tag(self):
        """地震レスポンスが [serious] タグで始まる"""
        result = get_emergency_response("地震", "ja")
        assert result["response"].startswith("[serious]")

    def test_fire_response_starts_with_serious_tag(self):
        """火事レスポンスが [serious] タグで始まる"""
        result = get_emergency_response("火事", "ja")
        assert result["response"].startswith("[serious]")

    def test_medical_response_starts_with_serious_tag(self):
        """医療緊急レスポンスが [serious] タグで始まる"""
        result = get_emergency_response("AED", "ja")
        assert result["response"].startswith("[serious]")

    def test_general_response_starts_with_serious_tag(self):
        """一般緊急レスポンスが [serious] タグで始まる"""
        result = get_emergency_response("緊急", "ja")
        assert result["response"].startswith("[serious]")

    def test_all_subtypes_have_serious_emotion_tag(self):
        """すべてのサブタイプで [serious] 感情タグが付与される"""
        queries = ["地震", "火事", "AED", "緊急事態"]
        for query in queries:
            result = get_emergency_response(query, "ja")
            assert result["response"].startswith(
                "[serious]"
            ), f"Expected [serious] tag for query: {query}"


class TestLanguageFallback:
    """未知の言語に対するフォールバック動作をテスト"""

    def test_unknown_language_falls_back_to_japanese(self):
        """未知の言語は日本語にフォールバック"""
        result = get_emergency_response("地震", "fr")  # type: ignore

        # 日本語メッセージになる（地震が含まれる）
        assert "地震" in result["response"] or "机の下" in result["response"]

    def test_default_language_is_japanese(self):
        """デフォルト言語は日本語"""
        result = get_emergency_response("地震")
        response = result["response"]

        assert "地震" in response or "机の下" in response
