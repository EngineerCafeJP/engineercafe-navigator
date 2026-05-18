"""Support helpers for live API RAGAS evaluation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).parent / "datasets"
MULTILINGUAL_QUERIES_PATH = DATASETS_DIR / "multilingual_queries.json"
GROUND_TRUTH_PATH = (
    Path(__file__).parent.parent / "tests" / "fixtures" / "golden_datasets" / "ground_truth.json"
)
DEFAULT_REPORTS_DIR = Path(__file__).parent.parent / "tests" / "evaluation" / "reports"
DEFAULT_CHAT_INTERVAL_SECONDS = 2.2
DEFAULT_CHAT_RETRY_ATTEMPTS = 4
DEFAULT_CHAT_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_CHAT_TIMEOUT_SECONDS = 60.0
DEFAULT_PROGRESS_HEARTBEAT_SECONDS = 60.0

ALL_LANGUAGES = ("ja", "en", "zh", "ko")
CASE_SUITE_DIAGNOSTIC_29 = "diagnostic-29"
CASE_SUITE_ALPHA_127 = "alpha-127"
CASE_SUITES = (CASE_SUITE_DIAGNOSTIC_29, CASE_SUITE_ALPHA_127)
CASE_SUITE_EXPECTED_TOTALS = {
    CASE_SUITE_DIAGNOSTIC_29: 29,
    CASE_SUITE_ALPHA_127: 127,
}
LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT = "enhanced_rag|knowledge_base|knowledge_base_cached"
EVENT_SOURCE_REQUIREMENT = (
    f"google_calendar|connpass|spreadsheet|{LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT}"
)
NO_SOURCE_REQUIRED_CATEGORIES = {"emergency", "farewell", "reception"}
EVENT_LIKE_CATEGORIES = {"event", "community", "clarification"}
LIVE_CONTEXT_REQUIRED_SOURCE_LABEL = "live_api_metadata"
MISSING_LIVE_CONTEXT_SOURCE_LABEL = "missing_live_contexts"
GOLDEN_NO_SOURCE_CONTEXT_LABEL = "golden_dataset_no_live_source_required"
EMERGENCY_TERMS = (
    "緊急",
    "避難",
    "地震",
    "火事",
    "aed",
    "earthquake",
    "fire",
    "evacuate",
)
TRACKED_METRICS = (
    "context_precision",
    "answer_correctness",
    "answer_relevancy",
    "faithfulness",
)

TARGETS: Dict[str, float] = {
    "ja": 0.80,
    "en": 0.75,
    "zh": 0.75,
    "ko": 0.70,
}


def _flatten_metadata_sources(value: Any) -> set[str]:
    sources: set[str] = set()
    if isinstance(value, str):
        sources.add(value.strip().lower())
    elif isinstance(value, list):
        for item in value:
            sources.update(_flatten_metadata_sources(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            sources.add(str(key).strip().lower())
            sources.update(_flatten_metadata_sources(item))
    return {source for source in sources if source}


def _source_gate_sources(metadata: Dict[str, Any]) -> set[str]:
    return _flatten_metadata_sources(metadata.get("sources")) | _flatten_metadata_sources(
        metadata.get("searched_sources")
    )


def _required_live_sources(query: Dict[str, Any]) -> List[str]:
    category = str(query.get("category") or "").strip().lower().replace("-", "_")
    question = str(query.get("question") or "").strip().lower()
    if category in NO_SOURCE_REQUIRED_CATEGORIES or any(
        term in question for term in EMERGENCY_TERMS
    ):
        return []
    if category in EVENT_LIKE_CATEGORIES:
        return [EVENT_SOURCE_REQUIREMENT]
    return [LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT]


def _source_requirement_ok(
    metadata: Dict[str, Any], required_sources: Sequence[str]
) -> tuple[bool, List[str], List[str]]:
    actual_sources = sorted(_source_gate_sources(metadata))
    missing: List[str] = []
    for requirement in required_sources:
        alternatives = [part.strip().lower() for part in requirement.split("|") if part.strip()]
        if not any(alt in actual_sources for alt in alternatives):
            missing.append(requirement)
    return not missing, missing, actual_sources


def _dedupe_contexts(contexts: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    deduped: List[str] = []
    for context in contexts:
        text = str(context or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _contexts_from_result_items(value: Any) -> List[str]:
    contexts: List[str] = []
    if not isinstance(value, list):
        return contexts
    for item in value:
        if not isinstance(item, dict):
            continue
        for key in ("content", "text", "snippet", "summary"):
            text = str(item.get(key) or "").strip()
            if text:
                contexts.append(text)
                break
    return contexts


def _contexts_from_container(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        contexts: List[str] = []
        for item in value:
            if isinstance(item, str):
                contexts.append(item)
            elif isinstance(item, dict):
                contexts.extend(_contexts_from_container(item))
        return contexts
    if not isinstance(value, dict):
        return []

    contexts: List[str] = []
    for key in ("contexts", "retrieved_contexts", "rag_contexts"):
        contexts.extend(_contexts_from_container(value.get(key)))
    for key in ("context", "context_string", "text", "content"):
        text = str(value.get(key) or "").strip()
        if text:
            contexts.append(text)
    contexts.extend(_contexts_from_result_items(value.get("results")))
    contexts.extend(_contexts_from_result_items(value.get("chunks")))
    return contexts


def _extract_live_contexts(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Extract retrieved context evidence exposed by live /api/chat metadata."""
    candidates: list[tuple[str, Any]] = [
        ("rag_evidence", metadata.get("rag_evidence")),
        ("retrieved_contexts", metadata.get("retrieved_contexts")),
        ("evidence", metadata.get("evidence")),
        ("retrieval_evidence", metadata.get("retrieval_evidence")),
        ("evaluation_context", metadata.get("evaluation_context")),
        ("knowledge_results", metadata.get("knowledge_results")),
        ("metadata", metadata),
    ]
    for source, value in candidates:
        contexts = _dedupe_contexts(_contexts_from_container(value))
        if contexts:
            return {
                "source": source,
                "contexts": contexts,
                "context_count": len(contexts),
                "context_char_count": sum(len(context) for context in contexts),
            }
    return {
        "source": None,
        "contexts": [],
        "context_count": 0,
        "context_char_count": 0,
    }


def _live_context_check(
    *,
    required_sources: Sequence[str],
    live_contexts: Dict[str, Any],
    enabled: bool,
) -> Dict[str, Any]:
    gate_enabled = enabled and bool(required_sources)
    context_count = int(live_contexts.get("context_count", 0) or 0)
    return {
        "enabled": gate_enabled,
        "passed": (not gate_enabled) or context_count > 0,
        "required_sources": list(required_sources),
        "context_source": live_contexts.get("source"),
        "context_count": context_count,
        "context_char_count": int(live_contexts.get("context_char_count", 0) or 0),
    }


def _evaluation_contexts_for_case(
    *,
    live_contexts: Dict[str, Any],
    golden_contexts: Sequence[str],
    required_sources: Sequence[str],
) -> tuple[List[str], str]:
    contexts = [str(context) for context in live_contexts.get("contexts", []) if context]
    if contexts:
        return contexts, LIVE_CONTEXT_REQUIRED_SOURCE_LABEL
    if required_sources:
        return [], MISSING_LIVE_CONTEXT_SOURCE_LABEL
    return [str(context) for context in golden_contexts], GOLDEN_NO_SOURCE_CONTEXT_LABEL


def _summarize_live_quality_signals(cases: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    quality_cases = [case for case in cases if case.get("quality_signal_enabled")]
    scorable_cases = [
        case for case in quality_cases if (case.get("live_context_check") or {}).get("passed", True)
    ]
    missing_context_failures = [
        {
            "case_id": str(case.get("query_id") or case.get("id") or case.get("ground_truth_id")),
            "language": str(case.get("language") or "unknown"),
            "failures": [MISSING_LIVE_CONTEXT_SOURCE_LABEL],
        }
        for case in quality_cases
        if (case.get("live_context_check") or {}).get("enabled")
        and not (case.get("live_context_check") or {}).get("passed")
    ]
    try:
        from backend.evaluation.quality_signals import summarize_quality_signals
    except ImportError:
        from evaluation.quality_signals import summarize_quality_signals

    summary = summarize_quality_signals(
        scorable_cases,
        include_ground_truth_context=False,
    )
    if missing_context_failures:
        _inject_missing_context_quality_failures(summary, missing_context_failures)
    summary["enabled"] = True
    summary["source"] = "live_retrieved_context"
    return summary


def _inject_missing_context_quality_failures(
    summary: Dict[str, Any],
    missing_context_failures: Sequence[Dict[str, Any]],
) -> None:
    """Add live context gate failures to deterministic quality-signal output."""
    summary["failed_cases"] = list(summary.get("failed_cases", [])) + list(missing_context_failures)
    summary_cases = list(summary.get("cases", []))
    for failure in missing_context_failures:
        summary_cases.append(
            {
                "case_id": failure["case_id"],
                "language": failure["language"],
                "language_match": 0.0,
                "groundedness": 0.0,
                "hallucination_risk": 1.0,
                "toxicity": 0.0,
                "passed": False,
                "failures": [MISSING_LIVE_CONTEXT_SOURCE_LABEL],
            }
        )
    summary["cases"] = summary_cases

    by_language: Dict[str, int] = {}
    for failure in missing_context_failures:
        language = str(failure["language"])
        by_language[language] = by_language.get(language, 0) + 1

    overall = summary.setdefault("overall", {})
    overall["case_count"] = int(overall.get("case_count", 0) or 0) + len(missing_context_failures)
    overall["failed_case_count"] = int(overall.get("failed_case_count", 0) or 0) + len(
        missing_context_failures
    )
    overall["passed"] = False

    per_language = summary.setdefault("per_language", {})
    for language, count in by_language.items():
        language_summary = per_language.setdefault(
            language,
            {
                "case_count": 0,
                "passed": True,
                "failed_case_count": 0,
                "language_match": 0.0,
                "groundedness": 0.0,
                "hallucination_risk": 0.0,
                "toxicity": 0.0,
            },
        )
        language_summary["case_count"] = int(language_summary.get("case_count", 0) or 0) + count
        language_summary["failed_case_count"] = (
            int(language_summary.get("failed_case_count", 0) or 0) + count
        )
        language_summary["passed"] = False


def _load_multilingual_config() -> Dict[str, Any]:
    """Load the multilingual evaluation manifest."""
    with open(MULTILINGUAL_QUERIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_ground_truth_lookup() -> Dict[str, Dict[str, Any]]:
    """Load ground truth cases indexed by id."""
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {case["id"]: case for case in data.get("test_cases", [])}


def _load_ground_truth_cases() -> List[Dict[str, Any]]:
    """Load ground truth cases in file order."""
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("test_cases", []))


def _query_from_ground_truth(case: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a ground-truth entry to the live API query manifest shape."""
    category = case.get("category", "")
    return {
        "id": case["id"],
        "language": case.get("language", "ja"),
        "question": case["question"],
        "category": category,
        "ground_truth_id": case["id"],
        "metadata": {
            "difficulty": "release",
            "intent": category,
            "source": "ground_truth_127",
        },
    }


def _load_case_suite_config(case_suite: str) -> Dict[str, Any]:
    """Load query manifest for a named C/RAGAS live suite."""
    if case_suite == CASE_SUITE_DIAGNOSTIC_29:
        config = _load_multilingual_config()
        config["case_suite"] = CASE_SUITE_DIAGNOSTIC_29
        config["expected_total_cases"] = CASE_SUITE_EXPECTED_TOTALS[CASE_SUITE_DIAGNOSTIC_29]
        return config
    if case_suite == CASE_SUITE_ALPHA_127:
        cases = _load_ground_truth_cases()
        return {
            "version": "1.0.0",
            "description": "Alpha release-blocking 127-case live API RAGAS suite.",
            "case_suite": CASE_SUITE_ALPHA_127,
            "expected_total_cases": CASE_SUITE_EXPECTED_TOTALS[CASE_SUITE_ALPHA_127],
            "queries": [_query_from_ground_truth(case) for case in cases],
        }
    raise ValueError(f"Unknown case suite: {case_suite}")


def _suite_coverage(
    *,
    case_suite: str,
    selected_languages: Sequence[str],
    requested_total: int,
) -> Dict[str, Any]:
    """Return artifact metadata that prevents partial suites from looking release-complete."""
    expected_total = CASE_SUITE_EXPECTED_TOTALS[case_suite]
    all_languages_selected = tuple(selected_languages) == ALL_LANGUAGES
    release_blocking = case_suite == CASE_SUITE_ALPHA_127
    passed = requested_total == expected_total and (not release_blocking or all_languages_selected)
    return {
        "case_suite": case_suite,
        "release_blocking": release_blocking,
        "expected_total_cases": expected_total,
        "requested_total_cases": requested_total,
        "all_languages_selected": all_languages_selected,
        "passed": passed,
    }


def _language_case_counts(config: Dict[str, Any]) -> Dict[str, int]:
    """Return manifest case counts by language for coverage artifacts."""
    counts = {lang: 0 for lang in ALL_LANGUAGES}
    for query in config.get("queries", []):
        language = str(query.get("language") or "")
        if language:
            counts[language] = counts.get(language, 0) + 1
    return counts


def _evaluation_summary(
    lang_results: Dict[str, Dict[str, Any]],
    languages: Sequence[str],
) -> Dict[str, Any]:
    """Aggregate collection/evaluation counts so partial 127 runs are obvious."""
    requested_by_language: Dict[str, int] = {}
    collected_by_language: Dict[str, int] = {}
    evaluated_by_language: Dict[str, int] = {}
    collection_errors_by_language: Dict[str, int] = {}
    api_failed_by_language: Dict[str, int] = {}
    ragas_errors_by_language: Dict[str, int] = {}

    for lang in languages:
        result = lang_results.get(lang, {})
        requested_by_language[lang] = int(result.get("requested_case_count", 0) or 0)
        collected_by_language[lang] = int(result.get("collected_case_count", 0) or 0)
        evaluated_by_language[lang] = int(result.get("evaluated_case_count", 0) or 0)
        collection_errors_by_language[lang] = int(result.get("collection_error_count", 0) or 0)
        api_failed_by_language[lang] = int(result.get("api_failed_case_count", 0) or 0)
        ragas_errors_by_language[lang] = int(result.get("ragas_error_count", 0) or 0)

    requested_total = sum(requested_by_language.values())
    collected_total = sum(collected_by_language.values())
    evaluated_total = sum(evaluated_by_language.values())
    collection_error_total = sum(collection_errors_by_language.values())
    api_failed_total = sum(api_failed_by_language.values())
    ragas_error_total = sum(ragas_errors_by_language.values())

    return {
        "requested_total_cases": requested_total,
        "collected_total_cases": collected_total,
        "evaluated_total_cases": evaluated_total,
        "collection_error_total": collection_error_total,
        "api_failed_total": api_failed_total,
        "ragas_error_total": ragas_error_total,
        "requested_by_language": requested_by_language,
        "collected_by_language": collected_by_language,
        "evaluated_by_language": evaluated_by_language,
        "collection_errors_by_language": collection_errors_by_language,
        "api_failed_by_language": api_failed_by_language,
        "ragas_errors_by_language": ragas_errors_by_language,
        "collection_complete": collected_total == requested_total and collection_error_total == 0,
        "evaluation_complete": (
            evaluated_total == requested_total
            and collection_error_total == 0
            and ragas_error_total == 0
        ),
    }


def _collection_error_record(
    query: Dict[str, Any],
    *,
    error_type: str,
    message: str,
) -> Dict[str, Any]:
    """Return a reportable record for cases that never reached RAGAS evaluation."""
    return {
        "query_id": query.get("id"),
        "ground_truth_id": query.get("ground_truth_id"),
        "language": query.get("language"),
        "category": query.get("category"),
        "question": query.get("question"),
        "error_type": error_type,
        "error": message,
    }


def _emit_progress(message: str) -> None:
    """Print progress immediately so long GitHub Actions runs do not look stalled."""
    print(message, flush=True)
    logger.info(message)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _progress_heartbeat_seconds() -> float:
    raw = os.environ.get("RAGAS_PROGRESS_HEARTBEAT_SECONDS")
    if raw is None:
        return DEFAULT_PROGRESS_HEARTBEAT_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning(
            "Invalid RAGAS_PROGRESS_HEARTBEAT_SECONDS=%s; using default %.1fs",
            raw,
            DEFAULT_PROGRESS_HEARTBEAT_SECONDS,
        )
        return DEFAULT_PROGRESS_HEARTBEAT_SECONDS


class _LiveEvalProgress:
    """Write a small sidecar artifact that survives runner timeout/kill failures."""

    def __init__(
        self,
        *,
        path: Path,
        case_suite: str,
        base_url: str,
        languages: Sequence[str],
        metrics: Sequence[str],
        total_requested_cases: int,
    ) -> None:
        self.path = path
        self.started_monotonic = time.monotonic()
        started_at = _utc_now_iso()
        self.state: Dict[str, Any] = {
            "schema_version": 1,
            "mode": "live-api-progress",
            "case_suite": case_suite,
            "base_url": base_url,
            "languages": list(languages),
            "metrics": list(metrics),
            "total_requested_cases": total_requested_cases,
            "started_at": started_at,
            "updated_at": started_at,
            "elapsed_seconds": 0.0,
            "phase": "initialized",
            "message": "initialized",
            "collection": {
                "collected": 0,
                "errors": 0,
                "current_language": None,
                "current_query_id": None,
                "completed_languages": [],
            },
            "ragas": {
                "current_language": None,
                "completed_languages": [],
                "evaluated_total": 0,
                "heartbeat_count": 0,
            },
        }
        self.write()

    def update(self, *, phase: str, message: str, **fields: Any) -> None:
        self.state["phase"] = phase
        self.state["message"] = message
        self.state["updated_at"] = _utc_now_iso()
        self.state["elapsed_seconds"] = round(time.monotonic() - self.started_monotonic, 1)
        for key, value in fields.items():
            if isinstance(value, dict) and isinstance(self.state.get(key), dict):
                self.state[key].update(value)
            else:
                self.state[key] = value
        self.write()

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)


async def _ragas_progress_heartbeat(
    progress: _LiveEvalProgress,
    *,
    language: str,
    case_count: int,
    interval_seconds: float,
) -> None:
    heartbeat_count = int(progress.state.get("ragas", {}).get("heartbeat_count", 0) or 0)
    started = time.monotonic()
    while True:
        await asyncio.sleep(interval_seconds)
        heartbeat_count += 1
        elapsed = time.monotonic() - started
        message = (
            "RAGAS heartbeat: " f"language={language} cases={case_count} elapsed={elapsed:.0f}s"
        )
        _emit_progress(message)
        progress.update(
            phase="ragas_scoring",
            message=message,
            ragas={
                "current_language": language,
                "heartbeat_count": heartbeat_count,
            },
        )


def _report_file_timestamp(value: Optional[str] = None) -> str:
    """Return a filesystem-safe timestamp marker for report artifact names."""
    raw = (value or "").strip()
    if not raw:
        raw = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw)
    return safe or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _retry_after_seconds(response: httpx.Response, fallback: float) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return fallback


async def _call_chat_api(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    question: str,
    language: str,
    api_key: Optional[str] = None,
    retry_attempts: int = DEFAULT_CHAT_RETRY_ATTEMPTS,
    retry_backoff_seconds: float = DEFAULT_CHAT_RETRY_BACKOFF_SECONDS,
    timeout_seconds: float = DEFAULT_CHAT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Call the /api/chat endpoint and return the response."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    payload = {
        "query": question,
        "language": language,
        "context": {
            "include_rag_evidence": True,
        },
    }

    url = f"{base_url.rstrip('/')}/api/chat"
    attempts = max(1, retry_attempts)
    for attempt in range(attempts):
        response = await client.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
        )
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if response.status_code != 429 or attempt >= attempts - 1:
                raise exc
            fallback = retry_backoff_seconds * (2**attempt)
            sleep_for = _retry_after_seconds(response, fallback)
            logger.warning(
                "  /api/chat returned 429; retrying in %.1fs (attempt %d/%d)",
                sleep_for,
                attempt + 2,
                attempts,
            )
            await asyncio.sleep(sleep_for)

    raise RuntimeError("unreachable chat retry loop")
