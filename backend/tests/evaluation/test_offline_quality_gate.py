"""Tests for deterministic offline RAG quality signals."""

import json

import pytest

from backend.evaluation.quality_signals import (
    groundedness_score,
    language_match_score,
    score_case,
    summarize_quality_signals,
    toxicity_score,
)
from backend.evaluation.run_offline_quality_gate import run_offline_quality_gate


def test_language_match_score_accounts_for_supported_languages() -> None:
    assert language_match_score("エンジニアカフェは無料です。", "ja") == 1.0
    assert language_match_score("Engineer Cafe is free to use.", "en") == 1.0
    assert language_match_score("工程师咖啡可以免费使用。", "zh") == 1.0
    assert language_match_score("엔지니어 카페는 무료로 이용할 수 있습니다.", "ko") == 1.0
    assert language_match_score("Engineer Cafe is free to use.", "ja") == 0.0


def test_groundedness_and_hallucination_signals_use_context_overlap() -> None:
    grounded = groundedness_score(
        "Engineer Cafe is open from 9:00 to 22:00.",
        ["Engineer Cafe is open from 9:00 to 22:00 every day."],
    )
    unsupported = groundedness_score(
        "Engineer Cafe is open from 7:00 and has a private sauna.",
        ["Engineer Cafe is open from 9:00 to 22:00 every day."],
    )

    assert grounded > unsupported
    assert grounded >= 0.7
    assert unsupported < 0.7


def test_toxicity_score_flags_lexicon_hits() -> None:
    assert toxicity_score("Please use the reception desk.") == 0.0
    assert toxicity_score("shut up") == 1.0


def test_score_case_reports_failures_without_external_services() -> None:
    result = score_case(
        {
            "query_id": "case-1",
            "language": "en",
            "answer": "エンジニアカフェは7時から開いています。shut up",
            "contexts": ["Engineer Cafe is open from 9:00 to 22:00."],
        }
    )

    assert result.passed is False
    assert "language_match" in result.failures
    assert "groundedness" in result.failures
    assert "toxicity" in result.failures


def test_summarize_quality_signals_groups_by_language() -> None:
    summary = summarize_quality_signals(
        [
            {
                "query_id": "ja-1",
                "language": "ja",
                "answer": "エンジニアカフェの開館時間は9:00から22:00です。",
                "contexts": ["エンジニアカフェの開館時間は9:00から22:00です。"],
            },
            {
                "query_id": "en-1",
                "language": "en",
                "answer": "Engineer Cafe is free to use.",
                "contexts": ["Engineer Cafe is free to use."],
            },
        ]
    )

    assert summary["overall"]["case_count"] == 2
    assert summary["overall"]["passed"] is True
    assert set(summary["per_language"]) == {"en", "ja"}
    assert summary["failed_cases"] == []


def test_cross_lingual_live_context_uses_reference_grounding_context() -> None:
    result = score_case(
        {
            "query_id": "en-cross-lingual",
            "language": "en",
            "answer": "Engineer Cafe is open from 9:00 to 22:00.",
            "contexts": ["エンジニアカフェの開館時間は9:00から22:00です。"],
            "ground_truth": "Engineer Cafe is open from 9:00 to 22:00.",
        },
        include_ground_truth_context=False,
    )

    assert result.language_match == 1.0
    assert result.groundedness >= 0.55
    assert result.cross_lingual_context is True
    assert result.reference_grounding_context is True
    assert result.passed is True
    assert result.failures == []


def test_cross_lingual_reference_grounding_still_fails_unsupported_answer() -> None:
    result = score_case(
        {
            "query_id": "en-cross-lingual-unsupported",
            "language": "en",
            "answer": "Engineer Cafe is open from 7:00 and has a private sauna.",
            "contexts": ["エンジニアカフェの開館時間は9:00から22:00です。"],
            "ground_truth": "Engineer Cafe is open from 9:00 to 22:00.",
        },
        include_ground_truth_context=False,
    )

    assert result.cross_lingual_context is True
    assert result.reference_grounding_context is True
    assert result.passed is False
    assert "groundedness" in result.failures
    assert "hallucination_risk" in result.failures


def test_cross_lingual_context_still_fails_wrong_language_answer() -> None:
    result = score_case(
        {
            "query_id": "wrong-language-cross-lingual",
            "language": "en",
            "answer": "エンジニアカフェの開館時間は9:00から22:00です。",
            "contexts": ["エンジニアカフェの開館時間は9:00から22:00です。"],
        },
        include_ground_truth_context=False,
    )

    assert result.reference_grounding_context is False
    assert result.passed is False
    assert "language_match" in result.failures


def test_run_offline_quality_gate_writes_reports_without_ragas_or_live_secrets(tmp_path) -> None:
    result = run_offline_quality_gate(
        languages=["ja", "en"],
        max_cases=2,
        output_dir=tmp_path,
    )

    assert result["mode"] == "offline"
    assert result["blocking_by_default"] is False
    assert result["quality_signals"]["overall"]["case_count"] == 4
    assert result["quality_signals"]["overall"]["passed"] is True

    reports = sorted(tmp_path.glob("offline_quality_gate_*.json"))
    summaries = sorted(tmp_path.glob("offline_quality_gate_*.md"))
    assert len(reports) == 1
    assert len(summaries) == 1

    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["quality_signals"]["per_language"]["ja"]["case_count"] == 2
    assert "Offline RAG Quality Gate" in summaries[0].read_text(encoding="utf-8")


def test_run_offline_quality_gate_can_surface_enforceable_failures(tmp_path) -> None:
    result = run_offline_quality_gate(
        languages=["en"],
        max_cases=1,
        output_dir=tmp_path,
        thresholds={"groundedness_min": 1.01},
    )

    assert result["quality_signals"]["overall"]["passed"] is False
    assert result["quality_signals"]["failed_cases"][0]["failures"] == ["groundedness"]


def test_language_match_rejects_unknown_language() -> None:
    with pytest.raises(ValueError, match="unsupported expected_language"):
        language_match_score("bonjour", "fr")
