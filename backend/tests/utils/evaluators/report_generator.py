"""
評価レポート生成器

ルーティング精度評価とLLM Judge評価の結果を統合したレポートを生成します。
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from tests.utils.evaluators.llm_judge import JudgeResult
from tests.utils.evaluators.routing_accuracy import RoutingMetrics, RoutingResult


@dataclass
class AgentEvaluationSummary:
    """エージェント別評価サマリー"""

    agent_name: str
    precision: float
    recall: float
    f1_score: float
    true_positives: int
    false_positives: int
    false_negatives: int


@dataclass
class LLMJudgeSummary:
    """LLM Judge評価サマリー"""

    total_evaluations: int
    average_scores: Dict[str, float]
    pass_rates: Dict[str, float]
    overall_pass_rate: float


@dataclass
class ComprehensiveEvaluationReport:
    """総合評価レポート"""

    report_id: str
    timestamp: str
    routing_metrics: Optional[Dict[str, Any]] = None
    llm_judge_summary: Optional[Dict[str, Any]] = None
    agent_summaries: List[Dict[str, Any]] = field(default_factory=list)
    confidence_analysis: Optional[Dict[str, Any]] = None
    language_analysis: Optional[Dict[str, Any]] = None
    tag_analysis: Optional[Dict[str, Any]] = None
    error_summary: Optional[Dict[str, Any]] = None
    ragas_metrics: Optional[Dict[str, float]] = None
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvaluationReportGenerator:
    """
    評価レポート生成器

    複数の評価結果を統合して包括的なレポートを生成します。
    """

    def __init__(self, reports_dir: Optional[Path] = None):
        """
        初期化

        Args:
            reports_dir: レポート保存ディレクトリ
        """
        self.reports_dir = reports_dir or Path(__file__).parent.parent.parent / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        routing_metrics: Optional[RoutingMetrics] = None,
        llm_judge_results: Optional[List[JudgeResult]] = None,
        routing_results: Optional[List[RoutingResult]] = None,
        confidence_analysis: Optional[Dict[float, Dict[str, float]]] = None,
        language_analysis: Optional[Dict[str, Dict[str, float]]] = None,
        tag_analysis: Optional[Dict[str, Dict[str, float]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ComprehensiveEvaluationReport:
        """
        総合レポートを生成

        Args:
            routing_metrics: ルーティング精度メトリクス
            llm_judge_results: LLM Judge評価結果のリスト
            routing_results: ルーティング結果のリスト（エラー分析用）
            confidence_analysis: 信頼度閾値分析結果
            language_analysis: 言語別分析結果
            tag_analysis: タグ別分析結果
            metadata: 追加メタデータ

        Returns:
            ComprehensiveEvaluationReport: 総合レポート
        """
        report_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp = datetime.now().isoformat()

        routing_metrics_dict = None
        agent_summaries = []

        if routing_metrics:
            routing_metrics_dict = {
                "overall_accuracy": routing_metrics.overall_accuracy,
                "category_accuracy": routing_metrics.category_accuracy,
                "total_test_cases": routing_metrics.total_test_cases,
                "correct_predictions": routing_metrics.correct_predictions,
                "average_confidence": routing_metrics.average_confidence,
                "average_latency_ms": routing_metrics.average_latency_ms,
                "macro_precision": routing_metrics.macro_precision,
                "macro_recall": routing_metrics.macro_recall,
                "macro_f1": routing_metrics.macro_f1,
            }

            for agent_name, metrics in routing_metrics.agent_metrics.items():
                agent_summaries.append(
                    {
                        "agent_name": agent_name,
                        "precision": metrics.precision,
                        "recall": metrics.recall,
                        "f1_score": metrics.f1_score,
                        "true_positives": metrics.true_positives,
                        "false_positives": metrics.false_positives,
                        "false_negatives": metrics.false_negatives,
                    }
                )

        llm_judge_summary_dict = None
        if llm_judge_results:
            llm_judge_summary_dict = self._compute_llm_judge_summary(llm_judge_results)

        error_summary = None
        if routing_results:
            error_cases = [r for r in routing_results if not r.is_correct]
            if error_cases:
                error_summary = self._compute_error_summary(error_cases)

        recommendations = self._generate_recommendations(
            routing_metrics=routing_metrics,
            llm_judge_results=llm_judge_results,
            confidence_analysis=confidence_analysis,
        )

        return ComprehensiveEvaluationReport(
            report_id=report_id,
            timestamp=timestamp,
            routing_metrics=routing_metrics_dict,
            llm_judge_summary=llm_judge_summary_dict,
            agent_summaries=agent_summaries,
            confidence_analysis=confidence_analysis,
            language_analysis=language_analysis,
            tag_analysis=tag_analysis,
            error_summary=error_summary,
            recommendations=recommendations,
            metadata=metadata or {},
        )

    def _compute_llm_judge_summary(self, results: List[JudgeResult]) -> Dict[str, Any]:
        """LLM Judge評価のサマリーを計算"""
        if not results:
            return {}

        dimension_scores: Dict[str, List[float]] = {}
        dimension_passed: Dict[str, List[bool]] = {}

        for result in results:
            dimension = result.dimension
            if dimension not in dimension_scores:
                dimension_scores[dimension] = []
                dimension_passed[dimension] = []

            dimension_scores[dimension].append(result.score)
            dimension_passed[dimension].append(result.passed)

        average_scores = {
            dim: sum(scores) / len(scores) for dim, scores in dimension_scores.items()
        }

        pass_rates = {dim: sum(passed) / len(passed) for dim, passed in dimension_passed.items()}

        overall_passed = sum(r.passed for r in results)
        overall_pass_rate = overall_passed / len(results)

        return {
            "total_evaluations": len(results),
            "average_scores": average_scores,
            "pass_rates": pass_rates,
            "overall_pass_rate": overall_pass_rate,
        }

    def _compute_error_summary(self, error_cases: List[RoutingResult]) -> Dict[str, Any]:
        """エラーケースのサマリーを計算"""
        confusion_pairs: Dict[str, int] = {}
        low_confidence_errors = 0
        high_confidence_errors = 0

        for error in error_cases:
            pair = f"{error.expected_agent} -> {error.actual_agent}"
            confusion_pairs[pair] = confusion_pairs.get(pair, 0) + 1

            if error.confidence < 0.5:
                low_confidence_errors += 1
            elif error.confidence >= 0.8:
                high_confidence_errors += 1

        sorted_pairs = sorted(confusion_pairs.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_errors": len(error_cases),
            "top_confusion_pairs": dict(sorted_pairs[:5]),
            "low_confidence_errors": low_confidence_errors,
            "high_confidence_errors": high_confidence_errors,
        }

    def _generate_recommendations(
        self,
        routing_metrics: Optional[RoutingMetrics] = None,
        llm_judge_results: Optional[List[JudgeResult]] = None,
        confidence_analysis: Optional[Dict[float, Dict[str, float]]] = None,
    ) -> List[str]:
        """改善推奨事項を生成"""
        recommendations = []

        if routing_metrics:
            if routing_metrics.overall_accuracy < 0.8:
                recommendations.append(
                    f"ルーティング精度が{routing_metrics.overall_accuracy:.1%}です。"
                    "80%以上を目指してルーティングロジックの改善を検討してください。"
                )

            for agent_name, metrics in routing_metrics.agent_metrics.items():
                if metrics.precision < 0.7:
                    recommendations.append(
                        f"{agent_name}エージェントの精度が{metrics.precision:.1%}と低いです。"
                        "誤検出を減らすためのルール調整を検討してください。"
                    )
                if metrics.recall < 0.7:
                    recommendations.append(
                        f"{agent_name}エージェントの再現率が{metrics.recall:.1%}と低いです。"
                        "見逃しを減らすためのキーワード追加を検討してください。"
                    )

        if llm_judge_results:
            dimension_pass_rates: Dict[str, List[bool]] = {}
            for result in llm_judge_results:
                if result.dimension not in dimension_pass_rates:
                    dimension_pass_rates[result.dimension] = []
                dimension_pass_rates[result.dimension].append(result.passed)

            for dim, passed_list in dimension_pass_rates.items():
                pass_rate = sum(passed_list) / len(passed_list)
                if pass_rate < 0.7:
                    recommendations.append(
                        f"回答の{dim}評価の合格率が{pass_rate:.1%}と低いです。"
                        "プロンプトの改善を検討してください。"
                    )

        if confidence_analysis:
            for threshold, metrics in sorted(confidence_analysis.items()):
                if threshold >= 0.8:
                    coverage = metrics.get("coverage", 0)
                    accuracy = metrics.get("accuracy", 0)
                    if (
                        coverage > 0.5 and accuracy > routing_metrics.overall_accuracy + 0.1
                        if routing_metrics
                        else False
                    ):
                        recommendations.append(
                            f"信頼度閾値{threshold}を適用すると、"
                            f"カバレッジ{coverage:.1%}で精度{accuracy:.1%}が達成可能です。"
                        )
                        break

        if not recommendations:
            recommendations.append(
                "現在の評価結果は良好です。引き続きモニタリングを継続してください。"
            )

        return recommendations

    def save_report(
        self,
        report: ComprehensiveEvaluationReport,
        filename: Optional[str] = None,
    ) -> Path:
        """
        レポートをJSONファイルとして保存

        Args:
            report: 保存するレポート
            filename: ファイル名（省略時は自動生成）

        Returns:
            Path: 保存されたファイルのパス
        """
        if filename is None:
            filename = f"evaluation_report_{report.report_id}.json"

        filepath = self.reports_dir / filename

        report_dict = asdict(report)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)

        return filepath

    def load_report(self, filename: str) -> Optional[ComprehensiveEvaluationReport]:
        """
        レポートをJSONファイルから読み込み

        Args:
            filename: ファイル名

        Returns:
            Optional[ComprehensiveEvaluationReport]: 読み込んだレポート
        """
        filepath = self.reports_dir / filename

        if not filepath.exists():
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ComprehensiveEvaluationReport(**data)

    def list_reports(self) -> List[Dict[str, Any]]:
        """
        保存されているレポートの一覧を取得

        Returns:
            List[Dict[str, Any]]: レポートのメタ情報リスト
        """
        reports = []

        for filepath in self.reports_dir.glob("evaluation_report_*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                reports.append(
                    {
                        "filename": filepath.name,
                        "report_id": data.get("report_id"),
                        "timestamp": data.get("timestamp"),
                        "overall_accuracy": (
                            data.get("routing_metrics", {}).get("overall_accuracy")
                            if data.get("routing_metrics")
                            else None
                        ),
                    }
                )
            except (json.JSONDecodeError, KeyError):
                continue

        return sorted(reports, key=lambda x: x.get("timestamp", ""), reverse=True)

    def get_trend_data(
        self,
        metric: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        指定メトリクスのトレンドデータを取得

        Args:
            metric: メトリクス名（例: "overall_accuracy", "macro_f1"）
            limit: 取得するレポート数の上限

        Returns:
            List[Dict[str, Any]]: トレンドデータ
        """
        reports = self.list_reports()[:limit]
        trend_data = []

        for report_meta in reports:
            report = self.load_report(report_meta["filename"])
            if report and report.routing_metrics:
                value = report.routing_metrics.get(metric)
                if value is not None:
                    trend_data.append(
                        {
                            "timestamp": report.timestamp,
                            "report_id": report.report_id,
                            "value": value,
                        }
                    )

        return sorted(trend_data, key=lambda x: x.get("timestamp", ""))

    def compare_reports(
        self,
        report1_filename: str,
        report2_filename: str,
    ) -> Dict[str, Any]:
        """
        2つのレポートを比較

        Args:
            report1_filename: 比較元レポートのファイル名
            report2_filename: 比較先レポートのファイル名

        Returns:
            Dict[str, Any]: 比較結果
        """
        report1 = self.load_report(report1_filename)
        report2 = self.load_report(report2_filename)

        if not report1 or not report2:
            return {"error": "One or both reports not found"}

        comparison = {
            "report1_id": report1.report_id,
            "report2_id": report2.report_id,
            "routing_metrics_diff": {},
        }

        if report1.routing_metrics and report2.routing_metrics:
            for key in report1.routing_metrics:
                val1 = report1.routing_metrics.get(key)
                val2 = report2.routing_metrics.get(key)

                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    comparison["routing_metrics_diff"][key] = {
                        "before": val1,
                        "after": val2,
                        "diff": val2 - val1,
                        "improved": val2 > val1,
                    }

        return comparison


def create_report_generator(
    reports_dir: Optional[Path] = None,
) -> EvaluationReportGenerator:
    """
    レポート生成器を作成

    Args:
        reports_dir: レポート保存ディレクトリ

    Returns:
        EvaluationReportGenerator: レポート生成器インスタンス
    """
    return EvaluationReportGenerator(reports_dir=reports_dir)
