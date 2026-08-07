"""
language_types のデモモード用ヘルパー（env gated）のユニットテスト
"""

import pytest

from backend.utils.language_types import (
    LANGUAGE_INSTRUCTION,
    get_calendar_fallback_message,
    get_forced_response_language,
    get_language_instruction,
)


class TestGetLanguageInstruction:
    """DEMO_CONCISE_ANSWER による簡潔回答指示の付加"""

    def test_unset_env_returns_base_instruction(self, monkeypatch):
        """未設定時は従来の LANGUAGE_INSTRUCTION と同一。"""
        monkeypatch.delenv("DEMO_CONCISE_ANSWER", raising=False)
        assert get_language_instruction("en") == LANGUAGE_INSTRUCTION["en"]
        assert get_language_instruction("ja") == ""
        assert get_language_instruction("zh") == LANGUAGE_INSTRUCTION["zh"]

    def test_concise_suffix_appended_for_en_when_enabled(self, monkeypatch):
        """DEMO_CONCISE_ANSWER=true で en に簡潔回答の指示が追記される。"""
        monkeypatch.setenv("DEMO_CONCISE_ANSWER", "true")
        result = get_language_instruction("en")
        assert result.startswith(LANGUAGE_INSTRUCTION["en"])
        assert "Keep your answer to 2-3 short sentences (under 35 words)." in result

    def test_concise_flag_does_not_affect_other_languages(self, monkeypatch):
        """簡潔回答の指示は en のみに付加される。"""
        monkeypatch.setenv("DEMO_CONCISE_ANSWER", "true")
        assert get_language_instruction("ja") == ""
        assert get_language_instruction("zh") == LANGUAGE_INSTRUCTION["zh"]
        assert get_language_instruction("ko") == LANGUAGE_INSTRUCTION["ko"]

    @pytest.mark.parametrize("value", ["1", "yes", "on", "TRUE", "True"])
    def test_truthy_variants_enable_concise(self, monkeypatch, value):
        monkeypatch.setenv("DEMO_CONCISE_ANSWER", value)
        concise = "Keep your answer to 2-3 short sentences (under 35 words)."
        assert concise in get_language_instruction("en")

    def test_falsy_variants_keep_base_instruction(self, monkeypatch):
        monkeypatch.setenv("DEMO_CONCISE_ANSWER", "false")
        assert get_language_instruction("en") == LANGUAGE_INSTRUCTION["en"]


class TestGetForcedResponseLanguage:
    """LANGUAGE_FORCE 強制言語ヘルパー"""

    def test_unset_returns_none(self, monkeypatch):
        monkeypatch.delenv("LANGUAGE_FORCE", raising=False)
        assert get_forced_response_language() is None

    def test_set_returns_normalized_code(self, monkeypatch):
        monkeypatch.setenv("LANGUAGE_FORCE", "en")
        assert get_forced_response_language() == "en"

    def test_locale_value_normalized_to_base_code(self, monkeypatch):
        monkeypatch.setenv("LANGUAGE_FORCE", "en-US")
        assert get_forced_response_language() == "en"

    def test_blank_returns_none(self, monkeypatch):
        monkeypatch.setenv("LANGUAGE_FORCE", "   ")
        assert get_forced_response_language() is None


class TestGetCalendarFallbackMessage:
    """カレンダー取得失敗時のデモ用英語メッセージ"""

    def test_none_when_no_demo_env(self, monkeypatch):
        monkeypatch.delenv("DEMO_CONCISE_ANSWER", raising=False)
        monkeypatch.delenv("LANGUAGE_FORCE", raising=False)
        assert get_calendar_fallback_message() is None

    def test_english_message_when_concise_enabled(self, monkeypatch):
        monkeypatch.setenv("DEMO_CONCISE_ANSWER", "true")
        monkeypatch.delenv("LANGUAGE_FORCE", raising=False)
        message = get_calendar_fallback_message()
        assert message is not None
        assert "event calendar" in message

    def test_english_message_when_language_forced_en(self, monkeypatch):
        monkeypatch.setenv("LANGUAGE_FORCE", "en")
        monkeypatch.delenv("DEMO_CONCISE_ANSWER", raising=False)
        assert get_calendar_fallback_message() is not None

    def test_none_when_forced_to_ja(self, monkeypatch):
        monkeypatch.setenv("LANGUAGE_FORCE", "ja")
        monkeypatch.delenv("DEMO_CONCISE_ANSWER", raising=False)
        assert get_calendar_fallback_message() is None
