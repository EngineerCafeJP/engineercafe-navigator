"""
ルーティング精度評価器のテスト
"""

import pytest

from backend.tests.utils.evaluators.routing_accuracy import (
    RoutingAccuracyEvaluator,
    RoutingTestCase,
    RoutingResult,
    RoutingMetrics,
    AgentMetrics,
    create_routing_evaluator,
)
from backend.tests.fixtures.dataset_loader import DatasetLoader


class TestRoutingTestCase:
    """RoutingTestCaseのテスト"""

    def test_creation(self):
        """テストケース作成"""
        case = RoutingTestCase(
            id="rt-001",
            query="Wi-Fiのパスワードを教えてください",
            expected_agent="facility",
            expected_category="facility-info",
            language="ja",
            tags=["fast-path", "facility"],
        )

        assert case.id == "rt-001"
        assert case.expected_agent == "facility"
        assert "fast-path" in case.tags


class TestRoutingResult:
    """RoutingResultのテスト"""

    def test_correct_result(self):
        """正しいルーティング結果"""
        result = RoutingResult(
            test_case_id="rt-001",
            expected_agent="facility",
            actual_agent="facility",
            is_correct=True,
            confidence=0.95,
        )

        assert result.is_correct is True
        assert result.confidence == 0.95

    def test_incorrect_result(self):
        """間違ったルーティング結果"""
        result = RoutingResult(
            test_case_id="rt-002",
            expected_agent="facility",
            actual_agent="event",
            is_correct=False,
            confidence=0.60,
        )

        assert result.is_correct is False


class TestAgentMetrics:
    """AgentMetricsのテスト"""

    def test_precision_calculation(self):
        """精度計算"""
        metrics = AgentMetrics(
            agent_name="facility",
            true_positives=8,
            false_positives=2,
            false_negatives=1,
        )

        assert metrics.precision == 0.8  # 8 / (8 + 2)

    def test_recall_calculation(self):
        """再現率計算"""
        metrics = AgentMetrics(
            agent_name="facility",
            true_positives=8,
            false_positives=2,
            false_negatives=2,
        )

        assert metrics.recall == 0.8  # 8 / (8 + 2)

    def test_f1_score_calculation(self):
        """F1スコア計算"""
        metrics = AgentMetrics(
            agent_name="facility",
            true_positives=8,
            false_positives=2,
            false_negatives=2,
        )

        expected_f1 = 2 * (0.8 * 0.8) / (0.8 + 0.8)
        assert metrics.f1_score == expected_f1

    def test_zero_division_handling(self):
        """ゼロ除算の処理"""
        metrics = AgentMetrics(
            agent_name="unused",
            true_positives=0,
            false_positives=0,
            false_negatives=0,
        )

        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0


class TestRoutingAccuracyEvaluator:
    """RoutingAccuracyEvaluatorのテスト"""

    @pytest.mark.asyncio
    async def test_evaluate_single_correct(self, routing_evaluator):
        """単一テストケース評価（正解）"""
        case = RoutingTestCase(
            id="rt-001",
            query="Wi-Fiのパスワード",
            expected_agent="facility",
        )

        result = await routing_evaluator.evaluate_single(
            test_case=case,
            actual_agent="facility",
            confidence=0.95,
        )

        assert result.is_correct is True
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_evaluate_single_incorrect(self, routing_evaluator):
        """単一テストケース評価（不正解）"""
        case = RoutingTestCase(
            id="rt-002",
            query="Wi-Fiのパスワード",
            expected_agent="facility",
        )

        result = await routing_evaluator.evaluate_single(
            test_case=case,
            actual_agent="event",
            confidence=0.60,
        )

        assert result.is_correct is False

    @pytest.mark.asyncio
    async def test_evaluate_batch(
        self, routing_evaluator, fast_path_test_cases, sample_routing_results
    ):
        """バッチ評価"""
        # テストケースを必要な数だけ取得
        cases = fast_path_test_cases[: len(sample_routing_results)]

        results = await routing_evaluator.evaluate_batch(
            test_cases=cases,
            routing_results=sample_routing_results,
        )

        assert len(results) == len(cases)
        for result in results:
            assert isinstance(result, RoutingResult)

    @pytest.mark.asyncio
    async def test_evaluate_batch_with_router_func(self, mock_router_func):
        """ルーター関数を使用したバッチ評価"""
        evaluator = RoutingAccuracyEvaluator(router_func=mock_router_func)

        cases = [
            RoutingTestCase(
                id="rt-001",
                query="Wi-Fiのパスワードを教えて",
                expected_agent="facility",
                language="ja",
            ),
            RoutingTestCase(
                id="rt-002",
                query="さっき何を聞いたっけ",
                expected_agent="general_knowledge",
                language="ja",
            ),
        ]

        results = await evaluator.evaluate_batch(test_cases=cases)

        assert len(results) == 2
        assert results[0].actual_agent == "facility"
        assert results[1].actual_agent == "general_knowledge"

    def test_compute_metrics(self, routing_evaluator):
        """メトリクス計算"""
        routing_evaluator.results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.9,
            ),
            RoutingResult(
                test_case_id="2",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.85,
            ),
            RoutingResult(
                test_case_id="3",
                expected_agent="event",
                actual_agent="facility",
                is_correct=False,
                confidence=0.6,
            ),
            RoutingResult(
                test_case_id="4",
                expected_agent="event",
                actual_agent="event",
                is_correct=True,
                confidence=0.95,
            ),
        ]

        metrics = routing_evaluator.compute_metrics()

        assert metrics.total_test_cases == 4
        assert metrics.correct_predictions == 3
        assert metrics.overall_accuracy == 0.75
        assert "facility" in metrics.agent_metrics
        assert "event" in metrics.agent_metrics

    def test_analyze_confidence_thresholds(self, routing_evaluator):
        """信頼度閾値分析"""
        routing_evaluator.results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.95,
            ),
            RoutingResult(
                test_case_id="2",
                expected_agent="facility",
                actual_agent="event",
                is_correct=False,
                confidence=0.4,
            ),
            RoutingResult(
                test_case_id="3",
                expected_agent="event",
                actual_agent="event",
                is_correct=True,
                confidence=0.85,
            ),
        ]

        analysis = routing_evaluator.analyze_confidence_thresholds(thresholds=[0.5, 0.8, 0.9])

        assert 0.5 in analysis
        assert 0.8 in analysis
        assert 0.9 in analysis
        assert analysis[0.5]["coverage"] > analysis[0.9]["coverage"]

    def test_analyze_by_tags(self, routing_evaluator):
        """タグ別分析"""
        routing_evaluator.results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.9,
                metadata={"tags": ["fast-path", "facility"]},
            ),
            RoutingResult(
                test_case_id="2",
                expected_agent="event",
                actual_agent="event",
                is_correct=True,
                confidence=0.85,
                metadata={"tags": ["event"]},
            ),
            RoutingResult(
                test_case_id="3",
                expected_agent="facility",
                actual_agent="event",
                is_correct=False,
                confidence=0.6,
                metadata={"tags": ["fast-path", "facility"]},
            ),
        ]

        analysis = routing_evaluator.analyze_by_tags()

        assert "fast-path" in analysis
        assert "facility" in analysis
        assert "event" in analysis
        assert analysis["event"]["accuracy"] == 1.0

    def test_analyze_by_language(self, routing_evaluator):
        """言語別分析"""
        routing_evaluator.results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.9,
                metadata={"language": "ja"},
            ),
            RoutingResult(
                test_case_id="2",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.85,
                metadata={"language": "en"},
            ),
        ]

        analysis = routing_evaluator.analyze_by_language()

        assert "ja" in analysis
        assert "en" in analysis

    def test_get_confusion_matrix(self, routing_evaluator):
        """混同行列取得"""
        routing_evaluator.results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.9,
            ),
            RoutingResult(
                test_case_id="2",
                expected_agent="event",
                actual_agent="facility",
                is_correct=False,
                confidence=0.6,
            ),
        ]

        matrix = routing_evaluator.get_confusion_matrix()

        assert matrix["facility"]["facility"] == 1
        assert matrix["event"]["facility"] == 1

    def test_get_error_cases(self, routing_evaluator):
        """エラーケース取得"""
        routing_evaluator.results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.9,
            ),
            RoutingResult(
                test_case_id="2",
                expected_agent="event",
                actual_agent="facility",
                is_correct=False,
                confidence=0.6,
            ),
        ]

        errors = routing_evaluator.get_error_cases()

        assert len(errors) == 1
        assert errors[0].test_case_id == "2"

    def test_clear_results(self, routing_evaluator):
        """結果クリア"""
        routing_evaluator.results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="facility",
                is_correct=True,
                confidence=0.9,
            ),
        ]

        routing_evaluator.clear_results()

        assert len(routing_evaluator.results) == 0


class TestDatasetLoader:
    """DatasetLoaderのテスト"""

    def test_load_routing_test_cases(self):
        """ルーティングテストケース読み込み"""
        cases = DatasetLoader.load_routing_test_cases()
        assert len(cases) > 0
        for case in cases:
            assert isinstance(case, RoutingTestCase)

    def test_load_routing_test_cases_by_language(self):
        """言語フィルタ付きルーティングテストケース"""
        ja_cases = DatasetLoader.load_routing_test_cases(language="ja")
        en_cases = DatasetLoader.load_routing_test_cases(language="en")

        for case in ja_cases:
            assert case.language == "ja"

        for case in en_cases:
            assert case.language == "en"

    def test_load_routing_test_cases_by_tags(self):
        """タグフィルタ付きルーティングテストケース"""
        fast_path_cases = DatasetLoader.load_routing_test_cases(tags=["fast-path"])

        for case in fast_path_cases:
            assert "fast-path" in case.tags

    def test_load_fast_path_cases(self):
        """Fast-pathテストケース読み込み"""
        cases = DatasetLoader.load_fast_path_cases()
        assert len(cases) > 0
        for case in cases:
            assert "fast-path" in case.tags

    def test_load_memory_cases(self):
        """メモリ関連テストケース読み込み"""
        cases = DatasetLoader.load_memory_cases()
        assert len(cases) > 0
        for case in cases:
            assert "memory" in case.tags

    def test_load_multilingual_cases(self):
        """多言語テストケース読み込み"""
        cases = DatasetLoader.load_multilingual_cases()

        assert "ja" in cases
        assert "en" in cases
        assert len(cases["ja"]) > 0
        assert len(cases["en"]) > 0

    def test_get_dataset_info(self):
        """データセット情報取得"""
        info = DatasetLoader.get_dataset_info()

        assert "routing_test_cases" in info
        assert "answer_quality_cases" in info
        assert "languages" in info
        assert "agents" in info
        assert "tags" in info


class TestCreateRoutingEvaluator:
    """create_routing_evaluator関数のテスト"""

    def test_create_without_router(self):
        """ルーター関数なしで作成"""
        evaluator = create_routing_evaluator()
        assert isinstance(evaluator, RoutingAccuracyEvaluator)
        assert evaluator.router_func is None

    def test_create_with_router(self, mock_router_func):
        """ルーター関数付きで作成"""
        evaluator = create_routing_evaluator(router_func=mock_router_func)
        assert evaluator.router_func is not None


class TestRoutingMetrics:
    """RoutingMetricsのテスト"""

    def test_macro_metrics(self):
        """マクロ平均メトリクス"""
        agent1 = AgentMetrics(
            agent_name="facility",
            true_positives=8,
            false_positives=2,
            false_negatives=1,
        )
        agent2 = AgentMetrics(
            agent_name="event",
            true_positives=6,
            false_positives=1,
            false_negatives=2,
        )

        metrics = RoutingMetrics(
            overall_accuracy=0.85,
            category_accuracy=0.80,
            agent_metrics={"facility": agent1, "event": agent2},
            total_test_cases=20,
            correct_predictions=17,
            average_confidence=0.88,
        )

        assert metrics.macro_precision > 0
        assert metrics.macro_recall > 0
        assert metrics.macro_f1 > 0
