"""
Multilingual RAGAS Evaluation Runner (#382)

Runs RAGAS evaluation per language (ja/en/zh/ko) and compares with baseline.
Outputs structured results with per-language breakdown.

Usage:
    python -m backend.evaluation.run_multilingual_eval
    python -m backend.evaluation.run_multilingual_eval --languages ja en
    python -m backend.evaluation.run_multilingual_eval --mode live --max-cases 5
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).parent / "datasets"
MULTILINGUAL_QUERIES_PATH = DATASETS_DIR / "multilingual_queries.json"
REPORTS_DIR = Path(__file__).parent.parent / "tests" / "evaluation" / "reports"

ALL_LANGUAGES = ["ja", "en", "zh", "ko"]

LANG_INSTRUCTIONS: Dict[str, str] = {
    "ja": "日本語で回答してください。",
    "en": "Answer in English.",
    "zh": "请用中文回答。",
    "ko": "한국어로 답변해 주세요.",
}

BASELINE_DATE = "2026-03-21"
BASELINE_METRICS: Dict[str, float] = {
    "context_precision": 1.000,
    "answer_correctness": 0.770,
    "answer_relevancy": 0.895,
    "faithfulness": 0.871,
}


def load_multilingual_config() -> Dict[str, Any]:
    """Load multilingual queries and targets from the dataset file."""
    if not MULTILINGUAL_QUERIES_PATH.exists():
        raise FileNotFoundError(
            f"Multilingual queries dataset not found: {MULTILINGUAL_QUERIES_PATH}"
        )
    with open(MULTILINGUAL_QUERIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ground_truth_by_language(
    language: str,
    max_cases: int = 50,
) -> List[Dict[str, Any]]:
    """Load ground truth cases for a specific language from the golden dataset.

    Args:
        language: Language code (ja, en, zh, ko)
        max_cases: Maximum number of cases to load

    Returns:
        List of ground truth case dicts with keys:
            question, answer, contexts, ground_truth, language, category
    """
    from backend.tests.fixtures.dataset_loader import DatasetLoader

    cases = DatasetLoader.load_ground_truth_cases(language=language)
    return [
        {
            "question": c.question,
            "answer": c.answer,
            "contexts": c.contexts,
            "ground_truth": c.ground_truth,
            "language": c.language,
            "category": c.category,
        }
        for c in cases[:max_cases]
    ]


async def generate_live_response(
    question: str,
    language: str = "ja",
) -> tuple:
    """Generate a live response using the actual RAG pipeline.

    Args:
        question: Query text
        language: Language code

    Returns:
        (answer, contexts) tuple. Empty strings/list on failure.
    """
    try:
        from backend.tools.enhanced_rag import EnhancedRAGSearch

        rag = EnhancedRAGSearch()
        result = await rag.search(
            query=question,
            language=language,
            max_results=5,
        )

        if not result.get("success") or not result.get("data"):
            logger.warning("RAG search returned no results for: %s", question[:50])
            return "", []

        context_text = result["data"].get("context", "")
        sources = result["data"].get("sources", [])
        contexts = [s.get("content", "") for s in sources if s.get("content")]
        if not contexts and context_text:
            contexts = [context_text]

        lang_instruction = LANG_INSTRUCTIONS.get(language, "Answer in English.")

        from langchain_core.messages import HumanMessage

        from backend.llm.models import get_model_config
        from backend.llm.openrouter import OpenRouterProvider

        model_cfg = get_model_config("gemini")
        provider = OpenRouterProvider(model_name=model_cfg.model_id)
        llm = provider.get_chat_model(temperature=0.1)

        prompt = (
            f"以下のコンテキストに基づいて質問に正確に回答してください。"
            f"コンテキストにない情報は推測しないでください。{lang_instruction}\n\n"
            f"コンテキスト:\n{context_text}\n\n"
            f"質問: {question}"
        )

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        answer = response.content.strip() if response.content else ""
        return answer, contexts

    except Exception as e:
        logger.error("Failed to generate live response: %s", e)
        return "", []


async def evaluate_language(
    language: str,
    cases: List[Dict[str, Any]],
    mode: str = "golden",
    max_cases: int = 10,
) -> Dict[str, Any]:
    """Run RAGAS evaluation for a single language.

    Args:
        language: Language code
        cases: Ground truth cases
        mode: 'golden' (pre-defined answers) or 'live' (actual RAG pipeline)
        max_cases: Maximum number of cases to evaluate

    Returns:
        Dict with language, metrics, case_count, and individual results
    """
    try:
        from backend.evaluation.ragas_pipeline import RagasEvaluator
    except ImportError:
        logger.error("Could not import RagasEvaluator. Check installation.")
        return {
            "language": language,
            "error": "ragas not installed",
            "metrics": {},
            "case_count": 0,
        }

    evaluator = RagasEvaluator()
    if not evaluator.is_available():
        return {
            "language": language,
            "error": "ragas not available (missing API key or dependencies)",
            "metrics": {},
            "case_count": 0,
        }

    target_cases = cases[:max_cases]
    eval_dicts: List[Dict[str, Any]] = []

    for i, c in enumerate(target_cases):
        question = c["question"]
        logger.info(
            "[%s] [%d/%d] %s...",
            language,
            i + 1,
            len(target_cases),
            question[:50],
        )

        if mode == "live":
            answer, contexts = await generate_live_response(
                question=question,
                language=language,
            )
            if not answer or not contexts:
                logger.warning("Skipping case: no live response for %s", question[:50])
                continue
        else:
            answer = c.get("answer", "")
            contexts = c.get("contexts", [])

        ground_truth = c.get("ground_truth", "")
        eval_dicts.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": ground_truth,
            }
        )

    if not eval_dicts:
        return {
            "language": language,
            "error": "no evaluable cases",
            "metrics": {},
            "case_count": 0,
        }

    report = await evaluator.evaluate_batch(eval_dicts)

    return {
        "language": language,
        "metrics": report.metrics_summary(),
        "case_count": len(eval_dicts),
        "results": [
            {
                "question": r.question,
                "answer_correctness": r.answer_correctness,
                "answer_relevancy": r.answer_relevancy,
                "faithfulness": r.faithfulness,
                "context_precision": r.context_precision,
                "error": r.error,
            }
            for r in report.results
        ],
    }


def compare_with_baseline(
    lang_results: Dict[str, Dict[str, Any]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare evaluation results with baseline and targets.

    Args:
        lang_results: Per-language evaluation results
        config: Multilingual config with targets

    Returns:
        Comparison report with pass/fail status per language and metric
    """
    targets = config.get("targets", {})
    comparisons: Dict[str, Any] = {}

    for lang, result in lang_results.items():
        metrics = result.get("metrics", {})
        lang_targets = targets.get(lang, {})
        lang_comparison: Dict[str, Any] = {"metrics": {}, "passed": True}

        for metric_name, target_value in lang_targets.items():
            actual = metrics.get(metric_name)
            if actual is None:
                lang_comparison["metrics"][metric_name] = {
                    "actual": None,
                    "target": target_value,
                    "passed": False,
                    "note": "metric not available",
                }
                lang_comparison["passed"] = False
                continue

            passed = actual >= target_value
            lang_comparison["metrics"][metric_name] = {
                "actual": round(actual, 4),
                "target": target_value,
                "passed": passed,
                "delta": round(actual - target_value, 4),
            }
            if not passed:
                lang_comparison["passed"] = False

        comparisons[lang] = lang_comparison

    # Overall baseline comparison (aggregate)
    all_passed = all(c.get("passed", False) for c in comparisons.values())

    return {
        "baseline_date": BASELINE_DATE,
        "baseline_metrics": BASELINE_METRICS,
        "per_language": comparisons,
        "all_targets_met": all_passed,
    }


def format_report(
    lang_results: Dict[str, Dict[str, Any]],
    comparison: Dict[str, Any],
) -> str:
    """Format evaluation results as a human-readable report.

    Args:
        lang_results: Per-language evaluation results
        comparison: Baseline comparison data

    Returns:
        Formatted report string
    """
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("RAGAS Multilingual Evaluation Report")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 70)

    # Baseline reference
    lines.append("")
    lines.append(f"Baseline ({BASELINE_DATE}):")
    for m, v in BASELINE_METRICS.items():
        lines.append(f"  {m}: {v:.3f}")

    # Per-language results
    for lang, result in lang_results.items():
        lines.append("")
        lines.append("-" * 50)
        error = result.get("error")
        if error:
            lines.append(f"[{lang.upper()}] ERROR: {error}")
            continue

        lines.append(f"[{lang.upper()}] Cases: {result.get('case_count', 0)}")
        metrics = result.get("metrics", {})
        lang_comp = comparison.get("per_language", {}).get(lang, {})
        lang_metrics_comp = lang_comp.get("metrics", {})

        for metric_name, value in metrics.items():
            target_info = lang_metrics_comp.get(metric_name, {})
            target = target_info.get("target")
            passed = target_info.get("passed")
            status = ""
            if target is not None:
                status = " PASS" if passed else " FAIL"
                status += f" (target: {target:.3f})"
            lines.append(f"  {metric_name}: {value:.4f}{status}")

        lang_passed = lang_comp.get("passed", False)
        lines.append(f"  Overall: {'PASS' if lang_passed else 'FAIL'}")

    # Summary
    lines.append("")
    lines.append("=" * 70)
    all_met = comparison.get("all_targets_met", False)
    lines.append(f"All targets met: {'YES' if all_met else 'NO'}")
    lines.append("=" * 70)

    return "\n".join(lines)


async def run_multilingual_evaluation(
    languages: Optional[List[str]] = None,
    max_cases: int = 10,
    mode: str = "golden",
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run RAGAS evaluation across multiple languages.

    Args:
        languages: List of language codes to evaluate (default: all)
        max_cases: Maximum cases per language
        mode: 'golden' or 'live'
        output_dir: Directory to write report files

    Returns:
        Full evaluation result dict
    """
    target_languages = languages or ALL_LANGUAGES
    config = load_multilingual_config()

    lang_results: Dict[str, Dict[str, Any]] = {}

    for lang in target_languages:
        logger.info("Evaluating language: %s", lang)
        cases = load_ground_truth_by_language(lang, max_cases=max_cases)

        if not cases:
            logger.warning("No ground truth cases found for language: %s", lang)
            lang_results[lang] = {
                "language": lang,
                "error": "no cases found",
                "metrics": {},
                "case_count": 0,
            }
            continue

        result = await evaluate_language(
            language=lang,
            cases=cases,
            mode=mode,
            max_cases=max_cases,
        )
        lang_results[lang] = result

    comparison = compare_with_baseline(lang_results, config)
    report_text = format_report(lang_results, comparison)

    logger.info("\n%s", report_text)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "languages": target_languages,
        "max_cases": max_cases,
        "per_language": lang_results,
        "comparison": comparison,
        "report": report_text,
    }

    # Write report files if output_dir specified
    out = output_dir or REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out / f"multilingual_eval_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    logger.info("JSON report written to: %s", json_path)

    txt_path = out / f"multilingual_eval_{ts}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info("Text report written to: %s", txt_path)

    return result


def main() -> None:
    """CLI entrypoint for multilingual RAGAS evaluation."""
    parser = argparse.ArgumentParser(description="Multilingual RAGAS Evaluation Runner (#382)")
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        choices=ALL_LANGUAGES,
        help="Languages to evaluate (default: all)",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=10,
        help="Max evaluation cases per language (default: 10)",
    )
    parser.add_argument(
        "--mode",
        choices=["golden", "live"],
        default="golden",
        help="Evaluation mode (default: golden)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Report output directory",
    )
    parser.add_argument(
        "--check-targets",
        action="store_true",
        help="Exit non-zero if targets not met",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

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

    if args.check_targets:
        all_met = result.get("comparison", {}).get("all_targets_met", False)
        if not all_met:
            logger.error("Target metrics NOT met. See report for details.")
            sys.exit(1)
        logger.info("All target metrics met.")


if __name__ == "__main__":
    main()
