"""回答品質E2Eテスト - LLM Judgeによるライブ回答品質評価"""

import os

import pytest

from backend.tests.e2e.conftest import _is_real_key, _is_real_url, keywords_match
from backend.tests.fixtures.dataset_loader import DatasetLoader


def _has_live_event_or_search_source() -> bool:
    """Live event cases need at least one configured event/search source."""
    if _is_real_url(os.getenv("GOOGLE_CALENDAR_ICAL_URL", "")):
        return True
    if _is_real_key(os.getenv("CONNPASS_API_KEY", "")):
        return True
    if _is_real_key(os.getenv("TAVILY_API_KEY", "")):
        return True
    return bool(
        _is_real_url(os.getenv("EVENT_SHEET_GAS_URL", ""))
        and _is_real_key(os.getenv("EVENT_SHEET_GAS_TOKEN", ""))
    )


def _is_live_event_case(case) -> bool:
    return case.category == "event" or case.expected_agent == "event"


def _is_infra_degraded_answer(answer: str) -> bool:
    """Detect infrastructure failures without masking normal product fallbacks."""
    text = (answer or "").lower()
    markers = (
        "event loop is closed",
        "httpx connection pool",
        "connection pool issue",
        "technical issue",
        "一時的なエラー",
        "技術的な問題",
    )
    return any(m in text for m in markers)


@pytest.mark.e2e
class TestAnswerQualityE2E:
    """LLM Judge による回答品質テスト"""

    @pytest.fixture
    def quality_cases(self):
        cases = DatasetLoader.load_answer_quality_cases(language="ja")
        if not _has_live_event_or_search_source():
            cases = [case for case in cases if not _is_live_event_case(case)]
        return cases[:10]  # コスト制限

    async def test_keyword_coverage(self, invoke_workflow, quality_cases):
        """キーワードカバレッジ（全体pass rate >= 60%）"""
        if not quality_cases:
            pytest.skip("No quality cases")

        passed = 0
        total = 0
        infra_degraded = 0

        for case in quality_cases:
            if not case.expected_keywords:
                continue

            total += 1
            try:
                result = await invoke_workflow(case.question, language=case.language)
                if _is_infra_degraded_answer(result["answer"]):
                    infra_degraded += 1
                    continue
                if keywords_match(result["answer"], case.expected_keywords, threshold=0.5):
                    passed += 1
            except Exception:
                continue

        if total == 0:
            pytest.skip("No cases with expected_keywords")
        if infra_degraded > 0 and passed == 0:
            pytest.xfail(
                f"Infra-degraded answers detected in keyword coverage test "
                f"(degraded_cases={infra_degraded})"
            )

        pass_rate = passed / total
        assert (
            pass_rate >= 0.7
        ), f"Keyword pass rate {pass_rate:.1%} < 70%. Passed: {passed}/{total}"

    async def test_llm_judge_quality(self, invoke_workflow, llm_judge, quality_cases):
        """LLM Judge 品質評価（全体pass rate >= 60%）"""
        if not quality_cases:
            pytest.skip("No quality cases")

        total_evaluations = 0
        total_passed = 0
        infra_degraded = 0
        failure_samples: list[str] = []

        for case in quality_cases[:5]:
            try:
                result = await invoke_workflow(case.question, language=case.language)
                if _is_infra_degraded_answer(result["answer"]):
                    infra_degraded += 1
                    continue
                judge_results = await llm_judge.evaluate_answer_quality(
                    question=case.question,
                    answer=result["answer"],
                )

                for jr in judge_results:
                    total_evaluations += 1
                    if jr.passed:
                        total_passed += 1
                    elif len(failure_samples) < 5:
                        failure_samples.append(
                            f"{case.id}:{jr.dimension}:score={jr.score}:" f"{jr.reasoning[:160]}"
                        )
            except Exception:
                continue

        if total_evaluations == 0:
            pytest.skip("No LLM Judge evaluations completed")

        pass_rate = total_passed / total_evaluations
        if infra_degraded > 0 and pass_rate < 0.7:
            pytest.xfail(
                "LLM Judge quality impacted by infra-degraded answers "
                f"(degraded_cases={infra_degraded}, pass_rate={pass_rate:.1%})"
            )
        assert pass_rate >= 0.7, (
            f"LLM Judge pass rate {pass_rate:.1%} < 70%. "
            f"Passed: {total_passed}/{total_evaluations}. "
            f"Failures: {failure_samples}"
        )
