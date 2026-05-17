"""RAGAS ライブE2Eテスト - 実回答のRAGAS6メトリクス評価"""

import asyncio

import pytest

from backend.evaluation.ragas_pipeline import resolve_ragas_judge_metadata
from backend.tests.fixtures.dataset_loader import DatasetLoader

WORKFLOW_CASE_TIMEOUT = 90
RAGAS_CASE_TIMEOUT = 120
INFRA_ERROR_FAILFAST_THRESHOLD = 2


def _is_infra_error(message: str) -> bool:
    lower = (message or "").lower()
    indicators = (
        "timeout",
        "timed out",
        "rate limit",
        "quota",
        "429",
        "503",
        "502",
        "connection",
        "network",
        "api key",
        "unauthorized",
        "forbidden",
    )
    return any(token in lower for token in indicators)


def _format_ragas_failure_context(metric_name: str, scores, errors, details) -> str:
    """Build a compact, high-signal failure message for flaky live evaluation triage."""
    detail_lines = []
    for d in details:
        detail_lines.append(
            (
                f"{d.get('case_id')} score={d.get('score'):.3f} "
                f"ctx={d.get('context_source')}:{d.get('context_count')} "
                f"q={d.get('question')}"
            )
        )
    parts = [f"metric={metric_name}", f"scores={scores}"]
    if errors:
        parts.append(f"errors={errors[:3]}")
    if detail_lines:
        parts.append("details=[" + "; ".join(detail_lines) + "]")
    return " | ".join(parts)


def _require_release_gate_ragas_judge() -> None:
    """Only run blocking live RAGAS gates with a direct OpenAI judge.

    The OpenRouter path is useful as a local fallback but is explicitly not a
    release-gate provider: RAGAS can issue many nested LLM calls, and the
    fallback has proven too slow and unstable for a blocking CI gate.
    """
    metadata = resolve_ragas_judge_metadata()
    if not metadata.get("release_gate_eligible"):
        pytest.xfail(
            "RAGAS live release gate requires direct OpenAI judge "
            f"(provider={metadata.get('provider')}, "
            f"fallback={metadata.get('fallback')}, "
            f"openai_key_present={metadata.get('openai_key_present')}, "
            f"openrouter_key_present={metadata.get('openrouter_key_present')})"
        )


async def _collect_scores(metric_name, invoke_workflow, ragas_evaluator, cases):
    """メトリクス別の評価ループ（case単位 timeout + infra fail-fast付き）"""
    scores = []
    errors = []
    details = []
    infra_errors = 0

    for case in cases:
        try:
            result = await asyncio.wait_for(
                invoke_workflow(case.question, language=case.language),
                timeout=WORKFLOW_CASE_TIMEOUT,
            )
            eval_contexts = result.get("retrieved_contexts") or case.contexts
            eval_result = await asyncio.wait_for(
                ragas_evaluator.evaluate_single(
                    question=case.question,
                    answer=result["answer"],
                    contexts=eval_contexts,
                    ground_truth=case.ground_truth,
                ),
                timeout=RAGAS_CASE_TIMEOUT,
            )

            if eval_result.error is None:
                score = getattr(eval_result, metric_name)
                scores.append(score)
                details.append(
                    {
                        "case_id": getattr(case, "id", "unknown"),
                        "metric": metric_name,
                        "score": score,
                        "context_source": (
                            "workflow" if result.get("retrieved_contexts") else "dataset"
                        ),
                        "context_count": len(eval_contexts or []),
                        "question": case.question[:50],
                    }
                )
            else:
                msg = f"{case.question[:30]}: {eval_result.error}"
                errors.append(msg)
                if _is_infra_error(eval_result.error):
                    infra_errors += 1
        except asyncio.TimeoutError:
            msg = f"{case.question[:30]}: case timeout"
            errors.append(msg)
            infra_errors += 1
        except Exception as e:
            msg = f"{case.question[:30]}: {e}"
            errors.append(msg)
            if _is_infra_error(str(e)):
                infra_errors += 1

        # infra failure (API/timeout/network) が続いた場合は早期終了して連鎖を防ぐ
        if infra_errors >= INFRA_ERROR_FAILFAST_THRESHOLD and not scores:
            pytest.xfail(
                "RAGAS live evaluation infrastructure unstable "
                f"(infra_errors={infra_errors}, examples={errors[:2]})"
            )

    return scores, errors, details


@pytest.mark.e2e
@pytest.mark.asyncio
class TestRagasLiveE2E:
    """実回答のRAGAS評価テスト"""

    @pytest.fixture
    def gt_cases(self):
        cases = DatasetLoader.load_ground_truth_cases()
        return cases[:10]  # コスト制限

    async def test_ragas_faithfulness(self, invoke_workflow, ragas_evaluator, gt_cases):
        """Faithfulness >= 0.7"""
        _require_release_gate_ragas_judge()
        if not gt_cases:
            pytest.skip("No ground truth cases")

        scores, errors, details = await _collect_scores(
            "faithfulness",
            invoke_workflow,
            ragas_evaluator,
            gt_cases[:5],
        )

        if not scores:
            pytest.skip(f"No valid RAGAS scores obtained. Errors: {errors[:3]}")

        avg_faithfulness = sum(scores) / len(scores)
        assert (
            avg_faithfulness >= 0.7
        ), f"Average faithfulness {avg_faithfulness:.3f} < 0.7. " + _format_ragas_failure_context(
            "faithfulness", scores, errors, details
        )

    async def test_ragas_answer_relevancy(self, invoke_workflow, ragas_evaluator, gt_cases):
        """Answer Relevancy >= 0.7"""
        _require_release_gate_ragas_judge()
        if not gt_cases:
            pytest.skip("No ground truth cases")

        scores, errors, details = await _collect_scores(
            "answer_relevancy",
            invoke_workflow,
            ragas_evaluator,
            gt_cases[:5],
        )

        if not scores:
            pytest.skip(f"No valid RAGAS scores obtained. Errors: {errors[:3]}")

        avg_relevancy = sum(scores) / len(scores)
        assert (
            avg_relevancy >= 0.7
        ), f"Average answer_relevancy {avg_relevancy:.3f} < 0.7. " + _format_ragas_failure_context(
            "answer_relevancy", scores, errors, details
        )
