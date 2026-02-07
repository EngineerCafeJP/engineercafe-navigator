"""
ルーティング精度評価器

マルチエージェントシステムのルーティング精度を評価します。
per-agent precision/recall、F1スコア、信頼度閾値分析を提供。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime


@dataclass
class RoutingTestCase:
    """ルーティングテストケース"""

    id: str
    query: str
    expected_agent: str
    expected_category: Optional[str] = None
    language: str = "ja"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingResult:
    """ルーティング評価結果"""

    test_case_id: str
    expected_agent: str
    actual_agent: str
    is_correct: bool
    confidence: float
    expected_category: Optional[str] = None
    actual_category: Optional[str] = None
    category_correct: bool = False
    latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMetrics:
    """エージェント別メトリクス"""

    agent_name: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    total_predictions: int = 0
    total_expected: int = 0

    @property
    def precision(self) -> float:
        """精度（Precision）"""
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        """再現率（Recall）"""
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        """F1スコア"""
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)


@dataclass
class RoutingMetrics:
    """ルーティング総合メトリクス"""

    overall_accuracy: float
    category_accuracy: float
    agent_metrics: Dict[str, AgentMetrics]
    total_test_cases: int
    correct_predictions: int
    average_confidence: float
    average_latency_ms: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def macro_precision(self) -> float:
        """マクロ平均精度"""
        if not self.agent_metrics:
            return 0.0
        return sum(m.precision for m in self.agent_metrics.values()) / len(self.agent_metrics)

    @property
    def macro_recall(self) -> float:
        """マクロ平均再現率"""
        if not self.agent_metrics:
            return 0.0
        return sum(m.recall for m in self.agent_metrics.values()) / len(self.agent_metrics)

    @property
    def macro_f1(self) -> float:
        """マクロ平均F1スコア"""
        if not self.agent_metrics:
            return 0.0
        return sum(m.f1_score for m in self.agent_metrics.values()) / len(self.agent_metrics)


class RoutingAccuracyEvaluator:
    """
    ルーティング精度評価器

    マルチエージェントシステムのルーティング精度を評価します。
    """

    def __init__(self, router_func=None):
        """
        初期化

        Args:
            router_func: ルーティング関数（Optional）
                引数: (query: str, language: str) -> Dict with 'agent', 'category', 'confidence'
        """
        self.router_func = router_func
        self.results: List[RoutingResult] = []

    async def evaluate_single(
        self,
        test_case: RoutingTestCase,
        actual_agent: str,
        actual_category: Optional[str] = None,
        confidence: float = 1.0,
        latency_ms: Optional[float] = None,
    ) -> RoutingResult:
        """
        単一テストケースを評価

        Args:
            test_case: テストケース
            actual_agent: 実際にルーティングされたエージェント
            actual_category: 実際のカテゴリ
            confidence: 信頼度スコア
            latency_ms: レイテンシ（ミリ秒）

        Returns:
            RoutingResult: 評価結果
        """
        is_correct = test_case.expected_agent == actual_agent
        category_correct = (
            test_case.expected_category == actual_category if test_case.expected_category else True
        )

        result = RoutingResult(
            test_case_id=test_case.id,
            expected_agent=test_case.expected_agent,
            actual_agent=actual_agent,
            is_correct=is_correct,
            confidence=confidence,
            expected_category=test_case.expected_category,
            actual_category=actual_category,
            category_correct=category_correct,
            latency_ms=latency_ms,
            metadata={"tags": test_case.tags, "language": test_case.language},
        )

        self.results.append(result)
        return result

    async def evaluate_batch(
        self,
        test_cases: List[RoutingTestCase],
        routing_results: Optional[List[Dict[str, Any]]] = None,
    ) -> List[RoutingResult]:
        """
        バッチ評価

        Args:
            test_cases: テストケースのリスト
            routing_results: ルーティング結果のリスト（Optionalの場合はrouter_funcを使用）

        Returns:
            List[RoutingResult]: 評価結果のリスト
        """
        results = []

        if routing_results:
            for test_case, routing_result in zip(test_cases, routing_results):
                result = await self.evaluate_single(
                    test_case=test_case,
                    actual_agent=routing_result.get("agent", ""),
                    actual_category=routing_result.get("category"),
                    confidence=routing_result.get("confidence", 1.0),
                    latency_ms=routing_result.get("latency_ms"),
                )
                results.append(result)
        elif self.router_func:
            import time

            for test_case in test_cases:
                start_time = time.time()
                routing_result = await self.router_func(test_case.query, test_case.language)
                latency_ms = (time.time() - start_time) * 1000

                result = await self.evaluate_single(
                    test_case=test_case,
                    actual_agent=routing_result.get("agent", ""),
                    actual_category=routing_result.get("category"),
                    confidence=routing_result.get("confidence", 1.0),
                    latency_ms=latency_ms,
                )
                results.append(result)
        else:
            raise ValueError("Either routing_results or router_func must be provided")

        return results

    def compute_metrics(self) -> RoutingMetrics:
        """
        精度メトリクスを計算

        Returns:
            RoutingMetrics: 総合メトリクス
        """
        if not self.results:
            return RoutingMetrics(
                overall_accuracy=0.0,
                category_accuracy=0.0,
                agent_metrics={},
                total_test_cases=0,
                correct_predictions=0,
                average_confidence=0.0,
            )

        agent_metrics: Dict[str, AgentMetrics] = {}
        all_agents = set()

        for result in self.results:
            all_agents.add(result.expected_agent)
            all_agents.add(result.actual_agent)

        for agent in all_agents:
            agent_metrics[agent] = AgentMetrics(agent_name=agent)

        for result in self.results:
            expected = result.expected_agent
            actual = result.actual_agent

            agent_metrics[expected].total_expected += 1
            agent_metrics[actual].total_predictions += 1

            if result.is_correct:
                agent_metrics[expected].true_positives += 1
            else:
                agent_metrics[expected].false_negatives += 1
                agent_metrics[actual].false_positives += 1

        total_test_cases = len(self.results)
        correct_predictions = sum(1 for r in self.results if r.is_correct)
        overall_accuracy = correct_predictions / total_test_cases

        category_results = [r for r in self.results if r.expected_category]
        category_correct = sum(1 for r in category_results if r.category_correct)
        category_accuracy = category_correct / len(category_results) if category_results else 1.0

        average_confidence = sum(r.confidence for r in self.results) / total_test_cases

        latencies = [r.latency_ms for r in self.results if r.latency_ms is not None]
        average_latency = sum(latencies) / len(latencies) if latencies else None

        return RoutingMetrics(
            overall_accuracy=overall_accuracy,
            category_accuracy=category_accuracy,
            agent_metrics=agent_metrics,
            total_test_cases=total_test_cases,
            correct_predictions=correct_predictions,
            average_confidence=average_confidence,
            average_latency_ms=average_latency,
        )

    def analyze_confidence_thresholds(
        self,
        thresholds: Optional[List[float]] = None,
    ) -> Dict[float, Dict[str, float]]:
        """
        信頼度閾値分析

        Args:
            thresholds: 分析する閾値のリスト

        Returns:
            Dict[float, Dict[str, float]]: 各閾値でのメトリクス
        """
        if thresholds is None:
            thresholds = [0.3, 0.5, 0.7, 0.8, 0.9, 0.95]

        analysis = {}

        for threshold in thresholds:
            filtered_results = [r for r in self.results if r.confidence >= threshold]

            if not filtered_results:
                analysis[threshold] = {
                    "coverage": 0.0,
                    "accuracy": 0.0,
                    "count": 0,
                }
                continue

            coverage = len(filtered_results) / len(self.results)
            correct = sum(1 for r in filtered_results if r.is_correct)
            accuracy = correct / len(filtered_results)

            analysis[threshold] = {
                "coverage": coverage,
                "accuracy": accuracy,
                "count": len(filtered_results),
            }

        return analysis

    def analyze_by_tags(self) -> Dict[str, Dict[str, float]]:
        """
        タグ別分析

        Returns:
            Dict[str, Dict[str, float]]: 各タグでのメトリクス
        """
        tag_results: Dict[str, List[RoutingResult]] = defaultdict(list)

        for result in self.results:
            tags = result.metadata.get("tags", [])
            for tag in tags:
                tag_results[tag].append(result)

        analysis = {}
        for tag, results in tag_results.items():
            correct = sum(1 for r in results if r.is_correct)
            analysis[tag] = {
                "accuracy": correct / len(results),
                "count": len(results),
            }

        return analysis

    def analyze_by_language(self) -> Dict[str, Dict[str, float]]:
        """
        言語別分析

        Returns:
            Dict[str, Dict[str, float]]: 各言語でのメトリクス
        """
        lang_results: Dict[str, List[RoutingResult]] = defaultdict(list)

        for result in self.results:
            language = result.metadata.get("language", "unknown")
            lang_results[language].append(result)

        analysis = {}
        for lang, results in lang_results.items():
            correct = sum(1 for r in results if r.is_correct)
            analysis[lang] = {
                "accuracy": correct / len(results),
                "count": len(results),
            }

        return analysis

    def get_confusion_matrix(self) -> Dict[str, Dict[str, int]]:
        """
        混同行列を取得

        Returns:
            Dict[str, Dict[str, int]]: 混同行列
        """
        all_agents = set()
        for result in self.results:
            all_agents.add(result.expected_agent)
            all_agents.add(result.actual_agent)

        matrix: Dict[str, Dict[str, int]] = {
            expected: {actual: 0 for actual in all_agents} for expected in all_agents
        }

        for result in self.results:
            matrix[result.expected_agent][result.actual_agent] += 1

        return matrix

    def get_error_cases(self) -> List[RoutingResult]:
        """
        エラーケースを取得

        Returns:
            List[RoutingResult]: 誤分類されたケース
        """
        return [r for r in self.results if not r.is_correct]

    def clear_results(self) -> None:
        """結果をクリア"""
        self.results = []


def create_routing_evaluator(router_func=None) -> RoutingAccuracyEvaluator:
    """
    ルーティング評価器を作成

    Args:
        router_func: ルーティング関数（Optional）

    Returns:
        RoutingAccuracyEvaluator: 評価器インスタンス
    """
    return RoutingAccuracyEvaluator(router_func=router_func)
