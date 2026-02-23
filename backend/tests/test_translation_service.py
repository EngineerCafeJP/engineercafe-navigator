"""
Tests for CTranslate2 translation service.

All tests use mocks so they run without actual models installed.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.services.translation_service import (
    TranslationService,
    get_translation_service,
)


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture()
def mock_ctranslate2():
    """Mock ctranslate2.Translator for unit tests."""
    mock_translator = MagicMock()
    # Simulate translate_batch returning a result with hypotheses
    hypothesis = MagicMock()
    hypothesis.hypotheses = [["translated", "token", "</s>"]]
    mock_translator.translate_batch.return_value = [hypothesis]

    mock_module = MagicMock()
    mock_module.Translator.return_value = mock_translator
    return mock_module, mock_translator


@pytest.fixture()
def mock_sentencepiece():
    """Mock sentencepiece.SentencePieceProcessor."""
    mock_sp = MagicMock()
    mock_sp.Encode.return_value = ["hello", "world"]
    mock_sp.Decode.return_value = "翻訳されたテキスト"

    mock_module = MagicMock()
    mock_module.SentencePieceProcessor.return_value = mock_sp
    return mock_module, mock_sp


@pytest.fixture()
def translation_service(tmp_path, mock_ctranslate2, mock_sentencepiece):
    """Create a TranslationService with mocked dependencies."""
    # Create fake model directories with required files
    for model_name in ("opus-mt-en-jap", "opus-mt-ja-en"):
        model_dir = tmp_path / model_name
        model_dir.mkdir()
        (model_dir / "model.bin").write_text("fake")
        (model_dir / "source.spm").write_text("fake")
        (model_dir / "target.spm").write_text("fake")

    ct2_mod, _ = mock_ctranslate2
    sp_mod, _ = mock_sentencepiece

    with (
        patch.dict("sys.modules", {"ctranslate2": ct2_mod, "sentencepiece": sp_mod}),
        patch(
            "importlib.import_module",
            side_effect=lambda name: ct2_mod if "ctranslate2" in name else sp_mod,
        ),
    ):
        svc = TranslationService(model_dir=str(tmp_path))
        # Manually inject mocks since _load_model uses import
        for direction in ("en_to_ja", "ja_to_en"):
            svc._translators[direction] = ct2_mod.Translator.return_value
            svc._source_sps[direction] = sp_mod.SentencePieceProcessor.return_value
            svc._target_sps[direction] = sp_mod.SentencePieceProcessor.return_value
        yield svc


# =====================================================================
# Language detection tests
# =====================================================================


class TestLanguageDetection:
    """Tests for is_japanese / is_latin_only static methods."""

    def test_is_japanese_hiragana(self):
        assert TranslationService.is_japanese("こんにちは") is True

    def test_is_japanese_katakana(self):
        assert TranslationService.is_japanese("カフェ") is True

    def test_is_japanese_kanji(self):
        assert TranslationService.is_japanese("営業時間") is True

    def test_is_japanese_english(self):
        assert TranslationService.is_japanese("Hello world") is False

    def test_is_japanese_mixed(self):
        assert TranslationService.is_japanese("Hello こんにちは") is True

    def test_is_latin_only_english(self):
        assert TranslationService.is_latin_only("Hello world!") is True

    def test_is_latin_only_digits(self):
        assert TranslationService.is_latin_only("Room 101, 2nd floor") is True

    def test_is_latin_only_japanese(self):
        assert TranslationService.is_latin_only("こんにちは") is False

    def test_is_latin_only_mixed(self):
        assert TranslationService.is_latin_only("Hello こんにちは") is False


# =====================================================================
# Translation tests (mocked)
# =====================================================================


class TestTranslation:
    """Tests for translate() async method with mocked CTranslate2."""

    @pytest.mark.asyncio
    async def test_en_to_ja_translation(self, translation_service, mock_sentencepiece):
        """English query should be translated to Japanese."""
        _, mock_sp = mock_sentencepiece
        mock_sp.Decode.return_value = "営業時間は何時ですか"

        result = await translation_service.translate("What are the opening hours?", "en_to_ja")
        assert result == "営業時間は何時ですか"

    @pytest.mark.asyncio
    async def test_ja_to_en_translation(self, translation_service, mock_sentencepiece):
        """Japanese text should be translated to English."""
        _, mock_sp = mock_sentencepiece
        mock_sp.Decode.return_value = "The opening hours are 9am to 10pm"

        result = await translation_service.translate("営業時間は9時から22時です", "ja_to_en")
        assert result == "The opening hours are 9am to 10pm"

    @pytest.mark.asyncio
    async def test_japanese_query_passthrough_en_to_ja(self, translation_service):
        """Japanese text should be returned as-is for en_to_ja direction."""
        result = await translation_service.translate("営業時間は？", "en_to_ja")
        assert result == "営業時間は？"

    @pytest.mark.asyncio
    async def test_english_query_passthrough_ja_to_en(self, translation_service):
        """English text should be returned as-is for ja_to_en direction."""
        result = await translation_service.translate("What are the hours?", "ja_to_en")
        assert result == "What are the hours?"

    @pytest.mark.asyncio
    async def test_empty_input(self, translation_service):
        """Empty input should be returned as-is."""
        result = await translation_service.translate("", "en_to_ja")
        assert result == ""

    @pytest.mark.asyncio
    async def test_whitespace_only_input(self, translation_service):
        """Whitespace-only input should be returned as-is."""
        result = await translation_service.translate("   ", "en_to_ja")
        assert result == "   "

    @pytest.mark.asyncio
    async def test_translation_error_returns_original(self, translation_service):
        """Translation error should return the original text (graceful fallback)."""
        # Force an error in the sync translation
        translation_service._translators["en_to_ja"].translate_batch.side_effect = RuntimeError(
            "Model error"
        )

        result = await translation_service.translate("What are the hours?", "en_to_ja")
        assert result == "What are the hours?"


# =====================================================================
# Batch translation tests
# =====================================================================


class TestBatchTranslation:
    """Tests for translate_batch() method."""

    @pytest.mark.asyncio
    async def test_batch_translation(self, translation_service, mock_sentencepiece):
        """Multiple texts should be translated."""
        _, mock_sp = mock_sentencepiece
        mock_sp.Decode.return_value = "翻訳結果"

        results = await translation_service.translate_batch(["Hello", "World"], "en_to_ja")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_empty_batch(self, translation_service):
        """Empty batch should return empty list."""
        results = await translation_service.translate_batch([], "en_to_ja")
        assert results == []


# =====================================================================
# Singleton pattern tests
# =====================================================================


class TestSingleton:
    """Tests for get_translation_service() singleton."""

    def test_singleton_returns_same_instance(self):
        """get_translation_service() should return the same instance."""
        # Reset singleton
        import backend.services.translation_service as mod

        mod._translation_service = None

        svc1 = get_translation_service()
        svc2 = get_translation_service()
        assert svc1 is svc2

        # Clean up
        mod._translation_service = None

    def test_singleton_custom_model_dir(self):
        """First call with model_dir should set the directory."""
        import backend.services.translation_service as mod

        mod._translation_service = None

        svc = get_translation_service(model_dir="/custom/path")
        assert svc._model_dir == "/custom/path"

        # Clean up
        mod._translation_service = None


# =====================================================================
# Model loading error tests
# =====================================================================


class TestModelLoading:
    """Tests for model loading error handling."""

    def test_model_not_found_error(self, tmp_path, mock_ctranslate2, mock_sentencepiece):
        """Missing model directory should raise RuntimeError."""
        ct2_mod, _ = mock_ctranslate2
        sp_mod, _ = mock_sentencepiece

        with patch.dict("sys.modules", {"ctranslate2": ct2_mod, "sentencepiece": sp_mod}):
            svc = TranslationService(model_dir=str(tmp_path))
            with pytest.raises(RuntimeError, match="Translation model not found"):
                svc._load_model("en_to_ja")

    def test_missing_spm_files_error(self, tmp_path, mock_ctranslate2, mock_sentencepiece):
        """Missing .spm files should raise RuntimeError."""
        model_dir = tmp_path / "opus-mt-en-jap"
        model_dir.mkdir()
        # Create model.bin but NOT .spm files
        (model_dir / "model.bin").write_text("fake")

        ct2_mod, _ = mock_ctranslate2
        sp_mod, _ = mock_sentencepiece

        with patch.dict("sys.modules", {"ctranslate2": ct2_mod, "sentencepiece": sp_mod}):
            svc = TranslationService(model_dir=str(tmp_path))
            with pytest.raises(RuntimeError, match="SentencePiece model not found"):
                svc._load_model("en_to_ja")


# =====================================================================
# EOS token stripping test
# =====================================================================


class TestEosTokenStripping:
    """Tests for </s> EOS token removal in _translate_sync."""

    def test_eos_token_stripped(self, translation_service, mock_ctranslate2):
        """</s> token at the end should be stripped before decode."""
        ct2_mod, mock_translator = mock_ctranslate2
        hypothesis = MagicMock()
        hypothesis.hypotheses = [["hello", "world", "</s>"]]
        mock_translator.translate_batch.return_value = [hypothesis]

        # Call sync directly to check token handling
        translation_service._translate_sync("test", "en_to_ja")
        # Decode should be called with tokens WITHOUT </s>
        sp = translation_service._target_sps["en_to_ja"]
        call_args = sp.Decode.call_args[0][0]
        assert "</s>" not in call_args
