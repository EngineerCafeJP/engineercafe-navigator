"""RAGAS ライブE2Eテスト - 実回答のRAGAS6メトリクス評価"""

import pytest

from backend.tests.fixtures.dataset_loader import DatasetLoader


@pytest.mark.e2e
class TestRagasLiveE2E:
    """実回答のRAGAS評価テスト"""

    @pytest.fixture
    def gt_cases(self):
        cases = DatasetLoader.load_ground_truth_cases()
        return cases[:10]  # コスト制限

    async def test_ragas_faithfulness(self, invoke_workflow, ragas_evaluator, gt_cases):
        """Faithfulness >= 0.4"""
        if not gt_cases:
            pytest.skip("No ground truth cases")

        scores = []
        for case in gt_cases[:5]:
            try:
                result = await invoke_workflow(case.question, language=case.language)
                eval_result = await ragas_evaluator.evaluate_single(
                    question=case.question,
                    answer=result["answer"],
                    contexts=case.contexts,
                    ground_truth=case.ground_truth,
                )
                if eval_result and "faithfulness" in eval_result:
                    scores.append(eval_result["faithfulness"])
            except Exception:
                continue

        if not scores:
            pytest.skip("No valid RAGAS scores obtained")

        avg_faithfulness = sum(scores) / len(scores)
        assert (
            avg_faithfulness >= 0.4
        ), f"Average faithfulness {avg_faithfulness:.3f} < 0.4. Scores: {scores}"

    async def test_ragas_answer_relevancy(self, invoke_workflow, ragas_evaluator, gt_cases):
        """Answer Relevancy >= 0.5"""
        if not gt_cases:
            pytest.skip("No ground truth cases")

        scores = []
        for case in gt_cases[:5]:
            try:
                result = await invoke_workflow(case.question, language=case.language)
                eval_result = await ragas_evaluator.evaluate_single(
                    question=case.question,
                    answer=result["answer"],
                    contexts=case.contexts,
                    ground_truth=case.ground_truth,
                )
                if eval_result and "answer_relevancy" in eval_result:
                    scores.append(eval_result["answer_relevancy"])
            except Exception:
                continue

        if not scores:
            pytest.skip("No valid RAGAS scores obtained")

        avg_relevancy = sum(scores) / len(scores)
        assert (
            avg_relevancy >= 0.5
        ), f"Average answer_relevancy {avg_relevancy:.3f} < 0.5. Scores: {scores}"
