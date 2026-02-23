"""ルーティング精度ライブE2Eテスト - 実LLMでのルーティング検証"""

import re

import pytest

from backend.tests.fixtures.dataset_loader import DatasetLoader
from backend.tests.utils.evaluators.routing_accuracy import RoutingResult


def _normalize_agent_name(name: str) -> str:
    """エージェント名を正規化（PascalCase → snake_case、末尾Agent除去）

    例: FacilityAgent → facility, GeneralKnowledgeAgent → general_knowledge
    """
    # 末尾の "Agent" を除去
    name = re.sub(r"Agent$", "", name)
    # PascalCase → snake_case
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return name.lower().strip("_")


@pytest.mark.e2e
class TestRoutingLiveE2E:
    """実LLMを使ったルーティング精度テスト"""

    @pytest.fixture
    def routing_cases(self):
        return DatasetLoader.load_routing_test_cases()

    async def test_routing_accuracy_overall(self, invoke_workflow, routing_cases):
        """全ルーティングケースの精度（目標: >=75%）"""
        if len(routing_cases) == 0:
            pytest.skip("No routing test cases")

        # 最大30ケースに制限（APIコスト管理）
        cases = routing_cases[:30]
        results = []

        for case in cases:
            try:
                result = await invoke_workflow(case.query, language=case.language)
                raw_agent = (
                    result.get("metadata", {})
                    .get("routing", {})
                    .get("agent", result.get("metadata", {}).get("agent", "unknown"))
                )
                actual_agent = _normalize_agent_name(raw_agent)

                results.append(
                    RoutingResult(
                        test_case_id=case.id,
                        expected_agent=case.expected_agent,
                        actual_agent=actual_agent,
                        is_correct=(actual_agent == case.expected_agent),
                        confidence=result.get("metadata", {})
                        .get("routing", {})
                        .get("confidence", 0.0),
                    )
                )
            except Exception as e:
                results.append(
                    RoutingResult(
                        test_case_id=case.id,
                        expected_agent=case.expected_agent,
                        actual_agent=f"error: {e}",
                        is_correct=False,
                        confidence=0.0,
                    )
                )

        correct = sum(1 for r in results if r.is_correct)
        total = len(results)
        accuracy = correct / total if total > 0 else 0

        errors = [
            (r.test_case_id, r.expected_agent, r.actual_agent) for r in results if not r.is_correct
        ][:5]
        assert accuracy >= 0.75, (
            f"Routing accuracy {accuracy:.1%} < 75%. "
            f"Correct: {correct}/{total}. "
            f"Errors: {errors}"
        )
