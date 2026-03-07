"""Tests for the reception templates module.

Covers both the legacy dict-based API (used by MainWorkflow)
and the new ReceptionResult-based API (used by ReceptionWorkflow).
"""

from backend.utils.reception_templates import (
    ReceptionResult,
    get_personalized_greeting,
    get_purpose_followup,
    get_purpose_hearing_prompt,
    get_reception_response,
)


# ===================================================================
# Legacy API tests (dict-based, backward-compatible)
# ===================================================================


class TestLegacyReceptionResponseStructure:
    """レスポンス構造のテスト"""

    def test_returns_dict_with_required_keys(self):
        result = get_reception_response("ja")
        assert "response" in result
        assert "emotion" in result
        assert "metadata" in result

    def test_response_is_string(self):
        result = get_reception_response("ja")
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0

    def test_emotion_is_happy(self):
        result = get_reception_response("ja")
        assert result["emotion"] == "happy"

    def test_metadata_contains_required_fields(self):
        result = get_reception_response("ja")
        metadata = result["metadata"]
        assert metadata["agent"] == "ReceptionAgent"
        assert isinstance(metadata["confidence"], float)
        assert metadata["category"] == "reception"
        assert isinstance(metadata["sources"], list)


class TestLegacyFirstTimeReception:
    def test_first_time_ja_contains_welcome(self):
        result = get_reception_response("ja", "first_time")
        response = result["response"]
        assert "ようこそ" in response
        assert "無料" in response

    def test_first_time_en_contains_welcome(self):
        result = get_reception_response("en", "first_time")
        response = result["response"]
        assert "Welcome" in response
        assert "free" in response.lower()

    def test_first_time_confidence_is_high(self):
        result = get_reception_response("ja", "first_time")
        assert result["metadata"]["confidence"] == 0.95

    def test_first_time_reception_type_in_metadata(self):
        result = get_reception_response("ja", "first_time")
        assert result["metadata"]["reception_type"] == "first_time"


class TestLegacyReturningReception:
    def test_returning_ja_contains_welcome_back(self):
        result = get_reception_response("ja", "returning")
        assert "おかえり" in result["response"]

    def test_returning_en_contains_welcome_back(self):
        result = get_reception_response("en", "returning")
        assert "Welcome back" in result["response"]

    def test_returning_confidence(self):
        result = get_reception_response("ja", "returning")
        assert result["metadata"]["confidence"] == 0.9


class TestLegacyGeneralReception:
    def test_general_ja_contains_basic_info(self):
        result = get_reception_response("ja", "general")
        response = result["response"]
        assert "Wi-Fi" in response or "wifi" in response.lower()

    def test_general_en_contains_basic_info(self):
        result = get_reception_response("en", "general")
        assert "Wi-Fi" in result["response"]

    def test_general_is_default_reception_type(self):
        result = get_reception_response("ja")
        assert result["metadata"]["reception_type"] == "general"

    def test_general_confidence(self):
        result = get_reception_response("ja", "general")
        assert result["metadata"]["confidence"] == 0.85


class TestLegacyEmotionTagging:
    def test_response_starts_with_emotion_tag(self):
        result = get_reception_response("ja")
        assert result["response"].startswith("[happy]")

    def test_all_types_have_emotion_tag(self):
        for reception_type in ["first_time", "returning", "general"]:
            result = get_reception_response("ja", reception_type)
            assert result["response"].startswith("[happy]")


class TestLegacyLanguageFallback:
    def test_unknown_language_falls_back_to_japanese(self):
        result = get_reception_response("fr")  # type: ignore
        assert "エンジニアカフェ" in result["response"] or "ようこそ" in result["response"]


# ===================================================================
# New API tests (ReceptionResult-based)
# ===================================================================


class TestGetReceptionResponseNewAPI:
    """Tests for the new-style greeting function (is_returning kwarg)."""

    def test_first_visit_ja(self) -> None:
        result = get_reception_response("ja", is_returning=False)
        assert isinstance(result, ReceptionResult)
        assert "ようこそ" in result.text
        assert result.language == "ja"
        assert result.template_type == "first_visit_greeting"

    def test_first_visit_en(self) -> None:
        result = get_reception_response("en", is_returning=False)
        assert "Welcome" in result.text
        assert result.language == "en"

    def test_returning_ja(self) -> None:
        result = get_reception_response("ja", is_returning=True)
        assert "おかえりなさい" in result.text
        assert result.template_type == "returning_greeting"

    def test_returning_en(self) -> None:
        result = get_reception_response("en", is_returning=True)
        assert "Welcome back" in result.text

    def test_unsupported_language_defaults_to_ja(self) -> None:
        result = get_reception_response("fr", is_returning=False)  # type: ignore[arg-type]
        assert result.language == "ja"


class TestGetPersonalizedGreeting:
    def test_personalized_greeting_ja(self) -> None:
        result = get_personalized_greeting("ja", name="田中", last_purpose="コワーキング利用")
        assert "田中" in result.text
        assert "コワーキング利用" in result.text
        assert result.template_type == "returning_personalized"

    def test_personalized_greeting_en(self) -> None:
        result = get_personalized_greeting("en", name="John", last_purpose="coworking")
        assert "John" in result.text
        assert "coworking" in result.text

    def test_personalized_greeting_without_purpose_ja(self) -> None:
        result = get_personalized_greeting("ja", name="佐藤")
        assert "佐藤" in result.text
        assert "ご利用" in result.text

    def test_personalized_greeting_without_purpose_en(self) -> None:
        result = get_personalized_greeting("en", name="Alice")
        assert "Alice" in result.text
        assert "a visit" in result.text


class TestGetPurposeHearingPrompt:
    def test_purpose_hearing_prompt_ja(self) -> None:
        result = get_purpose_hearing_prompt("ja")
        assert "ご用件" in result.text
        assert "コワーキング" in result.text
        assert result.template_type == "purpose_hearing"

    def test_purpose_hearing_prompt_en(self) -> None:
        result = get_purpose_hearing_prompt("en")
        assert "What brings you here" in result.text
        assert "coworking" in result.text


class TestGetPurposeFollowup:
    def test_purpose_followup_facility_use(self) -> None:
        result = get_purpose_followup("ja", "facility_use")
        assert "Wi-Fi" in result.text
        assert result.template_type == "purpose_followup_facility_use"

    def test_purpose_followup_event(self) -> None:
        result = get_purpose_followup("ja", "event_participation")
        assert "イベント" in result.text

    def test_purpose_followup_tour(self) -> None:
        result = get_purpose_followup("ja", "tour")
        assert "見学" in result.text

    def test_purpose_followup_consultation_ja(self) -> None:
        result = get_purpose_followup("ja", "consultation")
        assert "スタッフ" in result.text

    def test_purpose_followup_other_en(self) -> None:
        result = get_purpose_followup("en", "other")
        assert "Feel free" in result.text

    def test_purpose_followup_unknown_falls_back_to_other(self) -> None:
        result = get_purpose_followup("ja", "nonexistent_purpose")
        assert result.text == get_purpose_followup("ja", "other").text

    def test_purpose_followup_facility_use_en(self) -> None:
        result = get_purpose_followup("en", "facility_use")
        assert "coworking" in result.text
        assert "Wi-Fi" in result.text
