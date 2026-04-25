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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).parent / "datasets"
MULTILINGUAL_QUERIES_PATH = DATASETS_DIR / "multilingual_queries.json"
DEFAULT_REPORTS_DIR = Path(__file__).parent.parent / "tests" / "evaluation" / "reports"

ALL_LANGUAGES = ("ja", "en", "zh", "ko")
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
    if category == "event":
        return ["google_calendar|connpass"]
    return ["enhanced_rag"]


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
    gt_path = (
        Path(__file__).parent.parent
        / "tests"
        / "fixtures"
        / "golden_datasets"
        / "ground_truth.json"
    )
    with open(gt_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {case["id"]: case for case in data.get("test_cases", [])}


async def _call_chat_api(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    question: str,
    language: str,
    api_key: Optional[str] = None,
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
    response = await client.post(url, json=payload, headers=headers, timeout=60.0)
    response.raise_for_status()
    return response.json()


async def run_live_api_evaluation(
    *,
    base_url: str = "http://localhost:8000",
    api_key: Optional[str] = None,
    languages: Optional[Sequence[str]] = None,
    output_dir: Optional[Path] = None,
    check_live_sources: bool = True,
) -> Dict[str, Any]:
    """Run RAGAS evaluation against the live API.

    Args:
        base_url: Backend API base URL.
        api_key: Optional API key for authentication.
        languages: Languages to evaluate (default: all).
        output_dir: Directory for report output.

    Returns:
        Evaluation result dictionary with per-language metrics.
    """
    config = _load_multilingual_config()
    gt_lookup = _load_ground_truth_lookup()
    selected_languages = list(languages or ALL_LANGUAGES)

    per_language_results: Dict[str, Dict[str, Any]] = {}
    all_eval_cases: Dict[str, List[Dict[str, Any]]] = {}

    # Phase 1: Collect live API responses
    async with httpx.AsyncClient() as client:
        for lang in selected_languages:
            queries = [q for q in config["queries"] if q["language"] == lang]
            lang_cases: List[Dict[str, Any]] = []

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
                    continue

                try:
                    start = time.monotonic()
                    api_response = await _call_chat_api(
                        client,
                        base_url=base_url,
                        question=query["question"],
                        language=lang,
                        api_key=api_key,
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

            all_eval_cases[lang] = lang_cases

    # Phase 2: Run RAGAS evaluation
    try:
        from evaluation.ragas_pipeline import RagasEvaluator
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from evaluation.ragas_pipeline import RagasEvaluator

    for lang in selected_languages:
        cases = all_eval_cases.get(lang, [])
        if not cases:
            per_language_results[lang] = {
                "language": lang,
                "error": "no evaluable cases",
                "requested_case_count": 0,
                "evaluated_case_count": 0,
                "metrics": {},
                "results": [],
            }
            continue

        evaluator = RagasEvaluator(
            metrics=(
                "faithfulness",
                "answer_relevancy",
                "context_precision",
                "answer_correctness",
            ),
            max_cases=len(cases),
        )

        if not evaluator.is_available:
            logger.warning("RAGAS not available, returning API responses only")
            per_language_results[lang] = {
                "language": lang,
                "error": "ragas not installed",
                "requested_case_count": len(cases),
                "evaluated_case_count": 0,
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

        per_case_results: List[Dict[str, Any]] = []
        for case, result in zip(cases, report.results):
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

        per_language_results[lang] = {
            "language": lang,
            "requested_case_count": len(cases),
            "evaluated_case_count": report.evaluated_cases,
            "skipped_case_count": report.skipped_cases,
            "metrics": report.metrics,
            "errors": report.errors,
            "results": per_case_results,
        }

    # Phase 3: Compare with targets
    comparison = _compare_targets(
        per_language_results, selected_languages, check_live_sources=check_live_sources
    )
    report_text = _format_report(
        per_language_results,
        comparison,
        selected_languages,
        check_live_sources=check_live_sources,
    )

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "live-api",
        "base_url": base_url,
        "languages": selected_languages,
        "ragas_context_source": "golden_dataset",
        "live_source_gate_enabled": check_live_sources,
        "per_language": per_language_results,
        "comparison": comparison,
        "report": report_text,
    }

    # Save reports
    dest_dir = output_dir or DEFAULT_REPORTS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = dest_dir / f"live_api_eval_{ts}.json"
    txt_path = dest_dir / f"live_api_eval_{ts}.txt"
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
        passed = answer_target_passed and not source_failures
        per_language[lang] = {
            "answer_correctness": {
                "actual": (round(actual, 4) if isinstance(actual, (int, float)) else None),
                "target": target,
                "passed": answer_target_passed,
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
) -> str:
    """Format a human-readable report."""
    lines = [
        "=" * 60,
        "RAGAS Live API Evaluation Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "=" * 60,
        "",
        "Targets: ja >= 0.85, en >= 0.75, zh >= 0.65, ko >= 0.65",
        "RAGAS contexts: golden_dataset references, not live retrieved chunks",
        f"Live source metadata gate: {'enabled' if check_live_sources else 'disabled'}",
        "",
    ]

    for lang in languages:
        result = lang_results.get(lang, {})
        metrics = result.get("metrics", {})
        comp = comparison["per_language"].get(lang, {})

        lines.append(f"--- [{lang.upper()}] ---")
        lines.append(
            f"  Cases: requested={result.get('requested_case_count', 0)} "
            f"evaluated={result.get('evaluated_case_count', 0)} "
            f"skipped={result.get('skipped_case_count', 0)}"
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

    if not all_met:
        lines.append("Failed targets:")
        for f in comparison.get("failed_targets", []):
            lines.append(
                f"  {f['language']}: actual={f['actual']} target={f['target']} "
                f"answer_target_passed={f.get('answer_target_passed')} "
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
        help="API key for authentication (X-API-Key header).",
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
        "--check-targets",
        action="store_true",
        help="Exit with status 1 when targets are missed.",
    )
    parser.add_argument(
        "--no-check-live-sources",
        action="store_true",
        help=(
            "Do not fail targets when live /api/chat metadata.sources is missing expected "
            "RAG/event sources. Diagnostic use only."
        ),
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
            api_key=args.api_key,
            languages=args.languages,
            output_dir=output_dir,
            check_live_sources=not args.no_check_live_sources,
        )
    )

    if args.check_targets and not result["comparison"]["all_targets_met"]:
        logger.error("One or more evaluation targets were missed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
