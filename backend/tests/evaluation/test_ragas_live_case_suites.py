"""C/RAGAS live API case-suite selection tests."""

from collections import Counter

from backend.evaluation.run_live_api_eval import (
    ALL_LANGUAGES,
    CASE_SUITE_ALPHA_127,
    CASE_SUITE_DIAGNOSTIC_29,
    EVENT_SOURCE_REQUIREMENT,
    LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT,
    _load_case_suite_config,
    _required_live_sources,
    _source_requirement_ok,
    _suite_coverage,
)


def test_diagnostic_case_suite_preserves_29_case_manifest():
    config = _load_case_suite_config(CASE_SUITE_DIAGNOSTIC_29)
    queries = config["queries"]

    assert config["case_suite"] == CASE_SUITE_DIAGNOSTIC_29
    assert config["expected_total_cases"] == 29
    assert len(queries) == 29
    assert Counter(query["language"] for query in queries) == {
        "ja": 5,
        "en": 10,
        "zh": 7,
        "ko": 7,
    }


def test_alpha_case_suite_loads_full_127_case_ground_truth_dataset():
    config = _load_case_suite_config(CASE_SUITE_ALPHA_127)
    queries = config["queries"]

    assert config["case_suite"] == CASE_SUITE_ALPHA_127
    assert config["expected_total_cases"] == 127
    assert len(queries) == 127
    assert Counter(query["language"] for query in queries) == {
        "ja": 80,
        "en": 23,
        "zh": 12,
        "ko": 12,
    }
    assert all(query["ground_truth_id"] == query["id"] for query in queries)


def test_alpha_127_coverage_requires_all_languages_and_all_cases():
    full = _suite_coverage(
        case_suite=CASE_SUITE_ALPHA_127,
        selected_languages=ALL_LANGUAGES,
        requested_total=127,
    )
    partial_languages = _suite_coverage(
        case_suite=CASE_SUITE_ALPHA_127,
        selected_languages=("ja",),
        requested_total=80,
    )
    short_count = _suite_coverage(
        case_suite=CASE_SUITE_ALPHA_127,
        selected_languages=ALL_LANGUAGES,
        requested_total=126,
    )

    assert full["passed"] is True
    assert partial_languages["passed"] is False
    assert short_count["passed"] is False


def test_alpha_source_requirements_allow_live_metadata_aliases():
    assert _required_live_sources({"category": "access", "question": "雨の日の行き方は？"}) == [
        LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT
    ]
    assert _required_live_sources({"category": "community", "question": "DevDayはいつ？"}) == [
        EVENT_SOURCE_REQUIREMENT
    ]
    assert _required_live_sources({"category": "emergency", "question": "火事だ！"}) == []
    assert _required_live_sources({"category": "policy", "question": "緊急時の避難経路は？"}) == []


def test_source_requirement_accepts_knowledge_and_event_alternatives():
    assert _source_requirement_ok(
        {"sources": ["knowledge_base_cached"]}, [LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT]
    ) == (
        True,
        [],
        ["knowledge_base_cached"],
    )
    assert _source_requirement_ok({"sources": ["google_calendar"]}, [EVENT_SOURCE_REQUIREMENT]) == (
        True,
        [],
        ["google_calendar"],
    )
    assert _source_requirement_ok(
        {"sources": ["fallback"]}, [LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT]
    ) == (
        False,
        [LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT],
        ["fallback"],
    )
