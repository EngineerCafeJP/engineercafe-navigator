"""Tests for backend.utils.kanji_converter — kanji to kana conversion."""

import pytest

from backend.utils.kanji_converter import KanjiConverter


class TestKanjiConverter:
    def test_empty_string(self):
        converter = KanjiConverter()
        assert converter.convert_to_kana("") == ""

    def test_english_passthrough(self):
        converter = KanjiConverter()
        result = converter.convert_to_kana("Hello World")
        # Should return as-is or converted (depends on pykakasi behavior)
        assert result is not None
        assert len(result) > 0

    def test_is_available(self):
        import importlib.util

        converter = KanjiConverter()
        # If pykakasi is installed, should be True
        if importlib.util.find_spec("pykakasi") is not None:
            assert converter.is_available() is True
        else:
            assert converter.is_available() is False


class TestKanjiConverterWithPykakasi:
    """Tests that require pykakasi."""

    @pytest.fixture(autouse=True)
    def _check_pykakasi(self):
        pytest.importorskip("pykakasi")

    def test_kanji_to_kana(self):
        converter = KanjiConverter()
        result = converter.convert_to_kana("会議室")
        # Should produce katakana
        assert result != "会議室"  # Should be converted
        assert len(result) > 0

    def test_katakana_passthrough(self):
        converter = KanjiConverter()
        result = converter.convert_to_kana("エンジニアカフェ")
        assert "エンジニアカフェ" in result

    def test_mixed_text(self):
        converter = KanjiConverter()
        result = converter.convert_to_kana("会議室ABC")
        assert "ABC" in result or "abc" in result.lower()
        assert len(result) > 0


class TestKanjiConverterUnavailable:
    """Tests for when pykakasi is not available."""

    def test_unavailable_returns_original(self):
        converter = KanjiConverter()
        # Force unavailable
        converter._kakasi = None
        result = converter.convert_to_kana("会議室")
        assert result == "会議室"

    def test_unavailable_is_available_false(self):
        converter = KanjiConverter()
        converter._kakasi = None
        assert converter.is_available() is False
