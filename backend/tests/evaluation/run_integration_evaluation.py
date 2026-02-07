"""
統合評価スクリプト - 実際のOrchestratorAgentを使用したルーティング精度評価

実際のAPIを呼び出して定量的にパフォーマンスを測定します。

実行方法:
    cd backend
    export $(cat .env.local | grep -v '^#' | xargs)
    python tests/evaluation/run_integration_evaluation.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# プロジェクトルート（backend）をパスに追加
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root))

# backend を明示的にパスに追加
parent_root = backend_root.parent
sys.path.insert(0, str(parent_root))

from tests.fixtures.dataset_loader import DatasetLoader
from tests.utils.evaluators.routing_accuracy import (
    RoutingAccuracyEvaluator,
    RoutingResult,
    RoutingTestCase,
)


async def evaluate_with_orchestrator(
    test_cases: List[RoutingTestCase],
    max_cases: int = None,
) -> List[RoutingResult]:
    """
    OrchestratorAgentを使用してテストケースを評価

    Args:
        test_cases: テストケースのリスト
        max_cases: 最大テストケース数（APIコスト制限用）

    Returns:
        List[RoutingResult]: 評価結果
    """
    from backend.agents.orchestrator_agent import OrchestratorAgent

    orchestrator = OrchestratorAgent(debug_mode=False)
    results = []

    cases_to_test = test_cases[:max_cases] if max_cases else test_cases
    total = len(cases_to_test)

    print(f"\n{'='*60}")
    print(f"OrchestratorAgent ルーティング評価")
    print(f"テストケース数: {total}")
    print(f"{'='*60}\n")

    for i, case in enumerate(cases_to_test, 1):
        try:
            print(f"[{i}/{total}] テスト: {case.id}")
            print(f"  クエリ: {case.query[:50]}...")

            decision = await orchestrator.decide_next_agent(
                query=case.query,
                session_id=f"eval-{case.id}",
                memory_context=None,
            )

            is_correct = decision.next_agent == case.expected_agent
            status = "✓" if is_correct else "✗"

            print(f"  期待: {case.expected_agent}, 実際: {decision.next_agent} {status}")
            print(f"  信頼度: {decision.confidence:.2f}")

            results.append(
                RoutingResult(
                    test_case_id=case.id,
                    expected_agent=case.expected_agent,
                    actual_agent=decision.next_agent,
                    is_correct=is_correct,
                    confidence=decision.confidence,
                    expected_category=case.expected_category,
                    actual_category=decision.category,
                    metadata={
                        "language": case.language,
                        "tags": case.tags,
                        "reasoning": decision.reasoning,
                    },
                )
            )

        except Exception as e:
            print(f"  エラー: {e}")
            results.append(
                RoutingResult(
                    test_case_id=case.id,
                    expected_agent=case.expected_agent,
                    actual_agent="error",
                    is_correct=False,
                    confidence=0.0,
                    metadata={"error": str(e)},
                )
            )

    await orchestrator.close()
    return results


def print_evaluation_report(
    evaluator: RoutingAccuracyEvaluator,
    results: List[RoutingResult],
) -> Dict[str, Any]:
    """評価レポートを表示"""
    evaluator.results = results
    metrics = evaluator.compute_metrics()

    print(f"\n{'='*60}")
    print("評価結果サマリー")
    print(f"{'='*60}")
    print(f"テストケース総数: {metrics.total_test_cases}")
    print(f"正解数: {metrics.correct_predictions}")
    print(f"全体精度: {metrics.overall_accuracy:.2%}")
    print(f"平均信頼度: {metrics.average_confidence:.2%}")

    print(f"\n{'─'*60}")
    print("エージェント別メトリクス")
    print(f"{'─'*60}")
    print(f"{'エージェント':<20} {'精度':<10} {'再現率':<10} {'F1':<10}")
    print(f"{'─'*60}")

    for agent_name, agent_metrics in metrics.agent_metrics.items():
        print(
            f"{agent_name:<20} "
            f"{agent_metrics.precision:.2%}    "
            f"{agent_metrics.recall:.2%}    "
            f"{agent_metrics.f1_score:.2%}"
        )

    # 言語別分析
    lang_analysis = evaluator.analyze_by_language()
    if lang_analysis:
        print(f"\n{'─'*60}")
        print("言語別精度")
        print(f"{'─'*60}")
        for lang, data in lang_analysis.items():
            total = data.get('total', data.get('count', 0))
            print(f"  {lang}: {data['accuracy']:.2%} ({total}件)")

    # タグ別分析
    tag_analysis = evaluator.analyze_by_tags()
    if tag_analysis:
        print(f"\n{'─'*60}")
        print("タグ別精度（主要タグ）")
        print(f"{'─'*60}")
        for tag in ["fast-path", "memory", "facility", "event", "business_info"]:
            if tag in tag_analysis:
                data = tag_analysis[tag]
                total = data.get('total', data.get('count', 0))
                print(f"  {tag}: {data['accuracy']:.2%} ({total}件)")

    # エラーケース
    error_cases = evaluator.get_error_cases()
    if error_cases:
        print(f"\n{'─'*60}")
        print(f"エラーケース ({len(error_cases)}件)")
        print(f"{'─'*60}")
        for err in error_cases[:5]:  # 最初の5件のみ表示
            print(f"  [{err.test_case_id}] {err.expected_agent} → {err.actual_agent}")

    # 信頼度閾値分析
    threshold_analysis = evaluator.analyze_confidence_thresholds([0.5, 0.7, 0.8, 0.9])
    print(f"\n{'─'*60}")
    print("信頼度閾値分析")
    print(f"{'─'*60}")
    print(f"{'閾値':<10} {'精度':<10} {'カバレッジ':<10}")
    for threshold, data in threshold_analysis.items():
        print(f"{threshold:<10} {data['accuracy']:.2%}    {data['coverage']:.2%}")

    return {
        "total": metrics.total_test_cases,
        "correct": metrics.correct_predictions,
        "accuracy": metrics.overall_accuracy,
        "avg_confidence": metrics.average_confidence,
        "agent_metrics": {
            name: {
                "precision": m.precision,
                "recall": m.recall,
                "f1": m.f1_score,
            }
            for name, m in metrics.agent_metrics.items()
        },
        "language_analysis": lang_analysis,
        "tag_analysis": tag_analysis,
        "threshold_analysis": threshold_analysis,
        "errors": [
            {
                "id": e.test_case_id,
                "expected": e.expected_agent,
                "actual": e.actual_agent,
            }
            for e in error_cases
        ],
    }


async def main():
    """メイン実行"""
    print("=" * 60)
    print("Engineer Cafe Navigator - 統合評価")
    print(f"実行日時: {datetime.now().isoformat()}")
    print("=" * 60)

    # 環境変数確認
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("エラー: OPENROUTER_API_KEY が設定されていません")
        print("export $(cat .env.local | grep -v '^#' | xargs) を実行してください")
        return

    # テストケース読み込み
    test_cases = DatasetLoader.load_routing_test_cases()
    print(f"\n読み込んだテストケース数: {len(test_cases)}")

    # データセット情報
    info = DatasetLoader.get_dataset_info()
    print(f"対応言語: {', '.join(info['languages'])}")
    print(f"対応エージェント: {', '.join(info['agents'])}")

    # 評価実行（コスト削減のため最初は10件に制限）
    max_cases = int(os.getenv("EVAL_MAX_CASES", "10"))
    print(f"\n評価するケース数: {max_cases}")
    print("(全件評価するには EVAL_MAX_CASES=32 を設定)")

    results = await evaluate_with_orchestrator(test_cases, max_cases=max_cases)

    # 評価レポート
    evaluator = RoutingAccuracyEvaluator()
    report = print_evaluation_report(evaluator, results)

    # 結果をJSONに保存
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_file = reports_dir / f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "config": {
                    "max_cases": max_cases,
                    "model": "orchestrator",
                },
                "results": report,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n✓ レポート保存: {report_file}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
