"""C/RAGAS live API case-suite selection tests."""

import json
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
    TARGETS,
    _call_chat_api,
    _format_report,
    _load_case_suite_config,
    _required_live_sources,
    _source_requirement_ok,
    _suite_coverage,
    run_live_api_evaluation,
)

NO_RAGAS_JUDGE_METADATA = {
    "provider": "none",
    "provider_label": "none",
    "model": None,
    "embeddings_provider": None,
    "embeddings_model": None,
    "fallback": False,
    "openai_key_present": False,
    "openrouter_key_present": False,
    "release_gate_eligible": False,
}


def _install_small_live_eval_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    queries,
    ground_truth_cases,
    chat_responses_by_question,
    captured_ragas_cases,
):
    def fake_load_case_suite_config(case_suite):
        return {
            "case_suite": case_suite,
            "expected_total_cases": len(queries),
            "queries": queries,
        }

    def fake_load_ground_truth_lookup():
        return {case["id"]: case for case in ground_truth_cases}

    async def fake_call_chat_api(client, *, base_url, question, language, api_key=None, **kwargs):
        return chat_responses_by_question[question]

    class FakeRagasEvaluator:
        is_available = True

        def __init__(self, *, metrics, max_cases):
            self.metrics = metrics
            self.max_cases = max_cases

        async def evaluate_batch(self, cases):
            captured_ragas_cases.extend(cases)
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
        "backend.evaluation.run_live_api_eval._load_case_suite_config",
        fake_load_case_suite_config,
    )
    monkeypatch.setattr(
        "backend.evaluation.run_live_api_eval._load_ground_truth_lookup",
        fake_load_ground_truth_lookup,
    )
    monkeypatch.setattr(
        "backend.evaluation.run_live_api_eval._call_chat_api",
        fake_call_chat_api,
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "evaluation.ragas_pipeline",
        SimpleNamespace(
            RagasEvaluator=FakeRagasEvaluator,
            resolve_ragas_judge_metadata=lambda: NO_RAGAS_JUDGE_METADATA,
        ),
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


def test_alpha_live_gate_uses_phase1_japanese_answer_target():
    assert TARGETS["ja"] == 0.80

    report = _format_report(
        {
            "ja": {
                "metrics": {"answer_correctness": 0.80},
                "requested_case_count": 1,
                "collected_case_count": 1,
                "evaluated_case_count": 1,
                "collection_error_count": 0,
                "ragas_error_count": 0,
            }
        },
        {
            "per_language": {
                "ja": {
                    "answer_correctness": {"actual": 0.80, "target": 0.80},
                    "answer_target_passed": True,
                    "evaluation_complete": {
                        "requested": 1,
                        "collected": 1,
                        "evaluated": 1,
                        "collection_errors": 0,
                        "ragas_errors": 0,
                        "passed": True,
                    },
                    "collection_errors": 0,
                    "ragas_errors": 0,
                    "source_failures": 0,
                }
            },
            "failed_targets": [],
            "failed_source_cases": [],
            "all_targets_met": True,
        },
        ("ja",),
        check_live_sources=True,
        case_suite=CASE_SUITE_ALPHA_127,
    )

    assert "Targets: ja >= 0.80, en >= 0.75, zh >= 0.75, ko >= 0.70" in report


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
async def test_live_eval_uses_api_metadata_contexts_for_ragas_and_quality_signals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    queries = [
        {
            "id": "live-context-case",
            "language": "ja",
            "question": "エンジニアカフェの開館時間は？",
            "category": "hours",
            "ground_truth_id": "gt-live-context",
            "metadata": {"intent": "hours"},
        },
        {
            "id": "live-evidence-case",
            "language": "ja",
            "question": "メインホールは何席ありますか？",
            "category": "facility-info",
            "ground_truth_id": "gt-live-evidence",
            "metadata": {"intent": "facility-info"},
        },
    ]
    ground_truth_cases = [
        {
            "id": "gt-live-context",
            "question": queries[0]["question"],
            "contexts": ["GOLDEN_CONTEXT_SHOULD_NOT_BE_USED: 開館時間は10:00から18:00です。"],
            "ground_truth": "開館時間は9:00から22:00です。",
        },
        {
            "id": "gt-live-evidence",
            "question": queries[1]["question"],
            "contexts": ["GOLDEN_CONTEXT_SHOULD_NOT_BE_USED: メインホールは10席です。"],
            "ground_truth": "メインホールは30席です。",
        },
    ]
    live_context = "LIVE_RETRIEVED_CONTEXT: エンジニアカフェの開館時間は9:00から22:00です。"
    live_evidence = "LIVE_EVIDENCE: 1階メインホールは30席のコワーキングスペースです。"
    captured_ragas_cases = []
    _install_small_live_eval_fixture(
        monkeypatch,
        queries=queries,
        ground_truth_cases=ground_truth_cases,
        chat_responses_by_question={
            queries[0]["question"]: {
                "answer": "エンジニアカフェの開館時間は9:00から22:00です。",
                "metadata": {
                    "agent": "BusinessInfoAgent",
                    "route": "business_info",
                    "sources": ["enhanced_rag"],
                    "retrieved_contexts": [live_context],
                },
            },
            queries[1]["question"]: {
                "answer": "メインホールは30席です。",
                "metadata": {
                    "agent": "FacilityAgent",
                    "route": "facility",
                    "sources": ["enhanced_rag"],
                    "evidence": [{"content": live_evidence}],
                },
            },
        },
        captured_ragas_cases=captured_ragas_cases,
    )

    result = await run_live_api_evaluation(
        base_url="http://example.test",
        languages=("ja",),
        output_dir=tmp_path,
        case_suite=CASE_SUITE_DIAGNOSTIC_29,
        metrics=("answer_correctness",),
        report_timestamp="live-context-quality",
    )

    ragas_cases_by_id = {case["query_id"]: case for case in captured_ragas_cases}
    assert ragas_cases_by_id["live-context-case"]["contexts"] == [live_context]
    assert ragas_cases_by_id["live-evidence-case"]["contexts"] == [live_evidence]
    assert {case["evaluation_context_source"] for case in captured_ragas_cases} == {
        "live_api_metadata"
    }
    assert result["ragas_context_source"] == "live_api_metadata"
    assert result["quality_signals"]["overall"]["case_count"] == 2
    assert result["quality_signals"]["overall"]["passed"] is True
    assert result["comparison"]["quality_signals"]["overall"]["passed"] is True
    assert result["comparison"]["per_language"]["ja"]["quality_signals"]["passed"] is True
    assert "Quality signals:" in result["report"]


@pytest.mark.asyncio()
async def test_live_eval_uses_reference_grounding_for_cross_lingual_contexts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    query = {
        "id": "en-cross-lingual-context",
        "language": "en",
        "question": "What are Engineer Cafe's opening hours?",
        "category": "hours",
        "ground_truth_id": "gt-en-cross-lingual-context",
        "metadata": {"intent": "hours"},
    }
    live_context = "エンジニアカフェの開館時間は9:00から22:00です。"
    captured_ragas_cases = []
    _install_small_live_eval_fixture(
        monkeypatch,
        queries=[query],
        ground_truth_cases=[
            {
                "id": "gt-en-cross-lingual-context",
                "question": query["question"],
                "contexts": ["GOLDEN_CONTEXT_SHOULD_NOT_BE_USED: open from 10:00 to 18:00."],
                "answer": "Engineer Cafe is open from 9:00 to 22:00.",
                "ground_truth": "Use the official opening-hours answer from the reference dataset.",
            }
        ],
        chat_responses_by_question={
            query["question"]: {
                "answer": "Engineer Cafe is open from 9:00 to 22:00.",
                "metadata": {
                    "agent": "BusinessInfoAgent",
                    "route": "business_info",
                    "sources": ["enhanced_rag"],
                    "retrieved_contexts": [live_context],
                },
            }
        },
        captured_ragas_cases=captured_ragas_cases,
    )

    result = await run_live_api_evaluation(
        base_url="http://example.test",
        languages=("en",),
        output_dir=tmp_path,
        case_suite=CASE_SUITE_DIAGNOSTIC_29,
        metrics=("answer_correctness",),
        report_timestamp="cross-lingual-context-quality",
    )

    quality_case = result["quality_signals"]["cases"][0]
    assert captured_ragas_cases[0]["contexts"] == [live_context]
    assert captured_ragas_cases[0]["reference_answer"] == (
        "Engineer Cafe is open from 9:00 to 22:00."
    )
    assert quality_case["groundedness"] >= 0.55
    assert quality_case["cross_lingual_context"] is True
    assert quality_case["reference_grounding_context"] is True
    assert result["quality_signals"]["overall"]["passed"] is True
    assert result["comparison"]["per_language"]["en"]["quality_signals"]["passed"] is True


@pytest.mark.asyncio()
async def test_live_eval_cross_lingual_context_still_fails_unsupported_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    query = {
        "id": "en-cross-lingual-unsupported",
        "language": "en",
        "question": "What are Engineer Cafe's opening hours?",
        "category": "hours",
        "ground_truth_id": "gt-en-cross-lingual-unsupported",
        "metadata": {"intent": "hours"},
    }
    captured_ragas_cases = []
    _install_small_live_eval_fixture(
        monkeypatch,
        queries=[query],
        ground_truth_cases=[
            {
                "id": "gt-en-cross-lingual-unsupported",
                "question": query["question"],
                "contexts": ["GOLDEN_CONTEXT_SHOULD_NOT_BE_USED: open from 10:00 to 18:00."],
                "answer": "Engineer Cafe is open from 9:00 to 22:00.",
                "ground_truth": "Use the official opening-hours answer from the reference dataset.",
            }
        ],
        chat_responses_by_question={
            query["question"]: {
                "answer": "Engineer Cafe is open from 7:00 and has a private sauna.",
                "metadata": {
                    "agent": "BusinessInfoAgent",
                    "route": "business_info",
                    "sources": ["enhanced_rag"],
                    "retrieved_contexts": ["エンジニアカフェの開館時間は9:00から22:00です。"],
                },
            }
        },
        captured_ragas_cases=captured_ragas_cases,
    )

    result = await run_live_api_evaluation(
        base_url="http://example.test",
        languages=("en",),
        output_dir=tmp_path,
        case_suite=CASE_SUITE_DIAGNOSTIC_29,
        metrics=("answer_correctness",),
        report_timestamp="cross-lingual-context-unsupported",
    )

    quality_case = result["quality_signals"]["cases"][0]
    assert quality_case["cross_lingual_context"] is True
    assert quality_case["reference_grounding_context"] is True
    assert result["quality_signals"]["overall"]["passed"] is False
    assert {"groundedness", "hallucination_risk"}.issubset(set(quality_case["failures"]))
    assert result["comparison"]["per_language"]["en"]["quality_signals"]["passed"] is False


@pytest.mark.asyncio()
async def test_live_eval_quality_gate_fails_required_rag_case_without_live_contexts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    query = {
        "id": "missing-live-context-case",
        "language": "ja",
        "question": "雨の日にエンジニアカフェへ行く最短ルートは？",
        "category": "access",
        "ground_truth_id": "gt-missing-live-context",
        "metadata": {"intent": "access"},
    }
    captured_ragas_cases = []
    _install_small_live_eval_fixture(
        monkeypatch,
        queries=[query],
        ground_truth_cases=[
            {
                "id": "gt-missing-live-context",
                "question": query["question"],
                "contexts": ["天神駅16番出口から天神地下街を経由します。"],
                "ground_truth": "天神駅16番出口から天神地下街、アクロス福岡通路を経由します。",
            }
        ],
        chat_responses_by_question={
            query["question"]: {
                "answer": "天神駅16番出口から天神地下街、アクロス福岡通路を経由します。",
                "metadata": {
                    "agent": "BusinessInfoAgent",
                    "route": "business_info",
                    "sources": ["enhanced_rag"],
                },
            }
        },
        captured_ragas_cases=captured_ragas_cases,
    )

    result = await run_live_api_evaluation(
        base_url="http://example.test",
        languages=("ja",),
        output_dir=tmp_path,
        case_suite=CASE_SUITE_DIAGNOSTIC_29,
        metrics=("answer_correctness",),
        report_timestamp="missing-live-context-quality",
    )

    assert captured_ragas_cases[0]["contexts"] == []
    assert captured_ragas_cases[0]["evaluation_context_source"] == "missing_live_contexts"
    assert result["quality_signals"]["overall"]["passed"] is False
    assert result["quality_signals"]["failed_cases"] == [
        {
            "case_id": "missing-live-context-case",
            "language": "ja",
            "failures": ["missing_live_contexts"],
        }
    ]
    assert result["comparison"]["quality_signals"]["overall"]["passed"] is False
    assert result["comparison"]["per_language"]["ja"]["quality_signals"]["passed"] is False
    assert result["comparison"]["per_language"]["ja"]["passed"] is False
    assert result["comparison"]["all_targets_met"] is False
    assert "Quality signals:" in result["report"]
    assert "missing_live_contexts" in result["report"]


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
        SimpleNamespace(
            RagasEvaluator=FakeRagasEvaluator,
            resolve_ragas_judge_metadata=lambda: NO_RAGAS_JUDGE_METADATA,
        ),
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
    assert result["per_language"]["ja"]["collected_case_count"] == 79
    assert result["per_language"]["ja"]["evaluated_case_count"] == 79
    assert result["per_language"]["ja"]["api_failed_case_count"] == 1
    assert result["per_language"]["ja"]["collection_error_count"] == 1
    assert result["per_language"]["ja"]["ragas_error_count"] == 0
    assert result["per_language"]["ja"]["collection_errors"][0]["error_type"] == "api_call_failed"
    assert result["comparison"]["per_language"]["ja"]["evaluation_complete"] == {
        "requested": 80,
        "collected": 79,
        "evaluated": 79,
        "collection_errors": 1,
        "ragas_errors": 0,
        "passed": False,
    }
    assert result["evaluation_summary"] == {
        "requested_total_cases": 127,
        "collected_total_cases": 126,
        "evaluated_total_cases": 126,
        "collection_error_total": 1,
        "api_failed_total": 1,
        "ragas_error_total": 0,
        "requested_by_language": {"ja": 80, "en": 23, "zh": 12, "ko": 12},
        "collected_by_language": {"ja": 79, "en": 23, "zh": 12, "ko": 12},
        "evaluated_by_language": {"ja": 79, "en": 23, "zh": 12, "ko": 12},
        "collection_errors_by_language": {"ja": 1, "en": 0, "zh": 0, "ko": 0},
        "api_failed_by_language": {"ja": 1, "en": 0, "zh": 0, "ko": 0},
        "ragas_errors_by_language": {"ja": 0, "en": 0, "zh": 0, "ko": 0},
        "collection_complete": False,
        "evaluation_complete": False,
    }
    assert result["comparison"]["alpha_release_gate_met"] is False
    assert result["artifact_metadata"] == {
        "report_timestamp": "alpha-live-test-c",
        "json_report_filename": "live_api_eval_alpha-live-test-c.json",
        "text_report_filename": "live_api_eval_alpha-live-test-c.txt",
        "progress_report_filename": "live_api_eval_alpha-live-test-c.progress.json",
        "ragas_judge": NO_RAGAS_JUDGE_METADATA,
        "expected_total_cases": 127,
        "manifest_language_counts": {"ja": 80, "en": 23, "zh": 12, "ko": 12},
        "selected_language_counts": {"ja": 80, "en": 23, "zh": 12, "ko": 12},
        "chat_interval_seconds": 0.0,
        "chat_retry_attempts": 4,
        "chat_retry_backoff_seconds": 2.0,
        "chat_timeout_seconds": 60.0,
    }
    assert (tmp_path / "live_api_eval_alpha-live-test-c.json").is_file()
    assert (tmp_path / "live_api_eval_alpha-live-test-c.txt").is_file()
    progress_path = tmp_path / "live_api_eval_alpha-live-test-c.progress.json"
    assert progress_path.is_file()
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert progress["mode"] == "live-api-progress"
    assert progress["case_suite"] == CASE_SUITE_ALPHA_127
    assert progress["total_requested_cases"] == 127
    assert progress["phase"] == "report_written"
    assert progress["collection"]["collected"] == 126
    assert progress["collection"]["errors"] == 1
    assert progress["ragas"]["completed_languages"] == ["ja", "en", "zh", "ko"]
    assert progress["ragas"]["evaluated_total"] == 126
    assert "collection_errors: 1 (api_failed=1)" in result["report"]
    assert "Collection/evaluation summary:" in result["report"]
    assert "RAGAS judge:" in result["report"]
    assert "provider: none" in result["report"]
    assert "totals: requested=127 collected=126 evaluated=126" in result["report"]
    assert "ja=requested:80/collected:79/evaluated:79/errors:1" in result["report"]
    assert (
        "evaluation_complete: collected=79/80 evaluated=79/80 "
        "collection_errors=1 ragas_errors=0 [FAIL]"
    ) in result["report"]
    assert "Alpha release gate met: NO" in result["report"]


@pytest.mark.asyncio()
async def test_alpha_127_release_gate_requires_direct_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    async def fake_call_chat_api(client, *, base_url, question, language, api_key=None, **kwargs):
        answer_by_language = {
            "ja": "エンジニアカフェは9:00から22:00まで開館しています。",
            "en": "Engineer Cafe is open from 9:00 to 22:00.",
            "zh": "工程师咖啡营业时间是9:00到22:00。",
            "ko": "엔지니어 카페는 9:00부터 22:00까지 운영합니다.",
        }
        answer = answer_by_language.get(language, answer_by_language["ja"])
        return {
            "answer": answer,
            "metadata": {
                "agent": "FakeAgent",
                "category": "test",
                "route": "fake",
                "sources": ["knowledge_base_cached", "google_calendar"],
                "retrieved_contexts": [answer],
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

    openrouter_metadata = {
        "provider": "openrouter",
        "provider_label": "OpenRouter fallback",
        "model": "openai/gpt-5-mini",
        "embeddings_provider": "openrouter",
        "embeddings_model": "openai/text-embedding-3-small",
        "fallback": True,
        "openai_key_present": False,
        "openrouter_key_present": True,
        "release_gate_eligible": False,
    }

    monkeypatch.setattr(
        "backend.evaluation.run_live_api_eval._call_chat_api",
        fake_call_chat_api,
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "evaluation.ragas_pipeline",
        SimpleNamespace(
            RagasEvaluator=FakeRagasEvaluator,
            resolve_ragas_judge_metadata=lambda: openrouter_metadata,
        ),
    )

    result = await run_live_api_evaluation(
        base_url="http://example.test",
        languages=ALL_LANGUAGES,
        output_dir=tmp_path,
        case_suite=CASE_SUITE_ALPHA_127,
        metrics=("answer_correctness",),
        report_timestamp="alpha-live-openrouter",
    )

    assert result["comparison"]["all_targets_met"] is True
    assert result["suite_coverage"]["passed"] is True
    assert result["comparison"]["ragas_judge"] == openrouter_metadata
    assert result["ragas_judge"] == openrouter_metadata
    assert result["artifact_metadata"]["ragas_judge"] == openrouter_metadata
    assert result["comparison"]["alpha_release_gate_met"] is False
    assert "provider: OpenRouter fallback" in result["report"]
    assert "release_gate_eligible: FAIL" in result["report"]
    assert "All targets met: YES" in result["report"]
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
