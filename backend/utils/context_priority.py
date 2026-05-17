"""
Context-Driven Priority Engine
会話コンテキストに基づいてRAG検索の閾値を動的に調整する。
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 最大調整幅
MAX_ADJUSTMENT = 0.10


@dataclass(frozen=True)
class ContextSignals:
    """会話コンテキストから抽出されたシグナル"""

    memory_topics: tuple = ()
    rag_cache_top_score: float = 0.0
    request_specificity: float = 0.5
    conversation_depth: int = 0
    previous_categories: tuple = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "memory_topics", tuple(self.memory_topics or ()))
        object.__setattr__(self, "previous_categories", tuple(self.previous_categories or ()))


class ContextPriorityEngine:
    """コンテキスト駆動の優先度エンジン"""

    def compute_adjusted_thresholds(
        self,
        category: str,
        query: str,
        signals: ContextSignals,
        base_thresholds: Dict[str, float],
    ) -> Dict[str, float]:
        """
        コンテキストシグナルに基づいて閾値を調整

        調整ルール:
        1. トピック一貫性高い (previous_categoriesにカテゴリ一致): high/medium -0.03
        2. RAGキャッシュスコア高い (top_score > 0.8): high/medium +0.05
        3. リクエスト具体性高い (specificity > 0.8): medium +0.03
        4. 会話深度浅い (depth < 3): 変更なし
        5. 全調整は +-MAX_ADJUSTMENT にクランプ

        Args:
            category: クエリカテゴリ
            query: 検索クエリ
            signals: コンテキストシグナル
            base_thresholds: ベース閾値 {"high": float, "medium": float, "term_match": float}

        Returns:
            調整済み閾値辞書（新しいdictを返す、元のbase_thresholdsはミューテーションしない）
        """
        high_adj = 0.0
        medium_adj = 0.0
        term_match_adj = 0.0

        # Rule 1: トピック一貫性 - previous_categoriesにカテゴリ一致
        if category in signals.previous_categories:
            high_adj -= 0.03
            medium_adj -= 0.03

        # Rule 2: RAGキャッシュスコア高い
        if signals.rag_cache_top_score > 0.8:
            high_adj += 0.05
            medium_adj += 0.05

        # Rule 3: リクエスト具体性高い
        if signals.request_specificity > 0.8:
            medium_adj += 0.03

        # Rule 4: 会話深度浅い場合は変更なし（明示的にスキップ）
        if signals.conversation_depth < 3:
            pass

        return {
            "high": base_thresholds["high"] + self._clamp_adjustment(high_adj),
            "medium": base_thresholds["medium"] + self._clamp_adjustment(medium_adj),
            "term_match": base_thresholds["term_match"] + self._clamp_adjustment(term_match_adj),
        }

    def extract_signals_from_context(
        self,
        memory_context: Optional[Dict],
        knowledge_results: Optional[Dict],
    ) -> ContextSignals:
        """
        メモリコンテキストとRAG結果からシグナルを抽出

        Args:
            memory_context: memory_helperからのコンテキスト
            knowledge_results: RAGプリフェッチ結果

        Returns:
            抽出されたContextSignals
        """
        memory_topics: List[str] = []
        conversation_depth = 0
        previous_categories: List[str] = []

        if memory_context and isinstance(memory_context, dict):
            # 会話深度を抽出
            history = memory_context.get("conversation_history", [])
            if isinstance(history, list):
                conversation_depth = len(history)

            # メモリトピック抽出
            topics = memory_context.get("topics", [])
            if isinstance(topics, list):
                memory_topics = [str(t) for t in topics]

            # 直近カテゴリ抽出
            categories = memory_context.get("previous_categories", [])
            if isinstance(categories, list):
                previous_categories = [str(c) for c in categories]

        # RAG結果からシグナル抽出
        rag_top_score = 0.0
        rag_category = ""
        if knowledge_results and isinstance(knowledge_results, dict):
            results = knowledge_results.get("results", [])
            if isinstance(results, list) and results:
                # 最高スコアを取得
                scores = [
                    r.get("priority_score", r.get("similarity", 0.0))
                    for r in results
                    if isinstance(r, dict)
                ]
                if scores:
                    rag_top_score = max(scores)

            rag_category = knowledge_results.get("category", "")
            if rag_category and rag_category not in previous_categories:
                previous_categories.append(rag_category)

        # クエリ具体性はRAGクエリから計算
        query = knowledge_results.get("query", "") if knowledge_results else ""
        specificity = self._compute_specificity(query)

        return ContextSignals(
            memory_topics=tuple(memory_topics),
            rag_cache_top_score=rag_top_score,
            request_specificity=specificity,
            conversation_depth=conversation_depth,
            previous_categories=tuple(previous_categories),
        )

    def _compute_specificity(self, query: str) -> float:
        """
        クエリの具体性スコアを計算 (0.0-1.0)

        - 短いクエリ (<10文字): 低い具体性
        - 固有名詞含む: 高い具体性
        - 数値含む: 高い具体性
        - 一般的な質問: 中程度
        """
        if not query:
            return 0.0

        score = 0.5  # ベーススコア

        # 短いクエリは低い具体性
        if len(query) < 10:
            score -= 0.2
        elif len(query) >= 30:
            score += 0.1

        # 数値を含む場合、具体性が高い
        if re.search(r"\d+", query):
            score += 0.15

        # 固有名詞的キーワード
        proper_nouns = [
            "エンジニアカフェ",
            "engineer cafe",
            "saino",
            "サイノ",
            "赤煉瓦",
            "天神",
            "福岡",
        ]
        if any(noun in query.lower() for noun in proper_nouns):
            score += 0.2

        return max(0.0, min(1.0, score))

    def _clamp_adjustment(self, adjustment: float) -> float:
        """調整値を+-MAX_ADJUSTMENTにクランプ"""
        return max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, adjustment))
