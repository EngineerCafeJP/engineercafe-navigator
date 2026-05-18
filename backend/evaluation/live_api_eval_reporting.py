"""Target comparison and report rendering for live API evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

try:
    from backend.evaluation.live_api_eval_support import TARGETS, TRACKED_METRICS
except ImportError:  # pragma: no cover - supports `python -m evaluation...` from backend/
    from evaluation.live_api_eval_support import TARGETS, TRACKED_METRICS


def _compare_targets(
    lang_results: Dict[str, Dict[str, Any]],
    languages: Sequence[str],
    *,
    check_live_sources: bool,
    quality_signals: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare per-language answer_correctness against targets."""
    failed: List[Dict[str, Any]] = []
    failed_source_cases: List[Dict[str, Any]] = []
    per_language: Dict[str, Any] = {}
    quality_by_language = quality_signals.get("per_language", {})

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
        language_quality_signals = quality_by_language.get(
            lang,
            {
                "case_count": 0,
                "passed": True,
                "failed_case_count": 0,
            },
        )
        quality_passed = bool(language_quality_signals.get("passed", True))
        passed = (
            answer_target_passed and not source_failures and evaluation_complete and quality_passed
        )
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
            "quality_signals": language_quality_signals,
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
                    "quality_signal_failures": int(
                        language_quality_signals.get("failed_case_count", 0) or 0
                    ),
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
    target_summary = ", ".join(
        f"{lang} >= {TARGETS[lang]:.2f}" for lang in ("ja", "en", "zh", "ko")
    )
    lines = [
        "=" * 60,
        "RAGAS Live API Evaluation Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "=" * 60,
        "",
        f"Case suite: {case_suite}",
        f"Targets: {target_summary}",
        "RAGAS contexts: live /api/chat retrieved metadata when required; "
        "golden contexts only for no-source-required diagnostic cases",
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

    quality_signals = comparison.get("quality_signals", {})
    if quality_signals:
        overall_quality = quality_signals.get("overall", {})
        status = "PASS" if overall_quality.get("passed") else "FAIL"
        lines.extend(
            [
                "Quality signals:",
                "  overall: "
                f"cases={overall_quality.get('case_count', 0)} "
                f"failed={overall_quality.get('failed_case_count', 0)} "
                f"groundedness={overall_quality.get('groundedness', 0.0):.3f} "
                f"hallucination_risk={overall_quality.get('hallucination_risk', 0.0):.3f} "
                f"toxicity={overall_quality.get('toxicity', 0.0):.3f} "
                f"[{status}]",
            ]
        )
        failed_quality_cases = quality_signals.get("failed_cases", [])
        if failed_quality_cases:
            lines.append("  failed_cases:")
            for item in failed_quality_cases[:40]:
                lines.append(
                    "    "
                    f"{item.get('case_id')} ({item.get('language')}): "
                    f"{','.join(item.get('failures', []))}"
                )
        lines.append("")

    ragas_judge = comparison.get("ragas_judge", {})
    if ragas_judge:
        provider_gate = "PASS" if ragas_judge.get("release_gate_eligible") else "FAIL"
        fallback = "yes" if ragas_judge.get("fallback") else "no"
        lines.extend(
            [
                "RAGAS judge:",
                f"  provider: {ragas_judge.get('provider_label', ragas_judge.get('provider'))}",
                f"  model: {ragas_judge.get('model') or 'n/a'}",
                "  embeddings: "
                f"{ragas_judge.get('embeddings_provider') or 'n/a'}"
                f"/{ragas_judge.get('embeddings_model') or 'default'}",
                f"  fallback: {fallback}",
                f"  release_gate_eligible: {provider_gate}",
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
        quality_gate = comp.get("quality_signals", {})
        if quality_gate:
            q_status = "PASS" if quality_gate.get("passed") else "FAIL"
            lines.append(
                "  quality_signals: "
                f"failed_cases={quality_gate.get('failed_case_count', 0)} "
                f"groundedness={quality_gate.get('groundedness', 0.0):.3f} "
                f"hallucination_risk={quality_gate.get('hallucination_risk', 0.0):.3f} "
                f"toxicity={quality_gate.get('toxicity', 0.0):.3f} "
                f"[{q_status}]"
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
                f"source_failures={f.get('source_failures', 0)} "
                f"quality_signal_failures={f.get('quality_signal_failures', 0)}"
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
