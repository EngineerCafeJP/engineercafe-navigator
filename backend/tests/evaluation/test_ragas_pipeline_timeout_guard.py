"""Tests for timeout guard around ragas evaluate() calls."""

import time

import pytest

from backend.evaluation.ragas_pipeline import RagasEvaluator


class TestRagasEvaluateTimeoutGuard:
    @pytest.mark.asyncio
    async def test_ragas_evaluate_with_timeout_returns_result(self, monkeypatch):
        evaluator = RagasEvaluator(evaluation_llm="mock", evaluation_embeddings="mock")
        monkeypatch.setattr(evaluator, "_build_eval_kwargs", lambda metrics_objs: {})

        from backend.evaluation import ragas_pipeline as rp

        monkeypatch.setattr(rp, "_ragas_evaluate", lambda dataset, **kwargs: {"ok": True})
        result = await evaluator._ragas_evaluate_with_timeout(  # type: ignore[attr-defined]
            dataset={"dummy": True},
            metrics_objs=[],
            timeout_seconds=1.0,
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_ragas_evaluate_with_timeout_raises_timeout(self, monkeypatch):
        evaluator = RagasEvaluator(evaluation_llm="mock", evaluation_embeddings="mock")
        monkeypatch.setattr(evaluator, "_build_eval_kwargs", lambda metrics_objs: {})

        from backend.evaluation import ragas_pipeline as rp

        def _slow_eval(dataset, **kwargs):
            time.sleep(0.2)
            return {"ok": True}

        monkeypatch.setattr(rp, "_ragas_evaluate", _slow_eval)

        with pytest.raises(TimeoutError):
            await evaluator._ragas_evaluate_with_timeout(  # type: ignore[attr-defined]
                dataset={"dummy": True},
                metrics_objs=[],
                timeout_seconds=0.01,
            )
