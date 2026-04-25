"""RAGAS Evaluation Pipeline テスト (v0.4.3 対応・6メトリクス)

ragas が未インストールの環境でも全てパスすること。
"""

from unittest.mock import patch

import pytest

from backend.evaluation.ragas_pipeline import (
    DEFAULT_METRICS,
    EVAL_MAX_CASES,
    OPENAI_EVAL_MODEL,
    RAGAS_MAX_RETRIES,
    RAGAS_MAX_WORKERS,
    RAGAS_TIMEOUT,
    RagasEvaluator,
    RagasReport,
    RagasResult,
    _ragas_available,
)

# =============================================================================
# RagasResult tests
# =============================================================================


class TestRagasResult:
    """RagasResult frozen dataclass テスト"""

    def test_default_scores(self):
        result = RagasResult(question="test")
        assert result.faithfulness == 0.0
        assert result.answer_relevancy == 0.0
        assert result.context_precision == 0.0
        assert result.context_recall == 0.0
        assert result.answer_correctness == 0.0
        assert result.answer_similarity == 0.0
        assert result.error is None
        assert result.nan_metrics == ()

    def test_with_all_six_scores(self):
        result = RagasResult(
            question="test",
            faithfulness=0.9,
            answer_relevancy=0.85,
            context_precision=0.8,
            context_recall=0.7,
            answer_correctness=0.75,
            answer_similarity=0.92,
        )
        assert result.faithfulness == 0.9
        assert result.answer_relevancy == 0.85
        assert result.answer_correctness == 0.75
        assert result.answer_similarity == 0.92

    def test_with_error(self):
        result = RagasResult(question="test", error="ragas not installed")
        assert result.error == "ragas not installed"

    def test_frozen(self):
        result = RagasResult(question="test")
        with pytest.raises(AttributeError):
            result.faithfulness = 1.0  # type: ignore[misc]


# =============================================================================
# RagasReport tests
# =============================================================================


class TestRagasReport:
    """RagasReport テスト"""

    def test_empty_report(self):
        report = RagasReport()
        assert report.total_cases == 0
        assert report.evaluated_cases == 0
        assert report.metrics_summary == {}

    def test_metrics_summary_six_metrics(self):
        report = RagasReport(
            total_cases=2,
            evaluated_cases=2,
            results=[
                RagasResult(
                    question="q1",
                    faithfulness=0.8,
                    answer_relevancy=0.9,
                    context_precision=0.7,
                    context_recall=0.6,
                    answer_correctness=0.75,
                    answer_similarity=0.85,
                ),
                RagasResult(
                    question="q2",
                    faithfulness=0.6,
                    answer_relevancy=0.7,
                    context_precision=0.5,
                    context_recall=0.4,
                    answer_correctness=0.55,
                    answer_similarity=0.65,
                ),
            ],
        )
        summary = report.metrics_summary
        assert summary["faithfulness"] == pytest.approx(0.7)
        assert summary["answer_relevancy"] == pytest.approx(0.8)
        assert summary["context_precision"] == pytest.approx(0.6)
        assert summary["context_recall"] == pytest.approx(0.5)
        assert summary["answer_correctness"] == pytest.approx(0.65)
        assert summary["answer_similarity"] == pytest.approx(0.75)

    def test_metrics_summary_ignores_errors(self):
        report = RagasReport(
            total_cases=2,
            evaluated_cases=1,
            results=[
                RagasResult(question="q1", faithfulness=0.8, error=None),
                RagasResult(question="q2", error="failed"),
            ],
        )
        summary = report.metrics_summary
        assert summary["faithfulness"] == pytest.approx(0.8)

    def test_all_errors_empty_summary(self):
        report = RagasReport(
            total_cases=1,
            results=[RagasResult(question="q1", error="failed")],
        )
        assert report.metrics_summary == {}

    def test_metrics_summary_excludes_nan_metrics(self):
        """NaN だったメトリクスはそのメトリクスの平均値から除外されること"""
        report = RagasReport(
            total_cases=2,
            evaluated_cases=2,
            results=[
                RagasResult(
                    question="q1",
                    faithfulness=0.8,
                    answer_correctness=0.0,  # NaN → 0.0
                    answer_similarity=0.9,
                    nan_metrics=("answer_correctness",),  # answer_correctness was NaN
                ),
                RagasResult(
                    question="q2",
                    faithfulness=0.6,
                    answer_correctness=0.7,
                    answer_similarity=0.8,
                    nan_metrics=(),
                ),
            ],
        )
        summary = report.metrics_summary
        # faithfulness: (0.8 + 0.6) / 2 = 0.7 — both valid
        assert summary["faithfulness"] == pytest.approx(0.7)
        # answer_correctness: only q2 (0.7) — q1 was NaN
        assert summary["answer_correctness"] == pytest.approx(0.7)
        # answer_similarity: (0.9 + 0.8) / 2 = 0.85 — both valid
        assert summary["answer_similarity"] == pytest.approx(0.85)


# =============================================================================
# RagasEvaluator tests
# =============================================================================


class TestRagasEvaluator:
    """RagasEvaluator テスト"""

    def test_init_default_six_metrics(self):
        evaluator = RagasEvaluator()
        assert evaluator.metric_names == DEFAULT_METRICS
        assert len(evaluator.metric_names) == 6
        assert "answer_correctness" in evaluator.metric_names
        assert "answer_similarity" in evaluator.metric_names
        assert evaluator.max_cases == EVAL_MAX_CASES

    def test_init_custom_metrics(self):
        evaluator = RagasEvaluator(metrics=("faithfulness",), max_cases=5)
        assert evaluator.metric_names == ("faithfulness",)
        assert evaluator.max_cases == 5


class TestRagasEvaluatorGracefulFallback:
    """ragas 未インストール時の graceful fallback テスト"""

    @pytest.fixture()
    def evaluator_no_ragas(self):
        """ragas が利用不可な状態のevaluator"""
        evaluator = RagasEvaluator()
        evaluator._ragas_available = False
        return evaluator

    @pytest.mark.asyncio()
    async def test_evaluate_single_fallback(self, evaluator_no_ragas):
        """ragas 未インストールで空結果を返すこと"""
        result = await evaluator_no_ragas.evaluate_single(
            question="テスト",
            answer="回答",
            contexts=["コンテキスト"],
            ground_truth="正解",
        )
        assert isinstance(result, RagasResult)
        assert result.error == "ragas not installed"
        assert result.faithfulness == 0.0
        assert result.answer_correctness == 0.0

    @pytest.mark.asyncio()
    async def test_evaluate_batch_fallback(self, evaluator_no_ragas):
        """ragas 未インストールでバッチ評価が空レポートを返すこと"""
        cases = [
            {
                "question": "q1",
                "answer": "a1",
                "contexts": ["c1"],
                "ground_truth": "gt1",
            }
        ]
        report = await evaluator_no_ragas.evaluate_batch(cases)
        assert isinstance(report, RagasReport)
        assert report.total_cases == 1
        assert report.skipped_cases == 1
        assert "ragas not installed" in report.errors

    @pytest.mark.asyncio()
    async def test_evaluate_single_exception_handling(self):
        """ragas 評価中の例外がキャッチされること"""
        evaluator = RagasEvaluator()
        evaluator._ragas_available = True

        with patch.object(
            evaluator,
            "_run_ragas_evaluation",
            side_effect=RuntimeError("LLM API error"),
        ):
            result = await evaluator.evaluate_single(
                question="テスト",
                answer="回答",
                contexts=["コンテキスト"],
                ground_truth="正解",
            )
            assert result.error == "LLM API error"


class TestRagasEvaluatorBatchLimit:
    """バッチ評価のケース数制限テスト"""

    @pytest.mark.asyncio()
    async def test_batch_respects_max_cases(self):
        """max_cases を超えるケースがスキップされること"""
        evaluator = RagasEvaluator(max_cases=2)
        evaluator._ragas_available = True

        async def mock_batch(eval_cases, report):
            report.results = [
                RagasResult(question="q0", faithfulness=0.8),
                RagasResult(question="q1", faithfulness=0.7),
            ]
            report.evaluated_cases = len(report.results)
            return report

        with patch.object(evaluator, "_run_batch_evaluation", side_effect=mock_batch):
            cases = [
                {
                    "question": f"q{i}",
                    "answer": f"a{i}",
                    "contexts": [f"c{i}"],
                    "ground_truth": f"gt{i}",
                }
                for i in range(5)
            ]
            report = await evaluator.evaluate_batch(cases)
            assert report.total_cases == 5
            assert report.skipped_cases == 3
            assert report.evaluated_cases == 2


class TestRagasEvaluatorIsAvailable:
    """is_available プロパティのテスト"""

    def test_available_property(self):
        evaluator = RagasEvaluator()
        evaluator._ragas_available = True
        assert evaluator.is_available is True

    def test_not_available_property(self):
        evaluator = RagasEvaluator()
        evaluator._ragas_available = False
        assert evaluator.is_available is False


class TestResolveEvaluationLLM:
    """_resolve_evaluation_llm のOpenRouter フォールバックテスト"""

    @pytest.mark.skipif(not _ragas_available, reason="ragas not installed")
    def test_openai_key_creates_direct_llm(self):
        """OPENAI_API_KEY が設定されている場合は LangchainLLMWrapper を返す"""
        env = {"OPENAI_API_KEY": "sk-test"}
        with patch.dict("os.environ", env, clear=True):
            with patch("ragas.llms.LangchainLLMWrapper") as mock_wrapper:
                with patch("langchain_openai.ChatOpenAI") as mock_chat:
                    mock_chat_instance = mock_chat.return_value
                    mock_wrapper.return_value = "mock_langchain_llm"
                    result = RagasEvaluator._resolve_evaluation_llm()
                    mock_chat.assert_called_once_with(
                        model=OPENAI_EVAL_MODEL,
                        api_key="sk-test",
                        max_tokens=8192,
                        timeout=float(RAGAS_TIMEOUT),
                        max_retries=3,
                    )
                    mock_wrapper.assert_called_once_with(mock_chat_instance)
                    assert result == "mock_langchain_llm"

    def test_no_keys_returns_none(self):
        """API キーが何も設定されていない場合は None"""
        with patch.dict("os.environ", {}, clear=True):
            result = RagasEvaluator._resolve_evaluation_llm()
            assert result is None

    @pytest.mark.skipif(not _ragas_available, reason="ragas not installed")
    def test_openrouter_key_creates_llm_with_client(self):
        """OPENROUTER_API_KEY 使用時は OpenAI client + llm_factory"""
        env = {"OPENROUTER_API_KEY": "sk-or-test"}
        with patch.dict("os.environ", env, clear=True):
            with patch("ragas.llms.llm_factory") as mock_factory:
                with patch("openai.OpenAI") as mock_openai:
                    mock_client = mock_openai.return_value
                    mock_factory.return_value = "mock_llm"
                    result = RagasEvaluator._resolve_evaluation_llm()
                    mock_openai.assert_called_once_with(
                        api_key="sk-or-test",
                        base_url="https://openrouter.ai/api/v1",
                        timeout=float(RAGAS_TIMEOUT),
                        max_retries=3,
                    )
                    from backend.evaluation.ragas_pipeline import OPENROUTER_EVAL_MODEL

                    mock_factory.assert_called_once_with(
                        OPENROUTER_EVAL_MODEL,
                        client=mock_client,
                        max_tokens=8192,
                    )
                    assert result == "mock_llm"

    def test_openrouter_llm_factory_import_error(self):
        """ragas.llms.llm_factory がインポートできない場合は None"""
        env = {"OPENROUTER_API_KEY": "sk-or-test"}
        with patch.dict("os.environ", env, clear=True):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("no ragas.llms"),
            ):
                result = RagasEvaluator._resolve_evaluation_llm()
                assert result is None

    def test_custom_evaluation_llm_parameter(self):
        """evaluation_llm パラメータで直接 LLM を渡せる"""
        mock_llm = "custom_llm_instance"
        evaluator = RagasEvaluator(evaluation_llm=mock_llm)
        assert evaluator._evaluation_llm == mock_llm

    def test_build_eval_kwargs_with_llm(self):
        """カスタム LLM がある場合は kwargs に含まれる"""
        evaluator = RagasEvaluator(evaluation_llm="mock_llm")
        kwargs = evaluator._build_eval_kwargs(["metric1"])
        assert kwargs["llm"] == "mock_llm"
        assert kwargs["metrics"] == ["metric1"]

    def test_build_eval_kwargs_without_llm(self):
        """カスタム LLM がない場合は kwargs に含まれない"""
        evaluator = RagasEvaluator()
        evaluator._evaluation_llm = None
        kwargs = evaluator._build_eval_kwargs(["metric1"])
        assert "llm" not in kwargs
        assert kwargs["metrics"] == ["metric1"]

    def test_build_eval_kwargs_includes_run_config(self):
        """RunConfig が kwargs に含まれること（ragas インストール時）"""
        evaluator = RagasEvaluator()
        evaluator._evaluation_llm = None
        evaluator._evaluation_embeddings = None
        kwargs = evaluator._build_eval_kwargs(["metric1"])
        # ragas がインストールされている場合は run_config が含まれる
        from backend.evaluation.ragas_pipeline import _RunConfig

        if _RunConfig is not None:
            assert "run_config" in kwargs
            rc = kwargs["run_config"]
            assert rc.timeout == RAGAS_TIMEOUT
            assert rc.max_retries == RAGAS_MAX_RETRIES
            assert rc.max_workers == RAGAS_MAX_WORKERS


class TestRunConfigDefaults:
    """RunConfig デフォルト値テスト"""

    def test_timeout_default(self):
        """デフォルトタイムアウトが 600 秒であること"""
        assert RAGAS_TIMEOUT == 600

    def test_max_retries_default(self):
        """デフォルト max_retries が 15 であること"""
        assert RAGAS_MAX_RETRIES == 15

    def test_max_workers_default(self):
        """デフォルト max_workers が 16 であること"""
        assert RAGAS_MAX_WORKERS == 16

    def test_openai_eval_model_default(self):
        """デフォルト評価モデルが gpt-5.2-2025-12-11 であること"""
        assert OPENAI_EVAL_MODEL == "gpt-5.2-2025-12-11"


class TestExtractScores:
    """_extract_scores のカラム名マッピングテスト"""

    def test_extract_with_column_mapping(self):
        """v0.4.3 のカラム名マッピングが正しく動作すること"""
        evaluator = RagasEvaluator()
        row = {
            "faithfulness": 0.9,
            "answer_relevancy": 0.85,
            "llm_context_precision_with_reference": 0.8,
            "context_recall": 0.7,
            "answer_correctness": 0.75,
            "answer_similarity": 0.65,
        }
        scores = evaluator._extract_scores(row)
        assert scores["faithfulness"] == 0.9
        assert scores["context_precision"] == 0.8
        assert scores["answer_correctness"] == 0.75
        assert scores["_nan_metrics"] == ()

    def test_extract_missing_column_defaults_zero(self):
        """存在しないカラムは 0.0 にフォールバック"""
        evaluator = RagasEvaluator(metrics=("faithfulness", "answer_correctness"))
        row = {"faithfulness": 0.9}
        scores = evaluator._extract_scores(row)
        assert scores["faithfulness"] == 0.9
        assert scores["answer_correctness"] == 0.0

    def test_extract_nan_values_tracked(self):
        """NaN 値が _nan_metrics に記録され、0.0 に変換されること"""
        evaluator = RagasEvaluator(metrics=("faithfulness", "answer_correctness"))
        row = {"faithfulness": 0.9, "answer_correctness": float("nan")}
        scores = evaluator._extract_scores(row)
        assert scores["faithfulness"] == 0.9
        assert scores["answer_correctness"] == 0.0
        assert "answer_correctness" in scores["_nan_metrics"]
        assert "faithfulness" not in scores["_nan_metrics"]


class TestGetMetricObjects:
    """_get_metric_objects テスト"""

    @pytest.mark.skipif(not _ragas_available, reason="ragas not installed")
    def test_returns_six_metric_instances(self):
        """デフォルトで6つのメトリクスインスタンスを返す"""
        evaluator = RagasEvaluator()
        metrics = evaluator._get_metric_objects()
        assert len(metrics) == 6

    @pytest.mark.skipif(not _ragas_available, reason="ragas not installed")
    def test_returns_custom_subset(self):
        """カスタムメトリクス指定で部分集合を返す"""
        evaluator = RagasEvaluator(metrics=("faithfulness", "answer_similarity"))
        metrics = evaluator._get_metric_objects()
        assert len(metrics) == 2


# =============================================================================
# ComprehensiveEvaluationReport ragas_metrics テスト
# =============================================================================


class TestReportRagasMetrics:
    """ComprehensiveEvaluationReport に ragas_metrics フィールドが追加されていること"""

    def test_ragas_metrics_field_exists(self):
        from backend.tests.utils.evaluators.report_generator import ComprehensiveEvaluationReport

        report = ComprehensiveEvaluationReport(
            report_id="test",
            timestamp="2026-02-15",
            ragas_metrics={
                "faithfulness": 0.85,
                "context_precision": 0.80,
                "answer_correctness": 0.75,
                "answer_similarity": 0.90,
            },
        )
        assert report.ragas_metrics is not None
        assert report.ragas_metrics["faithfulness"] == 0.85
        assert report.ragas_metrics["answer_correctness"] == 0.75

    def test_ragas_metrics_defaults_to_none(self):
        from backend.tests.utils.evaluators.report_generator import ComprehensiveEvaluationReport

        report = ComprehensiveEvaluationReport(
            report_id="test",
            timestamp="2026-02-15",
        )
        assert report.ragas_metrics is None


class TestNanMetricsDetection:
    def test_all_nan_metrics_detected_as_failure(self):
        from backend.evaluation.ragas_pipeline import RagasReport, RagasResult

        all_nan = (
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "answer_similarity",
        )
        report = RagasReport(
            total_cases=2,
            evaluated_cases=2,
            results=[
                RagasResult(question="q1", nan_metrics=all_nan),
                RagasResult(question="q2", nan_metrics=all_nan),
            ],
        )
        assert report.all_metrics_nan is True
        assert report.nan_ratio == 1.0

    def test_nan_ratio_partial(self):
        from backend.evaluation.ragas_pipeline import RagasReport, RagasResult

        report = RagasReport(
            total_cases=2,
            evaluated_cases=2,
            results=[
                RagasResult(
                    question="q1",
                    faithfulness=0.9,
                    nan_metrics=("answer_correctness",),
                ),
                RagasResult(question="q2", nan_metrics=()),
            ],
        )
        assert report.all_metrics_nan is False
        assert report.nan_ratio == pytest.approx(1 / 12, abs=0.01)

    def test_nan_ratio_empty_report(self):
        from backend.evaluation.ragas_pipeline import RagasReport

        report = RagasReport()
        assert report.all_metrics_nan is False
        assert report.nan_ratio == 0.0
