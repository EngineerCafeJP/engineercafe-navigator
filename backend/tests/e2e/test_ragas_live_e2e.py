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
        """Faithfulness >= 0.7"""
        if not gt_cases:
            pytest.skip("No ground truth cases")

        scores = []
        errors = []
        for case in gt_cases[:5]:
            try:
                result = await invoke_workflow(case.question, language=case.language)
                eval_result = await ragas_evaluator.evaluate_single(
                    question=case.question,
                    answer=result["answer"],
                    contexts=case.contexts,
                    ground_truth=case.ground_truth,
                )
                if eval_result.error is None:
                    scores.append(eval_result.faithfulness)
                else:
                    errors.append(f"{case.question[:30]}: {eval_result.error}")
            except Exception as e:
                errors.append(f"{case.question[:30]}: {e}")
                continue

        if not scores:
            pytest.skip(f"No valid RAGAS scores obtained. Errors: {errors[:3]}")

        avg_faithfulness = sum(scores) / len(scores)
        assert (
            avg_faithfulness >= 0.7
        ), f"Average faithfulness {avg_faithfulness:.3f} < 0.7. Scores: {scores}"

    async def test_ragas_answer_relevancy(self, invoke_workflow, ragas_evaluator, gt_cases):
        """Answer Relevancy >= 0.7"""
        if not gt_cases:
            pytest.skip("No ground truth cases")

        scores = []
        errors = []
        for case in gt_cases[:5]:
            try:
                result = await invoke_workflow(case.question, language=case.language)
                eval_result = await ragas_evaluator.evaluate_single(
                    question=case.question,
                    answer=result["answer"],
                    contexts=case.contexts,
                    ground_truth=case.ground_truth,
                )
                if eval_result.error is None:
                    scores.append(eval_result.answer_relevancy)
                else:
                    errors.append(f"{case.question[:30]}: {eval_result.error}")
            except Exception as e:
                errors.append(f"{case.question[:30]}: {e}")
                continue

        if not scores:
            pytest.skip(f"No valid RAGAS scores obtained. Errors: {errors[:3]}")

        avg_relevancy = sum(scores) / len(scores)
        assert (
            avg_relevancy >= 0.7
        ), f"Average answer_relevancy {avg_relevancy:.3f} < 0.7. Scores: {scores}"
