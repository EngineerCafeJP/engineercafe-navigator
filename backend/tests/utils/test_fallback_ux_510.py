"""Tests for fallback UX improvement (Issue #510).

Validates:
1. EN fallback includes staff guidance + Japanese switch suggestion
2. ZH fallback includes staff guidance + Japanese switch suggestion
3. KO fallback includes staff guidance
4. JA fallback is unchanged from original
"""

from backend.utils.language_types import DEFAULT_NOT_FOUND_RESPONSE


class TestFallbackUX:
    def test_en_has_staff_guidance(self):
        msg = DEFAULT_NOT_FOUND_RESPONSE["en"]
        assert "staff" in msg.lower()
        assert "reception" in msg.lower()

    def test_en_has_japanese_switch(self):
        msg = DEFAULT_NOT_FOUND_RESPONSE["en"]
        assert "Japanese" in msg or "japanese" in msg

    def test_zh_has_staff_guidance(self):
        msg = DEFAULT_NOT_FOUND_RESPONSE["zh"]
        assert "前台" in msg or "工作人员" in msg

    def test_zh_has_japanese_switch(self):
        msg = DEFAULT_NOT_FOUND_RESPONSE["zh"]
        assert "日语" in msg

    def test_ko_has_staff_guidance(self):
        msg = DEFAULT_NOT_FOUND_RESPONSE["ko"]
        assert "직원" in msg or "프런트" in msg

    def test_ko_has_japanese_switch(self):
        msg = DEFAULT_NOT_FOUND_RESPONSE["ko"]
        assert "일본어" in msg

    def test_ja_unchanged(self):
        msg = DEFAULT_NOT_FOUND_RESPONSE["ja"]
        assert "申し訳ございません" in msg
        assert "スタッフ" in msg
        assert "日本語で" not in msg
        assert "Japanese" not in msg

    def test_all_languages_present(self):
        for lang in ["ja", "en", "zh", "ko"]:
            assert lang in DEFAULT_NOT_FOUND_RESPONSE
            assert "[sad]" in DEFAULT_NOT_FOUND_RESPONSE[lang]
