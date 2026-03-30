"""Tests for multilingual RAGAS evaluation runner (#382)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.evaluation.run_multilingual_eval import (
    MULTILINGUAL_QUERIES_PATH,
    compare_with_baseline,
    load_multilingual_config,
    load_query_cases,
    run_multilingual_evaluation,
    validate_multilingual_config,
)


class TestMultilingualQueryManifest:
    """Dataset validation for multilingual evaluation inputs."""

    def test_manifest_file_exists(self):
        assert MULTILINGUAL_QUERIES_PATH.exists()

    def test_manifest_validates_expected_distribution(self):
        config = load_multilingual_config()

        counts = validate_multilingual_config(config)

        assert counts == {"ja": 4, "en": 10, "zh": 5, "ko": 5}

    def test_manifest_references_existing_ground_truth_entries(self):
        config = load_multilingual_config()

        for language, expected_count in (("ja", 4), ("en", 10), ("zh", 5), ("ko", 5)):
            cases = load_query_cases(config, language=language)
            assert len(cases) == expected_count
            assert all(case["language"] == language for case in cases)
            assert all(case["ground_truth_id"].startswith("gt-") for case in cases)

    def test_manifest_can_be_limited_per_language(self):
        config = load_multilingual_config()

        cases = load_query_cases(config, language="en", max_cases=3)

        assert len(cases) == 3
        assert [case["query_id"] for case in cases] == ["ml-en-001", "ml-en-002", "ml-en-003"]


class TestMultilingualComparison:
    """Target and baseline comparison logic."""

    def test_compare_with_baseline_flags_failures(self):
        config = load_multilingual_config()
        lang_results = {
            "ja": {
                "metrics": {
                    "context_precision": 1.0,
                    "answer_correctness": 0.84,
                    "answer_relevancy": 0.92,
                    "faithfulness": 0.90,
                },
                "requested_case_count": 4,
                "evaluated_case_count": 4,
                "skipped_case_count": 0,
                "errors": [],
            },
            "en": {
                "metrics": {
                    "context_precision": 1.0,
                    "answer_correctness": 0.78,
                    "answer_relevancy": 0.90,
                    "faithfulness": 0.88,
                },
                "requested_case_count": 10,
                "evaluated_case_count": 10,
                "skipped_case_count": 0,
                "errors": [],
            },
        }

        comparison = compare_with_baseline(lang_results, config, languages=["ja", "en"])

        assert comparison["all_targets_met"] is False
        assert comparison["per_language"]["ja"]["passed"] is False
        assert comparison["per_language"]["en"]["passed"] is True
        assert comparison["per_language"]["ja"]["metrics"]["answer_correctness"]["target"] == 0.85
        assert comparison["per_language"]["ja"]["metrics"]["answer_correctness"]["baseline"] == 0.77
        assert comparison["failed_targets"] == [
            {
                "language": "ja",
                "metric": "answer_correctness",
                "actual": 0.84,
                "target": 0.85,
            }
        ]


class TestRunMultilingualEvaluation:
    """Runner behavior without calling live RAGAS."""

    @pytest.mark.asyncio()
    async def test_run_multilingual_evaluation_writes_reports(self, tmp_path):
        async def fake_evaluate_language(*, language, cases, mode):
            del mode
            metrics = {
                "context_precision": 1.0,
                "answer_correctness": {
                    "ja": 0.86,
                    "en": 0.78,
                    "zh": 0.66,
                    "ko": 0.67,
                }[language],
                "answer_relevancy": 0.91,
                "faithfulness": 0.89,
            }
            return {
                "language": language,
                "requested_case_count": len(cases),
                "evaluated_case_count": len(cases),
                "skipped_case_count": 0,
                "metrics": metrics,
                "errors": [],
                "results": [],
            }

        with patch(
            "backend.evaluation.run_multilingual_eval.evaluate_language",
            side_effect=fake_evaluate_language,
        ):
            result = await run_multilingual_evaluation(
                languages=["ja", "en", "zh", "ko"],
                output_dir=tmp_path,
            )

        assert result["comparison"]["all_targets_met"] is True
        assert result["query_counts"] == {"ja": 4, "en": 10, "zh": 5, "ko": 5}
        assert set(result["per_language"]) == {"ja", "en", "zh", "ko"}

        json_reports = sorted(tmp_path.glob("multilingual_eval_*.json"))
        text_reports = sorted(tmp_path.glob("multilingual_eval_*.txt"))
        assert len(json_reports) == 1
        assert len(text_reports) == 1

        payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
        assert payload["comparison"]["all_targets_met"] is True
        assert payload["per_language"]["zh"]["requested_case_count"] == 5
        assert "RAGAS Multilingual Evaluation Report" in text_reports[0].read_text(encoding="utf-8")


@pytest.mark.ragas
@pytest.mark.asyncio()
async def test_run_multilingual_evaluation_golden_smoke(tmp_path):
    from backend.evaluation.ragas_pipeline import RagasEvaluator

    evaluator = RagasEvaluator(max_cases=1)
    if not evaluator.is_available:
        pytest.skip("ragas not installed or evaluation credentials are unavailable")

    result = await run_multilingual_evaluation(
        languages=["en"],
        max_cases=1,
        output_dir=tmp_path,
    )

    assert result["per_language"]["en"]["evaluated_case_count"] == 1
    assert "answer_correctness" in result["per_language"]["en"]["metrics"]


def test_manifest_json_is_loadable():
    data = json.loads(Path(MULTILINGUAL_QUERIES_PATH).read_text(encoding="utf-8"))
    assert data["baseline"]["date"] == "2026-03-21"
