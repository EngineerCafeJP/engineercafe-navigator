"""
LangSmith統合モジュール

LangSmithを使用したエージェント評価・トレーシング機能を提供します。
環境変数 LANGSMITH_API_KEY が必要です。

参考: https://docs.smith.langchain.com/
"""

import os
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

try:
    from langsmith import Client

    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    Client = None


@dataclass
class EvaluationResult:
    """評価結果"""

    metric_name: str
    score: float
    passed: bool
    threshold: float
    details: Optional[Dict[str, Any]] = None


@dataclass
class AgentEvaluationReport:
    """エージェント評価レポート"""

    agent_name: str
    timestamp: str
    overall_passed: bool
    pass_rate: float
    results: List[EvaluationResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LangSmithEvaluator:
    """
    LangSmith統合評価器

    LangSmithのトレーシング・評価機能を使用してエージェントを評価します。
    """

    def __init__(self, project_name: str = "engineer-cafe-navigator"):
        """
        初期化

        Args:
            project_name: LangSmithプロジェクト名
        """
        self.project_name = project_name
        self.client: Optional[Client] = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """LangSmithクライアントを初期化"""
        if not LANGSMITH_AVAILABLE:
            return

        api_key = os.getenv("LANGSMITH_API_KEY")
        if api_key:
            try:
                self.client = Client(api_key=api_key)
            except Exception:
                self.client = None

    @property
    def is_available(self) -> bool:
        """LangSmithが利用可能かどうか"""
        return self.client is not None

    async def trace_agent_run(
        self,
        agent_name: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        エージェント実行をトレース

        Args:
            agent_name: エージェント名
            inputs: 入力データ
            outputs: 出力データ
            metadata: メタデータ

        Returns:
            Optional[str]: ラン ID（トレース不可の場合はNone）
        """
        if not self.is_available:
            return None

        try:
            run = self.client.create_run(
                name=agent_name,
                run_type="chain",
                inputs=inputs,
                outputs=outputs,
                project_name=self.project_name,
                extra=metadata or {},
            )
            return str(run.id) if hasattr(run, "id") else None
        except Exception:
            return None

    async def evaluate_agent(
        self,
        agent_name: str,
        test_cases: List[Dict[str, Any]],
        evaluators: Optional[List[Callable]] = None,
    ) -> AgentEvaluationReport:
        """
        エージェントを評価

        Args:
            agent_name: エージェント名
            test_cases: テストケースのリスト
            evaluators: カスタム評価関数のリスト

        Returns:
            AgentEvaluationReport: 評価レポート
        """
        results: List[EvaluationResult] = []
        evaluators = evaluators or self._get_default_evaluators()

        for test_case in test_cases:
            agent_output = test_case.get("output", {})
            expected_output = test_case.get("expected", {})

            for evaluator_func in evaluators:
                try:
                    score = await evaluator_func(agent_output, expected_output)
                    threshold = getattr(evaluator_func, "threshold", 0.7)
                    results.append(
                        EvaluationResult(
                            metric_name=evaluator_func.__name__,
                            score=score,
                            passed=score >= threshold,
                            threshold=threshold,
                        )
                    )
                except Exception as e:
                    results.append(
                        EvaluationResult(
                            metric_name=evaluator_func.__name__,
                            score=0.0,
                            passed=False,
                            threshold=0.7,
                            details={"error": str(e)},
                        )
                    )

        passed_count = sum(1 for r in results if r.passed)
        total_count = len(results)
        pass_rate = passed_count / total_count if total_count > 0 else 0.0

        return AgentEvaluationReport(
            agent_name=agent_name,
            timestamp=datetime.now().isoformat(),
            overall_passed=pass_rate >= 0.8,
            pass_rate=pass_rate,
            results=results,
            metadata={"total_tests": len(test_cases), "total_metrics": len(evaluators)},
        )

    def _get_default_evaluators(self) -> List[Callable]:
        """デフォルト評価関数を取得"""
        return [
            evaluate_answer_presence,
            evaluate_emotion_validity,
            evaluate_response_format,
            evaluate_language_consistency,
        ]

    async def create_dataset(
        self, dataset_name: str, examples: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        評価用データセットを作成

        Args:
            dataset_name: データセット名
            examples: サンプルデータのリスト

        Returns:
            Optional[str]: データセット ID
        """
        if not self.is_available:
            return None

        try:
            dataset = self.client.create_dataset(
                dataset_name=dataset_name,
                description=f"Evaluation dataset for {self.project_name}",
            )

            for example in examples:
                self.client.create_example(
                    inputs=example.get("inputs", {}),
                    outputs=example.get("outputs", {}),
                    dataset_id=dataset.id,
                )

            return str(dataset.id)
        except Exception:
            return None

    def get_evaluation_summary(self, reports: List[AgentEvaluationReport]) -> Dict[str, Any]:
        """
        複数のレポートからサマリーを生成

        Args:
            reports: 評価レポートのリスト

        Returns:
            Dict[str, Any]: サマリー
        """
        total_agents = len(reports)
        passed_agents = sum(1 for r in reports if r.overall_passed)

        return {
            "total_agents": total_agents,
            "passed_agents": passed_agents,
            "overall_pass_rate": passed_agents / total_agents if total_agents > 0 else 0.0,
            "agent_results": {r.agent_name: r.pass_rate for r in reports},
            "timestamp": datetime.now().isoformat(),
        }


# ==============================================================================
# 評価関数
# ==============================================================================


async def evaluate_answer_presence(
    agent_output: Dict[str, Any], expected_output: Optional[Dict[str, Any]] = None
) -> float:
    """回答が存在するかを評価"""
    answer = agent_output.get("answer", "")
    return 1.0 if answer and len(answer.strip()) > 0 else 0.0


evaluate_answer_presence.threshold = 1.0


async def evaluate_emotion_validity(
    agent_output: Dict[str, Any], expected_output: Optional[Dict[str, Any]] = None
) -> float:
    """感情タグの妥当性を評価"""
    valid_emotions = {"neutral", "happy", "sad", "surprised", "relaxed", "angry"}
    emotion = agent_output.get("emotion", "")
    return 1.0 if emotion in valid_emotions else 0.0


evaluate_emotion_validity.threshold = 1.0


async def evaluate_response_format(
    agent_output: Dict[str, Any], expected_output: Optional[Dict[str, Any]] = None
) -> float:
    """レスポンス形式の妥当性を評価"""
    required_fields = {"answer", "emotion"}
    present_fields = set(agent_output.keys())
    missing = required_fields - present_fields
    return (
        1.0 if len(missing) == 0 else (len(required_fields) - len(missing)) / len(required_fields)
    )


evaluate_response_format.threshold = 0.8


async def evaluate_language_consistency(
    agent_output: Dict[str, Any], expected_output: Optional[Dict[str, Any]] = None
) -> float:
    """言語の一貫性を評価（日本語/英語）"""
    answer = agent_output.get("answer", "")
    if not answer:
        return 0.0

    japanese_chars = sum(1 for c in answer if "\u3040" <= c <= "\u9fff")
    total_alpha = sum(1 for c in answer if c.isalpha())

    if total_alpha == 0:
        return 1.0

    jp_ratio = japanese_chars / total_alpha
    return 1.0 if jp_ratio > 0.5 or jp_ratio < 0.1 else 0.7


evaluate_language_consistency.threshold = 0.7


# ==============================================================================
# ヘルパー関数
# ==============================================================================


def create_langsmith_evaluator(
    project_name: str = "engineer-cafe-navigator",
) -> LangSmithEvaluator:
    """
    LangSmith評価器を作成

    Args:
        project_name: プロジェクト名

    Returns:
        LangSmithEvaluator: 評価器インスタンス
    """
    return LangSmithEvaluator(project_name=project_name)


async def run_agent_evaluation(
    agent_name: str,
    test_cases: List[Dict[str, Any]],
    project_name: str = "engineer-cafe-navigator",
) -> AgentEvaluationReport:
    """
    エージェント評価を実行

    Args:
        agent_name: エージェント名
        test_cases: テストケース
        project_name: プロジェクト名

    Returns:
        AgentEvaluationReport: 評価レポート
    """
    evaluator = create_langsmith_evaluator(project_name)
    return await evaluator.evaluate_agent(agent_name, test_cases)


# ==============================================================================
# 拡張評価器統合
# ==============================================================================


async def run_comprehensive_evaluation(
    test_cases: List[Dict[str, Any]],
    routing_results: Optional[List[Dict[str, Any]]] = None,
    include_llm_judge: bool = False,
    project_name: str = "engineer-cafe-navigator",
) -> Dict[str, Any]:
    """
    包括的な評価を実行

    LangSmith統合評価、ルーティング精度評価、LLM Judge評価を統合して実行します。

    Args:
        test_cases: テストケースのリスト
        routing_results: ルーティング結果のリスト
        include_llm_judge: LLM Judge評価を含めるか
        project_name: プロジェクト名

    Returns:
        Dict[str, Any]: 統合評価結果
    """
    from backend.tests.utils.evaluators.routing_accuracy import (
        RoutingAccuracyEvaluator,
        RoutingTestCase,
    )
    from backend.tests.utils.evaluators.llm_judge import LLMJudgeEvaluator
    from backend.tests.utils.evaluators.report_generator import EvaluationReportGenerator

    results: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "project_name": project_name,
    }

    # ルーティング精度評価
    if routing_results:
        routing_evaluator = RoutingAccuracyEvaluator()
        routing_test_cases = [
            RoutingTestCase(
                id=tc.get("id", str(i)),
                query=tc.get("query", ""),
                expected_agent=tc.get("expected_agent", ""),
                expected_category=tc.get("expected_category"),
                language=tc.get("language", "ja"),
                tags=tc.get("tags", []),
            )
            for i, tc in enumerate(test_cases)
        ]

        await routing_evaluator.evaluate_batch(
            test_cases=routing_test_cases,
            routing_results=routing_results,
        )

        results["routing_metrics"] = routing_evaluator.compute_metrics()
        results["routing_results"] = routing_evaluator.results
        results["confidence_analysis"] = routing_evaluator.analyze_confidence_thresholds()

    # LLM Judge評価
    if include_llm_judge:
        llm_judge = LLMJudgeEvaluator()
        if llm_judge.is_available:
            llm_test_cases = [
                {
                    "question": tc.get("query", ""),
                    "answer": tc.get("answer", ""),
                    "language": tc.get("language", "ja"),
                }
                for tc in test_cases
                if tc.get("answer")
            ]

            if llm_test_cases:
                batch_results = await llm_judge.batch_evaluate(llm_test_cases)
                results["llm_judge_results"] = batch_results

    # レポート生成
    report_generator = EvaluationReportGenerator()
    report = report_generator.generate_report(
        routing_metrics=results.get("routing_metrics"),
        llm_judge_results=results.get("llm_judge_results"),
        routing_results=results.get("routing_results"),
        confidence_analysis=results.get("confidence_analysis"),
        metadata={"project_name": project_name},
    )

    results["report"] = report
    return results
