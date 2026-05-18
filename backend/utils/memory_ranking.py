"""Ranking and context formatting mixin for SimplifiedMemoryHelper."""

from datetime import datetime
from typing import Dict, List

from backend.utils.cafe_entity import canonicalize_facility_memory_key_text


class MemoryRankingMixin:
    def _rank_messages(self, messages: List[Dict], current_query: str) -> List[Dict]:
        """メッセージをrecency/frequency/relevanceの複合スコアでランキング

        Args:
            messages: メッセージリスト
            current_query: 現在のクエリ

        Returns:
            _rank_score付きのソート済みメッセージリスト
        """
        if not messages:
            return []

        now = datetime.now()
        scored = []

        for msg in messages:
            # Recency (0-1): 新しいほど高い（1週間で0に減衰）
            timestamp = msg.get("metadata", {}).get("timestamp")
            if timestamp:
                age_hours = (now - datetime.fromtimestamp(timestamp / 1000)).total_seconds() / 3600
            else:
                age_hours = 168  # デフォルト: 1週間前
            recency = max(0.0, 1.0 - age_hours / (24 * 7))

            # Frequency (0-1): 同じトピックの出現頻度
            topic_count = sum(1 for m in messages if self._topic_overlap(msg, m) > 0.3)
            frequency = min(1.0, topic_count / max(len(messages), 1))

            # Relevance (0-1): 現在のクエリとの関連性
            relevance = self._compute_relevance(msg, current_query)

            # 複合スコア（重み付き）
            composite = 0.4 * recency + 0.2 * frequency + 0.4 * relevance

            scored.append({**msg, "_rank_score": composite})

        scored.sort(key=lambda x: x["_rank_score"], reverse=True)
        return self._dedupe_ranked_messages(scored)

    @staticmethod
    def _dedupe_ranked_messages(messages: List[Dict]) -> List[Dict]:
        """Keep the highest-ranked message for the same canonical facility content."""
        deduped: List[Dict] = []
        seen: set[str] = set()
        for msg in messages:
            metadata = msg.get("metadata", {})
            key = metadata.get("canonical_content_key") if isinstance(metadata, dict) else None
            if not key:
                key = canonicalize_facility_memory_key_text(str(msg.get("content") or ""))
            normalized_key = " ".join(str(key).strip().lower().split())
            if normalized_key and normalized_key in seen:
                continue
            if normalized_key:
                seen.add(normalized_key)
            deduped.append(msg)
        return deduped

    def _topic_overlap(self, msg_a: Dict, msg_b: Dict) -> float:
        """2メッセージのトピック類似度（bigramマッチ率）

        Args:
            msg_a: メッセージA
            msg_b: メッセージB

        Returns:
            類似度スコア (0.0-1.0)
        """
        content_a = msg_a.get("content", "")
        content_b = msg_b.get("content", "")

        if not content_a or not content_b:
            return 0.0

        bigrams_a = set(content_a[i : i + 2] for i in range(len(content_a) - 1))
        bigrams_b = set(content_b[i : i + 2] for i in range(len(content_b) - 1))

        if not bigrams_a or not bigrams_b:
            return 0.0

        intersection = bigrams_a & bigrams_b
        union = bigrams_a | bigrams_b

        return len(intersection) / len(union) if union else 0.0

    def _compute_relevance(self, msg: Dict, query: str) -> float:
        """クエリとメッセージの関連度（用語マッチ率）

        Args:
            msg: メッセージ
            query: クエリ文字列

        Returns:
            関連度スコア (0.0-1.0)
        """
        content = msg.get("content", "")
        if not content or not query:
            return 0.0

        # 2文字sliding windowでbigramを生成
        query_bigrams = set(query[i : i + 2] for i in range(len(query) - 1))
        content_lower = content.lower()

        if not query_bigrams:
            return 0.0

        match_count = sum(1 for bg in query_bigrams if bg in content_lower)
        return match_count / len(query_bigrams)

    def _build_comprehensive_context(
        self,
        recent_messages: List[Dict],
        knowledge_results: List[Dict],
        language: str,
    ) -> str:
        """
        会話履歴とナレッジベース結果からコンテキスト文字列を構築

        Args:
            recent_messages: 最近のメッセージリスト
            knowledge_results: ナレッジベース検索結果
            language: 言語設定（"ja" or "en"）

        Returns:
            フォーマット済みコンテキスト文字列
        """
        lines: List[str] = []

        # 会話履歴の追加
        if recent_messages:
            header = (
                "セッション内の会話履歴:" if language == "ja" else "Session conversation history:"
            )
            lines.append(header)

            for msg in recent_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                role_label = (
                    ("ユーザー" if role == "user" else "アシスタント")
                    if language == "ja"
                    else ("User" if role == "user" else "Assistant")
                )
                emotion = msg.get("metadata", {}).get("emotion")
                emotion_info = f" [{emotion}]" if emotion else ""
                lines.append(f"{role_label}: {content}{emotion_info}")

        # ナレッジベース結果の追加
        if knowledge_results:
            lines.append("")  # 空行
            header = (
                "関連するエンジニアカフェ情報:"
                if language == "ja"
                else "Relevant Engineer Cafe information:"
            )
            lines.append(header)

            for i, result in enumerate(knowledge_results, 1):
                category = result.get("category", "")
                category_info = f" [{category}]" if category else ""
                lines.append(f"{i}. {result.get('content', '')}{category_info}")

        if not lines:
            return "会話履歴がありません。" if language == "ja" else "No conversation context."

        return "\n".join(lines)
