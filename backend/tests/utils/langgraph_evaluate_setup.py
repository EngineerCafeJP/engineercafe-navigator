"""
LangGraph Evaluate基本セットアップ

LangGraphのエージェント評価に使用する基本的なセットアップとユーティリティを提供します。

参考: langgraph-reference/docs/docs/testing/
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class EvaluationMetric:
    """評価メトリクス"""

    name: str
    description: str
    evaluator: Callable
    threshold: float = 0.7


class LangGraphEvaluator:
    """
    LangGraphエージェント評価器（骨組み）

    TODO (完全実装):
    - langgraph.evaluation からの実際の Evaluator 統合
    - 評価データセットの読み込み
    - 評価結果の保存と可視化

    現在の実装:
    - 基本的な評価フレームワークの骨組み
    - カスタムメトリクスの定義
    """

    def __init__(self):
        """初期化"""
        self.metrics: List[EvaluationMetric] = []
        self.evaluation_results: List[Dict[str, Any]] = []

    def add_metric(
        self, name: str, evaluator: Callable, description: str = "", threshold: float = 0.7
    ):
        """
        評価メトリクスを追加

        Args:
            name: メトリクス名
            evaluator: 評価関数
            description: 説明
            threshold: 合格閾値
        """
        metric = EvaluationMetric(
            name=name, description=description, evaluator=evaluator, threshold=threshold
        )
        self.metrics.append(metric)

    async def evaluate(
        self,
        agent_output: Dict[str, Any],
        expected_output: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        エージェント出力を評価

        Args:
            agent_output: エージェントの実際の出力
            expected_output: 期待される出力（オプショナル）
            context: 評価コンテキスト（オプショナル）

        Returns:
            Dict[str, Any]: 評価結果

        TODO:
        - 実際のLangGraph Evaluatorとの統合
        - より高度な評価ロジック
        """
        results = {}

        for metric in self.metrics:
            try:
                score = await metric.evaluator(agent_output, expected_output, context)
                results[metric.name] = {
                    "score": score,
                    "passed": score >= metric.threshold,
                    "threshold": metric.threshold,
                }
            except Exception as e:
                results[metric.name] = {"error": str(e), "passed": False}

        # 全体の評価
        overall_passed = all(r.get("passed", False) for r in results.values())

        evaluation_result = {
            "overall_passed": overall_passed,
            "metrics": results,
            "agent_output": agent_output,
        }

        self.evaluation_results.append(evaluation_result)

        return evaluation_result

    def get_evaluation_summary(self) -> Dict[str, Any]:
        """
        評価結果のサマリーを取得

        Returns:
            Dict[str, Any]: 評価サマリー
        """
        total_evaluations = len(self.evaluation_results)
        passed_evaluations = sum(1 for r in self.evaluation_results if r["overall_passed"])

        return {
            "total_evaluations": total_evaluations,
            "passed_evaluations": passed_evaluations,
            "pass_rate": passed_evaluations / total_evaluations if total_evaluations > 0 else 0,
            "details": self.evaluation_results,
        }


# ==============================================================================
# 標準評価メトリクス
# ==============================================================================


async def evaluate_answer_presence(
    agent_output: Dict[str, Any],
    expected_output: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> float:
    """
    回答が存在するかを評価

    Args:
        agent_output: エージェント出力
        expected_output: 期待される出力
        context: コンテキスト

    Returns:
        float: スコア（0.0 or 1.0）
    """
    answer = agent_output.get("answer", "")
    return 1.0 if answer and len(answer) > 0 else 0.0


async def evaluate_emotion_validity(
    agent_output: Dict[str, Any],
    expected_output: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> float:
    """
    感情タグの妥当性を評価

    Args:
        agent_output: エージェント出力
        expected_output: 期待される出力
        context: コンテキスト

    Returns:
        float: スコア（0.0 or 1.0）
    """
    valid_emotions = ["neutral", "happy", "sad", "surprised", "relaxed", "angry"]
    emotion = agent_output.get("emotion", "")
    return 1.0 if emotion in valid_emotions else 0.0


async def evaluate_metadata_presence(
    agent_output: Dict[str, Any],
    expected_output: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> float:
    """
    メタデータが存在するかを評価

    Args:
        agent_output: エージェント出力
        expected_output: 期待される出力
        context: コンテキスト

    Returns:
        float: スコア（0.0 or 1.0）
    """
    metadata = agent_output.get("metadata", {})
    return 1.0 if isinstance(metadata, dict) and len(metadata) > 0 else 0.0


async def evaluate_answer_length(
    agent_output: Dict[str, Any],
    expected_output: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> float:
    """
    回答の長さを評価（短すぎず長すぎないか）

    Args:
        agent_output: エージェント出力
        expected_output: 期待される出力
        context: コンテキスト

    Returns:
        float: スコア（0.0 ~ 1.0）
    """
    answer = agent_output.get("answer", "")
    length = len(answer)

    # 理想的な長さ範囲: 10文字 ~ 500文字
    if 10 <= length <= 500:
        return 1.0
    elif length < 10:
        return length / 10.0  # 短い場合は比例スコア
    else:
        return max(0.5, 1.0 - (length - 500) / 1000)  # 長い場合は減点


# ==============================================================================
# ヘルパー関数
# ==============================================================================


def create_evaluator() -> LangGraphEvaluator:
    """
    標準メトリクスを持つLangGraphEvaluatorを作成

    Returns:
        LangGraphEvaluator: 評価器インスタンス
    """
    evaluator = LangGraphEvaluator()

    # 標準メトリクスを追加
    evaluator.add_metric(
        name="answer_presence",
        evaluator=evaluate_answer_presence,
        description="回答が存在するか",
        threshold=1.0,
    )

    evaluator.add_metric(
        name="emotion_validity",
        evaluator=evaluate_emotion_validity,
        description="感情タグが妥当か",
        threshold=1.0,
    )

    evaluator.add_metric(
        name="metadata_presence",
        evaluator=evaluate_metadata_presence,
        description="メタデータが存在するか",
        threshold=1.0,
    )

    evaluator.add_metric(
        name="answer_length",
        evaluator=evaluate_answer_length,
        description="回答の長さが適切か",
        threshold=0.7,
    )

    return evaluator


async def run_evaluation_suite(
    agent_outputs: List[Dict[str, Any]], evaluator: Optional[LangGraphEvaluator] = None
) -> Dict[str, Any]:
    """
    評価スイートを実行

    Args:
        agent_outputs: エージェント出力のリスト
        evaluator: 評価器（Noneの場合は標準評価器を使用）

    Returns:
        Dict[str, Any]: 評価サマリー
    """
    if evaluator is None:
        evaluator = create_evaluator()

    for output in agent_outputs:
        await evaluator.evaluate(output)

    return evaluator.get_evaluation_summary()
