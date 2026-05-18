"""Scoring, grading, and context helpers for EnhancedRAGSearch."""

import logging
from typing import Dict, List, Optional

from backend.tools.enhanced_rag_constants import (
    CATEGORY_THRESHOLDS,
    DEFAULT_THRESHOLDS,
    MEMBERSHIP_RESULT_TERMS,
)

logger = logging.getLogger(__name__)


class RAGScoringMixin:
    def _grade_result_relevance(
        self,
        scored_results: List[Dict],
        query: str,
        category: str = "general",
        language: str = "ja",
        context_signals=None,
    ) -> List[Dict]:
        """スコアリング済み結果の品質グレーディング（軽量CRAG）。

        priority_scoreとクエリ用語マッチ率を基に、低品質な結果を除外する。

        Grading criteria:
        - HIGH (priority_score >= high_threshold): 常に保持
        - MEDIUM (medium_threshold <= priority_score < high_threshold):
          クエリ用語マッチがある場合保持
        - LOW (priority_score < medium_threshold): 除外

        Args:
            scored_results: _score_results()でスコアリング済みの結果リスト
            query: 元のクエリ文字列
            category: クエリカテゴリ（hours, pricing, location等）
            language: 言語コード
            context_signals: コンテキストシグナル（Noneの場合は静的閾値を使用）

        Returns:
            品質フィルタリング済みの結果リスト
        """
        if not scored_results:
            return []

        # カテゴリ別閾値を取得
        thresholds = CATEGORY_THRESHOLDS.get(category, DEFAULT_THRESHOLDS)

        # コンテキストシグナルがある場合は動的調整
        if context_signals is not None:
            try:
                from backend.utils.context_priority import ContextPriorityEngine

                engine = ContextPriorityEngine()
                thresholds = engine.compute_adjusted_thresholds(
                    category=category,
                    query=query,
                    signals=context_signals,
                    base_thresholds=thresholds,
                )
            except Exception as e:
                logger.warning("Context priority adjustment failed, using static thresholds: %s", e)
                thresholds = CATEGORY_THRESHOLDS.get(category, DEFAULT_THRESHOLDS)

        high_threshold = thresholds["high"]
        medium_threshold = thresholds["medium"]
        term_match_threshold = thresholds["term_match"]

        # クエリ長による閾値調整
        query_len = len(query)
        if query_len < 10:
            high_threshold -= 0.05
            medium_threshold -= 0.05
            term_match_threshold -= 0.05
        elif query_len >= 50:
            high_threshold += 0.03
            medium_threshold += 0.03
            term_match_threshold += 0.03

        query_terms = self._extract_text_query_terms(query, category, language)
        membership_query = self._is_membership_query(query)

        graded_results: List[Dict] = []

        for result in scored_results:
            score = result.get("priority_score", 0.0)
            content = result.get("content", "").lower()
            title = result.get("title", "").lower()
            combined = f"{title} {content}"

            # HIGH: 常に保持
            if score >= high_threshold:
                graded_results.append({**result, "grade": "HIGH"})
                continue

            # MEDIUM: クエリ用語マッチがある場合保持
            if score >= medium_threshold:
                if query_terms:
                    match_count = sum(1 for term in query_terms if term in combined)
                    match_ratio = match_count / len(query_terms)

                    if match_ratio > term_match_threshold:
                        graded_results.append({**result, "grade": "MEDIUM"})
                        continue

                if membership_query and any(
                    term.lower() in combined for term in MEMBERSHIP_RESULT_TERMS
                ):
                    graded_results.append({**result, "grade": "MEDIUM"})
                    continue

            # LOW: 除外
            logger.debug(
                "Filtered out low-relevance result: title=%s, score=%.3f",
                result.get("title", "N/A"),
                score,
            )

        return graded_results

    def _score_results(
        self, results: List[Dict], query: str, category: str, language: str
    ) -> List[Dict]:
        """
        検索結果にスコアリングを適用
        エンティティ認識とカテゴリベースの優先順位付け
        """
        scored_results = []

        for result in results:
            # 基本スコア（類似度）
            base_score = result.get("similarity", 0.0)

            # エンティティ認識
            entity = self._detect_entity(result)

            # カテゴリボーナス
            category_bonus = self._calculate_category_bonus(result, category)

            # エンティティボーナス
            entity_bonus = self._calculate_entity_bonus(entity, query, category)

            # 最終スコア
            priority_score = base_score + category_bonus + entity_bonus

            scored_results.append(
                {
                    **result,
                    "entity": entity,
                    "priority_score": priority_score,
                    "original_similarity": base_score,
                }
            )

        # 優先度スコアでソート
        scored_results.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        if self._query_mentions_saino(query) and not self._query_mentions_engineer_cafe(query):
            saino_results = [r for r in scored_results if r.get("entity") == "saino"]
            if saino_results:
                return saino_results

        return scored_results

    def _detect_entity(self, result: Dict) -> str:
        """結果からエンティティを検出"""
        content = result.get("content", "").lower()
        title = result.get("title", "").lower()
        metadata = result.get("metadata", {})

        # メタデータからエンティティを取得
        if metadata and isinstance(metadata, dict):
            entity = metadata.get("entity", "")
            if entity:
                return entity

        # コンテンツからエンティティを推測
        if "saino" in content or "saino" in title or "サイノ" in content or "サイノ" in title:
            return "saino"
        elif (
            "engineer cafe" in content
            or "engineer cafe" in title
            or "エンジニアカフェ" in content
            or "エンジニアカフェ" in title
        ):
            return "engineer-cafe"
        elif "会議室" in content or "meeting room" in content:
            return "meeting-room"

        return "general"

    def _calculate_category_bonus(self, result: Dict, category: str) -> float:
        """カテゴリに基づくボーナススコア計算"""
        # トップレベルのcategoryカラム（RPC結果）を優先、fallbackでmetadata.category
        result_category = result.get("category", "")
        if not result_category:
            metadata = result.get("metadata", {})
            result_category = metadata.get("category", "") if isinstance(metadata, dict) else ""

        # カテゴリマッピング
        category_mapping = {
            "hours": ["hours", "営業時間", "business hours"],
            "pricing": ["pricing", "料金", "price", "cost"],
            "location": ["location", "access", "場所", "アクセス"],
            "facility-info": ["facility-info", "設備", "facilities"],
        }

        if category != "general" and self._category_matches(result_category, category, result):
            return 0.2

        if category in category_mapping:
            for keyword in category_mapping[category]:
                if keyword in result_category.lower():
                    return 0.2

        return 0.0

    def _calculate_entity_bonus(self, entity: str, query: str, category: str) -> float:
        """エンティティに基づくボーナススコア計算"""
        query_lower = query.lower()

        # クエリに特定のエンティティが含まれている場合、そのエンティティを優先
        if entity == "engineer-cafe" and ("engineer" in query_lower or "エンジニア" in query_lower):
            return 0.3
        elif entity == "saino" and self._query_mentions_saino(query):
            return 0.35
        elif entity == "meeting-room" and (
            "会議室" in query_lower or "meeting room" in query_lower
        ):
            return 0.3

        # カテゴリに応じたデフォルトエンティティ優先度
        entity_priority = {
            "hours": ["engineer-cafe", "saino", "general", "meeting-room"],
            "pricing": ["engineer-cafe", "saino", "meeting-room", "general"],
            "facility-info": ["engineer-cafe", "general", "meeting-room", "saino"],
            "location": ["engineer-cafe", "general", "saino", "meeting-room"],
            "saino-cafe": ["saino", "engineer-cafe", "general", "meeting-room"],
        }

        if category in entity_priority:
            priority_list = entity_priority[category]
            if entity in priority_list:
                # 優先度に応じたボーナス（最高0.1）
                index = priority_list.index(entity)
                return 0.1 * (1 - index / len(priority_list))

        return 0.0

    def _build_context_from_results(self, results: List[Dict], category: str, language: str) -> str:
        """スコアリング済み結果からコンテキストを構築"""
        if not results:
            return ""

        # エンティティごとにグループ化
        grouped_results: Dict[str, List[Dict]] = {}
        for result in results:
            entity = result.get("entity", "general")
            if entity not in grouped_results:
                grouped_results[entity] = []
            grouped_results[entity].append(result)

        # エンティティ優先順位を取得
        entity_priority = self._get_entity_priority(category)

        # コンテキスト構築
        context = ""

        for entity in entity_priority:
            entity_results = grouped_results.get(entity, [])
            if entity_results:
                # エンティティヘッダー追加
                if context:
                    context += "\n\n"

                entity_labels = {
                    "engineer-cafe": {
                        "ja": "【エンジニアカフェ】",
                        "en": "[Engineer Cafe]",
                        "zh": "【工程师咖啡】",
                        "ko": "【엔지니어 카페】",
                    },
                    "saino": {
                        "ja": "【sainoカフェ】",
                        "en": "[Saino Cafe]",
                        "zh": "【saino咖啡】",
                        "ko": "【saino 카페】",
                    },
                    "meeting-room": {
                        "ja": "【会議室】",
                        "en": "[Meeting Room]",
                        "zh": "【会议室】",
                        "ko": "【회의실】",
                    },
                }
                if entity in entity_labels:
                    labels = entity_labels[entity]
                    label = labels.get(language, labels["ja"])
                    context += f"{label}\n"

                # コンテンツを追加
                context += "\n".join(r.get("content", "") for r in entity_results)

        return context

    def _build_hierarchical_context(self, results: List[Dict], language: str = "ja") -> str:
        """Hierarchical結果からコンテキストを構築。

        親チャンクでグループ化し、階層的なコンテキストを生成する。

        Args:
            results: 親コンテキスト付きの検索結果
            language: 言語

        Returns:
            構築されたコンテキスト文字列
        """
        if not results:
            return ""

        # parent_idでグルーピング
        groups: Dict[Optional[str], List[Dict]] = {}
        for result in results:
            pid = result.get("parent_id")
            if pid not in groups:
                groups[pid] = []
            groups[pid].append(result)

        # コンテキスト構築
        context_parts: List[str] = []

        for pid, group in groups.items():
            if pid and group[0].get("parent_title"):
                # 親がある場合: 親タイトルでグループ化
                parent_title = group[0]["parent_title"]
                chunk_contents = "\n".join(r.get("content", "") for r in group)
                context_parts.append(f"【{parent_title}】\n{chunk_contents}")
            else:
                # 親がない場合: 通常のコンテンツ
                for r in group:
                    context_parts.append(r.get("content", ""))

        return "\n\n".join(context_parts)

    def _get_entity_priority(self, category: str) -> List[str]:
        """カテゴリに応じたエンティティ優先順位を取得"""
        priority_map = {
            "pricing": ["engineer-cafe", "saino", "meeting-room", "general"],
            "hours": ["engineer-cafe", "saino", "general", "meeting-room"],
            "facility-info": ["engineer-cafe", "general", "meeting-room", "saino"],
            "location": ["engineer-cafe", "general", "saino", "meeting-room"],
            "saino-cafe": ["saino", "engineer-cafe", "general", "meeting-room"],
        }

        return priority_map.get(category, ["engineer-cafe", "general", "saino", "meeting-room"])

    def _generate_practical_advice(
        self, results: List[Dict], query: str, category: str, language: str
    ) -> Optional[str]:
        """実用的なアドバイスを生成"""
        if not results:
            return None

        # カテゴリに応じたアドバイステンプレート
        advice_templates = {
            "hours": {
                "ja": (
                    "💡 営業時間は日によって異なる場合があります。"
                    "訪問前に確認することをお勧めします。"
                ),
                "en": (
                    "💡 Operating hours may vary by day. We recommend checking before your visit."
                ),
                "zh": ("💡 营业时间可能因日期而异。建议您在来访前确认。"),
                "ko": (
                    "💡 영업시간은 날에 따라 다를 수 있습니다."
                    " 방문 전에 확인하시는 것을 권장합니다."
                ),
            },
            "pricing": {
                "ja": (
                    "💡 料金プランは変更される場合があります。"
                    "最新情報はスタッフにお問い合わせください。"
                ),
                "en": (
                    "💡 Pricing plans may change. Please contact staff for the latest information."
                ),
                "zh": ("💡 价格方案可能会有变动。请联系工作人员获取最新信息。"),
                "ko": ("💡 요금제는 변경될 수 있습니다. 최신 정보는 직원에게 문의해 주세요."),
            },
            "facility-info": {
                "ja": ("💡 設備の利用方法がわからない場合は、スタッフにお気軽にお声がけください。"),
                "en": (
                    "💡 If you're unsure how to use the facilities, feel free to ask our staff."
                ),
                "zh": ("💡 如果您不确定如何使用设施，请随时向工作人员咨询。"),
                "ko": ("💡 시설 이용 방법을 모르시면 직원에게 편하게 문의해 주세요."),
            },
        }

        if category in advice_templates:
            return advice_templates[category].get(language, advice_templates[category].get("ja"))

        return None

    def _expand_parent_context(self, chunk_results: List[Dict]) -> List[Dict]:
        """親チャンクのコンテキストを展開。

        チャンク結果からparent_idを抽出し、親ドキュメントの内容を
        各チャンクに付与する。

        Args:
            chunk_results: チャンクレベルの検索結果

        Returns:
            親コンテキストが付与された結果リスト
        """
        if not chunk_results:
            return chunk_results

        parent_ids = list({r.get("parent_id") for r in chunk_results if r.get("parent_id")})

        if not parent_ids:
            return chunk_results

        try:
            parent_response = (
                self.supabase.table("knowledge_base")
                .select("id, title, content")
                .in_("id", parent_ids)
                .execute()
            )

            parent_map: Dict = {}
            if parent_response.data:
                for parent in parent_response.data:
                    parent_map[parent["id"]] = parent

            expanded: List[Dict] = []
            for result in chunk_results:
                pid = result.get("parent_id")
                if pid and pid in parent_map:
                    expanded.append(
                        {
                            **result,
                            "parent_content": parent_map[pid].get("content", ""),
                            "parent_title": parent_map[pid].get("title", ""),
                        }
                    )
                else:
                    expanded.append(result)

            return expanded

        except Exception as e:
            logger.error("Failed to expand parent context: %s", e)
            return chunk_results
