"""Tests for knowledge classifier module."""

import dataclasses

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.knowledge.classifier import (
    ClassificationResult,
    _compute_cosine_similarity,
    _parse_llm_response,
    classify_entry,
    detect_duplicates,
)


class TestClassificationResult:
    """Tests for the ClassificationResult frozen dataclass."""

    def test_frozen_dataclass(self):
        result = ClassificationResult(
            suggested_category="hours",
            confidence=0.9,
            suggested_tags=("tag1",),
            suggested_priority=60,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.suggested_category = "general"

    def test_default_values(self):
        result = ClassificationResult(
            suggested_category="general",
            confidence=0.5,
            suggested_tags=(),
            suggested_priority=50,
        )
        assert result.suggested_subcategory == ""
        assert result.reasoning == ""


class TestParseResponse:
    """Tests for _parse_llm_response."""

    def test_valid_json(self):
        raw = '{"category": "hours", "subcategory": "weekday", "tags": ["open", "close"], "priority": 60, "confidence": 0.9, "reasoning": "It is about hours"}'
        result = _parse_llm_response(raw)
        assert result.suggested_category == "hours"
        assert result.confidence == 0.9
        assert result.suggested_tags == ("open", "close")
        assert result.suggested_priority == 60

    def test_markdown_code_block(self):
        raw = '```json\n{"category": "pricing", "tags": [], "priority": 50, "confidence": 0.8, "reasoning": "ok"}\n```'
        result = _parse_llm_response(raw)
        assert result.suggested_category == "pricing"

    def test_invalid_json_fallback(self):
        result = _parse_llm_response("not json at all")
        assert result.suggested_category == "general"
        assert result.confidence == 0.0

    def test_unknown_category_falls_back(self):
        raw = '{"category": "nonexistent", "tags": [], "priority": 50, "confidence": 0.7, "reasoning": ""}'
        result = _parse_llm_response(raw)
        assert result.suggested_category == "general"

    def test_invalid_priority_falls_back(self):
        raw = (
            '{"category": "hours", "tags": [], "priority": 42, "confidence": 0.7, "reasoning": ""}'
        )
        result = _parse_llm_response(raw)
        assert result.suggested_priority == 50

    def test_confidence_clamped(self):
        raw = (
            '{"category": "hours", "tags": [], "priority": 50, "confidence": 1.5, "reasoning": ""}'
        )
        result = _parse_llm_response(raw)
        assert result.confidence == 1.0


class TestClassifyEntry:
    """Tests for classify_entry with mocked LLM."""

    @patch("backend.knowledge.classifier.get_llm_provider")
    async def test_successful_classification(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(
            return_value='{"category": "hours", "tags": ["open"], "priority": 60, "confidence": 0.95, "reasoning": "About opening hours"}'
        )
        mock_get_provider.return_value = mock_provider

        result = await classify_entry("Opening Hours", "We are open 9-21.")
        assert result.suggested_category == "hours"
        assert result.confidence == 0.95
        assert result.suggested_tags == ("open",)
        assert result.suggested_priority == 60

    @patch("backend.knowledge.classifier.get_llm_provider")
    async def test_unknown_category_fallback(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(
            return_value='{"category": "unknown_cat", "tags": [], "priority": 50, "confidence": 0.6, "reasoning": ""}'
        )
        mock_get_provider.return_value = mock_provider

        result = await classify_entry("Test", "Content")
        assert result.suggested_category == "general"

    @patch("backend.knowledge.classifier.get_llm_provider")
    async def test_invalid_json_fallback(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value="I cannot classify this.")
        mock_get_provider.return_value = mock_provider

        result = await classify_entry("Test", "Content")
        assert result.suggested_category == "general"
        assert result.confidence == 0.0

    @patch("backend.knowledge.classifier.get_llm_provider")
    async def test_empty_content(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(
            return_value='{"category": "general", "tags": [], "priority": 50, "confidence": 0.4, "reasoning": "Empty content"}'
        )
        mock_get_provider.return_value = mock_provider

        result = await classify_entry("Empty", "")
        assert result.suggested_category == "general"
        assert result.confidence == 0.4


class TestCosineSimilarity:
    """Tests for _compute_cosine_similarity."""

    def test_identical_vectors(self):
        assert _compute_cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _compute_cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_zero_vector(self):
        assert _compute_cosine_similarity([0, 0, 0], [1, 0, 0]) == 0.0


class TestDetectDuplicates:
    """Tests for detect_duplicates."""

    async def test_detects_duplicates(self):
        entries = [
            {"id": "a", "embedding": [1.0, 0.0, 0.0]},
            {"id": "b", "embedding": [1.0, 0.0, 0.0]},
        ]
        pairs = await detect_duplicates(entries, threshold=0.85)
        assert len(pairs) == 1
        assert pairs[0].entry_id_a == "a"
        assert pairs[0].entry_id_b == "b"
        assert pairs[0].similarity_score == pytest.approx(1.0)

    async def test_no_duplicates(self):
        entries = [
            {"id": "a", "embedding": [1.0, 0.0, 0.0]},
            {"id": "b", "embedding": [0.0, 1.0, 0.0]},
        ]
        pairs = await detect_duplicates(entries, threshold=0.85)
        assert len(pairs) == 0

    async def test_threshold_boundary(self):
        entries = [
            {"id": "a", "embedding": [1.0, 0.0, 0.0]},
            {"id": "b", "embedding": [0.85, 0.5268, 0.0]},
        ]
        sim = _compute_cosine_similarity(entries[0]["embedding"], entries[1]["embedding"])
        pairs = await detect_duplicates(entries, threshold=sim)
        assert len(pairs) == 1
