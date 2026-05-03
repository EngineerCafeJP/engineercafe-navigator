"""C/RAGAS live API case-suite selection tests."""

from collections import Counter
from types import SimpleNamespace

import httpx
import pytest

from backend.evaluation.run_live_api_eval import (
    ALL_LANGUAGES,
    CASE_SUITE_ALPHA_127,
    CASE_SUITE_DIAGNOSTIC_29,
    EVENT_SOURCE_REQUIREMENT,
    LOCAL_KNOWLEDGE_SOURCE_REQUIREMENT,
    _call_chat_api,
    _load_case_suite_config,
    _required_live_sources,
    _source_requirement_ok,
    _suite_coverage,
    run_live_api_evaluation,
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


@pytest.mark.asyncio()
async def test_live_eval_keeps_alpha_127_manifest_count_when_api_collection_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    calls = []

    async def fake_call_chat_api(client, *, base_url, question, language, api_key=None, **kwargs):
        calls.append((question, language))
        if len(calls) == 1:
            raise TimeoutError("synthetic timeout")
        return {
            "answer": "grounded answer",
            "metadata": {
                "agent": "FakeAgent",
                "category": "test",
                "route": "fake",
                "sources": ["knowledge_base_cached", "google_calendar"],
            },
        }

    class FakeRagasEvaluator:
        is_available = True

        def __init__(self, *, metrics, max_cases):
            self.metrics = metrics
            self.max_cases = max_cases

        async def evaluate_batch(self, cases):
            return SimpleNamespace(
                evaluated_cases=len(cases),
                skipped_cases=0,
                metrics={
                    "context_precision": 1.0,
                    "answer_correctness": 1.0,
                    "answer_relevancy": 1.0,
                    "faithfulness": 1.0,
                },
                errors=[],
                results=[
                    SimpleNamespace(
                        question=case["question"],
                        answer_correctness=1.0,
                        answer_relevancy=1.0,
                        faithfulness=1.0,
                        context_precision=1.0,
                        error=None,
                    )
                    for case in cases
                ],
            )

    monkeypatch.setattr(
        "backend.evaluation.run_live_api_eval._call_chat_api",
        fake_call_chat_api,
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "evaluation.ragas_pipeline",
        SimpleNamespace(RagasEvaluator=FakeRagasEvaluator),
    )

    result = await run_live_api_evaluation(
        base_url="http://example.test",
        languages=ALL_LANGUAGES,
        output_dir=tmp_path,
        case_suite=CASE_SUITE_ALPHA_127,
        metrics=("answer_correctness",),
        report_timestamp="alpha-live-test-c",
    )

    assert result["suite_coverage"]["requested_total_cases"] == 127
    assert result["suite_coverage"]["passed"] is True
    assert result["per_language"]["ja"]["requested_case_count"] == 80
    assert result["per_language"]["ja"]["evaluated_case_count"] == 79
    assert result["per_language"]["ja"]["api_failed_case_count"] == 1
    assert result["per_language"]["ja"]["collection_error_count"] == 1
    assert result["per_language"]["ja"]["collection_errors"][0]["error_type"] == "api_call_failed"
    assert result["comparison"]["per_language"]["ja"]["evaluation_complete"] == {
        "requested": 80,
        "evaluated": 79,
        "collection_errors": 1,
        "passed": False,
    }
    assert result["comparison"]["alpha_release_gate_met"] is False
    assert result["artifact_metadata"] == {
        "report_timestamp": "alpha-live-test-c",
        "json_report_filename": "live_api_eval_alpha-live-test-c.json",
        "text_report_filename": "live_api_eval_alpha-live-test-c.txt",
        "chat_interval_seconds": 0.0,
        "chat_retry_attempts": 4,
        "chat_retry_backoff_seconds": 2.0,
    }
    assert (tmp_path / "live_api_eval_alpha-live-test-c.json").is_file()
    assert (tmp_path / "live_api_eval_alpha-live-test-c.txt").is_file()
    assert "collection_errors: 1 (api_failed=1)" in result["report"]
    assert "evaluation_complete: evaluated=79/80 collection_errors=1 [FAIL]" in result["report"]
    assert "Alpha release gate met: NO" in result["report"]


@pytest.mark.asyncio
async def test_call_chat_api_retries_429_with_retry_after(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0.01"}, request=request)
        return httpx.Response(
            200,
            json={"answer": "ok", "metadata": {"agent": "GeneralKnowledgeAgent"}},
            request=request,
        )

    monkeypatch.setattr("backend.evaluation.run_live_api_eval.asyncio.sleep", fake_sleep)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _call_chat_api(
            client,
            base_url="http://example.test",
            question="少し雑談して",
            language="ja",
            retry_attempts=2,
            retry_backoff_seconds=2.0,
        )

    assert result["answer"] == "ok"
    assert attempts == 2
    assert sleeps == [0.01]
