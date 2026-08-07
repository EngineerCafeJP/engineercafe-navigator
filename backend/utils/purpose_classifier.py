"""Purpose Classifier - LLM-based visitor purpose classification.

Classifies visitor responses into one of five categories:
- facility_use: wants to use the coworking space
- event_participation: here for an event
- tour: wants to tour/visit the facility
- consultation: needs tech consultation or business advice
- other: anything else
"""

import json
import logging
from typing import Literal, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

PurposeCategory = Literal[
    "facility_use",
    "event_participation",
    "tour",
    "consultation",
    "other",
]

_VALID_CATEGORIES: set[str] = {
    "facility_use",
    "event_participation",
    "tour",
    "consultation",
    "other",
}

# Fast-path keyword matching before LLM
_PURPOSE_KEYWORDS: dict[PurposeCategory, list[str]] = {
    "facility_use": [
        "作業",
        "仕事",
        "勉強",
        "コーディング",
        "プログラミング",
        "work",
        "study",
        "coding",
        "programming",
        "coworking",
        "Wi-Fi",
        "wifi",
        "電源",
        "power",
        "席",
        "seat",
        "利用",
        "使いたい",
        "コーヒー",
        "珈琲",
        "ドリンク",
        "飲みたい",
        "食べたい",
        "休憩",
        "一息",
        "座りたい",
        "coffee",
        "drink",
        "take a break",
        "want coffee",
    ],
    "event_participation": [
        "イベント",
        "勉強会",
        "セミナー",
        "ワークショップ",
        "ハッカソン",
        "もくもく会",
        "LT",
        "ミートアップ",
        "meetup",
        "event",
        "seminar",
        "workshop",
        "hackathon",
        "参加",
        "申し込み",
        "register",
        "attend",
    ],
    "tour": [
        "見学",
        "見て",
        "案内",
        "ツアー",
        "tour",
        "visit",
        "look around",
        "show me",
    ],
    "consultation": [
        "相談",
        "アドバイス",
        "メンタリング",
        "技術相談",
        "consult",
        "advice",
        "mentoring",
    ],
}

SYSTEM_PROMPT = (
    "あなたはエンジニアカフェの受付AIです。来訪者の発言から、"
    "訪問目的を以下の5つに分類してください。\n\n"
    "分類カテゴリ:\n"
    "- facility_use: コワーキングスペースの利用（作業、勉強、Wi-Fi利用など）\n"
    "- event_participation: イベントへの参加（勉強会、セミナー、ワークショップなど）\n"
    "- tour: 施設の見学・案内\n"
    "- consultation: 技術相談・ビジネス相談\n"
    "- other: 上記に該当しないもの\n\n"
    "JSON形式で回答してください:\n"
    '{"category": "<カテゴリ>", "detail": "<具体的な内容の要約>", '
    '"confidence": <0.0-1.0>}'
)


def _extract_json(text: str) -> dict:
    """Extract a JSON object from LLM response text.

    Handles cases where the JSON is wrapped in markdown code blocks
    or surrounded by extra text.

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed JSON dictionary.

    Raises:
        json.JSONDecodeError: If no valid JSON is found.
    """
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise json.JSONDecodeError("No JSON object found", text, 0)


async def classify_purpose(
    query: str,
    language: str = "ja",
) -> Tuple[PurposeCategory, Optional[str], float]:
    """Classify visitor's purpose from their response.

    Uses a two-stage approach: fast keyword matching first, then
    LLM-based classification for ambiguous inputs.

    Args:
        query: The visitor's spoken or typed response.
        language: Language code (e.g., "ja", "en").

    Returns:
        Tuple of (category, detail, confidence) where:
            - category: One of the five PurposeCategory values.
            - detail: A brief summary of the specific purpose, or None.
            - confidence: Float between 0.0 and 1.0.
    """
    # Fast-path: keyword matching
    lower_query = query.lower()
    for category, keywords in _PURPOSE_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw.lower() in lower_query)
        if matches >= 2:
            logger.info(
                "Purpose classified by keywords: %s (matches=%d)",
                category,
                matches,
            )
            return category, query, 0.9

    # LLM classification
    try:
        from backend.llm.models import ModelConfig, SupportedModel
        from backend.llm.provider import resolve_llm_provider

        provider = resolve_llm_provider()
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            temperature=0.1,
            max_tokens=200,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )

        response = await provider.generate(
            messages=[
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            config=config,
        )

        parsed = _extract_json(response)
        category = parsed.get("category", "other")
        detail = parsed.get("detail")
        confidence = float(parsed.get("confidence", 0.7))

        if category not in _VALID_CATEGORIES:
            category = "other"

        logger.info(
            "Purpose classified by LLM: %s (confidence=%.2f)",
            category,
            confidence,
        )
        return category, detail, confidence

    except Exception as e:
        logger.warning("LLM purpose classification failed: %s", e)
        # Fallback to keyword single-match or default
        for category, keywords in _PURPOSE_KEYWORDS.items():
            if any(kw.lower() in lower_query for kw in keywords):
                return category, None, 0.5
        return "other", None, 0.3
