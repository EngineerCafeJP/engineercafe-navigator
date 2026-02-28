"""Phase B RAGAS 評価テスト

Phase B で追加された ground truth (gt-078 〜 gt-087) を含む
包括的な RAGAS 評価を実行する。

ragas が未インストールの環境では全テストがスキップされる。

実行方法:
    pytest backend/tests/evaluation/test_ragas_phase_b.py -v --timeout=300
"""

import json
import logging
from pathlib import Path
import pytest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ground truth loader
# ---------------------------------------------------------------------------

GROUND_TRUTH_PATH = (
    Path(__file__).parent.parent / "fixtures" / "golden_datasets" / "ground_truth.json"
)

PHASE_B_IDS = {
    "gt-078",
    "gt-079",
    "gt-080",
    "gt-081",
    "gt-082",
    "gt-083",
    "gt-084",
    "gt-085",
    "gt-086",
    "gt-087",
}

BASELINE_THRESHOLD = 0.7


def _load_ground_truth() -> list[dict]:
    """ground_truth.json からテストケースを読み込む"""
    if not GROUND_TRUTH_PATH.exists():
        pytest.skip("ground_truth.json not found")
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("test_cases", [])


# ---------------------------------------------------------------------------
# Test: ground truth data integrity
# ---------------------------------------------------------------------------


class TestGroundTruthIntegrity:
    """ground_truth.json のデータ整合性テスト"""

    def test_ground_truth_file_exists(self):
        """ground_truth.json が存在する"""
        assert GROUND_TRUTH_PATH.exists(), f"Not found: {GROUND_TRUTH_PATH}"

    def test_phase_b_entries_exist(self):
        """Phase B エントリ (gt-078 〜 gt-087) が存在する"""
        cases = _load_ground_truth()
        case_ids = {c["id"] for c in cases}
        missing = PHASE_B_IDS - case_ids
        assert not missing, f"Missing Phase B entries: {missing}"

    def test_total_cases_count(self):
        """全テストケースが 87 件以上"""
        cases = _load_ground_truth()
        assert len(cases) >= 87, f"Expected >= 87 cases, got {len(cases)}"

    def test_phase_b_entries_have_required_fields(self):
        """Phase B エントリに必須フィールドがある"""
        cases = _load_ground_truth()
        phase_b = [c for c in cases if c["id"] in PHASE_B_IDS]
        required = {"id", "question", "answer", "contexts", "ground_truth", "category"}
        for case in phase_b:
            missing = required - set(case.keys())
            assert not missing, f"{case['id']} missing fields: {missing}"

    def test_phase_b_categories(self):
        """Phase B エントリのカテゴリが正しい"""
        cases = _load_ground_truth()
        phase_b = {c["id"]: c for c in cases if c["id"] in PHASE_B_IDS}
        expected_categories = {
            "gt-078": "emergency",
            "gt-079": "emergency",
            "gt-080": "emergency",
            "gt-081": "reception",
            "gt-082": "reception",
            "gt-083": "clarification",
            "gt-084": "clarification",
            "gt-085": "reception",
            "gt-086": "accessibility",
            "gt-087": "emergency",
        }
        for case_id, expected_cat in expected_categories.items():
            if case_id in phase_b:
                assert phase_b[case_id]["category"] == expected_cat, (
                    f"{case_id}: expected category '{expected_cat}', "
                    f"got '{phase_b[case_id]['category']}'"
                )


# ---------------------------------------------------------------------------
# Test: RAGAS evaluation (requires ragas + OPENAI_API_KEY)
# ---------------------------------------------------------------------------


@pytest.mark.ragas
class TestRagasPhaseB:
    """Phase B ground truth に対する RAGAS 評価"""

    @pytest.fixture
    def evaluator(self):
        """RAGAS 評価器を取得（未インストール時は skip）"""
        try:
            from backend.evaluation.ragas_pipeline import RagasEvaluator

            return RagasEvaluator()
        except ImportError:
            pytest.skip("ragas is not installed")

    @pytest.mark.asyncio
    async def test_phase_b_single_evaluation(self, evaluator):
        """Phase B エントリ 1 件の RAGAS 評価"""
        cases = _load_ground_truth()
        phase_b = [c for c in cases if c["id"] in PHASE_B_IDS]
        if not phase_b:
            pytest.skip("No Phase B entries found")

        case = phase_b[0]
        result = await evaluator.evaluate_single(
            question=case["question"],
            answer=case["answer"],
            contexts=case["contexts"],
            ground_truth=case["ground_truth"],
        )
        assert result.error is None, f"Evaluation error: {result.error}"
        logger.info(
            "Single eval result: faithfulness=%.2f, relevancy=%.2f, correctness=%.2f",
            result.faithfulness,
            result.answer_relevancy,
            result.answer_correctness,
        )

    @pytest.mark.asyncio
    async def test_phase_b_batch_evaluation(self, evaluator):
        """Phase B エントリ全件のバッチ RAGAS 評価"""
        cases = _load_ground_truth()
        phase_b = [c for c in cases if c["id"] in PHASE_B_IDS]
        if not phase_b:
            pytest.skip("No Phase B entries found")

        report = await evaluator.evaluate_batch(phase_b)
        logger.info(
            "Batch eval: total=%d, evaluated=%d, metrics=%s",
            report.total_cases,
            report.evaluated_cases,
            report.metrics_summary,
        )

        # ベースラインチェック
        summary = report.metrics_summary
        for metric_name, score in summary.items():
            assert (
                score >= BASELINE_THRESHOLD
            ), f"Metric '{metric_name}' score {score:.2f} < baseline {BASELINE_THRESHOLD}"

    @pytest.mark.asyncio
    async def test_full_ground_truth_evaluation(self, evaluator):
        """全 ground truth (77 + 10 = 87 件) の包括評価"""
        cases = _load_ground_truth()
        assert len(cases) >= 87

        report = await evaluator.evaluate_batch(cases)
        logger.info(
            "Full eval: total=%d, evaluated=%d, metrics=%s",
            report.total_cases,
            report.evaluated_cases,
            report.metrics_summary,
        )

        summary = report.metrics_summary
        for metric_name, score in summary.items():
            assert (
                score >= BASELINE_THRESHOLD
            ), f"Metric '{metric_name}' score {score:.2f} < baseline {BASELINE_THRESHOLD}"


# ---------------------------------------------------------------------------
# Test: Category-level analysis (no ragas required)
# ---------------------------------------------------------------------------


class TestCategoryAnalysis:
    """カテゴリ別の ground truth 分布分析"""

    def test_emergency_category_count(self):
        """emergency カテゴリが 4 件以上"""
        cases = _load_ground_truth()
        emergency = [c for c in cases if c.get("category") == "emergency"]
        assert len(emergency) >= 4, f"Expected >= 4 emergency cases, got {len(emergency)}"

    def test_reception_category_count(self):
        """reception カテゴリが 3 件以上"""
        cases = _load_ground_truth()
        reception = [c for c in cases if c.get("category") == "reception"]
        assert len(reception) >= 3, f"Expected >= 3 reception cases, got {len(reception)}"

    def test_clarification_category_count(self):
        """clarification カテゴリが 2 件以上"""
        cases = _load_ground_truth()
        clarification = [c for c in cases if c.get("category") == "clarification"]
        assert (
            len(clarification) >= 2
        ), f"Expected >= 2 clarification cases, got {len(clarification)}"

    def test_english_cases_exist(self):
        """英語ケースが存在する"""
        cases = _load_ground_truth()
        english = [c for c in cases if c.get("language") == "en"]
        assert len(english) >= 1, "Expected at least 1 English case"
