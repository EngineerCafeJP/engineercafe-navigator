"""Evidence, hallucination, and tRAG validation helpers for MainWorkflow."""

import logging
import re
from typing import Any, Optional

import httpx as _httpx

logger = logging.getLogger(__name__)

# tRAG: Reusable httpx client for KO/ZH translation
_trag_http_client: Optional["_httpx.AsyncClient"] = None

# tRAG: Japanese kana detection for translation validation.
# Keep this regex kana-only. Kanji acceptance is handled by the narrower
# _is_acceptable_trag_japanese helper so untranslated Chinese is not broadly
# accepted just because it contains CJK characters.
_JA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
_TRAG_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_TRAG_DISALLOWED_SCRIPT_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318fA-Za-z]")
_TRAG_JA_KANJI_TERMS = frozenset(
    {
        "営業時間",
        "営業",
        "開館",
        "閉館",
        "休館",
        "会員登録",
        "会員",
        "登録",
        "駐車場",
        "駐車",
        "駐輪場",
        "駐輪",
        "会議室",
        "貸切",
        "利用",
        "予約",
        "料金",
        "無料",
        "有料",
        "設備",
        "施設",
        "電源",
        "住所",
        "受付",
        "場所",
        "写真",
        "飲食",
        "持込",
        "喫煙",
        "禁煙",
        "建物",
        "歴史",
        "最寄",
        "相談",
        "転職",
        "勉強会",
        "交流会",
        "参加",
        "車椅子",
        "子供",
        "可能",
        "必要",
    }
)

# tRAG: Preamble pattern to strip from LLM translation output
# Require delimiter (colon/space) after keyword to avoid stripping
# valid Japanese like "以下の情報をお伝えします"
_TRAG_PREAMBLE_RE = re.compile(
    r"^(Translation:\s*|翻訳[：:]\s*|Here is[^:]*:\s*|以下[はがの]翻訳[：:]?\s*)",
    re.IGNORECASE,
)
_TRAG_REPEAT_PUNCT_RE = re.compile(r"[\s、。,.!?！？・…:：;；'\"`]+")

RAG_EVIDENCE_MAX_CONTEXTS = 5
RAG_EVIDENCE_MAX_CONTEXT_CHARS = 900
RAG_EVIDENCE_MAX_CONTEXT_STRING_CHARS = 4000

_BOOLEAN_TRUE_VALUES = {"1", "true", "yes", "on"}
_BOOLEAN_FALSE_VALUES = {"0", "false", "no", "off"}
_HALLUCINATION_CAUTION_RE = re.compile(
    r"("
    r"わかりません|分かりません|確認できません|見つかりません|"
    r"情報がありません|回答できません|申し訳|すみません|"
    r"i don't know|not sure|could not find|can't confirm|cannot confirm"
    r")",
    re.IGNORECASE,
)
_HALLUCINATION_CONCRETE_CLAIM_RE = re.compile(
    r"("
    r"https?://|"
    r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b|"
    r"\d{1,4}\s*[:：]\s*\d{2}|"
    r"\d+(?:\.\d+)?\s*"
    r"(?:円|yen|minutes?|mins?|分|hours?|時|日|階|名|人|people|%|パーセント)"
    r")",
    re.IGNORECASE,
)


def _get_trag_client() -> "_httpx.AsyncClient":
    """Return a shared httpx client for tRAG translation."""
    global _trag_http_client
    if _trag_http_client is None or _trag_http_client.is_closed:
        _trag_http_client = _httpx.AsyncClient(
            timeout=_httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        )
    return _trag_http_client


def _is_pathological_translation(text: str) -> bool:
    """Reject low-information repeated outputs from translation models."""
    compact = _TRAG_REPEAT_PUNCT_RE.sub("", text or "")
    if len(compact) < 4:
        return False

    if len(set(compact)) == 1:
        return True

    for unit_len in range(1, min(8, len(compact) // 3) + 1):
        if len(compact) < unit_len * 3 or len(compact) % unit_len:
            continue
        unit = compact[:unit_len]
        if unit * (len(compact) // unit_len) == compact:
            return True

    if len(compact) >= 8 and len(set(compact)) / len(compact) < 0.25:
        return True

    return False


def _clean_trag_translation(text: str) -> str:
    translated = _TRAG_PREAMBLE_RE.sub("", text or "").strip()
    if re.search(r"^[A-Za-z]{5,}", translated):
        logger.warning("tRAG preamble: '%s'", translated[:60])
        return ""
    if _is_pathological_translation(translated):
        logger.warning("tRAG low-information translation rejected: '%s'", translated[:60])
        return ""
    return translated


def _is_acceptable_trag_japanese(text: str) -> bool:
    """Return True when a tRAG translation looks usable as Japanese."""
    if _JA_RE.search(text or ""):
        return True

    compact = _TRAG_REPEAT_PUNCT_RE.sub("", text or "")
    if not compact or not _TRAG_CJK_RE.search(compact):
        return False
    if _TRAG_DISALLOWED_SCRIPT_RE.search(compact):
        return False
    if _is_pathological_translation(compact):
        return False

    return any(term in compact for term in _TRAG_JA_KANJI_TERMS)


def _truthy_context_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _BOOLEAN_TRUE_VALUES:
            return True
        if normalized in _BOOLEAN_FALSE_VALUES:
            return False
    return None


def _detect_hallucination_flag(answer: str, metadata: dict[str, Any]) -> bool:
    """Simple conservative unsupported-claim detector for structured logs."""
    explicit_flag = _coerce_optional_bool(metadata.get("hallucination_flag"))
    if explicit_flag is not None:
        return explicit_flag

    text = str(answer or "").strip()
    if not text or _HALLUCINATION_CAUTION_RE.search(text):
        return False

    sources = {source.strip().lower() for source in _metadata_sources(metadata)}
    sources.discard("")
    fallback_sources = bool(sources) and sources <= {"fallback"}
    explicit_fallback = (
        _coerce_optional_bool(metadata.get("rag_fallback")) is True
        or _coerce_optional_bool(metadata.get("fallback")) is True
    )

    confidence: float | None = None
    try:
        raw_confidence = metadata.get("confidence")
        if raw_confidence is not None and raw_confidence != "":
            confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = None

    if confidence is not None and confidence >= 0.95 and not explicit_fallback:
        return False

    unsupported = not sources or fallback_sources or explicit_fallback
    low_confidence = confidence is not None and confidence < 0.5
    if not unsupported and not low_confidence:
        return False

    return bool(_HALLUCINATION_CONCRETE_CLAIM_RE.search(text))


def _clip_evidence_text(value: Any, *, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _rag_evidence_result(result: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for key in ("id", "category", "subcategory", "language", "source", "entity"):
        if result.get(key) is not None:
            evidence[key] = result.get(key)
    for key in ("similarity", "score", "final_score"):
        value = result.get(key)
        if isinstance(value, (int, float)):
            evidence[key] = round(float(value), 4)
    content = _clip_evidence_text(
        result.get("content", ""),
        max_chars=RAG_EVIDENCE_MAX_CONTEXT_CHARS,
    )
    if content:
        evidence["content"] = content
    return evidence


def _build_rag_evidence_metadata(context: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Build bounded, opt-in retrieval evidence for live quality evaluation."""
    if not _truthy_context_flag(context.get("include_rag_evidence")):
        return None

    knowledge_results = context.get("knowledge_results")
    if not isinstance(knowledge_results, dict):
        return None

    context_string = str(knowledge_results.get("context_string") or "")
    raw_results = knowledge_results.get("results") or []
    results = [item for item in raw_results if isinstance(item, dict)]
    evidence_results = [
        evidence
        for evidence in (
            _rag_evidence_result(result) for result in results[:RAG_EVIDENCE_MAX_CONTEXTS]
        )
        if evidence.get("content")
    ]
    contexts = [str(item["content"]) for item in evidence_results if item.get("content")]
    if not contexts and context_string.strip():
        contexts = [
            _clip_evidence_text(
                context_string,
                max_chars=RAG_EVIDENCE_MAX_CONTEXT_STRING_CHARS,
            )
        ]

    if not contexts:
        return None

    return {
        "source": "workflow_knowledge_results",
        "query": knowledge_results.get("query"),
        "translated_query": knowledge_results.get("translated_query"),
        "category": knowledge_results.get("category"),
        "context_char_count": len(context_string),
        "contexts": contexts,
        "results": evidence_results,
    }


def _metadata_sources(metadata: dict[str, Any]) -> list[str]:
    sources = metadata.get("sources")
    if isinstance(sources, str):
        return [sources] if sources.strip() else []
    if isinstance(sources, list):
        return [str(source) for source in sources if str(source).strip()]
    return []


def _is_static_source_backed_response(metadata: dict[str, Any], sources: list[str]) -> bool:
    confidence = metadata.get("confidence")
    if isinstance(confidence, (int, float)) and float(confidence) >= 0.95:
        return True

    agent = metadata.get("agent")
    category = metadata.get("category")
    request_type = metadata.get("request_type")
    if agent == "FacilityAgent" and (category == "smoking" or request_type == "smoking"):
        return True

    event_count = metadata.get("event_count")
    try:
        parsed_event_count = int(event_count)
    except (TypeError, ValueError):
        parsed_event_count = None
    return agent == "EventAgent" and parsed_event_count == 0 and "connpass" in sources


def _build_agent_response_evidence_metadata(
    context: dict[str, Any],
    metadata: dict[str, Any],
    answer: str,
) -> Optional[dict[str, Any]]:
    """Expose bounded evidence for opt-in live eval canonical/static agent answers."""
    if not _truthy_context_flag(context.get("include_rag_evidence")):
        return None

    sources = _metadata_sources(metadata)
    if not sources or all(source == "fallback" for source in sources):
        return None
    if not _is_static_source_backed_response(metadata, sources):
        return None

    content = _clip_evidence_text(answer, max_chars=RAG_EVIDENCE_MAX_CONTEXT_STRING_CHARS)
    if not content:
        return None

    agent = metadata.get("agent")
    result: dict[str, Any] = {
        "source": "agent_response",
        "sources": sources,
        "content": content,
    }
    if agent:
        result["agent"] = agent
    if metadata.get("category"):
        result["category"] = metadata.get("category")
    if metadata.get("request_type"):
        result["request_type"] = metadata.get("request_type")

    return {
        "source": "agent_response",
        "agent": agent,
        "category": metadata.get("category"),
        "request_type": metadata.get("request_type"),
        "sources": sources,
        "context_char_count": len(content),
        "contexts": [content],
        "results": [result],
    }


def _merge_rag_evidence_metadata(
    existing: Any,
    supplemental: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Append supplemental evidence without discarding retrieved contexts."""
    if supplemental is None:
        return existing if isinstance(existing, dict) else None
    if not isinstance(existing, dict):
        return supplemental

    merged = dict(existing)
    contexts = [str(context) for context in existing.get("contexts", []) if str(context).strip()]
    for context in supplemental.get("contexts", []):
        text = str(context).strip()
        if text and text not in contexts:
            contexts.append(text)
    merged["contexts"] = contexts
    merged["context_char_count"] = sum(len(context) for context in contexts)

    results = list(existing.get("results", []) or [])
    results.extend(supplemental.get("results", []) or [])
    if results:
        merged["results"] = results

    source_labels = [
        str(source)
        for source in (existing.get("source"), supplemental.get("source"))
        if str(source or "").strip()
    ]
    deduped_sources = list(dict.fromkeys(source_labels))
    if deduped_sources:
        merged["source"] = "+".join(deduped_sources)

    return merged
