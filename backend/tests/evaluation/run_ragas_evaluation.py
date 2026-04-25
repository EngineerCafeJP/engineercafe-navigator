"""
RAGAS 評価ランナー

Ground Truth データセットを使って RAG システムの品質を評価する。

2つの評価モード:
  - golden: 事前定義の回答・コンテキストで RAGAS スコアを算出（オフライン/CI向け）
  - live:   実際の RAG パイプライン（EnhancedRAGSearch + LLM）を呼び出して評価（本番品質検証向け）

Usage:
    cd backend
    python -m tests.evaluation.run_ragas_evaluation [--mode golden|live] [--max-cases 10]

環境変数:
    EVAL_MAX_CASES: 評価ケース数の上限（デフォルト 10）
    OPENAI_API_KEY: RAGAS が使う LLM の API キー（優先）
    OPENROUTER_API_KEY: OpenRouter 経由の LLM API キー（OPENAI_API_KEY 未設定時に自動使用）
    SUPABASE_URL: Supabase URL（live モードで必要）
    SUPABASE_KEY: Supabase API Key（live モードで必要）
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# backend/ とプロジェクトルートを sys.path に追加
_backend_dir = str(Path(__file__).parent.parent.parent)
_project_root = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, _backend_dir)

# .env.local から環境変数を読み込む（dotenv が利用可能な場合）
_env_local = Path(_backend_dir) / ".env.local"
try:
    from dotenv import load_dotenv

    if _env_local.exists():
        load_dotenv(_env_local)
except ImportError:
    pass

from backend.tests.fixtures.dataset_loader import DatasetLoader, GroundTruthCase  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def _generate_live_response(
    question: str,
    language: str = "ja",
    category: str = "general",
) -> Tuple[str, List[str]]:
    """実際の RAG パイプラインを呼び出してライブ回答とコンテキストを取得する。

    Args:
        question: 質問テキスト
        language: 言語コード
        category: クエリカテゴリ

    Returns:
        (answer, contexts) タプル。失敗時は ("", [])。
    """
    try:
        from backend.tools.enhanced_rag import EnhancedRAGSearch

        rag = EnhancedRAGSearch()
        result = await rag.search(
            query=question,
            category=category,
            language=language,
            max_results=5,
        )

        if not result.get("success") or not result.get("data"):
            logger.warning("RAG search returned no results for: %s", question[:50])
            return "", []

        context_text = result["data"].get("context", "")
        raw_results = result["data"].get("results", [])

        # 個別のコンテキストチャンクを抽出
        contexts = [r.get("content", "") for r in raw_results if r.get("content")]
        if not contexts and context_text:
            contexts = [context_text]

        # LLM で回答を生成
        from langchain_core.messages import HumanMessage

        from backend.llm.models import get_model_config
        from backend.llm.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()
        model_config = get_model_config("qa_response")

        lang_instruction = (
            "日本語で回答してください。" if language == "ja" else "Answer in English."
        )
        prompt = (
            f"以下のコンテキストに基づいて質問に正確に回答してください。"
            f"コンテキストにない情報は推測しないでください。{lang_instruction}\n\n"
            f"コンテキスト:\n{context_text}\n\n"
            f"質問: {question}"
        )

        messages = [HumanMessage(content=prompt)]
        answer = await provider.generate(messages=messages, config=model_config)

        logger.info("Live response generated: %d chars, %d contexts", len(answer), len(contexts))
        return answer, contexts

    except Exception as e:
        logger.error("Failed to generate live response for %s: %s", question[:50], e)
        return "", []


async def _build_eval_dicts_golden(
    cases: List[GroundTruthCase],
    max_cases: int,
) -> List[Dict]:
    """ゴールデンモード: 事前定義データをそのまま使用"""
    return [
        {
            "question": c.question,
            "answer": c.answer,
            "contexts": c.contexts,
            "ground_truth": c.ground_truth,
        }
        for c in cases[:max_cases]
    ]


async def _build_eval_dicts_live(
    cases: List[GroundTruthCase],
    max_cases: int,
) -> List[Dict]:
    """ライブモード: 実際の RAG パイプラインを呼び出してデータを生成

    ground_truth.json から question と ground_truth のみ使用し、
    answer と contexts は実際のシステムから取得する。
    """
    eval_dicts: List[Dict] = []
    target_cases = cases[:max_cases]

    for i, c in enumerate(target_cases):
        logger.info("[%d/%d] Live query: %s...", i + 1, len(target_cases), c.question[:50])
        answer, contexts = await _generate_live_response(
            question=c.question,
            language=c.language,
            category=c.category,
        )

        if not answer or not contexts:
            logger.warning("Skipping case %s: no live response generated", c.id)
            continue

        eval_dicts.append(
            {
                "question": c.question,
                "answer": answer,  # ライブ LLM 回答
                "contexts": contexts,  # ライブ RAG 検索結果
                "ground_truth": c.ground_truth,  # ゴールデンデータの正解
            }
        )

    return eval_dicts


async def run_evaluation(
    max_cases: int = 10,
    category: Optional[str] = None,
    language: Optional[str] = None,
    output_dir: Optional[Path] = None,
    mode: str = "golden",
) -> Dict:
    """
    RAGAS 評価を実行

    Args:
        max_cases: 評価ケース数の上限
        category: フィルタするカテゴリ
        language: フィルタする言語
        output_dir: レポート出力先
        mode: 評価モード ("golden" or "live")

    Returns:
        Dict: 評価結果サマリー
    """
    # データ読み込み
    cases: List[GroundTruthCase] = DatasetLoader.load_ground_truth_cases(
        language=language,
        category=category,
    )

    if not cases:
        logger.error("No ground truth cases found.")
        return {"error": "no cases found"}

    logger.info("Loaded %d ground truth cases (mode=%s)", len(cases), mode)

    # RagasEvaluator をインポート（ragas 未インストール時は graceful fallback）
    try:
        from backend.evaluation.ragas_pipeline import RagasEvaluator
    except ImportError:
        logger.error("Could not import RagasEvaluator. Check your installation.")
        return {"error": "import failed"}

    evaluator = RagasEvaluator(max_cases=max_cases)

    if not evaluator.is_available:
        logger.warning("RAGAS is not installed. Install with: pip install -e '.[evaluation]'")
        return {
            "status": "skipped",
            "reason": "ragas not installed",
            "total_cases": len(cases),
        }

    # モードに応じて評価データを構築
    if mode == "live":
        logger.info("Running in LIVE mode: calling actual RAG pipeline...")
        eval_dicts = await _build_eval_dicts_live(cases, max_cases)
    else:
        logger.info("Running in GOLDEN mode: using pre-defined answers/contexts...")
        eval_dicts = await _build_eval_dicts_golden(cases, max_cases)

    if not eval_dicts:
        logger.error("No evaluation cases could be prepared.")
        return {"error": "no eval cases prepared", "mode": mode}

    logger.info("Running RAGAS evaluation on %d cases...", len(eval_dicts))
    report = await evaluator.evaluate_batch(eval_dicts)

    # サマリー
    summary: Dict = {
        "status": "completed",
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
        "total_cases": len(cases),
        "evaluated_cases": report.evaluated_cases,
        "skipped_cases": report.skipped_cases,
        "metrics": report.metrics,
        "nan_ratio": report.nan_ratio,
        "all_metrics_nan": report.all_metrics_nan,
        "errors": report.errors,
    }

    # ケース別詳細を追加（デバッグ用）
    if report.results:
        summary["per_case"] = [
            {
                "question": r.question[:80],
                "faithfulness": r.faithfulness,
                "answer_relevancy": r.answer_relevancy,
                "context_precision": r.context_precision,
                "context_recall": r.context_recall,
                "answer_correctness": r.answer_correctness,
                "answer_similarity": r.answer_similarity,
                "nan_metrics": list(r.nan_metrics),
            }
            for r in report.results
        ]

    # レポート出力
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"ragas_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("Report saved to: %s", report_path)
    logger.info("Metrics: %s", summary["metrics"])

    return summary


def _write_github_outputs(result: Dict) -> None:
    """Write metrics to $GITHUB_OUTPUT for use in subsequent steps."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        logger.debug("GITHUB_OUTPUT not set, skipping output writing")
        return

    try:
        with open(output_file, "a", encoding="utf-8") as f:
            metrics = result.get("metrics", {})
            for key, value in metrics.items():
                f.write(f"{key}={value}\n")
            f.write(f"nan_ratio={result.get('nan_ratio', 0.0)}\n")
            f.write(f"all_metrics_nan={result.get('all_metrics_nan', False)}\n")
            f.write(f"evaluated_cases={result.get('evaluated_cases', 0)}\n")
            f.write(f"skipped_cases={result.get('skipped_cases', 0)}\n")
            f.write(f"status={result.get('status', 'unknown')}\n")
            f.write(f"mode={result.get('mode', 'unknown')}\n")
        logger.info("Wrote %d outputs to GITHUB_OUTPUT", len(metrics) + 6)
    except Exception as e:
        logger.warning("Failed to write GITHUB_OUTPUT: %s", e)


def _write_github_summary(result: Dict) -> None:
    """Write Markdown summary to $GITHUB_STEP_SUMMARY."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        logger.debug("GITHUB_STEP_SUMMARY not set, skipping summary writing")
        return

    try:
        mode = result.get("mode", "unknown")
        lines = [f"## RAGAS Evaluation Results ({mode} mode)\n"]
        metrics = result.get("metrics", {})
        if metrics:
            lines.append("| Metric | Score |")
            lines.append("|--------|-------|")
            for metric, score in metrics.items():
                score_str = f"{score:.3f}" if isinstance(score, (int, float)) else str(score)
                lines.append(f"| {metric} | {score_str} |")
        lines.append("")
        lines.append(
            f"**Cases**: {result.get('evaluated_cases', 0)} evaluated, "
            f"{result.get('skipped_cases', 0)} skipped"
        )

        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("Wrote evaluation summary to GITHUB_STEP_SUMMARY")
    except Exception as e:
        logger.warning("Failed to write GITHUB_STEP_SUMMARY: %s", e)


def main():
    parser = argparse.ArgumentParser(description="RAGAS Evaluation Runner")
    parser.add_argument("--max-cases", type=int, default=10, help="Max evaluation cases")
    parser.add_argument("--category", type=str, default=None, help="Filter by category")
    parser.add_argument("--language", type=str, default=None, help="Filter by language")
    parser.add_argument("--output-dir", type=str, default=None, help="Report output directory")
    parser.add_argument("--ci-mode", action="store_true", help="GitHub Actions output mode")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["golden", "live"],
        default="golden",
        help="Evaluation mode: 'golden' uses pre-defined data, 'live' calls actual RAG pipeline",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    result = asyncio.run(
        run_evaluation(
            max_cases=args.max_cases,
            category=args.category,
            language=args.language,
            output_dir=output_dir,
            mode=args.mode,
        )
    )

    if args.ci_mode:
        _write_github_outputs(result)
        _write_github_summary(result)

    per_case = result.get("per_case", [])
    all_metric_names = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "answer_correctness",
        "answer_similarity",
    ]

    if per_case and all(
        set(case.get("nan_metrics", [])) == set(all_metric_names) for case in per_case
    ):
        logger.error(
            "All %d cases produced NaN for every metric. "
            "Evaluation is invalid - treating as CI failure.",
            len(per_case),
        )
        sys.exit(1)

    nan_ratio = float(result.get("nan_ratio", 0.0) or 0.0)
    if nan_ratio > 0.5:
        logger.error(
            "RAGAS evaluation produced excessive NaN metrics (%.0f%%). " "Treating as CI failure.",
            nan_ratio * 100,
        )
        sys.exit(1)

    if result.get("status") == "completed":
        logger.info("Evaluation completed successfully.")
    elif result.get("status") == "skipped":
        logger.info("Evaluation skipped (ragas not installed).")
    else:
        logger.error("Evaluation failed: %s", result)
        sys.exit(1)


if __name__ == "__main__":
    main()
