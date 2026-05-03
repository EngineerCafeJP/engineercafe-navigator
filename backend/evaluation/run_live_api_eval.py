"""
Live API RAGAS evaluation runner.

Sends queries to the running backend at ``/api/chat`` and evaluates
the responses against ground truth using the RAGAS pipeline.

Usage:
    python -m evaluation.run_live_api_eval --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
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

ALL_LANGUAGES = ("ja", "en", "zh", "ko")
CASE_SUITE_DIAGNOSTIC_29 = "diagnostic-29"
CASE_SUITE_ALPHA_127 = "alpha-127"
CASE_SUITES = (CASE_SUITE_DIAGNOSTIC_29, CASE_SUITE_ALPHA_127)
CASE_SUITE_EXPECTED_TOTALS = {
    CASE_SUITE_DIAGNOSTIC_29: 29,
    CASE_SUITE_ALPHA_127: 127,
}
LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT = "enhanced_rag|knowledge_base|knowledge_base_cached"
EVENT_SOURCE_REQUIREMENT = f"google_calendar|connpass|{LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT}"
NO_SOURCE_REQUIRED_CATEGORIES = {"emergency", "farewell", "reception"}
EVENT_LIKE_CATEGORIES = {"event", "community", "clarification"}
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
    "ja": 0.85,
    "en": 0.75,
    "zh": 0.65,
    "ko": 0.65,
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
    actual_sources = sorted(_flatten_metadata_sources(metadata.get("sources")))
    missing: List[str] = []
    for requirement in required_sources:
        alternatives = [part.strip().lower() for part in requirement.split("|") if part.strip()]
        if not any(alt in actual_sources for alt in alternatives):
            missing.append(requirement)
    return not missing, missing, actual_sources


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
) -> Dict[str, Any]:
    """Call the /api/chat endpoint and return the response."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    payload = {
        "query": question,
        "language": language,
    }

    url = f"{base_url.rstrip('/')}/api/chat"
    attempts = max(1, retry_attempts)
    for attempt in range(attempts):
        response = await client.post(url, json=payload, headers=headers, timeout=60.0)
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


async def run_live_api_evaluation(
    *,
    base_url: str = "http://localhost:8000",
    api_key: Optional[str] = None,
    languages: Optional[Sequence[str]] = None,
    output_dir: Optional[Path] = None,
    check_live_sources: bool = True,
    metrics: Optional[Sequence[str]] = None,
    case_suite: str = CASE_SUITE_DIAGNOSTIC_29,
    report_timestamp: Optional[str] = None,
    chat_interval_seconds: float = 0.0,
    chat_retry_attempts: int = DEFAULT_CHAT_RETRY_ATTEMPTS,
    chat_retry_backoff_seconds: float = DEFAULT_CHAT_RETRY_BACKOFF_SECONDS,
) -> Dict[str, Any]:
    """Run RAGAS evaluation against the live API.

    Args:
        base_url: Backend API base URL.
        api_key: Optional API key for authentication.
        languages: Languages to evaluate (default: all).
        output_dir: Directory for report output.
        report_timestamp: Optional stable artifact filename marker.
        chat_interval_seconds: Minimum seconds between live /api/chat request starts.
        chat_retry_attempts: Total /api/chat attempts for retryable 429 responses.
        chat_retry_backoff_seconds: Base exponential backoff for 429 responses.

    Returns:
        Evaluation result dictionary with per-language metrics.
    """
    config = _load_case_suite_config(case_suite)
    gt_lookup = _load_ground_truth_lookup()
    selected_languages = list(languages or ALL_LANGUAGES)
    selected_metrics = tuple(metrics or TRACKED_METRICS)
    manifest_language_counts = _language_case_counts(config)

    per_language_results: Dict[str, Dict[str, Any]] = {}
    all_eval_cases: Dict[str, List[Dict[str, Any]]] = {}
    requested_case_counts: Dict[str, int] = {}
    collection_errors: Dict[str, List[Dict[str, Any]]] = {}
    last_chat_started: Optional[float] = None

    # Phase 1: Collect live API responses
    async with httpx.AsyncClient() as client:
        for lang in selected_languages:
            queries = [q for q in config["queries"] if q["language"] == lang]
            lang_cases: List[Dict[str, Any]] = []
            lang_collection_errors: List[Dict[str, Any]] = []
            requested_case_counts[lang] = len(queries)

            logger.info("Evaluating %d queries for language: %s", len(queries), lang)

            for query in queries:
                gt_id = query["ground_truth_id"]
                gt_case = gt_lookup.get(gt_id)
                if gt_case is None:
                    logger.warning(
                        "Skipping %s: ground truth %s not found",
                        query["id"],
                        gt_id,
                    )
                    lang_collection_errors.append(
                        _collection_error_record(
                            query,
                            error_type="missing_ground_truth",
                            message=f"ground truth {gt_id} not found",
                        )
                    )
                    continue

                try:
                    if chat_interval_seconds > 0 and last_chat_started is not None:
                        since_last_start = time.monotonic() - last_chat_started
                        sleep_for = chat_interval_seconds - since_last_start
                        if sleep_for > 0:
                            await asyncio.sleep(sleep_for)
                    start = time.monotonic()
                    last_chat_started = start
                    api_response = await _call_chat_api(
                        client,
                        base_url=base_url,
                        question=query["question"],
                        language=lang,
                        api_key=api_key,
                        retry_attempts=chat_retry_attempts,
                        retry_backoff_seconds=chat_retry_backoff_seconds,
                    )
                    elapsed = time.monotonic() - start

                    answer = api_response.get("answer", "")
                    metadata = api_response.get("metadata", {})
                    metadata_dict = metadata if isinstance(metadata, dict) else {}
                    required_sources = _required_live_sources(query)
                    sources_ok, missing_sources, actual_sources = _source_requirement_ok(
                        metadata_dict, required_sources
                    )

                    lang_cases.append(
                        {
                            "query_id": query["id"],
                            "ground_truth_id": gt_id,
                            "question": query["question"],
                            "answer": answer,
                            "contexts": gt_case.get("contexts", []),
                            "ground_truth": gt_case.get("ground_truth", ""),
                            "language": lang,
                            "category": query["category"],
                            "metadata": query["metadata"],
                            "evaluation_context_source": "golden_dataset",
                            "live_source_check": {
                                "enabled": check_live_sources,
                                "passed": sources_ok,
                                "required_sources": required_sources,
                                "actual_sources": actual_sources,
                                "missing_sources": missing_sources,
                            },
                            "api_metadata": {
                                "agent": metadata_dict.get("agent"),
                                "category": metadata_dict.get("category"),
                                "route": metadata_dict.get("route"),
                                "sources": metadata_dict.get("sources"),
                                "elapsed_seconds": round(elapsed, 2),
                            },
                        }
                    )
                    logger.info(
                        "  [%s] %s -> agent=%s (%.1fs)",
                        query["id"],
                        query["question"][:40],
                        metadata_dict.get("agent", "?"),
                        elapsed,
                    )
                except Exception as exc:
                    logger.error("  [%s] API call failed: %s", query["id"], exc)
                    lang_collection_errors.append(
                        _collection_error_record(
                            query,
                            error_type="api_call_failed",
                            message=str(exc),
                        )
                    )

            all_eval_cases[lang] = lang_cases
            collection_errors[lang] = lang_collection_errors

    # Phase 2: Run RAGAS evaluation
    try:
        from evaluation.ragas_pipeline import RagasEvaluator
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from evaluation.ragas_pipeline import RagasEvaluator

    for lang in selected_languages:
        cases = all_eval_cases.get(lang, [])
        requested_count = requested_case_counts.get(lang, 0)
        lang_collection_errors = collection_errors.get(lang, [])
        api_failed_count = len(
            [
                error
                for error in lang_collection_errors
                if error.get("error_type") == "api_call_failed"
            ]
        )
        if not cases:
            per_language_results[lang] = {
                "language": lang,
                "error": "no evaluable cases",
                "requested_case_count": requested_count,
                "collected_case_count": 0,
                "evaluated_case_count": 0,
                "skipped_case_count": requested_count,
                "api_failed_case_count": api_failed_count,
                "collection_error_count": len(lang_collection_errors),
                "ragas_error_count": 0,
                "collection_errors": lang_collection_errors,
                "metrics": {},
                "results": [],
            }
            continue

        evaluator = RagasEvaluator(
            metrics=selected_metrics,
            max_cases=len(cases),
        )

        if not evaluator.is_available:
            logger.warning("RAGAS not available, returning API responses only")
            per_language_results[lang] = {
                "language": lang,
                "error": "ragas not installed",
                "requested_case_count": requested_count,
                "collected_case_count": len(cases),
                "evaluated_case_count": 0,
                "skipped_case_count": requested_count,
                "api_failed_case_count": api_failed_count,
                "collection_error_count": len(lang_collection_errors),
                "ragas_error_count": 0,
                "collection_errors": lang_collection_errors,
                "metrics": {},
                "results": [
                    {
                        "query_id": c["query_id"],
                        "question": c["question"],
                        "answer": c["answer"][:200],
                        "api_metadata": c["api_metadata"],
                        "evaluation_context_source": c["evaluation_context_source"],
                        "live_source_check": c["live_source_check"],
                    }
                    for c in cases
                ],
            }
            continue

        logger.info("Running RAGAS evaluation for %s (%d cases)...", lang, len(cases))
        report = await evaluator.evaluate_batch(cases)
        report_error_count = len(
            [error for error in getattr(report, "errors", []) if str(error).strip()]
        )
        per_case_error_count = 0

        per_case_results: List[Dict[str, Any]] = []
        for case, result in zip(cases, report.results):
            if result.error:
                per_case_error_count += 1
            per_case_results.append(
                {
                    "query_id": case["query_id"],
                    "ground_truth_id": case["ground_truth_id"],
                    "category": case["category"],
                    "question": result.question,
                    "answer": case["answer"][:200],
                    "answer_correctness": result.answer_correctness,
                    "answer_relevancy": result.answer_relevancy,
                    "faithfulness": result.faithfulness,
                    "context_precision": result.context_precision,
                    "error": result.error,
                    "api_metadata": case["api_metadata"],
                    "evaluation_context_source": case["evaluation_context_source"],
                    "live_source_check": case["live_source_check"],
                }
            )
        ragas_error_count = max(report_error_count, per_case_error_count)

        per_language_results[lang] = {
            "language": lang,
            "requested_case_count": requested_count,
            "collected_case_count": len(cases),
            "evaluated_case_count": report.evaluated_cases,
            "skipped_case_count": report.skipped_cases + len(lang_collection_errors),
            "api_failed_case_count": api_failed_count,
            "collection_error_count": len(lang_collection_errors),
            "ragas_error_count": ragas_error_count,
            "collection_errors": lang_collection_errors,
            "metrics": report.metrics,
            "errors": report.errors,
            "results": per_case_results,
        }

    # Phase 3: Compare with targets
    requested_total = sum(
        int(result.get("requested_case_count", 0) or 0) for result in per_language_results.values()
    )
    suite_coverage = _suite_coverage(
        case_suite=case_suite,
        selected_languages=selected_languages,
        requested_total=requested_total,
    )
    evaluation_summary = _evaluation_summary(per_language_results, selected_languages)
    comparison = _compare_targets(
        per_language_results, selected_languages, check_live_sources=check_live_sources
    )
    comparison["suite_coverage"] = suite_coverage
    comparison["evaluation_summary"] = evaluation_summary
    comparison["alpha_release_gate_met"] = (
        comparison["all_targets_met"]
        and suite_coverage["release_blocking"]
        and suite_coverage["passed"]
    )
    report_text = _format_report(
        per_language_results,
        comparison,
        selected_languages,
        check_live_sources=check_live_sources,
        case_suite=case_suite,
    )
    report_file_ts = _report_file_timestamp(report_timestamp)
    json_report_filename = f"live_api_eval_{report_file_ts}.json"
    text_report_filename = f"live_api_eval_{report_file_ts}.txt"

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "live-api",
        "case_suite": case_suite,
        "suite_coverage": suite_coverage,
        "evaluation_summary": evaluation_summary,
        "base_url": base_url,
        "languages": selected_languages,
        "metrics": list(selected_metrics),
        "ragas_context_source": "golden_dataset",
        "live_source_gate_enabled": check_live_sources,
        "artifact_metadata": {
            "report_timestamp": report_file_ts,
            "json_report_filename": json_report_filename,
            "text_report_filename": text_report_filename,
            "expected_total_cases": config.get("expected_total_cases"),
            "manifest_language_counts": manifest_language_counts,
            "selected_language_counts": {
                lang: manifest_language_counts.get(lang, 0) for lang in selected_languages
            },
            "chat_interval_seconds": chat_interval_seconds,
            "chat_retry_attempts": chat_retry_attempts,
            "chat_retry_backoff_seconds": chat_retry_backoff_seconds,
        },
        "per_language": per_language_results,
        "comparison": comparison,
        "report": report_text,
    }

    # Save reports
    dest_dir = output_dir or DEFAULT_REPORTS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    json_path = dest_dir / json_report_filename
    txt_path = dest_dir / text_report_filename
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(report_text, encoding="utf-8")

    logger.info("Wrote live API evaluation report to %s", json_path)
    print(report_text)

    return result


def _compare_targets(
    lang_results: Dict[str, Dict[str, Any]],
    languages: Sequence[str],
    *,
    check_live_sources: bool,
) -> Dict[str, Any]:
    """Compare per-language answer_correctness against targets."""
    failed: List[Dict[str, Any]] = []
    failed_source_cases: List[Dict[str, Any]] = []
    per_language: Dict[str, Any] = {}

    for lang in languages:
        result = lang_results.get(lang, {})
        metrics = result.get("metrics", {})
        target = TARGETS.get(lang, 0.0)
        actual = metrics.get("answer_correctness")
        source_failures = []
        if check_live_sources:
            for case_result in result.get("results", []):
                source_check = case_result.get("live_source_check") or {}
                if source_check.get("enabled") and not source_check.get("passed"):
                    source_failures.append(
                        {
                            "query_id": case_result.get("query_id"),
                            "language": lang,
                            "missing_sources": source_check.get("missing_sources", []),
                            "actual_sources": source_check.get("actual_sources", []),
                        }
                    )

        answer_target_passed = isinstance(actual, (int, float)) and actual >= target
        requested_count = int(result.get("requested_case_count", 0) or 0)
        collected_count = int(result.get("collected_case_count", 0) or 0)
        evaluated_count = int(result.get("evaluated_case_count", 0) or 0)
        collection_error_count = int(result.get("collection_error_count", 0) or 0)
        ragas_error_count = int(result.get("ragas_error_count", 0) or 0)
        evaluation_complete = (
            requested_count > 0
            and collected_count == requested_count
            and evaluated_count == requested_count
            and not result.get("errors")
            and not result.get("error")
            and collection_error_count == 0
            and ragas_error_count == 0
        )
        passed = answer_target_passed and not source_failures and evaluation_complete
        per_language[lang] = {
            "answer_correctness": {
                "actual": (round(actual, 4) if isinstance(actual, (int, float)) else None),
                "target": target,
                "passed": answer_target_passed,
            },
            "evaluation_complete": {
                "requested": requested_count,
                "collected": collected_count,
                "evaluated": evaluated_count,
                "collection_errors": collection_error_count,
                "ragas_errors": ragas_error_count,
                "passed": evaluation_complete,
            },
            "live_source_gate": {
                "enabled": check_live_sources,
                "failed_case_count": len(source_failures),
                "passed": not source_failures,
            },
            "passed": passed,
        }

        for metric in TRACKED_METRICS:
            if metric != "answer_correctness":
                val = metrics.get(metric)
                per_language[lang][metric] = {
                    "actual": (round(val, 4) if isinstance(val, (int, float)) else None),
                }

        if not passed:
            failed.append(
                {
                    "language": lang,
                    "actual": per_language[lang]["answer_correctness"]["actual"],
                    "target": target,
                    "answer_target_passed": answer_target_passed,
                    "evaluation_complete": evaluation_complete,
                    "collection_errors": collection_error_count,
                    "ragas_errors": ragas_error_count,
                    "source_failures": len(source_failures),
                }
            )
        failed_source_cases.extend(source_failures)

    return {
        "per_language": per_language,
        "failed_targets": failed,
        "failed_source_cases": failed_source_cases,
        "all_targets_met": not failed,
    }


def _format_report(
    lang_results: Dict[str, Dict[str, Any]],
    comparison: Dict[str, Any],
    languages: Sequence[str],
    *,
    check_live_sources: bool,
    case_suite: str,
) -> str:
    """Format a human-readable report."""
    lines = [
        "=" * 60,
        "RAGAS Live API Evaluation Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "=" * 60,
        "",
        f"Case suite: {case_suite}",
        "Targets: ja >= 0.85, en >= 0.75, zh >= 0.65, ko >= 0.65",
        "RAGAS contexts: golden_dataset references, not live retrieved chunks",
        f"Live source metadata gate: {'enabled' if check_live_sources else 'disabled'}",
        "",
    ]
    suite_coverage = comparison.get("suite_coverage", {})
    if suite_coverage:
        status = "PASS" if suite_coverage.get("passed") else "FAIL"
        lines.extend(
            [
                "Suite coverage:",
                f"  release_blocking: {suite_coverage.get('release_blocking')}",
                "  cases: "
                f"requested={suite_coverage.get('requested_total_cases')} "
                f"expected={suite_coverage.get('expected_total_cases')} [{status}]",
                "",
            ]
        )
    evaluation_summary = comparison.get("evaluation_summary", {})
    if evaluation_summary:
        collection_status = "PASS" if evaluation_summary.get("collection_complete") else "FAIL"
        evaluation_status = "PASS" if evaluation_summary.get("evaluation_complete") else "FAIL"
        requested_by_language = evaluation_summary.get("requested_by_language", {})
        collected_by_language = evaluation_summary.get("collected_by_language", {})
        evaluated_by_language = evaluation_summary.get("evaluated_by_language", {})
        errors_by_language = evaluation_summary.get("collection_errors_by_language", {})
        lines.extend(
            [
                "Collection/evaluation summary:",
                "  totals: "
                f"requested={evaluation_summary.get('requested_total_cases', 0)} "
                f"collected={evaluation_summary.get('collected_total_cases', 0)} "
                f"evaluated={evaluation_summary.get('evaluated_total_cases', 0)} "
                f"collection_errors={evaluation_summary.get('collection_error_total', 0)} "
                f"ragas_errors={evaluation_summary.get('ragas_error_total', 0)}",
                f"  collection_complete: {collection_status}",
                f"  evaluation_complete: {evaluation_status}",
                "  language_counts: "
                + ", ".join(
                    f"{lang}=requested:{requested_by_language.get(lang, 0)}"
                    f"/collected:{collected_by_language.get(lang, 0)}"
                    f"/evaluated:{evaluated_by_language.get(lang, 0)}"
                    f"/errors:{errors_by_language.get(lang, 0)}"
                    for lang in languages
                ),
                "",
            ]
        )

    for lang in languages:
        result = lang_results.get(lang, {})
        metrics = result.get("metrics", {})
        comp = comparison["per_language"].get(lang, {})

        lines.append(f"--- [{lang.upper()}] ---")
        lines.append(
            f"  Cases: requested={result.get('requested_case_count', 0)} "
            f"collected={result.get('collected_case_count', 0)} "
            f"evaluated={result.get('evaluated_case_count', 0)} "
            f"skipped={result.get('skipped_case_count', 0)}"
        )
        collection_error_count = result.get("collection_error_count", 0)
        if collection_error_count:
            lines.append(
                "  collection_errors: "
                f"{collection_error_count} "
                f"(api_failed={result.get('api_failed_case_count', 0)})"
            )

        if result.get("error"):
            lines.append(f"  ERROR: {result['error']}")
            lines.append("")
            continue

        for metric in TRACKED_METRICS:
            val = metrics.get(metric)
            val_str = f"{val:.4f}" if isinstance(val, (int, float)) else "n/a"

            if metric == "answer_correctness":
                target = TARGETS.get(lang, 0.0)
                passed = comp.get("passed", False)
                status = "PASS" if passed else "FAIL"
                lines.append(f"  {metric}: {val_str}  " f"(target={target:.2f}) [{status}]")
            else:
                lines.append(f"  {metric}: {val_str}")

        source_gate = comp.get("live_source_gate", {})
        eval_complete = comp.get("evaluation_complete", {})
        eval_status = "PASS" if eval_complete.get("passed") else "FAIL"
        lines.append(
            "  evaluation_complete: "
            f"collected={eval_complete.get('collected', 0)}/"
            f"{eval_complete.get('requested', 0)} "
            f"evaluated={eval_complete.get('evaluated', 0)}/"
            f"{eval_complete.get('requested', 0)} "
            f"collection_errors={eval_complete.get('collection_errors', 0)} "
            f"ragas_errors={eval_complete.get('ragas_errors', 0)} "
            f"[{eval_status}]"
        )
        if source_gate.get("enabled"):
            sg_status = "PASS" if source_gate.get("passed") else "FAIL"
            lines.append(
                "  live_source_gate: "
                f"failed_cases={source_gate.get('failed_case_count', 0)} [{sg_status}]"
            )

        overall = "PASS" if comp.get("passed", False) else "FAIL"
        lines.append(f"  overall: {overall}")
        lines.append("")

        results_list = result.get("results", [])
        if results_list:
            lines.append("  Per-case details:")
            for r in results_list:
                ac = r.get("answer_correctness")
                ac_str = f"{ac:.3f}" if isinstance(ac, (int, float)) else "n/a"
                agent = r.get("api_metadata", {}).get("agent", "?")
                elapsed = r.get("api_metadata", {}).get("elapsed_seconds", "?")
                source_check = r.get("live_source_check") or {}
                source_status = "src=off"
                if source_check.get("enabled"):
                    source_status = "src=ok" if source_check.get("passed") else "src=missing"
                lines.append(
                    f"    {r.get('query_id', '?')}: "
                    f"ac={ac_str} "
                    f"agent={agent} "
                    f"{source_status} "
                    f"time={elapsed}s "
                    f"q={r.get('question', '')[:40]}"
                )
            lines.append("")

    lines.append("=" * 60)
    all_met = comparison.get("all_targets_met", False)
    lines.append(f"All targets met: {'YES' if all_met else 'NO'}")
    lines.append(
        "Alpha release gate met: "
        f"{'YES' if comparison.get('alpha_release_gate_met', False) else 'NO'}"
    )
    if suite_coverage and not suite_coverage.get("passed"):
        lines.append(
            "Suite coverage failed: "
            f"case_suite={suite_coverage.get('case_suite')} "
            f"requested={suite_coverage.get('requested_total_cases')} "
            f"expected={suite_coverage.get('expected_total_cases')} "
            f"all_languages_selected={suite_coverage.get('all_languages_selected')}"
        )

    if not all_met:
        lines.append("Failed targets:")
        for f in comparison.get("failed_targets", []):
            lines.append(
                f"  {f['language']}: actual={f['actual']} target={f['target']} "
                f"answer_target_passed={f.get('answer_target_passed')} "
                f"evaluation_complete={f.get('evaluation_complete')} "
                f"collection_errors={f.get('collection_errors', 0)} "
                f"ragas_errors={f.get('ragas_errors', 0)} "
                f"source_failures={f.get('source_failures', 0)}"
            )

    failed_source_cases = comparison.get("failed_source_cases", [])
    if failed_source_cases:
        lines.append("Failed live source cases:")
        for case in failed_source_cases[:40]:
            lines.append(
                f"  {case.get('query_id')}: missing={case.get('missing_sources')} "
                f"actual={case.get('actual_sources')}"
            )

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Live API RAGAS evaluation runner")
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="Backend API base URL.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key for authentication (X-API-Key header). Prefer API_SECRET_KEY env.",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=ALL_LANGUAGES,
        default=None,
        help="Languages to evaluate. Defaults to all.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Report output directory.",
    )
    parser.add_argument(
        "--report-timestamp",
        type=str,
        default=None,
        help="Stable timestamp marker for report artifact filenames.",
    )
    parser.add_argument(
        "--check-targets",
        action="store_true",
        help="Exit with status 1 when targets are missed.",
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        choices=TRACKED_METRICS,
        default=list(TRACKED_METRICS),
        help=(
            "RAGAS metrics to evaluate. For alpha GO target checks, "
            "answer_correctness plus live source gate is sufficient."
        ),
    )
    parser.add_argument(
        "--case-suite",
        choices=CASE_SUITES,
        default=CASE_SUITE_DIAGNOSTIC_29,
        help=(
            "C/RAGAS live case suite. diagnostic-29 is the existing fast diagnostic path; "
            "alpha-127 is the release-blocking full dataset."
        ),
    )
    parser.add_argument(
        "--no-check-live-sources",
        action="store_true",
        help=(
            "Do not fail targets when live /api/chat metadata.sources is missing expected "
            "RAG/event sources. Diagnostic use only."
        ),
    )
    parser.add_argument(
        "--chat-interval-seconds",
        type=float,
        default=0.0,
        help="Minimum seconds between live /api/chat request starts.",
    )
    parser.add_argument(
        "--chat-retry-attempts",
        type=int,
        default=DEFAULT_CHAT_RETRY_ATTEMPTS,
        help="Total /api/chat attempts for retryable 429 responses.",
    )
    parser.add_argument(
        "--chat-retry-backoff-seconds",
        type=float,
        default=DEFAULT_CHAT_RETRY_BACKOFF_SECONDS,
        help="Base exponential backoff seconds for retryable 429 responses.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    output_dir = Path(args.output_dir) if args.output_dir else None
    result = asyncio.run(
        run_live_api_evaluation(
            base_url=args.base_url,
            api_key=args.api_key or os.environ.get("API_SECRET_KEY"),
            languages=args.languages,
            output_dir=output_dir,
            check_live_sources=not args.no_check_live_sources,
            metrics=args.metrics,
            case_suite=args.case_suite,
            report_timestamp=args.report_timestamp,
            chat_interval_seconds=args.chat_interval_seconds,
            chat_retry_attempts=args.chat_retry_attempts,
            chat_retry_backoff_seconds=args.chat_retry_backoff_seconds,
        )
    )

    target_key = (
        "alpha_release_gate_met" if args.case_suite == CASE_SUITE_ALPHA_127 else "all_targets_met"
    )
    if args.check_targets and not result["comparison"][target_key]:
        logger.error("One or more evaluation targets were missed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
