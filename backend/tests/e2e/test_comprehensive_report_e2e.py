"""総合レポートE2Eテスト - 全評価統合レポート生成"""

import json
import logging
import re
from datetime import datetime

import pytest

from backend.tests.e2e.conftest import keywords_match
from backend.tests.fixtures.dataset_loader import DatasetLoader
from backend.tests.utils.evaluators.routing_accuracy import RoutingResult

logger = logging.getLogger(__name__)


def _normalize_agent_name(name: str) -> str:
    """エージェント名を正規化（PascalCase → snake_case、末尾Agent除去）"""
    name = re.sub(r"Agent$", "", name)
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return name.lower().strip("_")


@pytest.mark.e2e
class TestComprehensiveReportE2E:
    """総合レポート生成テスト"""

    async def test_generate_comprehensive_report(
        self,
        invoke_workflow,
        routing_evaluator,
        e2e_report_generator,
    ):
        """総合評価レポートを生成"""
        # 1. ルーティング評価（最大10ケース）
        routing_cases = DatasetLoader.load_routing_test_cases()[:10]
        routing_results = []

        for case in routing_cases:
            try:
                result = await invoke_workflow(case.query, language=case.language)
                raw_agent = (
                    result.get("metadata", {})
                    .get("routing", {})
                    .get("agent", result.get("metadata", {}).get("agent", "unknown"))
                )
                actual_agent = _normalize_agent_name(raw_agent)
                routing_results.append(
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
                routing_results.append(
                    RoutingResult(
                        test_case_id=case.id,
                        expected_agent=case.expected_agent,
                        actual_agent=f"error: {e}",
                        is_correct=False,
                        confidence=0.0,
                    )
                )

        # 2. キーワード評価（最大10ケース）
        quality_cases = DatasetLoader.load_answer_quality_cases(language="ja")[:10]
        keyword_pass = 0
        keyword_total = 0

        for case in quality_cases:
            if not case.expected_keywords:
                continue
            keyword_total += 1
            try:
                result = await invoke_workflow(case.question, language=case.language)
                if keywords_match(result["answer"], case.expected_keywords, threshold=0.5):
                    keyword_pass += 1
            except Exception:
                continue

        # 2.5. RAGAS評価（optional - ragas未インストール時はスキップ）
        ragas_metrics: dict = {}
        try:
            from ragas import evaluate as ragas_evaluate
            from ragas.metrics import answer_relevancy, faithfulness

            ragas_scores_faith = []
            ragas_scores_relevancy = []

            for case in quality_cases[:3]:
                try:
                    result = await invoke_workflow(case.question, language=case.language)
                    answer = result.get("answer", "")
                    context = result.get("metadata", {}).get("context", "")

                    # Build RAGAS-compatible dataset
                    from datasets import Dataset

                    ragas_dataset = Dataset.from_dict(
                        {
                            "question": [case.question],
                            "answer": [answer],
                            "contexts": [[context] if context else [""]],
                            "ground_truth": [
                                (
                                    case.reference_answer
                                    if hasattr(case, "reference_answer") and case.reference_answer
                                    else answer
                                )
                            ],
                        }
                    )

                    ragas_result = ragas_evaluate(
                        ragas_dataset,
                        metrics=[faithfulness, answer_relevancy],
                    )

                    if "faithfulness" in ragas_result:
                        ragas_scores_faith.append(ragas_result["faithfulness"])
                    if "answer_relevancy" in ragas_result:
                        ragas_scores_relevancy.append(ragas_result["answer_relevancy"])
                except Exception as ragas_case_err:
                    logger.warning("RAGAS evaluation failed for case: %s", ragas_case_err)
                    continue

            if ragas_scores_faith:
                ragas_metrics["ragas_faithfulness"] = sum(ragas_scores_faith) / len(
                    ragas_scores_faith
                )
            if ragas_scores_relevancy:
                ragas_metrics["ragas_answer_relevancy"] = sum(ragas_scores_relevancy) / len(
                    ragas_scores_relevancy
                )

            logger.info("RAGAS evaluation completed: %s", ragas_metrics)
        except ImportError:
            logger.info("RAGAS not installed, skipping RAGAS evaluation step")
        except Exception as ragas_err:
            logger.warning("RAGAS evaluation failed: %s", ragas_err)

        # 3. レポート生成
        report = e2e_report_generator.generate_report(
            metadata={
                "test_type": "e2e_comprehensive",
                "timestamp": datetime.now().isoformat(),
                "routing_cases_tested": len(routing_cases),
                "quality_cases_tested": keyword_total,
                "keyword_pass_rate": keyword_pass / keyword_total if keyword_total > 0 else 0,
                "routing_correct": sum(1 for r in routing_results if r.is_correct),
                "routing_total": len(routing_results),
                **ragas_metrics,
            }
        )

        # 4. レポート保存
        filepath = e2e_report_generator.save_report(
            report,
            filename=f"e2e_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )

        assert filepath.exists(), f"レポートが保存されていません: {filepath}"

        with open(filepath, "r", encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["metadata"]["test_type"] == "e2e_comprehensive"
