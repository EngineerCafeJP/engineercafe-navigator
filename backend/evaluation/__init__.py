"""
RAGAS Evaluation Package

RAGシステムの品質評価パイプラインを提供します。
ragas がインストールされていない場合でもインポート可能です（graceful fallback）。
"""

from backend.evaluation.ragas_pipeline import RagasEvaluator, RagasResult, RagasReport
from backend.evaluation.run_multilingual_eval import run_multilingual_evaluation

__all__ = ["RagasEvaluator", "RagasResult", "RagasReport", "run_multilingual_evaluation"]
