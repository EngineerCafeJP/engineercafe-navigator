"""
評価レポート生成器のテスト
"""

from backend.tests.utils.evaluators.report_generator import (
    EvaluationReportGenerator,
    ComprehensiveEvaluationReport,
    create_report_generator,
)
from backend.tests.utils.evaluators.routing_accuracy import (
    RoutingMetrics,
    AgentMetrics,
    RoutingResult,
)
from backend.tests.utils.evaluators.llm_judge import JudgeResult


class TestEvaluationReportGenerator:
    """EvaluationReportGeneratorのテスト"""

    def test_initialization(self, tmp_path):
        """初期化テスト"""
        generator = EvaluationReportGenerator(reports_dir=tmp_path)
        assert generator.reports_dir == tmp_path

    def test_default_reports_dir(self):
        """デフォルトレポートディレクトリ"""
        generator = EvaluationReportGenerator()
        assert generator.reports_dir.exists()

    def test_generate_report_with_routing_metrics(self, report_generator):
        """ルーティングメトリクス付きレポート生成"""
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

        routing_metrics = RoutingMetrics(
            overall_accuracy=0.85,
            category_accuracy=0.80,
            agent_metrics={"facility": agent1, "event": agent2},
            total_test_cases=20,
            correct_predictions=17,
            average_confidence=0.88,
        )

        report = report_generator.generate_report(routing_metrics=routing_metrics)

        assert isinstance(report, ComprehensiveEvaluationReport)
        assert report.routing_metrics is not None
        assert report.routing_metrics["overall_accuracy"] == 0.85
        assert len(report.agent_summaries) == 2

    def test_generate_report_with_llm_judge_results(self, report_generator):
        """LLM Judge結果付きレポート生成"""
        llm_results = [
            JudgeResult(
                dimension="accuracy",
                score=0.85,
                passed=True,
                reasoning="正確な回答",
                threshold=0.7,
            ),
            JudgeResult(
                dimension="relevance",
                score=0.90,
                passed=True,
                reasoning="関連性が高い",
                threshold=0.7,
            ),
            JudgeResult(
                dimension="accuracy",
                score=0.60,
                passed=False,
                reasoning="やや不正確",
                threshold=0.7,
            ),
        ]

        report = report_generator.generate_report(llm_judge_results=llm_results)

        assert report.llm_judge_summary is not None
        assert report.llm_judge_summary["total_evaluations"] == 3
        assert "accuracy" in report.llm_judge_summary["average_scores"]
        assert "relevance" in report.llm_judge_summary["average_scores"]

    def test_generate_report_with_error_summary(self, report_generator):
        """エラーサマリー付きレポート生成"""
        routing_results = [
            RoutingResult(
                test_case_id="1",
                expected_agent="facility",
                actual_agent="event",
                is_correct=False,
                confidence=0.6,
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
                actual_agent="business_info",
                is_correct=False,
                confidence=0.85,
            ),
        ]

        report = report_generator.generate_report(routing_results=routing_results)

        assert report.error_summary is not None
        assert report.error_summary["total_errors"] == 3
        assert "top_confusion_pairs" in report.error_summary

    def test_generate_report_with_confidence_analysis(self, report_generator):
        """信頼度分析付きレポート生成"""
        confidence_analysis = {
            0.5: {"coverage": 0.95, "accuracy": 0.80, "count": 19},
            0.8: {"coverage": 0.70, "accuracy": 0.93, "count": 14},
            0.9: {"coverage": 0.50, "accuracy": 0.98, "count": 10},
        }

        report = report_generator.generate_report(confidence_analysis=confidence_analysis)

        assert report.confidence_analysis is not None
        assert 0.8 in report.confidence_analysis

    def test_generate_recommendations_low_accuracy(self, report_generator):
        """低精度時の推奨事項生成"""
        agent1 = AgentMetrics(
            agent_name="facility",
            true_positives=5,
            false_positives=5,
            false_negatives=3,
        )

        routing_metrics = RoutingMetrics(
            overall_accuracy=0.60,
            category_accuracy=0.55,
            agent_metrics={"facility": agent1},
            total_test_cases=20,
            correct_predictions=12,
            average_confidence=0.75,
        )

        report = report_generator.generate_report(routing_metrics=routing_metrics)

        assert len(report.recommendations) > 0
        assert any("精度" in rec or "80%" in rec for rec in report.recommendations)

    def test_save_and_load_report(self, report_generator, tmp_path):
        """レポートの保存と読み込み"""
        report = report_generator.generate_report(
            metadata={"test": True},
        )

        filepath = report_generator.save_report(report)
        assert filepath.exists()

        loaded_report = report_generator.load_report(filepath.name)
        assert loaded_report is not None
        assert loaded_report.report_id == report.report_id
        assert loaded_report.metadata == {"test": True}

    def test_load_nonexistent_report(self, report_generator):
        """存在しないレポートの読み込み"""
        result = report_generator.load_report("nonexistent.json")
        assert result is None

    def test_list_reports(self, report_generator):
        """レポート一覧取得"""
        report1 = report_generator.generate_report()
        report_generator.save_report(report1, "evaluation_report_001.json")

        report2 = report_generator.generate_report()
        report_generator.save_report(report2, "evaluation_report_002.json")

        reports = report_generator.list_reports()

        assert len(reports) >= 2
        for report_meta in reports:
            assert "filename" in report_meta
            assert "report_id" in report_meta

    def test_get_trend_data(self, report_generator, tmp_path):
        """トレンドデータ取得"""
        agent = AgentMetrics(
            agent_name="facility",
            true_positives=8,
            false_positives=2,
            false_negatives=1,
        )

        for i, accuracy in enumerate([0.80, 0.82, 0.85]):
            routing_metrics = RoutingMetrics(
                overall_accuracy=accuracy,
                category_accuracy=0.75,
                agent_metrics={"facility": agent},
                total_test_cases=20,
                correct_predictions=int(20 * accuracy),
                average_confidence=0.88,
            )
            report = report_generator.generate_report(routing_metrics=routing_metrics)
            report_generator.save_report(report, f"evaluation_report_trend_{i}.json")

        trend = report_generator.get_trend_data("overall_accuracy", limit=10)

        assert len(trend) >= 3
        for point in trend:
            assert "timestamp" in point
            assert "value" in point

    def test_compare_reports(self, report_generator):
        """レポート比較"""
        agent = AgentMetrics(
            agent_name="facility",
            true_positives=8,
            false_positives=2,
            false_negatives=1,
        )

        metrics1 = RoutingMetrics(
            overall_accuracy=0.80,
            category_accuracy=0.75,
            agent_metrics={"facility": agent},
            total_test_cases=20,
            correct_predictions=16,
            average_confidence=0.85,
        )
        report1 = report_generator.generate_report(routing_metrics=metrics1)
        report_generator.save_report(report1, "report_before.json")

        metrics2 = RoutingMetrics(
            overall_accuracy=0.90,
            category_accuracy=0.85,
            agent_metrics={"facility": agent},
            total_test_cases=20,
            correct_predictions=18,
            average_confidence=0.90,
        )
        report2 = report_generator.generate_report(routing_metrics=metrics2)
        report_generator.save_report(report2, "report_after.json")

        comparison = report_generator.compare_reports("report_before.json", "report_after.json")

        assert "routing_metrics_diff" in comparison
        assert comparison["routing_metrics_diff"]["overall_accuracy"]["improved"] is True
        assert abs(comparison["routing_metrics_diff"]["overall_accuracy"]["diff"] - 0.10) < 0.001


class TestComprehensiveEvaluationReport:
    """ComprehensiveEvaluationReportのテスト"""

    def test_report_creation(self):
        """レポート作成"""
        report = ComprehensiveEvaluationReport(
            report_id="20250207_120000",
            timestamp="2025-02-07T12:00:00",
            routing_metrics={"overall_accuracy": 0.85},
            recommendations=["推奨事項1"],
        )

        assert report.report_id == "20250207_120000"
        assert report.routing_metrics["overall_accuracy"] == 0.85
        assert len(report.recommendations) == 1


class TestCreateReportGenerator:
    """create_report_generator関数のテスト"""

    def test_create_default(self):
        """デフォルト設定で作成"""
        generator = create_report_generator()
        assert isinstance(generator, EvaluationReportGenerator)

    def test_create_with_custom_dir(self, tmp_path):
        """カスタムディレクトリで作成"""
        generator = create_report_generator(reports_dir=tmp_path)
        assert generator.reports_dir == tmp_path
