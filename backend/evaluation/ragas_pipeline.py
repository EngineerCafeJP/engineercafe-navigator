"""
RAGAS Evaluation Pipeline (v0.4.3 対応)

RAGシステムの品質を6メトリクスで評価するパイプライン:
  1. faithfulness           - コンテキストへの忠実度
  2. answer_relevancy       - 質問への回答関連性
  3. context_precision       - コンテキスト精度
  4. context_recall          - コンテキスト再現率
  5. answer_correctness      - 正解に対する回答正確性
  6. answer_similarity       - 正解との意味的類似度

ragas がインストールされていない場合は graceful fallback し、
テストは全てパスする状態を維持する。

Usage:
    pip install -e ".[evaluation]"
    evaluator = RagasEvaluator()
    result = await evaluator.evaluate_single(question, answer, contexts, ground_truth)
"""

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ragas のインポートを試行（未インストール時は graceful fallback）
_ragas_available = False
_ragas_evaluate = None
_SingleTurnSample = None
_EvaluationDataset = None
_metric_classes: Dict[str, Any] = {}

try:
    from ragas import EvaluationDataset, SingleTurnSample
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics._answer_correctness import AnswerCorrectness
    from ragas.metrics._answer_relevance import ResponseRelevancy
    from ragas.metrics._answer_similarity import AnswerSimilarity
    from ragas.metrics._context_precision import LLMContextPrecisionWithReference
    from ragas.metrics._context_recall import LLMContextRecall
    from ragas.metrics._faithfulness import Faithfulness
    from ragas.run_config import RunConfig as _RunConfig

    _ragas_available = True
    _ragas_evaluate = ragas_evaluate
    _SingleTurnSample = SingleTurnSample
    _EvaluationDataset = EvaluationDataset
    _metric_classes = {
        "faithfulness": Faithfulness,
        "answer_relevancy": ResponseRelevancy,
        "context_precision": LLMContextPrecisionWithReference,
        "context_recall": LLMContextRecall,
        "answer_correctness": AnswerCorrectness,
        "answer_similarity": AnswerSimilarity,
    }
except ImportError:
    _RunConfig = None  # type: ignore[assignment,misc]
    logger.info("ragas is not installed. Install with: pip install -e '.[evaluation]'")


def _safe_int_env(name: str, default: int) -> int:
    """Safely parse an integer environment variable with fallback."""
    raw = os.environ.get(name, str(default))
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.warning("Invalid %s value %s, using default %d", name, raw, default)
        return default


# 評価ケース数の上限（LLM APIコスト制御）
EVAL_MAX_CASES = _safe_int_env("EVAL_MAX_CASES", 10)

# Direct OpenAI 設定（OPENAI_API_KEY が設定されている場合に使用）
OPENAI_EVAL_MODEL = os.environ.get("RAGAS_EVAL_MODEL", "gpt-5.2-2025-12-11")

# OpenRouter 設定（OPENAI_API_KEY が未設定の場合のフォールバック）
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_EVAL_MODEL = os.environ.get("RAGAS_OPENROUTER_MODEL", "openai/gpt-5-mini")
OPENROUTER_EMBEDDING_MODEL = "openai/text-embedding-3-small"
# RAGAS の faithfulness / answer_correctness 評価は長いJSON出力を生成するため、
# 十分な max_tokens を確保する。
OPENROUTER_EVAL_MAX_TOKENS = 8192

# RAGAS RunConfig: answer_correctness/answer_similarity は複数回の LLM 分解呼び出しを行うため、
# 十分なタイムアウトを確保する。直接 OpenAI API なら高速だが余裕を持って 600s に設定。
RAGAS_TIMEOUT = _safe_int_env("RAGAS_TIMEOUT", 600)
RAGAS_MAX_RETRIES = _safe_int_env("RAGAS_MAX_RETRIES", 15)
RAGAS_MAX_WORKERS = _safe_int_env("RAGAS_MAX_WORKERS", 16)

# 全6メトリクス
DEFAULT_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
    "answer_similarity",
)

# v0.4.3 のカラム名マッピング（メトリクスのname属性は内部名と異なる場合がある）
_COLUMN_NAME_MAP = {
    "faithfulness": "faithfulness",
    "answer_relevancy": "answer_relevancy",
    "context_precision": "llm_context_precision_with_reference",
    "context_recall": "context_recall",
    "answer_correctness": "answer_correctness",
    "answer_similarity": "answer_similarity",
}


@dataclass(frozen=True)
class RagasResult:
    """単一ケースの RAGAS 評価結果（6メトリクス）"""

    question: str
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_correctness: float = 0.0
    answer_similarity: float = 0.0
    error: Optional[str] = None
    nan_metrics: tuple = ()  # NaNだったメトリクス名（平均値計算から除外される）


@dataclass
class RagasReport:
    """バッチ評価のレポート"""

    total_cases: int = 0
    evaluated_cases: int = 0
    skipped_cases: int = 0
    metrics: Dict[str, float] = field(default_factory=dict)
    results: List[RagasResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def metrics_summary(self) -> Dict[str, float]:
        """メトリクスの平均値サマリー（NaNだったメトリクスはそのメトリクスの平均から除外）"""
        if not self.results:
            return {}
        valid = [r for r in self.results if r.error is None]
        if not valid:
            return {}

        metric_names = (
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "answer_similarity",
        )
        summary: Dict[str, float] = {}
        for name in metric_names:
            values = [getattr(r, name) for r in valid if name not in r.nan_metrics]
            summary[name] = sum(values) / len(values) if values else 0.0
        return summary


class RagasEvaluator:
    """
    RAGAS 評価エンジン（v0.4.3 対応・6メトリクス）

    ragas がインストールされていない場合は全操作で警告ログを出力し、
    空の結果を返す（graceful fallback）。
    """

    def __init__(
        self,
        metrics: Optional[tuple] = None,
        max_cases: Optional[int] = None,
        evaluation_llm: Optional[Any] = None,
        evaluation_embeddings: Optional[Any] = None,
    ):
        """
        Args:
            metrics: 使用するメトリクス名のタプル（デフォルト: 全6メトリクス）
            max_cases: 評価ケース数の上限（デフォルト: EVAL_MAX_CASES環境変数）
            evaluation_llm: カスタム評価用LLM（None の場合は自動解決）
            evaluation_embeddings: カスタム評価用Embeddings（None の場合は自動解決）
        """
        self.metric_names = metrics or DEFAULT_METRICS
        self.max_cases = max_cases or EVAL_MAX_CASES
        self._ragas_available = _ragas_available
        self._evaluation_llm = evaluation_llm or self._resolve_evaluation_llm()
        self._evaluation_embeddings = evaluation_embeddings or self._resolve_evaluation_embeddings()

        if not self._ragas_available:
            logger.warning(
                "RAGAS is not installed. Evaluation will return empty results. "
                "Install with: pip install -e '.[evaluation]'"
            )

    @property
    def is_available(self) -> bool:
        """ragas が利用可能かどうか"""
        return self._ragas_available

    @staticmethod
    def _resolve_evaluation_llm() -> Optional[Any]:
        """Resolve the best available LLM for RAGAS evaluation.

        Priority:
            1. OPENAI_API_KEY set → llm_factory with direct OpenAI client (gpt-5.2)
            2. OPENROUTER_API_KEY set → llm_factory via OpenRouter client
            3. Neither → None (RAGAS will fail gracefully)
        """
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                from langchain_openai import ChatOpenAI

                from ragas.llms import LangchainLLMWrapper

                # GPT-5 クラスは max_tokens 非対応（max_completion_tokens を要求）。
                # LangChain の ChatOpenAI は内部で自動変換してくれるため、
                # llm_factory ではなく LangchainLLMWrapper を使用する。
                langchain_llm = ChatOpenAI(
                    model=OPENAI_EVAL_MODEL,
                    api_key=openai_key,
                    max_tokens=OPENROUTER_EVAL_MAX_TOKENS,
                    timeout=float(RAGAS_TIMEOUT),
                    max_retries=3,
                )
                logger.info("Using direct OpenAI (%s) as RAGAS evaluation LLM", OPENAI_EVAL_MODEL)
                return LangchainLLMWrapper(langchain_llm)
            except ImportError:
                logger.warning("ragas.llms.llm_factory or openai not available")
                return None
            except Exception as e:
                logger.warning("Failed to create OpenAI LLM for RAGAS: %s", e)
                return None

        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if not openrouter_key:
            logger.info("No OPENAI_API_KEY or OPENROUTER_API_KEY found for RAGAS evaluation")
            return None

        try:
            from openai import OpenAI

            from ragas.llms import llm_factory

            client = OpenAI(
                api_key=openrouter_key,
                base_url=OPENROUTER_BASE_URL,
                timeout=float(RAGAS_TIMEOUT),
                max_retries=3,
            )
            logger.info("Using OpenRouter (%s) as RAGAS evaluation LLM", OPENROUTER_EVAL_MODEL)
            return llm_factory(
                OPENROUTER_EVAL_MODEL,
                client=client,
                max_tokens=OPENROUTER_EVAL_MAX_TOKENS,
            )
        except ImportError:
            logger.warning("ragas.llms.llm_factory or openai not available; cannot use OpenRouter")
            return None
        except Exception as e:
            logger.warning("Failed to create OpenRouter LLM for RAGAS: %s", e)
            return None

    @staticmethod
    def _resolve_evaluation_embeddings() -> Optional[Any]:
        """Resolve embeddings for RAGAS evaluation.

        Priority:
            1. OPENAI_API_KEY set → None (use RAGAS default OpenAI embeddings)
            2. OPENROUTER_API_KEY set → embedding_factory via OpenRouter
            3. Neither → None
        """
        if os.environ.get("OPENAI_API_KEY"):
            return None

        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if not openrouter_key:
            return None

        try:
            from openai import AsyncOpenAI

            from ragas.embeddings.base import embedding_factory

            client = AsyncOpenAI(
                api_key=openrouter_key,
                base_url=OPENROUTER_BASE_URL,
                timeout=float(RAGAS_TIMEOUT),
                max_retries=3,
            )
            logger.info(
                "Using OpenRouter (%s) as RAGAS evaluation embeddings",
                OPENROUTER_EMBEDDING_MODEL,
            )
            embedder = embedding_factory(
                "openai",
                model=OPENROUTER_EMBEDDING_MODEL,
                client=client,
            )
            # ResponseRelevancy メトリクスは LangChain 形式の embed_query/embed_documents を
            # 要求するが、RAGAS v0.4.3 の OpenAIEmbeddings は embed_text/embed_texts のみ。
            # 互換性のため LangChain インターフェースをエイリアスとして追加。
            if not hasattr(embedder, "embed_query"):
                embedder.embed_query = embedder.embed_text  # type: ignore[attr-defined]
            if not hasattr(embedder, "embed_documents"):
                embedder.embed_documents = embedder.embed_texts  # type: ignore[attr-defined]
            return embedder
        except ImportError:
            logger.warning("ragas embedding_factory or openai not available")
            return None
        except Exception as e:
            logger.warning("Failed to create OpenRouter embeddings for RAGAS: %s", e)
            return None

    async def evaluate_single(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: str,
    ) -> RagasResult:
        """
        単一ケースを評価

        Args:
            question: 質問テキスト
            answer: 生成された回答
            contexts: RAG検索で取得したコンテキスト群
            ground_truth: 正解テキスト

        Returns:
            RagasResult: 評価結果
        """
        if not self._ragas_available:
            logger.warning("RAGAS not available. Returning empty result.")
            return RagasResult(question=question, error="ragas not installed")

        try:
            return await self._run_ragas_evaluation(question, answer, contexts, ground_truth)
        except Exception as e:
            logger.error("RAGAS evaluation failed for question %s: %s", question[:50], e)
            return RagasResult(question=question, error=str(e))

    async def evaluate_batch(
        self,
        cases: List[Dict],
    ) -> RagasReport:
        """
        バッチ評価

        Args:
            cases: 評価ケースのリスト。各ケースは dict で:
                - question: str
                - answer: str
                - contexts: List[str]
                - ground_truth: str

        Returns:
            RagasReport: バッチ評価レポート
        """
        report = RagasReport(total_cases=len(cases))

        if not self._ragas_available:
            logger.warning("RAGAS not available. Returning empty report.")
            report.skipped_cases = len(cases)
            report.errors.append("ragas not installed")
            return report

        # ケース数を制限
        eval_cases = cases[: self.max_cases]
        report.skipped_cases = len(cases) - len(eval_cases)

        if report.skipped_cases > 0:
            logger.info(
                "Evaluating %d of %d cases (limit: %d)", len(eval_cases), len(cases), self.max_cases
            )

        try:
            report = await self._run_batch_evaluation(eval_cases, report)
        except Exception as e:
            logger.error("Batch RAGAS evaluation failed: %s", e)
            report.errors.append(str(e))

        report.metrics = report.metrics_summary
        return report

    def _build_eval_kwargs(self, metrics_objs: list) -> Dict:
        """Build keyword arguments for ragas evaluate(), including custom LLM/embeddings/run_config."""
        kwargs: Dict[str, Any] = {"metrics": metrics_objs}
        if self._evaluation_llm is not None:
            kwargs["llm"] = self._evaluation_llm
        if self._evaluation_embeddings is not None:
            kwargs["embeddings"] = self._evaluation_embeddings
        if _RunConfig is not None:
            kwargs["run_config"] = _RunConfig(
                timeout=RAGAS_TIMEOUT,
                max_retries=RAGAS_MAX_RETRIES,
                max_workers=RAGAS_MAX_WORKERS,
            )
        return kwargs

    def _extract_scores(self, row: Any) -> Dict[str, Any]:
        """DataFrame の行からメトリクス名でスコアを抽出（カラム名マッピング対応）

        Returns:
            Dict with metric scores (float) and "_nan_metrics" (tuple of metric names that were NaN).
        """
        scores: Dict[str, Any] = {}
        nan_metrics: list = []
        for metric_name in self.metric_names:
            col = _COLUMN_NAME_MAP.get(metric_name, metric_name)
            val = row.get(col, None)
            if val is None:
                val = row.get(metric_name, 0.0)
            fval = float(val) if val is not None else 0.0
            if math.isnan(fval):
                nan_metrics.append(metric_name)
                fval = 0.0  # dataclass 互換のため 0.0 を設定
            scores[metric_name] = fval
        scores["_nan_metrics"] = tuple(nan_metrics)
        return scores

    async def _run_ragas_evaluation(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: str,
    ) -> RagasResult:
        """ragas ライブラリを使って単一評価を実行（v0.4.3 EvaluationDataset API）"""
        sample = _SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
            reference=ground_truth,
        )
        dataset = _EvaluationDataset(samples=[sample])

        metrics_objs = self._get_metric_objects()
        result = _ragas_evaluate(dataset, **self._build_eval_kwargs(metrics_objs))

        scores = result.to_pandas().iloc[0]
        extracted = self._extract_scores(scores)
        nan_metrics = extracted.pop("_nan_metrics", ())

        return RagasResult(question=question, nan_metrics=nan_metrics, **extracted)

    async def _run_batch_evaluation(
        self,
        cases: List[Dict],
        report: RagasReport,
    ) -> RagasReport:
        """バッチ評価を実行（v0.4.3 EvaluationDataset API）"""
        samples = [
            _SingleTurnSample(
                user_input=c["question"],
                response=c["answer"],
                retrieved_contexts=c["contexts"],
                reference=c["ground_truth"],
            )
            for c in cases
        ]
        dataset = _EvaluationDataset(samples=samples)

        metrics_objs = self._get_metric_objects()
        result = _ragas_evaluate(dataset, **self._build_eval_kwargs(metrics_objs))

        df = result.to_pandas()
        questions = [c["question"] for c in cases]
        for idx, row in df.iterrows():
            extracted = self._extract_scores(row)
            nan_metrics = extracted.pop("_nan_metrics", ())
            report.results.append(
                RagasResult(question=questions[idx], nan_metrics=nan_metrics, **extracted)
            )

        report.evaluated_cases = len(report.results)
        return report

    def _get_metric_objects(self) -> list:
        """メトリクス名からメトリクスインスタンスを生成（v0.4.3 クラスベース）"""
        return [_metric_classes[name]() for name in self.metric_names if name in _metric_classes]
