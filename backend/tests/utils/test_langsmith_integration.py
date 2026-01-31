"""
LangSmith統合のテスト
"""

import pytest
from tests.utils.langsmith_integration import (
    LangSmithEvaluator,
    AgentEvaluationReport,
    EvaluationResult,
    evaluate_answer_presence,
    evaluate_emotion_validity,
    evaluate_response_format,
    evaluate_language_consistency,
    create_langsmith_evaluator,
    run_agent_evaluation,
)


class TestEvaluationFunctions:
    """評価関数のテスト"""

    @pytest.mark.asyncio
    async def test_evaluate_answer_presence_with_answer(self):
        """回答がある場合のテスト"""
        output = {"answer": "Wi-Fiは無料で利用できます。"}
        score = await evaluate_answer_presence(output)
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_answer_presence_without_answer(self):
        """回答がない場合のテスト"""
        output = {"emotion": "neutral"}
        score = await evaluate_answer_presence(output)
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_answer_presence_empty_answer(self):
        """空の回答の場合のテスト"""
        output = {"answer": "   "}
        score = await evaluate_answer_presence(output)
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_emotion_validity_valid(self):
        """有効な感情タグのテスト"""
        for emotion in ["neutral", "happy", "sad", "surprised", "relaxed", "angry"]:
            output = {"emotion": emotion}
            score = await evaluate_emotion_validity(output)
            assert score == 1.0, f"Failed for emotion: {emotion}"

    @pytest.mark.asyncio
    async def test_evaluate_emotion_validity_invalid(self):
        """無効な感情タグのテスト"""
        output = {"emotion": "excited"}
        score = await evaluate_emotion_validity(output)
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_response_format_complete(self):
        """完全なレスポンス形式のテスト"""
        output = {"answer": "テスト回答", "emotion": "neutral"}
        score = await evaluate_response_format(output)
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_response_format_partial(self):
        """部分的なレスポンス形式のテスト"""
        output = {"answer": "テスト回答"}
        score = await evaluate_response_format(output)
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_evaluate_language_consistency_japanese(self):
        """日本語の一貫性テスト"""
        output = {"answer": "これは日本語のテストです。"}
        score = await evaluate_language_consistency(output)
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_language_consistency_english(self):
        """英語の一貫性テスト"""
        output = {"answer": "This is an English test."}
        score = await evaluate_language_consistency(output)
        assert score == 1.0


class TestLangSmithEvaluator:
    """LangSmithEvaluatorのテスト"""

    def test_create_evaluator(self):
        """評価器の作成テスト"""
        evaluator = create_langsmith_evaluator()
        assert isinstance(evaluator, LangSmithEvaluator)
        assert evaluator.project_name == "engineer-cafe-navigator"

    def test_create_evaluator_custom_project(self):
        """カスタムプロジェクト名での評価器作成テスト"""
        evaluator = create_langsmith_evaluator("custom-project")
        assert evaluator.project_name == "custom-project"

    @pytest.mark.asyncio
    async def test_evaluate_agent_basic(self):
        """基本的なエージェント評価テスト"""
        evaluator = LangSmithEvaluator()

        test_cases = [
            {
                "output": {"answer": "Wi-Fiは無料です。", "emotion": "neutral"},
                "expected": {},
            }
        ]

        report = await evaluator.evaluate_agent("TestAgent", test_cases)

        assert isinstance(report, AgentEvaluationReport)
        assert report.agent_name == "TestAgent"
        assert len(report.results) > 0

    @pytest.mark.asyncio
    async def test_evaluate_agent_multiple_cases(self):
        """複数テストケースでのエージェント評価"""
        evaluator = LangSmithEvaluator()

        test_cases = [
            {
                "output": {"answer": "営業時間は10時から22時です。", "emotion": "happy"},
                "expected": {},
            },
            {
                "output": {"answer": "地下にはMTGスペースがあります。", "emotion": "neutral"},
                "expected": {},
            },
            {
                "output": {"answer": "申し訳ありません、分かりません。", "emotion": "sad"},
                "expected": {},
            },
        ]

        report = await evaluator.evaluate_agent("FacilityAgent", test_cases)

        assert report.agent_name == "FacilityAgent"
        assert report.metadata["total_tests"] == 3

    @pytest.mark.asyncio
    async def test_evaluate_agent_all_pass(self):
        """全テスト合格のケース"""
        evaluator = LangSmithEvaluator()

        test_cases = [
            {
                "output": {"answer": "完璧な回答です。", "emotion": "happy"},
                "expected": {},
            }
        ]

        report = await evaluator.evaluate_agent("PerfectAgent", test_cases)

        assert report.overall_passed is True
        assert report.pass_rate >= 0.8


class TestAgentEvaluationReport:
    """AgentEvaluationReportのテスト"""

    def test_report_creation(self):
        """レポート作成テスト"""
        result = EvaluationResult(
            metric_name="test_metric",
            score=0.9,
            passed=True,
            threshold=0.7,
        )

        report = AgentEvaluationReport(
            agent_name="TestAgent",
            timestamp="2025-01-24T10:00:00",
            overall_passed=True,
            pass_rate=0.9,
            results=[result],
        )

        assert report.agent_name == "TestAgent"
        assert report.overall_passed is True
        assert len(report.results) == 1


class TestRunAgentEvaluation:
    """run_agent_evaluation関数のテスト"""

    @pytest.mark.asyncio
    async def test_run_evaluation(self):
        """評価実行テスト"""
        test_cases = [
            {
                "output": {"answer": "テスト回答", "emotion": "neutral"},
                "expected": {},
            }
        ]

        report = await run_agent_evaluation("TestAgent", test_cases)

        assert isinstance(report, AgentEvaluationReport)
        assert report.agent_name == "TestAgent"


class TestLangSmithClientIntegration:
    """LangSmithクライアント統合テスト（モック使用）"""

    @pytest.mark.asyncio
    async def test_trace_agent_run_without_client(self):
        """クライアントなしでのトレーステスト"""
        evaluator = LangSmithEvaluator()
        evaluator.client = None

        result = await evaluator.trace_agent_run(
            agent_name="TestAgent",
            inputs={"query": "test"},
            outputs={"answer": "response"},
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_create_dataset_without_client(self):
        """クライアントなしでのデータセット作成テスト"""
        evaluator = LangSmithEvaluator()
        evaluator.client = None

        result = await evaluator.create_dataset(
            dataset_name="test-dataset",
            examples=[{"inputs": {}, "outputs": {}}],
        )

        assert result is None

    def test_get_evaluation_summary(self):
        """評価サマリー生成テスト"""
        evaluator = LangSmithEvaluator()

        reports = [
            AgentEvaluationReport(
                agent_name="Agent1",
                timestamp="2025-01-24T10:00:00",
                overall_passed=True,
                pass_rate=0.9,
            ),
            AgentEvaluationReport(
                agent_name="Agent2",
                timestamp="2025-01-24T10:00:00",
                overall_passed=False,
                pass_rate=0.6,
            ),
        ]

        summary = evaluator.get_evaluation_summary(reports)

        assert summary["total_agents"] == 2
        assert summary["passed_agents"] == 1
        assert summary["overall_pass_rate"] == 0.5
        assert "Agent1" in summary["agent_results"]
        assert "Agent2" in summary["agent_results"]
