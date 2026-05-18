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
import contextlib
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

try:
    from backend.evaluation import live_api_eval_support as _live_eval_support
    from backend.evaluation.live_api_eval_reporting import _compare_targets, _format_report
except ImportError:  # pragma: no cover - supports `python -m evaluation...` from backend/
    from evaluation import live_api_eval_support as _live_eval_support
    from evaluation.live_api_eval_reporting import _compare_targets, _format_report

ALL_LANGUAGES = _live_eval_support.ALL_LANGUAGES
CASE_SUITE_ALPHA_127 = _live_eval_support.CASE_SUITE_ALPHA_127
CASE_SUITE_DIAGNOSTIC_29 = _live_eval_support.CASE_SUITE_DIAGNOSTIC_29
CASE_SUITES = _live_eval_support.CASE_SUITES
DEFAULT_CHAT_RETRY_ATTEMPTS = _live_eval_support.DEFAULT_CHAT_RETRY_ATTEMPTS
DEFAULT_CHAT_RETRY_BACKOFF_SECONDS = _live_eval_support.DEFAULT_CHAT_RETRY_BACKOFF_SECONDS
DEFAULT_CHAT_TIMEOUT_SECONDS = _live_eval_support.DEFAULT_CHAT_TIMEOUT_SECONDS
DEFAULT_REPORTS_DIR = _live_eval_support.DEFAULT_REPORTS_DIR
LIVE_CONTEXT_REQUIRED_SOURCE_LABEL = _live_eval_support.LIVE_CONTEXT_REQUIRED_SOURCE_LABEL
TRACKED_METRICS = _live_eval_support.TRACKED_METRICS
_LiveEvalProgress = _live_eval_support._LiveEvalProgress
_call_chat_api = _live_eval_support._call_chat_api
_collection_error_record = _live_eval_support._collection_error_record
_emit_progress = _live_eval_support._emit_progress
_evaluation_contexts_for_case = _live_eval_support._evaluation_contexts_for_case
_evaluation_summary = _live_eval_support._evaluation_summary
_extract_live_contexts = _live_eval_support._extract_live_contexts
_language_case_counts = _live_eval_support._language_case_counts
_live_context_check = _live_eval_support._live_context_check
_load_case_suite_config = _live_eval_support._load_case_suite_config
_load_ground_truth_lookup = _live_eval_support._load_ground_truth_lookup
_progress_heartbeat_seconds = _live_eval_support._progress_heartbeat_seconds
_ragas_progress_heartbeat = _live_eval_support._ragas_progress_heartbeat
_report_file_timestamp = _live_eval_support._report_file_timestamp
_required_live_sources = _live_eval_support._required_live_sources
_source_requirement_ok = _live_eval_support._source_requirement_ok
_suite_coverage = _live_eval_support._suite_coverage
_summarize_live_quality_signals = _live_eval_support._summarize_live_quality_signals


def __getattr__(name: str) -> Any:
    return getattr(_live_eval_support, name)


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
    chat_timeout_seconds: float = DEFAULT_CHAT_TIMEOUT_SECONDS,
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
        chat_timeout_seconds: Per-attempt timeout for live /api/chat calls.

    Returns:
        Evaluation result dictionary with per-language metrics.
    """
    config = _load_case_suite_config(case_suite)
    gt_lookup = _load_ground_truth_lookup()
    selected_languages = list(languages or ALL_LANGUAGES)
    selected_metrics = tuple(metrics or TRACKED_METRICS)
    manifest_language_counts = _language_case_counts(config)
    report_file_ts = _report_file_timestamp(report_timestamp)
    dest_dir = output_dir or DEFAULT_REPORTS_DIR
    json_report_filename = f"live_api_eval_{report_file_ts}.json"
    text_report_filename = f"live_api_eval_{report_file_ts}.txt"
    progress_report_filename = f"live_api_eval_{report_file_ts}.progress.json"

    per_language_results: Dict[str, Dict[str, Any]] = {}
    all_eval_cases: Dict[str, List[Dict[str, Any]]] = {}
    requested_case_counts: Dict[str, int] = {}
    collection_errors: Dict[str, List[Dict[str, Any]]] = {}
    last_chat_started: Optional[float] = None
    total_requested_cases = sum(
        1 for query in config.get("queries", []) if query.get("language") in selected_languages
    )
    collected_count = 0
    collection_error_count = 0
    progress = _LiveEvalProgress(
        path=dest_dir / progress_report_filename,
        case_suite=case_suite,
        base_url=base_url,
        languages=selected_languages,
        metrics=selected_metrics,
        total_requested_cases=total_requested_cases,
    )

    # Phase 1: Collect live API responses
    message = (
        "Live API collection phase start: "
        f"case_suite={case_suite} total_cases={total_requested_cases} "
        f"languages={','.join(selected_languages)} timeout_per_attempt={chat_timeout_seconds:.1f}s"
    )
    _emit_progress(message)
    progress.update(
        phase="collection",
        message=message,
        collection={"collected": collected_count, "errors": collection_error_count},
    )
    async with httpx.AsyncClient() as client:
        for lang in selected_languages:
            queries = [q for q in config["queries"] if q["language"] == lang]
            lang_cases: List[Dict[str, Any]] = []
            lang_collection_errors: List[Dict[str, Any]] = []
            requested_case_counts[lang] = len(queries)

            _emit_progress(f"Live API collection language start: {lang} cases={len(queries)}")
            progress.update(
                phase="collection",
                message=f"Live API collection language start: {lang} cases={len(queries)}",
                collection={"current_language": lang, "current_query_id": None},
            )

            for lang_index, query in enumerate(queries, start=1):
                global_index = collected_count + collection_error_count + 1
                gt_id = query["ground_truth_id"]
                gt_case = gt_lookup.get(gt_id)
                if gt_case is None:
                    message = f"ground truth {gt_id} not found"
                    collection_error_count += 1
                    _emit_progress(
                        "Live API collection case error: "
                        f"{global_index}/{total_requested_cases} "
                        f"{lang} {lang_index}/{len(queries)} {query['id']} "
                        f"type=missing_ground_truth error={message}"
                    )
                    progress.update(
                        phase="collection",
                        message=(
                            "Live API collection case error: "
                            f"{global_index}/{total_requested_cases} "
                            f"{lang} {query['id']} type=missing_ground_truth"
                        ),
                        collection={
                            "collected": collected_count,
                            "errors": collection_error_count,
                            "current_language": lang,
                            "current_query_id": query["id"],
                        },
                    )
                    lang_collection_errors.append(
                        _collection_error_record(
                            query,
                            error_type="missing_ground_truth",
                            message=message,
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
                    _emit_progress(
                        "Live API collection case start: "
                        f"{global_index}/{total_requested_cases} "
                        f"{lang} {lang_index}/{len(queries)} {query['id']} "
                        f"category={query.get('category', '?')}"
                    )
                    progress.update(
                        phase="collection",
                        message=(
                            "Live API collection case start: "
                            f"{global_index}/{total_requested_cases} {lang} {query['id']}"
                        ),
                        collection={
                            "collected": collected_count,
                            "errors": collection_error_count,
                            "current_language": lang,
                            "current_query_id": query["id"],
                        },
                    )
                    api_response = await _call_chat_api(
                        client,
                        base_url=base_url,
                        question=query["question"],
                        language=lang,
                        api_key=api_key,
                        retry_attempts=chat_retry_attempts,
                        retry_backoff_seconds=chat_retry_backoff_seconds,
                        timeout_seconds=chat_timeout_seconds,
                    )
                    elapsed = time.monotonic() - start

                    answer = api_response.get("answer", "")
                    metadata = api_response.get("metadata", {})
                    metadata_dict = metadata if isinstance(metadata, dict) else {}
                    required_sources = _required_live_sources(query)
                    sources_ok, missing_sources, actual_sources = _source_requirement_ok(
                        metadata_dict, required_sources
                    )
                    live_contexts = _extract_live_contexts(metadata_dict)
                    evaluation_contexts, evaluation_context_source = _evaluation_contexts_for_case(
                        live_contexts=live_contexts,
                        golden_contexts=gt_case.get("contexts", []),
                        required_sources=required_sources,
                    )
                    live_context_check = _live_context_check(
                        required_sources=required_sources,
                        live_contexts=live_contexts,
                        enabled=check_live_sources,
                    )

                    lang_cases.append(
                        {
                            "query_id": query["id"],
                            "ground_truth_id": gt_id,
                            "question": query["question"],
                            "answer": answer,
                            "contexts": evaluation_contexts,
                            "ground_truth": gt_case.get("ground_truth", ""),
                            "reference_answer": gt_case.get("answer", ""),
                            "language": lang,
                            "category": query["category"],
                            "metadata": query["metadata"],
                            "evaluation_context_source": evaluation_context_source,
                            "quality_signal_enabled": check_live_sources and bool(required_sources),
                            "live_context_check": live_context_check,
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
                                "live_context_source": live_contexts.get("source"),
                                "live_context_count": live_contexts.get("context_count", 0),
                            },
                        }
                    )
                    collected_count += 1
                    _emit_progress(
                        "Live API collection case done: "
                        f"{global_index}/{total_requested_cases} "
                        f"{lang} {lang_index}/{len(queries)} {query['id']} "
                        f"agent={metadata_dict.get('agent', '?')} "
                        f"sources_ok={sources_ok} elapsed={elapsed:.1f}s"
                    )
                    progress.update(
                        phase="collection",
                        message=(
                            "Live API collection case done: "
                            f"{global_index}/{total_requested_cases} {lang} {query['id']}"
                        ),
                        collection={
                            "collected": collected_count,
                            "errors": collection_error_count,
                            "current_language": lang,
                            "current_query_id": query["id"],
                        },
                    )
                except Exception as exc:
                    collection_error_count += 1
                    _emit_progress(
                        "Live API collection case error: "
                        f"{global_index}/{total_requested_cases} "
                        f"{lang} {lang_index}/{len(queries)} {query['id']} "
                        f"type=api_call_failed error={exc}"
                    )
                    progress.update(
                        phase="collection",
                        message=(
                            "Live API collection case error: "
                            f"{global_index}/{total_requested_cases} {lang} {query['id']} "
                            "type=api_call_failed"
                        ),
                        collection={
                            "collected": collected_count,
                            "errors": collection_error_count,
                            "current_language": lang,
                            "current_query_id": query["id"],
                        },
                    )
                    lang_collection_errors.append(
                        _collection_error_record(
                            query,
                            error_type="api_call_failed",
                            message=str(exc),
                        )
                    )

            all_eval_cases[lang] = lang_cases
            collection_errors[lang] = lang_collection_errors
            _emit_progress(
                "Live API collection language done: "
                f"{lang} collected={len(lang_cases)}/{len(queries)} "
                f"errors={len(lang_collection_errors)}"
            )
            completed_languages = list(progress.state["collection"]["completed_languages"])
            completed_languages.append(lang)
            progress.update(
                phase="collection",
                message=(
                    "Live API collection language done: "
                    f"{lang} collected={len(lang_cases)}/{len(queries)} "
                    f"errors={len(lang_collection_errors)}"
                ),
                collection={
                    "collected": collected_count,
                    "errors": collection_error_count,
                    "current_language": None,
                    "current_query_id": None,
                    "completed_languages": completed_languages,
                },
            )

    message = (
        "Live API collection phase done: "
        f"collected={collected_count}/{total_requested_cases} errors={collection_error_count}"
    )
    _emit_progress(message)
    progress.update(
        phase="collection_done",
        message=message,
        collection={"collected": collected_count, "errors": collection_error_count},
    )

    # Phase 2: Run RAGAS evaluation
    message = (
        "RAGAS scoring phase start: "
        f"languages={','.join(selected_languages)} metrics={','.join(selected_metrics)}"
    )
    _emit_progress(message)
    progress.update(phase="ragas_scoring", message=message)
    try:
        from evaluation.ragas_pipeline import RagasEvaluator, resolve_ragas_judge_metadata
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from evaluation.ragas_pipeline import RagasEvaluator, resolve_ragas_judge_metadata

    ragas_judge_metadata = resolve_ragas_judge_metadata()

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
            _emit_progress(
                "RAGAS language skipped: "
                f"{lang} reason=no_evaluable_cases requested={requested_count} "
                f"collection_errors={len(lang_collection_errors)}"
            )
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
            _emit_progress(
                "RAGAS language skipped: "
                f"{lang} reason=ragas_not_available collected={len(cases)}"
            )
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
                        "live_context_check": c["live_context_check"],
                        "live_source_check": c["live_source_check"],
                    }
                    for c in cases
                ],
            }
            continue

        message = f"RAGAS language start: {lang} cases={len(cases)}"
        _emit_progress(message)
        progress.update(
            phase="ragas_scoring",
            message=message,
            ragas={"current_language": lang},
        )
        heartbeat_interval = _progress_heartbeat_seconds()
        heartbeat_task: Optional[asyncio.Task[None]] = None
        if heartbeat_interval > 0:
            heartbeat_task = asyncio.create_task(
                _ragas_progress_heartbeat(
                    progress,
                    language=lang,
                    case_count=len(cases),
                    interval_seconds=heartbeat_interval,
                )
            )
        try:
            report = await evaluator.evaluate_batch(cases)
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task
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
                    "live_context_check": case["live_context_check"],
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
        _emit_progress(
            "RAGAS language done: "
            f"{lang} evaluated={report.evaluated_cases}/{requested_count} "
            f"ragas_errors={ragas_error_count}"
        )
        completed_languages = list(progress.state["ragas"]["completed_languages"])
        completed_languages.append(lang)
        progress.update(
            phase="ragas_scoring",
            message=(
                "RAGAS language done: "
                f"{lang} evaluated={report.evaluated_cases}/{requested_count} "
                f"ragas_errors={ragas_error_count}"
            ),
            ragas={
                "current_language": None,
                "completed_languages": completed_languages,
                "evaluated_total": sum(
                    int(result.get("evaluated_case_count", 0) or 0)
                    for result in per_language_results.values()
                ),
            },
        )

    _emit_progress("RAGAS scoring phase done")
    progress.update(phase="ragas_done", message="RAGAS scoring phase done")

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
    quality_signals = _summarize_live_quality_signals(
        [case for cases in all_eval_cases.values() for case in cases]
    )
    comparison = _compare_targets(
        per_language_results,
        selected_languages,
        check_live_sources=check_live_sources,
        quality_signals=quality_signals,
    )
    comparison["suite_coverage"] = suite_coverage
    comparison["evaluation_summary"] = evaluation_summary
    comparison["quality_signals"] = quality_signals
    comparison["ragas_judge"] = ragas_judge_metadata
    comparison["alpha_release_gate_met"] = (
        comparison["all_targets_met"]
        and suite_coverage["release_blocking"]
        and suite_coverage["passed"]
        and ragas_judge_metadata["release_gate_eligible"]
    )
    report_text = _format_report(
        per_language_results,
        comparison,
        selected_languages,
        check_live_sources=check_live_sources,
        case_suite=case_suite,
    )

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "live-api",
        "case_suite": case_suite,
        "suite_coverage": suite_coverage,
        "evaluation_summary": evaluation_summary,
        "base_url": base_url,
        "languages": selected_languages,
        "metrics": list(selected_metrics),
        "ragas_context_source": LIVE_CONTEXT_REQUIRED_SOURCE_LABEL,
        "quality_signals": quality_signals,
        "ragas_judge": ragas_judge_metadata,
        "live_source_gate_enabled": check_live_sources,
        "artifact_metadata": {
            "report_timestamp": report_file_ts,
            "json_report_filename": json_report_filename,
            "text_report_filename": text_report_filename,
            "progress_report_filename": progress_report_filename,
            "ragas_judge": ragas_judge_metadata,
            "expected_total_cases": config.get("expected_total_cases"),
            "manifest_language_counts": manifest_language_counts,
            "selected_language_counts": {
                lang: manifest_language_counts.get(lang, 0) for lang in selected_languages
            },
            "chat_interval_seconds": chat_interval_seconds,
            "chat_retry_attempts": chat_retry_attempts,
            "chat_retry_backoff_seconds": chat_retry_backoff_seconds,
            "chat_timeout_seconds": chat_timeout_seconds,
        },
        "per_language": per_language_results,
        "comparison": comparison,
        "report": report_text,
    }

    # Save reports
    dest_dir.mkdir(parents=True, exist_ok=True)
    json_path = dest_dir / json_report_filename
    txt_path = dest_dir / text_report_filename
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(report_text, encoding="utf-8")

    logger.info("Wrote live API evaluation report to %s", json_path)
    progress.update(
        phase="report_written",
        message=f"Wrote live API evaluation report to {json_path}",
        json_report=str(json_path),
        text_report=str(txt_path),
    )
    print(report_text)

    return result


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
    parser.add_argument(
        "--chat-timeout-seconds",
        type=float,
        default=DEFAULT_CHAT_TIMEOUT_SECONDS,
        help="Per-attempt timeout seconds for live /api/chat calls.",
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
            chat_timeout_seconds=args.chat_timeout_seconds,
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
