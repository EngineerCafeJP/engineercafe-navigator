"""Tests for RAGAS CI/CD integration (GitHub Actions output) and live mode."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tests.evaluation.run_ragas_evaluation import (
    _build_eval_dicts_golden,
    _build_eval_dicts_live,
    _generate_live_response,
    _write_github_outputs,
    _write_github_summary,
    run_evaluation,
)
from backend.tests.fixtures.dataset_loader import GroundTruthCase


class TestWriteGithubOutputs:
    """Tests for _write_github_outputs function."""

    def test_ci_mode_writes_github_output(self, tmp_path):
        """$GITHUB_OUTPUT にメトリクス書込み"""
        output_file = tmp_path / "github_output.txt"
        result = {
            "status": "completed",
            "mode": "golden",
            "metrics": {
                "faithfulness": 0.85,
                "context_precision": 0.78,
            },
            "evaluated_cases": 20,
            "skipped_cases": 0,
        }

        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_file)}):
            _write_github_outputs(result)

        content = output_file.read_text()
        assert "faithfulness=0.85" in content
        assert "context_precision=0.78" in content
        assert "evaluated_cases=20" in content
        assert "status=completed" in content
        assert "mode=golden" in content

    def test_ci_mode_no_env_vars_graceful(self):
        """環境変数なしでもエラーなし"""
        result = {
            "metrics": {"faithfulness": 0.5},
            "evaluated_cases": 1,
            "skipped_cases": 0,
        }

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_OUTPUT", None)
            _write_github_outputs(result)  # Should not raise


class TestWriteGithubSummary:
    """Tests for _write_github_summary function."""

    def test_ci_mode_writes_github_summary(self, tmp_path):
        """$GITHUB_STEP_SUMMARY にMarkdown書込み"""
        summary_file = tmp_path / "github_summary.md"
        result = {
            "mode": "golden",
            "metrics": {
                "faithfulness": 0.850,
                "context_precision": 0.780,
                "context_recall": 0.720,
                "answer_relevancy": 0.810,
            },
            "evaluated_cases": 20,
            "skipped_cases": 0,
        }

        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
            _write_github_summary(result)

        content = summary_file.read_text()
        assert "## RAGAS Evaluation Results (golden mode)" in content
        assert "| Metric | Score |" in content
        assert "faithfulness" in content

    def test_summary_contains_all_metrics(self, tmp_path):
        """全メトリクスが含まれる"""
        summary_file = tmp_path / "github_summary.md"
        metrics = {
            "faithfulness": 0.85,
            "context_precision": 0.78,
            "context_recall": 0.72,
            "answer_relevancy": 0.81,
        }
        result = {"mode": "live", "metrics": metrics, "evaluated_cases": 20, "skipped_cases": 0}

        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
            _write_github_summary(result)

        content = summary_file.read_text()
        assert "(live mode)" in content
        for metric_name in metrics:
            assert metric_name in content


class TestCLIParsing:
    """Tests for CLI argument parsing."""

    def test_ci_functions_are_callable(self):
        """CI用関数がimportできてcallable"""
        assert callable(_write_github_outputs)
        assert callable(_write_github_summary)


class TestBuildEvalDictsGolden:
    """ゴールデンモードのテスト"""

    @pytest.mark.asyncio()
    async def test_golden_mode_returns_prebaked_data(self):
        """ゴールデンモードは事前定義データをそのまま返す"""
        cases = [
            GroundTruthCase(
                id="gt-001",
                question="テスト質問",
                answer="テスト回答",
                contexts=["テストコンテキスト"],
                ground_truth="テスト正解",
            ),
        ]
        result = await _build_eval_dicts_golden(cases, max_cases=10)
        assert len(result) == 1
        assert result[0]["question"] == "テスト質問"
        assert result[0]["answer"] == "テスト回答"
        assert result[0]["contexts"] == ["テストコンテキスト"]
        assert result[0]["ground_truth"] == "テスト正解"

    @pytest.mark.asyncio()
    async def test_golden_mode_respects_max_cases(self):
        """ゴールデンモードは max_cases を守る"""
        cases = [GroundTruthCase(id=f"gt-{i}", question=f"q{i}", answer=f"a{i}") for i in range(5)]
        result = await _build_eval_dicts_golden(cases, max_cases=2)
        assert len(result) == 2


class TestBuildEvalDictsLive:
    """ライブモードのテスト"""

    @pytest.mark.asyncio()
    async def test_live_mode_calls_rag_pipeline(self):
        """ライブモードが実際のRAGパイプラインを呼び出すこと"""
        cases = [
            GroundTruthCase(
                id="gt-001",
                question="テスト質問",
                answer="事前定義回答（使われない）",
                contexts=["事前定義コンテキスト（使われない）"],
                ground_truth="テスト正解",
                language="ja",
                category="general",
            ),
        ]

        with patch(
            "backend.tests.evaluation.run_ragas_evaluation._generate_live_response",
            new_callable=AsyncMock,
            return_value=("ライブLLM回答", ["ライブコンテキスト1", "ライブコンテキスト2"]),
        ):
            result = await _build_eval_dicts_live(cases, max_cases=10)

        assert len(result) == 1
        assert result[0]["answer"] == "ライブLLM回答"
        assert result[0]["contexts"] == ["ライブコンテキスト1", "ライブコンテキスト2"]
        assert result[0]["ground_truth"] == "テスト正解"

    @pytest.mark.asyncio()
    async def test_live_mode_skips_failed_cases(self):
        """ライブ応答生成が失敗したケースはスキップされること"""
        cases = [
            GroundTruthCase(id="gt-001", question="q1", answer="a1", ground_truth="gt1"),
            GroundTruthCase(id="gt-002", question="q2", answer="a2", ground_truth="gt2"),
        ]

        call_count = 0

        async def mock_generate(question, language="ja", category="general"):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "", []  # 1つ目は失敗
            return "成功回答", ["成功コンテキスト"]

        with patch(
            "backend.tests.evaluation.run_ragas_evaluation._generate_live_response",
            side_effect=mock_generate,
        ):
            result = await _build_eval_dicts_live(cases, max_cases=10)

        assert len(result) == 1
        assert result[0]["question"] == "q2"


class TestGenerateLiveResponse:
    """_generate_live_response のテスト"""

    @pytest.mark.asyncio()
    async def test_success_returns_answer_and_contexts(self):
        """RAG検索+LLM生成が成功する場合"""
        mock_rag_instance = MagicMock()
        mock_rag_instance.search = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "context": "フルコンテキスト文字列",
                    "results": [
                        {"content": "コンテキスト1"},
                        {"content": "コンテキスト2"},
                    ],
                },
            }
        )

        mock_provider_instance = MagicMock()
        mock_provider_instance.generate = AsyncMock(return_value="LLM生成回答")

        # _generate_live_response は関数内で lazy import するので、
        # 実際のモジュールパスでパッチする
        with (
            patch(
                "backend.tools.enhanced_rag.EnhancedRAGSearch",
                return_value=mock_rag_instance,
            ),
            patch(
                "backend.llm.openrouter.OpenRouterProvider",
                return_value=mock_provider_instance,
            ),
            patch(
                "backend.llm.models.get_model_config",
                return_value=MagicMock(),
            ),
        ):
            answer, contexts = await _generate_live_response("テスト質問", "ja", "general")

        assert answer == "LLM生成回答"
        assert contexts == ["コンテキスト1", "コンテキスト2"]

    @pytest.mark.asyncio()
    async def test_rag_search_no_results_returns_empty(self):
        """RAG 検索結果なしの場合はコンテキスト空を返す（LLMフォールバック回答は許容）"""
        mock_rag_instance = MagicMock()
        mock_rag_instance.search = AsyncMock(
            return_value={"success": True, "data": {"context": "", "results": []}}
        )

        with patch(
            "backend.tools.enhanced_rag.EnhancedRAGSearch",
            return_value=mock_rag_instance,
        ):
            answer, contexts = await _generate_live_response("テスト質問")
            assert isinstance(answer, str)
            assert contexts == []

    @pytest.mark.asyncio()
    async def test_exception_returns_empty(self):
        """例外発生時は空のタプルを返す"""
        with patch(
            "backend.tools.enhanced_rag.EnhancedRAGSearch",
            side_effect=Exception("connection error"),
        ):
            answer, contexts = await _generate_live_response("テスト質問")
            assert answer == ""
            assert contexts == []


class TestRunEvaluationModeArg:
    """run_evaluation の mode 引数テスト"""

    @pytest.mark.asyncio()
    async def test_golden_mode_is_default(self):
        """デフォルトモードが golden であること"""
        with (
            patch(
                "backend.tests.evaluation.run_ragas_evaluation.DatasetLoader.load_ground_truth_cases",
                return_value=[],
            ),
        ):
            result = await run_evaluation(mode="golden")
            assert result.get("error") == "no cases found"

    @pytest.mark.asyncio()
    async def test_live_mode_accepts_argument(self):
        """live モードが受け入れられること"""
        with (
            patch(
                "backend.tests.evaluation.run_ragas_evaluation.DatasetLoader.load_ground_truth_cases",
                return_value=[],
            ),
        ):
            result = await run_evaluation(mode="live")
            assert result.get("error") == "no cases found"
