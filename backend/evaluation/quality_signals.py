"""Deterministic offline RAG quality signals.

These checks are intentionally lightweight and provider-free. They complement
RAGAS by making language adherence, context grounding, hallucination risk, and
toxicity accounting available in CI without live credentials.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

SUPPORTED_LANGUAGES = ("ja", "en", "zh", "ko")

DEFAULT_THRESHOLDS = {
    "language_match_min": 0.9,
    "groundedness_min": 0.55,
    "hallucination_risk_max": 0.45,
    "toxicity_max": 0.0,
}

_LATIN_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9&+._/-]*")
_NUMBER_RE = re.compile(r"\d+(?::\d+)?")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]+")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af]+")

_TOXIC_TERMS = {
    "idiot",
    "stupid",
    "shut up",
    "kill yourself",
    "死ね",
    "バカ",
    "馬鹿",
    "멍청",
    "죽어",
    "傻瓜",
    "白痴",
}


@dataclass(frozen=True)
class QualitySignalCaseResult:
    """Offline quality signals for one RAG answer."""

    case_id: str
    language: str
    language_match: float
    groundedness: float
    hallucination_risk: float
    toxicity: float
    passed: bool
    failures: list[str] = field(default_factory=list)
    cross_lingual_context: bool = False
    reference_grounding_context: bool = False


def script_counts(text: str) -> Counter[str]:
    """Count broad writing systems used by supported response languages."""
    counts: Counter[str] = Counter()
    for char in text:
        codepoint = ord(char)
        if 0x3040 <= codepoint <= 0x30FF:
            counts["kana"] += 1
        elif 0x3400 <= codepoint <= 0x9FFF:
            counts["cjk"] += 1
        elif 0xAC00 <= codepoint <= 0xD7AF:
            counts["hangul"] += 1
        elif char.isascii() and char.isalpha():
            counts["latin"] += 1
    return counts


def language_match_score(text: str, expected_language: str) -> float:
    """Return a deterministic 0..1 score for expected response language use."""
    if expected_language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported expected_language: {expected_language}")
    if not text.strip():
        return 0.0

    counts = script_counts(text)
    lexical_total = sum(counts.values())
    if lexical_total == 0:
        return 0.0

    if expected_language == "ja":
        if counts["kana"] > 0:
            return 1.0
        if counts["cjk"] > 0 and counts["hangul"] == 0:
            return 0.5
        return 0.0

    if expected_language == "zh":
        non_latin = counts["cjk"] + counts["kana"] + counts["hangul"]
        if non_latin == 0:
            return 0.0
        if counts["cjk"] > 0 and counts["kana"] == 0 and counts["hangul"] == 0:
            return 1.0
        return counts["cjk"] / non_latin

    if expected_language == "ko":
        non_latin = counts["cjk"] + counts["kana"] + counts["hangul"]
        if non_latin == 0:
            return 0.0
        return counts["hangul"] / non_latin

    latin_words = _LATIN_WORD_RE.findall(text)
    cjk_or_hangul = counts["kana"] + counts["cjk"] + counts["hangul"]
    if len(latin_words) >= 3 and cjk_or_hangul == 0:
        return 1.0
    return counts["latin"] / lexical_total


def evidence_units(text: str) -> set[str]:
    """Extract comparable content units from English and CJK/Korean text."""
    lowered = text.lower()
    units = {token for token in _LATIN_WORD_RE.findall(lowered) if len(token.strip("&+._/-")) >= 3}
    units.update(_NUMBER_RE.findall(lowered))

    for pattern in (_CJK_RE, _HANGUL_RE):
        for match in pattern.findall(text):
            units.update(_char_ngrams(match, size=3))

    return units


def _dominant_language_hint(text: str) -> str | None:
    counts = script_counts(text)
    latin_words = _LATIN_WORD_RE.findall(text)
    non_latin = counts["kana"] + counts["cjk"] + counts["hangul"]
    if counts["hangul"] > 0 and counts["hangul"] >= counts["kana"] + counts["cjk"]:
        return "ko"
    if counts["kana"] > 0:
        return "ja"
    if len(latin_words) >= 3 and non_latin == 0:
        return "en"
    if counts["cjk"] > 0 and counts["hangul"] == 0 and counts["kana"] == 0:
        return "zh"
    return None


def _is_cross_lingual_context(expected_language: str, contexts: Iterable[str]) -> bool:
    context_text = "\n".join(str(context) for context in contexts if str(context).strip())
    if not context_text.strip() or expected_language not in SUPPORTED_LANGUAGES:
        return False

    context_language = _dominant_language_hint(context_text)
    if context_language is None:
        return False
    if expected_language == context_language:
        return False

    # Kanji-only context is ambiguous between Japanese and Chinese; do not
    # exempt Japanese answers from grounding on that weak signal alone.
    if expected_language == "ja" and context_language == "zh":
        return False
    return True


def _reference_grounding_text(case: dict[str, Any]) -> str:
    for key in ("reference_answer", "ground_truth"):
        text = str(case.get(key) or "").strip()
        if text:
            return text
    return ""


def _char_ngrams(text: str, *, size: int) -> set[str]:
    compact = "".join(char for char in text if not char.isspace())
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def groundedness_score(answer: str, contexts: Iterable[str]) -> float:
    """Estimate how much of the answer is supported by supplied evidence text."""
    answer_units = evidence_units(answer)
    if not answer_units:
        return 0.0

    context_units = evidence_units("\n".join(contexts))
    if not context_units:
        return 0.0

    return len(answer_units & context_units) / len(answer_units)


def toxicity_score(text: str) -> float:
    """Return a simple lexicon-based toxicity risk score."""
    lowered = text.lower()
    hits = sum(1 for term in _TOXIC_TERMS if term.lower() in lowered)
    return min(1.0, float(hits))


def score_case(
    case: dict[str, Any],
    *,
    thresholds: dict[str, float] | None = None,
    include_ground_truth_context: bool = True,
) -> QualitySignalCaseResult:
    """Score one evaluation case and apply offline gate thresholds."""
    gate = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    answer = str(case.get("answer") or "")
    language = str(case.get("language") or "unknown")
    case_id = str(case.get("query_id") or case.get("id") or case.get("ground_truth_id") or "")
    contexts = [str(context) for context in case.get("contexts") or []]
    cross_lingual_context = _is_cross_lingual_context(language, contexts)
    reference_text = _reference_grounding_text(case)
    reference_grounding_context = False
    grounding_contexts = list(contexts)
    if include_ground_truth_context and reference_text:
        grounding_contexts.append(reference_text)
        reference_grounding_context = True
    elif cross_lingual_context and reference_text:
        grounding_contexts.append(reference_text)
        reference_grounding_context = True

    language_match = language_match_score(answer, language)
    groundedness = groundedness_score(answer, grounding_contexts)
    hallucination_risk = 1.0 - groundedness if answer.strip() else 1.0
    toxicity = toxicity_score(answer)

    failures: list[str] = []
    if language_match < gate["language_match_min"]:
        failures.append("language_match")
    if groundedness < gate["groundedness_min"]:
        failures.append("groundedness")
    if hallucination_risk > gate["hallucination_risk_max"]:
        failures.append("hallucination_risk")
    if toxicity > gate["toxicity_max"]:
        failures.append("toxicity")

    return QualitySignalCaseResult(
        case_id=case_id,
        language=language,
        language_match=round(language_match, 4),
        groundedness=round(groundedness, 4),
        hallucination_risk=round(hallucination_risk, 4),
        toxicity=round(toxicity, 4),
        passed=not failures,
        failures=failures,
        cross_lingual_context=cross_lingual_context,
        reference_grounding_context=reference_grounding_context,
    )


def summarize_quality_signals(
    cases: Iterable[dict[str, Any]],
    *,
    thresholds: dict[str, float] | None = None,
    include_ground_truth_context: bool = True,
) -> dict[str, Any]:
    """Aggregate offline signal scores across multilingual RAG cases."""
    results = [
        score_case(
            case,
            thresholds=thresholds,
            include_ground_truth_context=include_ground_truth_context,
        )
        for case in cases
    ]
    by_language: dict[str, list[QualitySignalCaseResult]] = defaultdict(list)
    for result in results:
        by_language[result.language].append(result)

    per_language = {
        language: _summarize_results(language_results)
        for language, language_results in sorted(by_language.items())
    }
    overall = _summarize_results(results)

    return {
        "thresholds": {**DEFAULT_THRESHOLDS, **(thresholds or {})},
        "overall": overall,
        "per_language": per_language,
        "failed_cases": [
            {
                "case_id": result.case_id,
                "language": result.language,
                "failures": result.failures,
            }
            for result in results
            if not result.passed
        ],
        "cases": [_result_to_dict(result) for result in results],
    }


def _summarize_results(results: list[QualitySignalCaseResult]) -> dict[str, Any]:
    if not results:
        return {
            "case_count": 0,
            "passed": True,
            "failed_case_count": 0,
            "language_match": 0.0,
            "groundedness": 0.0,
            "hallucination_risk": 0.0,
            "toxicity": 0.0,
            "cross_lingual_context_case_count": 0,
            "reference_grounding_context_case_count": 0,
        }

    return {
        "case_count": len(results),
        "passed": all(result.passed for result in results),
        "failed_case_count": sum(1 for result in results if not result.passed),
        "language_match": _average(result.language_match for result in results),
        "groundedness": _average(result.groundedness for result in results),
        "hallucination_risk": _average(result.hallucination_risk for result in results),
        "toxicity": _average(result.toxicity for result in results),
        "cross_lingual_context_case_count": sum(
            1 for result in results if result.cross_lingual_context
        ),
        "reference_grounding_context_case_count": sum(
            1 for result in results if result.reference_grounding_context
        ),
    }


def _average(values: Iterable[float]) -> float:
    materialized = list(values)
    if not materialized:
        return 0.0
    return round(sum(materialized) / len(materialized), 4)


def _result_to_dict(result: QualitySignalCaseResult) -> dict[str, Any]:
    return {
        "case_id": result.case_id,
        "language": result.language,
        "language_match": result.language_match,
        "groundedness": result.groundedness,
        "hallucination_risk": result.hallucination_risk,
        "toxicity": result.toxicity,
        "passed": result.passed,
        "failures": result.failures,
        "cross_lingual_context": result.cross_lingual_context,
        "reference_grounding_context": result.reference_grounding_context,
    }
