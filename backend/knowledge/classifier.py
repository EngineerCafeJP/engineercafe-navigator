"""LLM-based knowledge entry classifier for Engineer Cafe Navigator."""

import json
import logging
import math
from dataclasses import dataclass

import numpy as np
from langchain_core.messages import HumanMessage

from backend.llm import MODEL_CONFIGS, get_llm_provider

logger = logging.getLogger(__name__)

# Input validation limits
MAX_TITLE_LENGTH = 500
MAX_CONTENT_LENGTH = 10000
MAX_TAGS_COUNT = 10

VALID_CATEGORIES = (
    "hours",
    "pricing",
    "facility-info",
    "location",
    "event",
    "general",
    "consultation",
    "community",
    "staff",
    "history",
    "rules",
    "services",
    "faq",
    "news",
    "technical",
)

VALID_PRIORITIES = (30, 50, 60, 90)

CLASSIFICATION_SYSTEM_PROMPT = """You are a knowledge base classifier for Engineer Cafe Navigator.
Given a knowledge entry's title and content, classify it into one of these categories:
{categories}

Respond ONLY with valid JSON in this exact format:
{{"category": "<category>", "subcategory": "", "tags": ["tag1", "tag2"], "priority": 60, "confidence": 0.9, "reasoning": "Brief reason"}}

Priority values: 30 (low), 50 (normal), 60 (important), 90 (critical)
Confidence: 0.0 to 1.0"""


@dataclass(frozen=True)
class ClassificationResult:
    """Immutable result of a knowledge entry classification."""

    suggested_category: str
    confidence: float
    suggested_tags: tuple[str, ...]
    suggested_priority: int
    suggested_subcategory: str = ""
    reasoning: str = ""


@dataclass(frozen=True)
class DuplicatePair:
    """Immutable pair of potentially duplicate entries."""

    entry_id_a: str
    entry_id_b: str
    similarity_score: float


def _build_classification_prompt(title: str, content: str, categories: tuple[str, ...]) -> str:
    """Build the system prompt for classification.

    Input is JSON-encoded to prevent prompt injection.

    Args:
        title: Knowledge entry title.
        content: Knowledge entry content.
        categories: Valid categories tuple.

    Returns:
        Formatted prompt string for the LLM.
    """
    categories_str = ", ".join(categories)
    system = CLASSIFICATION_SYSTEM_PROMPT.format(categories=categories_str)
    title_safe = json.dumps(title, ensure_ascii=False)
    content_safe = json.dumps(content, ensure_ascii=False)
    user_text = f"Title: {title_safe}\n\nContent: {content_safe}"
    return f"{system}\n\n{user_text}"


def _parse_llm_response(response_text: str) -> ClassificationResult:
    """Parse and validate LLM JSON response into a ClassificationResult.

    Handles markdown code blocks (```json ... ```) and validates all fields
    against known constants, falling back to safe defaults.

    Args:
        response_text: Raw LLM response text.

    Returns:
        Validated ClassificationResult.
    """
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        data = json.loads(cleaned)

        category = data.get("category", "general")
        if category not in VALID_CATEGORIES:
            category = "general"

        priority = data.get("priority", 50)
        if priority not in VALID_PRIORITIES:
            priority = 50

        raw_confidence = float(data.get("confidence", 0.5))
        if math.isnan(raw_confidence) or math.isinf(raw_confidence):
            raw_confidence = 0.5
        confidence = max(0.0, min(1.0, raw_confidence))

        raw_tags = data.get("tags", ())
        if isinstance(raw_tags, list):
            raw_tags = raw_tags[:MAX_TAGS_COUNT]
        tags = tuple(str(t) for t in raw_tags)
        subcategory = data.get("subcategory", "")
        reasoning = data.get("reasoning", "")

        return ClassificationResult(
            suggested_category=category,
            confidence=confidence,
            suggested_tags=tags,
            suggested_priority=priority,
            suggested_subcategory=subcategory,
            reasoning=reasoning,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse LLM classification response: %s", exc)
        return ClassificationResult(
            suggested_category="general",
            confidence=0.0,
            suggested_tags=(),
            suggested_priority=50,
            reasoning="Parse error",
        )


def _make_fallback(reasoning: str = "Classification failed") -> ClassificationResult:
    """Return a safe fallback ClassificationResult."""
    return ClassificationResult(
        suggested_category="general",
        confidence=0.0,
        suggested_tags=(),
        suggested_priority=50,
        reasoning=reasoning,
    )


async def classify_entry(
    title: str,
    content: str,
    existing_categories: tuple[str, ...] = VALID_CATEGORIES,
) -> ClassificationResult:
    """Classify a knowledge entry using the LLM.

    Args:
        title: Knowledge entry title.
        content: Knowledge entry content.
        existing_categories: Allowed categories for classification.

    Returns:
        ClassificationResult with suggested category, tags, and priority.
    """
    if not isinstance(title, str) or not isinstance(content, str):
        logger.warning("Invalid input types for classify_entry")
        return _make_fallback("Invalid input types")

    if len(title) > MAX_TITLE_LENGTH:
        title = title[:MAX_TITLE_LENGTH]
        logger.info("Title truncated to %d chars", MAX_TITLE_LENGTH)
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH]
        logger.info("Content truncated to %d chars", MAX_CONTENT_LENGTH)

    try:
        prompt = _build_classification_prompt(title, content, existing_categories)
        provider = get_llm_provider()
        response = await provider.generate(
            messages=[HumanMessage(content=prompt)],
            config=MODEL_CONFIGS["router"],
        )
        return _parse_llm_response(response)
    except Exception as exc:
        logger.error("Classification failed: %s", exc)
        return _make_fallback("Classification failed")


def _compute_cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Cosine similarity in range [0.0, 1.0]. Returns 0.0 for zero vectors.
    """
    a = np.asarray(vec_a, dtype=np.float64)
    b = np.asarray(vec_b, dtype=np.float64)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def detect_duplicates(entries: list, threshold: float = 0.85) -> list[DuplicatePair]:
    """Detect duplicate entries by comparing embedding similarity.

    Args:
        entries: List of dicts with keys "id" and "embedding" (list[float]).
        threshold: Minimum cosine similarity to consider a duplicate pair.

    Returns:
        List of DuplicatePair for pairs at or above the threshold.
    """
    duplicates: list[DuplicatePair] = []
    count = len(entries)
    for i in range(count):
        for j in range(i + 1, count):
            emb_a = entries[i].get("embedding", [])
            emb_b = entries[j].get("embedding", [])
            if not emb_a or not emb_b:
                continue
            sim = _compute_cosine_similarity(emb_a, emb_b)
            if sim >= threshold:
                duplicates = [
                    *duplicates,
                    DuplicatePair(
                        entry_id_a=entries[i]["id"],
                        entry_id_b=entries[j]["id"],
                        similarity_score=sim,
                    ),
                ]
    return duplicates
