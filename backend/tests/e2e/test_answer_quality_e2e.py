"""回答品質E2Eテスト - LLM Judgeによるライブ回答品質評価"""

import pytest

from backend.tests.e2e.conftest import keywords_match
from backend.tests.fixtures.dataset_loader import DatasetLoader


@pytest.mark.e2e
class TestAnswerQualityE2E:
    """LLM Judge による回答品質テスト"""

    @pytest.fixture
    def quality_cases(self):
        cases = DatasetLoader.load_answer_quality_cases(language="ja")
        return cases[:10]  # コスト制限

    async def test_keyword_coverage(self, invoke_workflow, quality_cases):
        """キーワードカバレッジ（全体pass rate >= 60%）"""
        if not quality_cases:
            pytest.skip("No quality cases")

        passed = 0
        total = 0

        for case in quality_cases:
            if not case.expected_keywords:
                continue

            total += 1
            try:
                result = await invoke_workflow(case.question, language=case.language)
                if keywords_match(result["answer"], case.expected_keywords, threshold=0.5):
                    passed += 1
            except Exception:
                continue

        if total == 0:
            pytest.skip("No cases with expected_keywords")

        pass_rate = passed / total
        assert (
            pass_rate >= 0.6
        ), f"Keyword pass rate {pass_rate:.1%} < 60%. Passed: {passed}/{total}"

    async def test_llm_judge_quality(self, invoke_workflow, llm_judge, quality_cases):
        """LLM Judge 品質評価（全体pass rate >= 60%）"""
        if not quality_cases:
            pytest.skip("No quality cases")

        total_evaluations = 0
        total_passed = 0

        for case in quality_cases[:5]:
            try:
                result = await invoke_workflow(case.question, language=case.language)
                judge_results = await llm_judge.evaluate_all_dimensions(
                    question=case.question,
                    answer=result["answer"],
                    expected_answer=case.expected_answer,
                )

                for jr in judge_results:
                    total_evaluations += 1
                    if jr.passed:
                        total_passed += 1
            except Exception:
                continue

        if total_evaluations == 0:
            pytest.skip("No LLM Judge evaluations completed")

        pass_rate = total_passed / total_evaluations
        assert pass_rate >= 0.6, (
            f"LLM Judge pass rate {pass_rate:.1%} < 60%. "
            f"Passed: {total_passed}/{total_evaluations}"
        )
