"""Offline multilingual RAG quality gate.

This runner uses the existing multilingual RAGAS manifest and golden cases, but
does not invoke RAGAS, LLMs, vector search, Supabase, or live APIs. By default it
writes report artifacts and exits successfully even when cases miss thresholds;
use ``--enforce`` to make it blocking in CI.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from backend.evaluation.quality_signals import DEFAULT_THRESHOLDS, summarize_quality_signals
    from backend.evaluation.run_multilingual_eval import (
        ALL_LANGUAGES,
        DEFAULT_REPORTS_DIR,
        load_multilingual_config,
        load_query_cases,
        validate_multilingual_config,
    )
except ImportError:  # pragma: no cover - supports running from backend/ as cwd
    from evaluation.quality_signals import DEFAULT_THRESHOLDS, summarize_quality_signals
    from evaluation.run_multilingual_eval import (
        ALL_LANGUAGES,
        DEFAULT_REPORTS_DIR,
        load_multilingual_config,
        load_query_cases,
        validate_multilingual_config,
    )

logger = logging.getLogger(__name__)


def load_offline_cases(
    *,
    languages: Sequence[str] | None = None,
    max_cases: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Load multilingual golden cases for deterministic quality scoring."""
    config = load_multilingual_config()
    query_counts = validate_multilingual_config(config)
    selected_languages = list(languages or ALL_LANGUAGES)

    unknown_languages = [
        language for language in selected_languages if language not in ALL_LANGUAGES
    ]
    if unknown_languages:
        raise ValueError(f"unsupported languages requested: {', '.join(sorted(unknown_languages))}")

    cases: list[dict[str, Any]] = []
    for language in selected_languages:
        cases.extend(load_query_cases(config, language=language, max_cases=max_cases))
    return cases, query_counts


def run_offline_quality_gate(
    *,
    languages: Sequence[str] | None = None,
    max_cases: int | None = None,
    output_dir: Path | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run offline quality signals and write JSON/Markdown reports."""
    cases, query_counts = load_offline_cases(languages=languages, max_cases=max_cases)
    signals = summarize_quality_signals(cases, thresholds=thresholds)
    selected_languages = list(languages or ALL_LANGUAGES)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "offline",
        "blocking_by_default": False,
        "languages": selected_languages,
        "max_cases": max_cases,
        "query_counts": query_counts,
        "quality_signals": signals,
    }
    result["report"] = format_markdown_report(result)

    destination_dir = output_dir or DEFAULT_REPORTS_DIR
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = destination_dir / f"offline_quality_gate_{timestamp}.json"
    md_path = destination_dir / f"offline_quality_gate_{timestamp}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(result["report"], encoding="utf-8")
    result["artifacts"] = {"json": str(json_path), "markdown": str(md_path)}

    logger.info("Wrote offline quality gate report to %s", json_path)
    logger.info("Wrote offline quality gate summary to %s", md_path)
    return result


def format_markdown_report(result: dict[str, Any]) -> str:
    """Format a compact CI-readable Markdown report."""
    signals = result["quality_signals"]
    overall = signals["overall"]
    thresholds = signals["thresholds"]
    lines = [
        "# Offline RAG Quality Gate",
        "",
        f"- Generated: {result['timestamp']}",
        "- Mode: offline golden dataset; no live credentials required",
        "- Blocking: opt-in via `--enforce`",
        f"- Languages: {', '.join(result['languages'])}",
        "",
        "## Thresholds",
        "",
        "| Signal | Threshold |",
        "| --- | ---: |",
        f"| language_match | >= {thresholds['language_match_min']:.2f} |",
        f"| groundedness | >= {thresholds['groundedness_min']:.2f} |",
        f"| hallucination_risk | <= {thresholds['hallucination_risk_max']:.2f} |",
        f"| toxicity | <= {thresholds['toxicity_max']:.2f} |",
        "",
        "## Summary",
        "",
        "| Scope | Cases | Failed | Language | Grounded | Hallucination Risk | Toxicity | Pass |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        _summary_row("overall", overall),
    ]

    for language, summary in signals["per_language"].items():
        lines.append(_summary_row(language, summary))

    failed_cases = signals["failed_cases"]
    if failed_cases:
        lines.extend(["", "## Failed Cases", ""])
        for item in failed_cases:
            failures = ", ".join(item["failures"])
            lines.append(f"- {item['case_id']} ({item['language']}): {failures}")

    return "\n".join(lines) + "\n"


def _summary_row(scope: str, summary: dict[str, Any]) -> str:
    status = "PASS" if summary["passed"] else "FAIL"
    return (
        f"| {scope} | {summary['case_count']} | {summary['failed_case_count']} | "
        f"{summary['language_match']:.3f} | {summary['groundedness']:.3f} | "
        f"{summary['hallucination_risk']:.3f} | {summary['toxicity']:.3f} | {status} |"
    )


def _threshold_args(args: argparse.Namespace) -> dict[str, float]:
    return {
        "language_match_min": args.language_match_min,
        "groundedness_min": args.groundedness_min,
        "hallucination_risk_max": args.hallucination_risk_max,
        "toxicity_max": args.toxicity_max,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline multilingual RAG quality gate")
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=ALL_LANGUAGES,
        default=None,
        help="Languages to score. Defaults to all supported languages.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Optional per-language cap applied after the multilingual query manifest.",
    )
    parser.add_argument("--output-dir", type=str, default=None, help="Report output directory.")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when any offline signal threshold is missed.",
    )
    parser.add_argument(
        "--language-match-min",
        type=float,
        default=DEFAULT_THRESHOLDS["language_match_min"],
    )
    parser.add_argument(
        "--groundedness-min",
        type=float,
        default=DEFAULT_THRESHOLDS["groundedness_min"],
    )
    parser.add_argument(
        "--hallucination-risk-max",
        type=float,
        default=DEFAULT_THRESHOLDS["hallucination_risk_max"],
    )
    parser.add_argument("--toxicity-max", type=float, default=DEFAULT_THRESHOLDS["toxicity_max"])
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = run_offline_quality_gate(
        languages=args.languages,
        max_cases=args.max_cases,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        thresholds=_threshold_args(args),
    )
    print(result["report"])

    if args.enforce and not result["quality_signals"]["overall"]["passed"]:
        logger.error("Offline quality gate failed under --enforce.")
        sys.exit(1)


if __name__ == "__main__":
    main()
