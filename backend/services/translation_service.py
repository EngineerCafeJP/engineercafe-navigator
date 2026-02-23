"""
CTranslate2 + Helsinki-NLP/opus-mt translation service.

Provides bidirectional EN<->JA translation for the query translation pipeline.
Japanese knowledge base is searched with translated queries, enabling
English users to access the same knowledge.

Uses:
- CTranslate2 for fast CPU inference with int8 quantization
- sentencepiece for tokenization (source.spm / target.spm)
- Helsinki-NLP/opus-mt-en-jap for EN->JA
- Helsinki-NLP/opus-mt-ja-en for JA->EN

Runtime dependencies: ctranslate2, sentencepiece (no torch/transformers needed).
"""

import asyncio
import logging
import os
import re
from typing import Literal, Optional

logger = logging.getLogger(__name__)

TranslationDirection = Literal["en_to_ja", "ja_to_en"]

# Japanese character detection (Hiragana, Katakana, CJK)
_JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]")
# Latin-only text (ASCII letters, digits, punctuation, whitespace)
_LATIN_ONLY_RE = re.compile(r"^[a-zA-Z0-9\s\W]+$")

# Model sub-directory names (under model_dir)
_MODEL_NAMES: dict[TranslationDirection, str] = {
    "en_to_ja": "opus-mt-en-jap",
    "ja_to_en": "opus-mt-ja-en",
}

# Default model directory (relative to backend/)
_DEFAULT_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "translation",
)


class TranslationService:
    """
    Bidirectional EN<->JA translation service using CTranslate2.

    Models are loaded lazily on first use to avoid startup overhead.
    Use get_translation_service() for singleton access.

    CTranslate2 best-practice settings (from official docs):
    - compute_type="int8" for ~6-10x speedup with minimal quality loss
    - beam_size=1 for lowest latency on short queries
    - return_scores=False to skip score computation
    - inter_threads=2, intra_threads=1 for CPU parallelism
    """

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = model_dir or _DEFAULT_MODEL_DIR
        self._translators: dict[str, object] = {}
        self._source_sps: dict[str, object] = {}
        self._target_sps: dict[str, object] = {}
        logger.info("TranslationService initialized (lazy load): %s", self._model_dir)

    # ------------------------------------------------------------------
    # Model loading (lazy, following stt_agent.py pattern)
    # ------------------------------------------------------------------

    def _load_model(self, direction: TranslationDirection) -> None:
        """Load CTranslate2 translator + SentencePiece tokenizers."""
        if direction in self._translators:
            return

        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError(
                f"Missing dependency: {exc}. " "Install with: pip install ctranslate2 sentencepiece"
            ) from exc

        model_name = _MODEL_NAMES[direction]
        model_path = os.path.join(self._model_dir, model_name)

        if not os.path.isdir(model_path):
            raise RuntimeError(
                f"Translation model not found: {model_path}. "
                "Run: bash scripts/download_translation_models.sh"
            )

        source_spm_path = os.path.join(model_path, "source.spm")
        target_spm_path = os.path.join(model_path, "target.spm")

        for spm_path in (source_spm_path, target_spm_path):
            if not os.path.isfile(spm_path):
                raise RuntimeError(
                    f"SentencePiece model not found: {spm_path}. "
                    "Re-run: bash scripts/download_translation_models.sh"
                )

        self._translators[direction] = ctranslate2.Translator(
            model_path,
            compute_type="int8",
            inter_threads=2,
            intra_threads=1,
        )

        source_sp = spm.SentencePieceProcessor()
        source_sp.Load(source_spm_path)
        self._source_sps[direction] = source_sp

        target_sp = spm.SentencePieceProcessor()
        target_sp.Load(target_spm_path)
        self._target_sps[direction] = target_sp

        logger.info("Loaded translation model: %s (%s)", direction, model_path)

    # ------------------------------------------------------------------
    # Language detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_japanese(text: str) -> bool:
        """Return True if *text* contains any Japanese characters."""
        return bool(_JAPANESE_CHAR_RE.search(text))

    @staticmethod
    def is_latin_only(text: str) -> bool:
        """Return True if *text* consists entirely of Latin/ASCII chars."""
        return bool(_LATIN_ONLY_RE.match(text))

    # ------------------------------------------------------------------
    # Core translation (synchronous, CPU-bound)
    # ------------------------------------------------------------------

    def _translate_sync(self, text: str, direction: TranslationDirection) -> str:
        """Synchronous translation — runs in thread pool via translate()."""
        self._load_model(direction)

        source_sp = self._source_sps[direction]
        target_sp = self._target_sps[direction]
        translator = self._translators[direction]

        # SentencePiece encode -> list[str]
        tokens: list[str] = source_sp.Encode(text, out_type=str)

        # CTranslate2 translate (beam=1, no scores for speed)
        results = translator.translate_batch(
            [tokens],
            beam_size=1,
            return_scores=False,
        )

        output_tokens: list[str] = results[0].hypotheses[0]

        # Strip EOS token if present
        if output_tokens and output_tokens[-1] == "</s>":
            output_tokens = output_tokens[:-1]

        # SentencePiece decode -> str
        translated: str = target_sp.Decode(output_tokens)
        return translated

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def translate(
        self,
        text: str,
        direction: TranslationDirection,
    ) -> str:
        """
        Translate text between English and Japanese.

        Skips translation when text is already in the target language.

        Args:
            text: Source text.
            direction: ``"en_to_ja"`` or ``"ja_to_en"``.

        Returns:
            Translated text, or the original if already in the target language
            or if translation fails.
        """
        if not text or not text.strip():
            return text

        # Skip when already in target language
        if direction == "en_to_ja" and self.is_japanese(text):
            logger.debug("Skip EN->JA: text already contains Japanese")
            return text
        if direction == "ja_to_en" and self.is_latin_only(text):
            logger.debug("Skip JA->EN: text is already Latin-only")
            return text

        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(None, self._translate_sync, text, direction)
            logger.debug(
                "Translated [%s]: '%s' -> '%s'",
                direction,
                text[:60],
                translated[:60],
            )
            return translated
        except Exception:
            logger.warning(
                "Translation failed [%s], returning original text.",
                direction,
                exc_info=True,
            )
            return text

    async def translate_batch(
        self,
        texts: list[str],
        direction: TranslationDirection,
    ) -> list[str]:
        """Translate multiple texts. Currently sequential; batch CTranslate2 possible later."""
        if not texts:
            return []
        return [await self.translate(t, direction) for t in texts]


# ======================================================================
# Singleton access
# ======================================================================

_translation_service: Optional[TranslationService] = None


def get_translation_service(
    model_dir: Optional[str] = None,
) -> TranslationService:
    """
    Return the singleton :class:`TranslationService`.

    Args:
        model_dir: Override model directory (only effective on first call).
    """
    global _translation_service  # noqa: PLW0603
    if _translation_service is None:
        _translation_service = TranslationService(model_dir=model_dir)
    return _translation_service
