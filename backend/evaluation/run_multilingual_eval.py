"""
Multilingual RAGAS evaluation runner for Engineer Cafe Navigator.

The runner is driven by ``evaluation/datasets/multilingual_queries.json`` and
resolves each query against the golden ground-truth dataset so both golden and
live evaluation modes use the same multilingual query manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
REQUIRED_QUERY_COUNTS = {"ja": 5, "en": 10, "zh": 7, "ko": 7}

LANG_INSTRUCTIONS: Dict[str, str] = {
    "ja": "日本語で回答してください。",
    "en": "Answer in English.",
    "zh": "请用中文回答。",
    "ko": "한국어로 답변해 주세요.",
}


def load_multilingual_config() -> Dict[str, Any]:
    """Load the multilingual evaluation manifest."""
    if not MULTILINGUAL_QUERIES_PATH.exists():
        raise FileNotFoundError(
            f"Multilingual query dataset not found: {MULTILINGUAL_QUERIES_PATH}"
        )

    with open(MULTILINGUAL_QUERIES_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def validate_multilingual_config(config: Dict[str, Any]) -> Dict[str, int]:
    """Validate multilingual evaluation configuration and return per-language counts."""
    required_top_level = {"baseline", "targets", "queries"}
    missing_top_level = required_top_level - set(config)
    if missing_top_level:
        missing = ", ".join(sorted(missing_top_level))
        raise ValueError(f"multilingual config missing top-level keys: {missing}")

    queries = config.get("queries")
    if not isinstance(queries, list):
        raise ValueError("multilingual config 'queries' must be a list")

    if len(queries) != sum(REQUIRED_QUERY_COUNTS.values()):
        raise ValueError(
            "multilingual config must contain exactly "
            f"{sum(REQUIRED_QUERY_COUNTS.values())} queries"
        )

    required_query_fields = {
        "id",
        "language",
        "question",
        "category",
        "ground_truth_id",
        "metadata",
    }
    seen_ids: set[str] = set()
    language_counts: Counter[str] = Counter()

    for query in queries:
        missing_fields = required_query_fields - set(query)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"query {query.get('id', '<missing-id>')} missing fields: {missing}")

        query_id = query["id"]
        if query_id in seen_ids:
            raise ValueError(f"duplicate multilingual query id: {query_id}")
        seen_ids.add(query_id)

        language = query["language"]
        if language not in ALL_LANGUAGES:
            raise ValueError(f"unsupported multilingual query language: {language}")

        metadata = query["metadata"]
        if not isinstance(metadata, dict):
            raise ValueError(f"query {query_id} metadata must be an object")

        language_counts[language] += 1

    for language, expected_count in REQUIRED_QUERY_COUNTS.items():
        actual_count = language_counts.get(language, 0)
        if actual_count != expected_count:
            raise ValueError(
                "unexpected query count for "
                f"{language}: expected {expected_count}, got {actual_count}"
            )

    baseline = config["baseline"]
    if not isinstance(baseline, dict) or "date" not in baseline or "metrics" not in baseline:
        raise ValueError("multilingual config baseline must include 'date' and 'metrics'")

    targets = config["targets"]
    if not isinstance(targets, dict):
        raise ValueError("multilingual config targets must be an object")

    for language in ALL_LANGUAGES:
        if language not in targets:
            raise ValueError(f"missing target thresholds for language: {language}")

        if "answer_correctness" not in targets[language]:
            raise ValueError(f"language {language} is missing answer_correctness target")

    return dict(language_counts)


def load_ground_truth_lookup() -> Dict[str, Any]:
    """Load the golden dataset and index it by id."""
    from backend.tests.fixtures.dataset_loader import DatasetLoader

    cases = DatasetLoader.load_ground_truth_cases()
    return {case.id: case for case in cases}


def load_query_cases(
    config: Dict[str, Any],
    *,
    language: str,
    max_cases: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Resolve multilingual query entries into evaluation-ready cases."""
    if language not in ALL_LANGUAGES:
        raise ValueError(f"unsupported language: {language}")

    lookup = load_ground_truth_lookup()
    selected_queries = [query for query in config["queries"] if query["language"] == language]
    if max_cases is not None:
        selected_queries = selected_queries[:max_cases]

    resolved_cases: List[Dict[str, Any]] = []
    for query in selected_queries:
        ground_truth_id = query["ground_truth_id"]
        matched_case = lookup.get(ground_truth_id)
        if matched_case is None:
            raise ValueError(
                f"query {query['id']} references unknown ground truth id: {ground_truth_id}"
            )

        if matched_case.language != language:
            raise ValueError(
                f"query {query['id']} expects language {language}, "
                f"but {ground_truth_id} is {matched_case.language}"
            )

        resolved_cases.append(
            {
                "query_id": query["id"],
                "ground_truth_id": ground_truth_id,
                "question": query["question"],
                "answer": matched_case.answer,
                "contexts": matched_case.contexts,
                "ground_truth": matched_case.ground_truth,
                "language": language,
                "category": query["category"],
                "metadata": query["metadata"],
            }
        )

    return resolved_cases


async def generate_live_response(
    *,
    question: str,
    language: str,
    category: str,
) -> tuple[str, List[str]]:
    """Generate a live response using the actual RAG pipeline."""
    try:
        from langchain_core.messages import HumanMessage

        from backend.llm.models import get_model_config
        from backend.llm.openrouter import OpenRouterProvider
        from backend.tools.enhanced_rag import EnhancedRAGSearch

        rag = EnhancedRAGSearch()
        rag_result = await rag.search(
            query=question,
            category=category,
            language=language,
            max_results=5,
        )

        if not rag_result.get("success") or not rag_result.get("data"):
            logger.warning("RAG search returned no results for %s", question[:80])
            return "", []

        data = rag_result["data"]
        contexts = [
            item.get("content", "") for item in data.get("results", []) if item.get("content")
        ]
        context_text = data.get("context", "")
        if not contexts and context_text:
            contexts = [context_text]

        if not contexts:
            logger.warning("No contexts extracted for %s", question[:80])
            return "", []

        provider = OpenRouterProvider()
        model_config = get_model_config("qa_response")
        language_instruction = LANG_INSTRUCTIONS.get(language, LANG_INSTRUCTIONS["en"])
        prompt = (
            "Answer the question accurately using only the supplied context. "
            "Do not guess beyond the context. "
            f"{language_instruction}\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {question}"
        )

        answer = await provider.generate(
            messages=[HumanMessage(content=prompt)],
            config=model_config,
        )
        return answer, contexts
    except Exception as exc:  # pragma: no cover - exercised by live integration only
        logger.error("Failed to generate live multilingual response for %s: %s", question[:80], exc)
        return "", []


async def evaluate_language(
    *,
    language: str,
    cases: Sequence[Dict[str, Any]],
    mode: str,
) -> Dict[str, Any]:
    """Evaluate one language in golden or live mode."""
    from backend.evaluation.ragas_pipeline import RagasEvaluator

    evaluator = RagasEvaluator(max_cases=len(cases))
    if not evaluator.is_available:
        return {
            "language": language,
            "error": "ragas not installed",
            "requested_case_count": len(cases),
            "evaluated_case_count": 0,
            "skipped_case_count": len(cases),
            "metrics": {},
            "errors": ["ragas not installed"],
            "results": [],
        }

    eval_dicts: List[Dict[str, Any]] = []
    live_skips = 0
    for case in cases:
        if mode == "live":
            answer, contexts = await generate_live_response(
                question=case["question"],
                language=language,
                category=case["category"],
            )
            if not answer or not contexts:
                live_skips += 1
                continue
        else:
            answer = case["answer"]
            contexts = case["contexts"]

        eval_dicts.append(
            {
                **case,
                "answer": answer,
                "contexts": contexts,
            }
        )

    if not eval_dicts:
        return {
            "language": language,
            "error": "no evaluable cases",
            "requested_case_count": len(cases),
            "evaluated_case_count": 0,
            "skipped_case_count": len(cases),
            "metrics": {},
            "errors": ["no evaluable cases"],
            "results": [],
        }

    report = await evaluator.evaluate_batch(eval_dicts)

    per_case_results: List[Dict[str, Any]] = []
    for case, result in zip(eval_dicts, report.results):
        per_case_results.append(
            {
                "query_id": case["query_id"],
                "ground_truth_id": case["ground_truth_id"],
                "category": case["category"],
                "question": result.question,
                "answer_correctness": result.answer_correctness,
                "answer_relevancy": result.answer_relevancy,
                "faithfulness": result.faithfulness,
                "context_precision": result.context_precision,
                "error": result.error,
            }
        )

    return {
        "language": language,
        "requested_case_count": len(cases),
        "evaluated_case_count": report.evaluated_cases,
        "skipped_case_count": report.skipped_cases + live_skips,
        "metrics": report.metrics,
        "errors": report.errors,
        "results": per_case_results,
    }


def compare_with_baseline(
    lang_results: Dict[str, Dict[str, Any]],
    config: Dict[str, Any],
    *,
    languages: Sequence[str],
) -> Dict[str, Any]:
    """Compare per-language metrics against targets and the shared baseline."""
    baseline = config["baseline"]
    baseline_metrics = baseline["metrics"]
    targets = config["targets"]
    per_language: Dict[str, Any] = {}
    failed_targets: List[Dict[str, Any]] = []

    for language in languages:
        result = lang_results.get(language, {})
        metrics = result.get("metrics", {})
        lang_targets = targets.get(language, {})
        language_summary: Dict[str, Any] = {"passed": True, "metrics": {}}

        for metric_name in TRACKED_METRICS:
            actual = metrics.get(metric_name)
            baseline_value = baseline_metrics.get(metric_name)
            target_value = lang_targets.get(metric_name)

            metric_summary: Dict[str, Any] = {
                "actual": round(actual, 4) if isinstance(actual, (int, float)) else None,
                "baseline": baseline_value,
                "baseline_delta": (
                    round(actual - baseline_value, 4)
                    if isinstance(actual, (int, float)) and isinstance(baseline_value, (int, float))
                    else None
                ),
            }

            if target_value is not None:
                passed = isinstance(actual, (int, float)) and actual >= target_value
                metric_summary["target"] = target_value
                metric_summary["target_delta"] = (
                    round(actual - target_value, 4) if isinstance(actual, (int, float)) else None
                )
                metric_summary["passed"] = passed
                if not passed:
                    language_summary["passed"] = False
                    failed_targets.append(
                        {
                            "language": language,
                            "metric": metric_name,
                            "actual": metric_summary["actual"],
                            "target": target_value,
                        }
                    )

            language_summary["metrics"][metric_name] = metric_summary

        if result.get("error"):
            language_summary["passed"] = False

        per_language[language] = language_summary

    return {
        "baseline_date": baseline["date"],
        "baseline_metrics": baseline_metrics,
        "per_language": per_language,
        "failed_targets": failed_targets,
        "all_targets_met": not failed_targets,
    }


def format_report(
    lang_results: Dict[str, Dict[str, Any]],
    comparison: Dict[str, Any],
    *,
    languages: Sequence[str],
) -> str:
    """Format a human-readable evaluation report."""
    lines = [
        "RAGAS Multilingual Evaluation Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Baseline ({comparison['baseline_date']}):",
    ]

    for metric_name in TRACKED_METRICS:
        baseline_value = comparison["baseline_metrics"].get(metric_name)
        if baseline_value is not None:
            lines.append(f"  {metric_name}: {baseline_value:.3f}")

    for language in languages:
        result = lang_results[language]
        lines.append("")
        lines.append(
            f"[{language.upper()}] requested={result['requested_case_count']} "
            f"evaluated={result['evaluated_case_count']} "
            f"skipped={result['skipped_case_count']}"
        )

        if result.get("error"):
            lines.append(f"  error: {result['error']}")
            continue

        metric_comparison = comparison["per_language"][language]["metrics"]
        for metric_name in TRACKED_METRICS:
            actual = result["metrics"].get(metric_name)
            if actual is None:
                lines.append(f"  {metric_name}: n/a")
                continue

            details = metric_comparison[metric_name]
            baseline_delta = details.get("baseline_delta")
            target = details.get("target")
            status = ""
            if target is not None:
                status = " PASS" if details.get("passed") else " FAIL"
                status += f" target={target:.3f}"

            baseline_suffix = ""
            if isinstance(baseline_delta, (int, float)):
                baseline_suffix = f" baseline_delta={baseline_delta:+.3f}"

            lines.append(f"  {metric_name}: {actual:.4f}{baseline_suffix}{status}")

        overall = "PASS" if comparison["per_language"][language]["passed"] else "FAIL"
        lines.append(f"  overall: {overall}")

    lines.extend(
        [
            "",
            f"All targets met: {'YES' if comparison['all_targets_met'] else 'NO'}",
        ]
    )

    return "\n".join(lines)


async def run_multilingual_evaluation(
    *,
    languages: Optional[Sequence[str]] = None,
    max_cases: Optional[int] = None,
    mode: str = "golden",
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run multilingual RAGAS evaluation and persist JSON/text reports."""
    if mode not in {"golden", "live"}:
        raise ValueError("mode must be 'golden' or 'live'")

    config = load_multilingual_config()
    query_counts = validate_multilingual_config(config)

    selected_languages = list(languages or ALL_LANGUAGES)
    unknown_languages = [
        language for language in selected_languages if language not in ALL_LANGUAGES
    ]
    if unknown_languages:
        raise ValueError(f"unsupported languages requested: {', '.join(sorted(unknown_languages))}")

    per_language_results: Dict[str, Dict[str, Any]] = {}
    for language in selected_languages:
        cases = load_query_cases(config, language=language, max_cases=max_cases)
        per_language_results[language] = await evaluate_language(
            language=language,
            cases=cases,
            mode=mode,
        )

    comparison = compare_with_baseline(
        per_language_results,
        config,
        languages=selected_languages,
    )
    report_text = format_report(
        per_language_results,
        comparison,
        languages=selected_languages,
    )

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "languages": selected_languages,
        "query_counts": query_counts,
        "max_cases": max_cases,
        "per_language": per_language_results,
        "comparison": comparison,
        "report": report_text,
    }

    destination_dir = output_dir or DEFAULT_REPORTS_DIR
    destination_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = destination_dir / f"multilingual_eval_{timestamp}.json"
    txt_path = destination_dir / f"multilingual_eval_{timestamp}.txt"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(report_text, encoding="utf-8")

    logger.info("Wrote multilingual evaluation report to %s", json_path)
    logger.info("Wrote multilingual evaluation summary to %s", txt_path)

    return result


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Multilingual RAGAS evaluation runner")
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=ALL_LANGUAGES,
        default=None,
        help="Languages to evaluate. Defaults to all supported languages.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Optional per-language cap applied after the multilingual query manifest.",
    )
    parser.add_argument(
        "--mode",
        choices=["golden", "live"],
        default="golden",
        help="Golden uses the canned dataset, live calls the actual RAG pipeline.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional report output directory.",
    )
    parser.add_argument(
        "--check-targets",
        action="store_true",
        help="Exit with status 1 when any configured language target is missed.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    output_dir = Path(args.output_dir) if args.output_dir else None
    result = asyncio.run(
        run_multilingual_evaluation(
            languages=args.languages,
            max_cases=args.max_cases,
            mode=args.mode,
            output_dir=output_dir,
        )
    )

    if args.check_targets and not result["comparison"]["all_targets_met"]:
        logger.error("One or more multilingual evaluation targets were missed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
