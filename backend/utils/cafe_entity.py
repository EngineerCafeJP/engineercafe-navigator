"""Deterministic entity resolution for Engineer Cafe vs cafe&bar saino."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from backend.config.routing_constants import BUSINESS_HOURS_KEYWORDS, match_keywords

CafeEntity = Literal[
    "engineer-cafe",
    "saino",
    "ambiguous-cafe",
    "engineer_cafe",
    "saino_cafe",
    "ambiguous",
    "unknown",
]


_SPACE_RE = re.compile(r"\s+")

_SAINO_EXPLICIT_MARKERS = (
    "saino",
    "cafe&barsaino",
    "cafeandbarsaino",
    "サイノ",
    "サイノウ",
    "さいの",
    "さいのう",
    "才の",
    "才能カフェ",
    "カフェアンドバーサイノ",
    "カフェバーサイノ",
)

_SAINO_CONTEXT_MARKERS = (
    "併設",
    "閉接",
    "隣",
    "となり",
    "となりの",
    "横の",
    "隣接",
    "普通のカフェ",
    "通常のカフェ",
    "有料カフェ",
    "カフェバー",
    "バー",
    "飲食",
)

_CO_LOCATED_OR_ADJACENT_MARKERS = (
    "併設",
    "閉接",
    "隣",
    "隣り",
    "となり",
    "横",
    "よこ",
    "隣接",
    "同じ建物",
    "館内",
    "施設内",
)

_ENGINEER_CAFE_MARKERS = (
    "エンジニアカフェ",
    "エンジニア カフェ",
    "engineercafe",
    "engineer cafe",
    "engineerカフェ",
    "工程师咖啡",
    "엔지니어카페",
    "엔지니어 카페",
)

_ENGINEER_CAFE_ASR_MARKERS = (
    "エンジンやカベ",
    "エンジンヤカベ",
    "エンジンやカフェ",
)

_CAFE_MARKERS = ("カフェ", "cafe", "coffee", "喫茶", "咖啡", "카페")


def normalize_cafe_entity_text(text: str) -> str:
    """Normalize text for cafe entity checks while preserving readable Japanese."""

    normalized = unicodedata.normalize("NFKC", text or "").strip().lower()
    normalized = _SPACE_RE.sub(" ", normalized)
    return normalized


def compact_cafe_entity_text(text: str) -> str:
    """Normalize and remove whitespace/punctuation useful for substring checks."""

    normalized = normalize_cafe_entity_text(text)
    return re.sub(r"[\s・･_\-ー|/／:：,，.。!！?？'\"`]+", "", normalized)


def has_cafe_reference(text: str) -> bool:
    normalized = normalize_cafe_entity_text(text)
    compact = compact_cafe_entity_text(text)
    return any(marker in normalized or marker in compact for marker in _CAFE_MARKERS)


def is_engineer_cafe_query(text: str) -> bool:
    normalized = normalize_cafe_entity_text(text)
    compact = compact_cafe_entity_text(text)
    return any(
        marker in normalized or marker in compact for marker in _ENGINEER_CAFE_MARKERS
    ) or any(compact_cafe_entity_text(marker) in compact for marker in _ENGINEER_CAFE_ASR_MARKERS)


def is_saino_cafe_query(text: str) -> bool:
    compact = compact_cafe_entity_text(text)

    if any(compact_cafe_entity_text(marker) in compact for marker in _SAINO_EXPLICIT_MARKERS):
        return True

    if not has_cafe_reference(text):
        return False

    return any(compact_cafe_entity_text(marker) in compact for marker in _SAINO_CONTEXT_MARKERS)


def resolve_cafe_entity(text: str) -> CafeEntity | None:
    """Resolve a user utterance to a cafe entity when deterministic enough."""

    canonical = canonicalize_facility_aliases(text)
    if is_saino_cafe_query(canonical):
        return "saino"
    if is_engineer_cafe_query(canonical):
        return "engineer-cafe"
    if has_cafe_reference(canonical):
        return "ambiguous-cafe"
    return None


def normalize_cafe_query(query: str) -> str:
    return normalize_cafe_entity_text(canonicalize_facility_aliases(query))


def compact_query(query: str) -> str:
    return compact_cafe_entity_text(canonicalize_facility_aliases(query))


def has_cafe_or_bar_token(query: str) -> bool:
    normalized = normalize_cafe_query(query)
    compact = compact_query(query)
    return has_cafe_reference(normalized) or any(
        marker in normalized or marker in compact for marker in ("バー", "bar")
    )


def has_business_hours_signal(query: str) -> bool:
    normalized = normalize_cafe_query(query)
    return match_keywords(normalized, BUSINESS_HOURS_KEYWORDS) or any(
        marker in normalized for marker in ("営業", "開店", "閉店")
    )


def is_explicit_engineer_cafe_query(query: str) -> bool:
    return is_engineer_cafe_query(canonicalize_facility_aliases(query))


def is_saino_reference(query: str) -> bool:
    return is_saino_cafe_query(canonicalize_facility_aliases(query))


def is_colocated_or_adjacent_saino_reference(query: str) -> bool:
    if not has_cafe_or_bar_token(query):
        return False
    compact = compact_query(query)
    return any(
        compact_cafe_entity_text(marker) in compact for marker in _CO_LOCATED_OR_ADJACENT_MARKERS
    )


def is_ambiguous_cafe_hours_query(query: str) -> bool:
    if not has_cafe_or_bar_token(query):
        return False
    if is_saino_reference(query) or is_explicit_engineer_cafe_query(query):
        return False
    return has_business_hours_signal(query)


def _public_entity_name(entity: str | None) -> str:
    if entity == "engineer-cafe":
        return "engineer_cafe"
    if entity == "saino":
        return "saino_cafe"
    if entity == "ambiguous-cafe":
        return "ambiguous"
    return entity or "unknown"


def cafe_entity_metadata(
    text: str | None = None,
    *,
    entity: CafeEntity | None = None,
    status: Literal["resolved", "needs_clarification"] | None = None,
    source: str = "deterministic_cafe_entity",
    request_type: str | None = None,
    context_used: bool = False,
    confidence: float | None = None,
) -> dict[str, Any]:
    resolved = entity or (resolve_cafe_entity(text or "") if text is not None else None)
    if resolved is None:
        return {}
    public_entity = _public_entity_name(str(resolved))
    resolved_status = status or (
        "needs_clarification" if public_entity == "ambiguous" else "resolved"
    )
    metadata: dict[str, Any] = {
        "cafe_entity": resolved,
        "entity": public_entity,
        "status": resolved_status,
        "source": source,
        "context_used": context_used,
        "confidence": (
            confidence
            if confidence is not None
            else (0.95 if resolved_status == "resolved" else 0.7)
        ),
        "entity_resolution": source,
    }
    if request_type:
        metadata["request_type"] = request_type
    if public_entity == "ambiguous":
        metadata["candidates"] = ["engineer_cafe", "saino_cafe"]
    return metadata


def context_mentions_engineer_cafe_hours(memory_context: Any) -> bool:
    """Detect recent same-session Engineer Cafe hours context from memory payloads."""
    if not isinstance(memory_context, dict):
        return False

    messages = memory_context.get("recent_messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = str(message.get("content") or "")
            if is_engineer_cafe_query(content) and has_business_hours_signal(content):
                return True

    context_string = memory_context.get("context_string")
    if isinstance(context_string, str):
        return is_engineer_cafe_query(context_string) and has_business_hours_signal(context_string)

    return False


def inherited_request_type(memory_context: Any) -> str | None:
    if not isinstance(memory_context, dict):
        return None
    value = memory_context.get("inherited_request_type")
    return value if isinstance(value, str) and value else None


def legacy_cafe_entity_metadata(text: str) -> dict[str, Any]:
    entity = resolve_cafe_entity(text)
    if entity is None:
        return {}
    return cafe_entity_metadata(text)


def canonicalize_facility_aliases(text: str) -> str:
    """Canonicalize known facility aliases for memory/dedup evidence text."""

    if not text:
        return text

    canonical = text
    for marker in _ENGINEER_CAFE_ASR_MARKERS:
        canonical = re.sub(re.escape(marker), "エンジニアカフェ", canonical, flags=re.IGNORECASE)
    canonical = re.sub(r"engineer\s*cafe", "Engineer Cafe", canonical, flags=re.IGNORECASE)
    canonical = re.sub(r"エンジニア\s*カフェ", "エンジニアカフェ", canonical)

    canonical = re.sub(r"cafe\s*&\s*bar\s*saino", "cafe&bar saino", canonical, flags=re.I)
    canonical = re.sub(r"cafe\s*and\s*bar\s*saino", "cafe&bar saino", canonical, flags=re.I)
    canonical = re.sub(r"coffee\s+say\s+no", "saino cafe", canonical, flags=re.I)
    canonical = re.sub(r"say\s+no", "saino", canonical, flags=re.I)
    for marker in ("サイノウ", "セイノ", "さいのう", "さいの", "才能カフェ"):
        canonical = canonical.replace(marker, "サイノカフェ")
    canonical = re.sub(r"サイノ(?!カフェ)", "サイノカフェ", canonical)
    canonical = canonical.replace("才能", "saino")
    canonical = canonical.replace("閉接のカフェ", "併設のカフェ")
    return canonical
