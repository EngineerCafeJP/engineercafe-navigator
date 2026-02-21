"""RAGAS Live Evaluation Tests

These tests are marked with @pytest.mark.ragas and require:
  - OPENAI_API_KEY or OPENROUTER_API_KEY environment variable
  - ragas package installed (pip install -e ".[evaluation]")

They are excluded from the default CI test run (`pytest -m "not ragas and not slow"`)
and only executed in the dedicated `backend-test-ragas` CI job.

Usage:
    pytest -m ragas --tb=short -q
"""

import os

import pytest

from backend.evaluation.ragas_pipeline import RagasEvaluator, RagasReport, RagasResult
from backend.tests.fixtures.dataset_loader import DatasetLoader

# Skip entire module if no API key is available
_has_api_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))
pytestmark = [
    pytest.mark.ragas,
    pytest.mark.skipif(not _has_api_key, reason="OPENAI_API_KEY or OPENROUTER_API_KEY required"),
]


class TestRagasGoldenEvaluation:
    """Golden mode: evaluate pre-defined answer/context against ground truth."""

    @pytest.fixture()
    def evaluator(self):
        """Create a RagasEvaluator with limited cases for CI speed."""
        return RagasEvaluator(max_cases=3)

    @pytest.fixture()
    def ground_truth_cases(self):
        """Load ground truth dataset (first 3 cases)."""
        cases = DatasetLoader.load_ground_truth_cases(language="ja")
        assert len(cases) > 0, "No ground truth cases found in golden_datasets/"
        return cases[:3]

    def test_evaluator_is_available(self, evaluator):
        """RAGAS library should be importable when evaluation extra is installed."""
        if not evaluator.is_available:
            pytest.skip("ragas package not installed")

    @pytest.mark.asyncio()
    async def test_single_case_evaluation(self, evaluator, ground_truth_cases):
        """Evaluate a single ground truth case and verify result structure."""
        if not evaluator.is_available:
            pytest.skip("ragas package not installed")

        case = ground_truth_cases[0]
        result = await evaluator.evaluate_single(
            question=case.question,
            answer=case.answer,
            contexts=case.contexts,
            ground_truth=case.ground_truth,
        )

        assert isinstance(result, RagasResult)
        assert result.error is None, f"Evaluation error: {result.error}"
        assert result.question == case.question

        # Print scores to stdout (visible with pytest -s)
        metrics = (
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "answer_similarity",
        )
        print("\n=== RAGAS Evaluation Scores ===")
        for metric in metrics:
            score = getattr(result, metric, None)
            if score is not None:
                print(f"  {metric:<22} {score:.4f}")
            else:
                print(f"  {metric:<22} N/A")
        print("===============================")

        # Scores should be between 0 and 1
        for metric in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            score = getattr(result, metric)
            assert 0.0 <= score <= 1.0, f"{metric} score {score} out of range"

    @pytest.mark.asyncio()
    async def test_batch_evaluation(self, evaluator, ground_truth_cases):
        """Evaluate a batch of ground truth cases."""
        if not evaluator.is_available:
            pytest.skip("ragas package not installed")

        eval_dicts = [
            {
                "question": c.question,
                "answer": c.answer,
                "contexts": c.contexts,
                "ground_truth": c.ground_truth,
            }
            for c in ground_truth_cases
        ]

        report = await evaluator.evaluate_batch(eval_dicts)

        assert isinstance(report, RagasReport)
        assert report.evaluated_cases > 0
        assert report.metrics, "Metrics summary should not be empty"

        # Print batch scores to stdout (visible with pytest -s)
        print("\n=== RAGAS Evaluation Scores ===")
        for metric in (
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "answer_similarity",
        ):
            score = report.metrics.get(metric)
            if score is not None:
                print(f"  {metric:<22} {score:.4f}")
            else:
                print(f"  {metric:<22} N/A")
        print("===============================")

        # All 6 metrics should be present
        for metric in (
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "answer_similarity",
        ):
            assert metric in report.metrics, f"Missing metric: {metric}"
            assert 0.0 <= report.metrics[metric] <= 1.0

    @pytest.mark.asyncio()
    async def test_evaluation_quality_baseline(self, evaluator, ground_truth_cases):
        """Golden data should achieve reasonable scores (baseline > 0.5)."""
        if not evaluator.is_available:
            pytest.skip("ragas package not installed")

        case = ground_truth_cases[0]
        result = await evaluator.evaluate_single(
            question=case.question,
            answer=case.answer,
            contexts=case.contexts,
            ground_truth=case.ground_truth,
        )

        assert result.error is None, f"Evaluation error: {result.error}"
        # Golden data with matching context should score > 0.5 on faithfulness
        assert (
            result.faithfulness >= 0.5
        ), f"Faithfulness {result.faithfulness} below baseline for golden data"


class TestRagasLiveEvaluation:
    """Live mode: call actual RAG pipeline for evaluation.

    These tests require both API keys AND a running Supabase instance.
    They are informational and help validate end-to-end RAG quality.
    """

    @pytest.fixture()
    def has_supabase(self):
        """Check if Supabase connection details are available."""
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key or "placeholder" in url:
            pytest.skip("SUPABASE_URL and SUPABASE_KEY required for live evaluation")
        return True

    @pytest.mark.asyncio()
    async def test_live_response_generation(self, has_supabase):
        """Test that _generate_live_response works with real RAG pipeline."""
        from backend.tests.evaluation.run_ragas_evaluation import _generate_live_response

        answer, contexts = await _generate_live_response(
            question="エンジニアカフェの営業時間は？",
            language="ja",
            category="hours",
        )

        # Live response should return non-empty results
        assert len(answer) > 0, "Live response should not be empty"
        assert len(contexts) > 0, "Live contexts should not be empty"
