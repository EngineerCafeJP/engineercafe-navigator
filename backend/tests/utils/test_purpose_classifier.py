"""Tests for the purpose classifier module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.utils.purpose_classifier import (
    _extract_json,
    classify_purpose,
)

# ===================================================================
# Keyword-based classification tests
# ===================================================================


class TestKeywordClassification:
    """Tests for fast-path keyword matching (>= 2 keyword hits)."""

    @pytest.mark.asyncio
    async def test_keyword_facility_use(self) -> None:
        """Two facility keywords ('作業' and 'Wi-Fi') should match facility_use."""
        category, detail, confidence = await classify_purpose(
            "作業したいんですが、Wi-Fiは使えますか？"
        )
        assert category == "facility_use"
        assert confidence == 0.9
        assert detail is not None

    @pytest.mark.asyncio
    async def test_keyword_event_participation(self) -> None:
        """Two event keywords ('イベント' and '参加') should match."""
        category, detail, confidence = await classify_purpose("今日のイベントに参加したいです")
        assert category == "event_participation"
        assert confidence == 0.9

    @pytest.mark.asyncio
    async def test_keyword_tour(self) -> None:
        """Two tour keywords ('見学' and '案内') should match."""
        category, detail, confidence = await classify_purpose(
            "施設の見学をしたいのですが、案内してもらえますか？"
        )
        assert category == "tour"
        assert confidence == 0.9

    @pytest.mark.asyncio
    async def test_keyword_consultation(self) -> None:
        """Two consultation keywords ('技術相談' and '相談') should match."""
        category, detail, confidence = await classify_purpose(
            "技術相談がしたいです。プログラミングの相談です。"
        )
        # '技術相談' contains '相談', plus '相談' appears again
        assert category == "consultation"
        assert confidence == 0.9

    @pytest.mark.asyncio
    async def test_keyword_english_facility(self) -> None:
        """English keywords should also trigger fast-path."""
        category, detail, confidence = await classify_purpose("I want to study and use the wifi")
        assert category == "facility_use"
        assert confidence == 0.9


# ===================================================================
# LLM fallback classification tests
# ===================================================================


class TestLLMClassification:
    """Tests for LLM-based classification when keywords are insufficient."""

    @pytest.mark.asyncio
    async def test_llm_classification(self) -> None:
        """LLM should classify ambiguous queries that lack keyword matches."""
        mock_response = json.dumps(
            {
                "category": "facility_use",
                "detail": "ノートPCで開発作業",
                "confidence": 0.85,
            }
        )

        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        with (
            patch(
                "backend.llm.openrouter.OpenRouterProvider",
                return_value=mock_provider,
            ),
        ):
            category, detail, confidence = await classify_purpose(
                "ちょっとパソコンで開発させてもらえますか"
            )

        assert category == "facility_use"
        assert detail == "ノートPCで開発作業"
        assert confidence == pytest.approx(0.85)
        mock_provider.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_classification_with_markdown_json(self) -> None:
        """LLM response wrapped in markdown code block should still parse."""
        mock_response = (
            '```json\n{"category": "tour", "detail": "見学希望", "confidence": 0.9}\n```'
        )

        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        with patch(
            "backend.llm.openrouter.OpenRouterProvider",
            return_value=mock_provider,
        ):
            category, detail, confidence = await classify_purpose("ここはどんな場所ですか？")

        assert category == "tour"
        assert confidence == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_llm_invalid_category_falls_back_to_other(self) -> None:
        """An invalid category from LLM should be coerced to 'other'."""
        mock_response = json.dumps(
            {
                "category": "invalid_category",
                "detail": "不明",
                "confidence": 0.6,
            }
        )

        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)

        with patch(
            "backend.llm.openrouter.OpenRouterProvider",
            return_value=mock_provider,
        ):
            category, _, _ = await classify_purpose("何か面白いことない？")

        assert category == "other"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_with_single_keyword(self) -> None:
        """When LLM fails and one keyword matches, use that category at 0.5."""
        with patch(
            "backend.llm.openrouter.OpenRouterProvider",
            side_effect=ValueError("No API key"),
        ):
            category, detail, confidence = await classify_purpose("イベントについて")

        assert category == "event_participation"
        assert detail is None
        assert confidence == 0.5

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_no_keywords(self) -> None:
        """When LLM fails and no keywords match, return 'other' at 0.3."""
        with patch(
            "backend.llm.openrouter.OpenRouterProvider",
            side_effect=ValueError("No API key"),
        ):
            category, detail, confidence = await classify_purpose("こんにちは")

        assert category == "other"
        assert detail is None
        assert confidence == pytest.approx(0.3)


# ===================================================================
# JSON extraction helper tests
# ===================================================================


class TestExtractJson:
    """Tests for the _extract_json helper."""

    def test_plain_json(self) -> None:
        result = _extract_json('{"category": "tour"}')
        assert result == {"category": "tour"}

    def test_json_with_surrounding_text(self) -> None:
        result = _extract_json('Here is the result: {"category": "tour"} done')
        assert result == {"category": "tour"}

    def test_no_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _extract_json("no json here")
