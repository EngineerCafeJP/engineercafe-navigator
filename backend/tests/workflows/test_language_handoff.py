"""Tests for MainWorkflow._get_response_language handoff logic.

Bug #444 regression: ensure language detection and frontend fallback
interact correctly for multilingual queries.
"""

import pytest


@pytest.fixture
def workflow():
    from backend.workflows.main_workflow import MainWorkflow

    return MainWorkflow.__new__(MainWorkflow)  # no __init__, we only need the method


class TestGetResponseLanguage:
    """Regression matrix for _get_response_language after Bug #444 fix."""

    def test_kanji_only_japanese_returns_ja(self, workflow):
        """Bug #444: kanji-only Japanese (no hiragana) → ja via scoring fallback."""
        assert workflow._get_response_language("営業時間", "ja") == "ja"
        assert workflow._get_response_language("時間", "ja") == "ja"
        assert workflow._get_response_language("今日", "ja") == "ja"

    def test_japanese_with_hiragana_returns_ja(self, workflow):
        """Standard Japanese with particles → ja."""
        assert workflow._get_response_language("今日の営業時間は？", "ja") == "ja"
        assert workflow._get_response_language("Wi-Fiのパスワードを教えて", "ja") == "ja"

    def test_english_returns_en(self, workflow):
        """English query with latin alphabet → en."""
        assert workflow._get_response_language("What are opening hours?", "ja") == "en"

    def test_pure_chinese_returns_zh(self, workflow):
        """Regression: Chinese query must not be overridden to ja."""
        assert workflow._get_response_language("你好", "ja") == "zh"
        assert workflow._get_response_language("营业时间是几点", "ja") == "zh"
        assert workflow._get_response_language("现在几点", "ja") == "zh"

    def test_korean_returns_ko(self, workflow):
        """Korean hangul query → ko."""
        assert workflow._get_response_language("영업시간이 언제인가요", "ja") == "ko"

    def test_fallback_language_used_when_detection_none(self, workflow):
        """If detector returns empty/None, fallback kicks in."""
        # Empty string: scoring falls to default ("ja" via default_language)
        assert workflow._get_response_language("", "ja") == "ja"
        # Single space: same
        assert workflow._get_response_language("   ", "ja") == "ja"
