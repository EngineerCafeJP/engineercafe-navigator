"""
Enhanced RAG Search Tool
Supabase + OpenRouter Embeddings統合による高精度RAG検索
"""

import os
from typing import List, Dict, Optional
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class EnhancedRAGSearch:
    """Enhanced RAG検索ツール"""

    def __init__(self):
        """初期化"""
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
        )

    async def search(
        self,
        query: str,
        category: str,
        language: str = "ja",
        include_advice: bool = True,
        max_results: int = 10,
    ) -> Dict:
        """
        Enhanced RAG検索を実行

        Args:
            query: 検索クエリ
            category: クエリカテゴリ（hours, pricing, location, facility-info等）
            language: 言語（ja or en）
            include_advice: 実用的なアドバイスを含めるか
            max_results: 最大結果数

        Returns:
            検索結果辞書 {success, data: {context, results, totalResults, topEntity}}
        """
        try:
            logger.info(f"Starting search with query: {query[:50]}")
            logger.debug(f"Category: {category}, Language: {language}")

            # 1. OpenAI Embeddings APIでクエリをエンベディング化
            embedding = await self._generate_embedding(query)

            # 2. Supabase RPCでベクトル検索
            search_results = self.supabase.rpc(
                "search_knowledge_base",
                {
                    "query_embedding": embedding,
                    "similarity_threshold": 0.5,
                    "match_count": max_results * 2,  # スコアリング用に多めに取得
                },
            ).execute()

            if not search_results.data:
                return {
                    "success": True,
                    "data": {
                        "context": "",
                        "results": [],
                        "totalResults": 0,
                        "topEntity": "general",
                    },
                }

            # 3. エンティティ認識とスコアリング
            results_list: List[Dict] = (
                list(search_results.data) if isinstance(search_results.data, list) else []
            )
            scored_results = self._score_results(results_list, query, category, language)

            # 3.5. 品質グレーディング（軽量CRAG）
            scored_results = self._grade_result_relevance(scored_results, query)

            # 4. トップ結果を取得
            top_results = scored_results[:max_results]

            logger.debug(
                f"Top results after scoring: {[{'title': r.get('title'), 'entity': r.get('entity'), 'priority_score': r.get('priority_score')} for r in top_results]}"
            )

            # 5. コンテキストを構築
            context = self._build_context_from_results(top_results, category, language)

            # 6. 実用的なアドバイスを追加（オプション）
            if include_advice:
                advice = self._generate_practical_advice(top_results, query, category, language)
                if advice:
                    context += f"\n\n{advice}"

            return {
                "success": True,
                "data": {
                    "context": context,
                    "results": top_results,
                    "totalResults": len(scored_results),
                    "topEntity": (
                        top_results[0].get("entity", "general") if top_results else "general"
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Search error: {e}")
            return {"success": False, "error": str(e)}

    async def _generate_embedding(self, text: str) -> List[float]:
        """OpenRouter API経由でエンベディングを生成（共通サービスに委譲）"""
        from utils.embedding_service import generate_embedding

        return await generate_embedding(text)

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

        return scored_results

    def _grade_result_relevance(self, scored_results: List[Dict], query: str) -> List[Dict]:
        """スコアリング済み結果の品質グレーディング（軽量CRAG）

        priority_scoreとクエリ用語マッチ率を基に、低品質な結果を除外する。

        Grading criteria:
        - HIGH (priority_score >= 0.8): 常に保持
        - MEDIUM (0.6 <= priority_score < 0.8): クエリ用語マッチがある場合保持
        - LOW (priority_score < 0.6): 除外

        Args:
            scored_results: _score_results()でスコアリング済みの結果リスト
            query: 元のクエリ文字列

        Returns:
            品質フィルタリング済みの結果リスト
        """
        if not scored_results:
            return []

        query_lower = query.lower()

        # Check if query contains CJK characters (Japanese/Chinese/Korean)
        has_cjk = any(
            "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff"
            for c in query_lower
        )

        if has_cjk:
            # For Japanese: use 2-character sliding window matching
            query_terms = [query_lower[i : i + 2] for i in range(len(query_lower) - 1)]
            # Filter out particles and common characters
            query_terms = [
                t
                for t in query_terms
                if t
                not in (
                    "は",
                    "の",
                    "が",
                    "を",
                    "に",
                    "で",
                    "と",
                    "も",
                    "か",
                    "です",
                    "ます",
                    "した",
                    "ません",
                    "まし",
                    "ませ",
                    "ありま",
                    "りま",
                )
            ]
        else:
            query_terms = query_lower.split()

        graded_results: List[Dict] = []

        for result in scored_results:
            score = result.get("priority_score", 0.0)

            # HIGH: 常に保持
            if score >= 0.8:
                graded_results.append({**result, "grade": "HIGH"})
                continue

            # MEDIUM: クエリ用語マッチがある場合保持
            if score >= 0.6:
                content = result.get("content", "").lower()
                title = result.get("title", "").lower()
                combined = f"{title} {content}"

                # クエリ用語のマッチ率を計算
                if query_terms:
                    match_count = sum(1 for term in query_terms if term in combined)
                    match_ratio = match_count / len(query_terms)

                    if match_ratio > 0.3:  # At least 30% of terms match
                        graded_results.append({**result, "grade": "MEDIUM"})
                        continue

            # LOW: 除外（ログに記録）
            logger.debug(
                f"Filtered out low-relevance result: "
                f"title={result.get('title', 'N/A')}, score={score:.3f}"
            )

        logger.info(
            f"Grade results: {len(graded_results)}/{len(scored_results)} passed "
            f"(HIGH: {sum(1 for r in graded_results if r.get('grade') == 'HIGH')}, "
            f"MEDIUM: {sum(1 for r in graded_results if r.get('grade') == 'MEDIUM')})"
        )

        return graded_results

    def _detect_entity(self, result: Dict) -> str:
        """結果からエンティティを検出"""
        content = str(result.get("content", "")).lower()
        title = str(result.get("title", "")).lower()
        metadata = result.get("metadata", {})

        # メタデータからエンティティを取得
        if metadata and isinstance(metadata, dict):
            entity = metadata.get("entity", "")
            if entity and isinstance(entity, str):
                return str(entity)

        # コンテンツからエンティティを推測
        if "engineer cafe" in content or "engineer cafe" in title or "エンジニアカフェ" in content:
            return "engineer-cafe"
        elif "saino" in content or "saino" in title or "サイノ" in content or "saino" in content:
            return "saino"
        elif "会議室" in content or "meeting room" in content:
            return "meeting-room"

        return "general"

    def _calculate_category_bonus(self, result: Dict, category: str) -> float:
        """カテゴリに基づくボーナススコア計算"""
        metadata = result.get("metadata", {})
        result_category = metadata.get("category", "") if isinstance(metadata, dict) else ""

        # カテゴリマッピング
        category_mapping = {
            "hours": ["hours", "営業時間", "business hours"],
            "pricing": ["pricing", "料金", "price", "cost"],
            "location": ["location", "access", "場所", "アクセス"],
            "facility-info": ["facility-info", "設備", "facilities"],
        }

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
        elif entity == "saino" and ("saino" in query_lower or "サイノ" in query_lower):
            return 0.3
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

                if entity == "engineer-cafe" and language == "ja":
                    context += "【エンジニアカフェ】\n"
                elif entity == "saino" and language == "ja":
                    context += "【sainoカフェ】\n"
                elif entity == "meeting-room" and language == "ja":
                    context += "【会議室】\n"

                # コンテンツを追加
                context += "\n".join(r.get("content", "") for r in entity_results)

        return context

    def _get_entity_priority(self, category: str) -> List[str]:
        """カテゴリに応じたエンティティ優先順位を取得"""
        priority_map = {
            "pricing": ["engineer-cafe", "saino", "meeting-room", "general"],
            "hours": ["engineer-cafe", "saino", "general", "meeting-room"],
            "facility-info": ["engineer-cafe", "general", "meeting-room", "saino"],
            "location": ["engineer-cafe", "general", "saino", "meeting-room"],
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
                "ja": "💡 営業時間は日によって異なる場合があります。訪問前に確認することをお勧めします。",
                "en": "💡 Operating hours may vary by day. We recommend checking before your visit.",
            },
            "pricing": {
                "ja": "💡 料金プランは変更される場合があります。最新情報はスタッフにお問い合わせください。",
                "en": "💡 Pricing plans may change. Please contact staff for the latest information.",
            },
            "facility-info": {
                "ja": "💡 設備の利用方法がわからない場合は、スタッフにお気軽にお声がけください。",
                "en": "💡 If you're unsure how to use the facilities, feel free to ask our staff.",
            },
        }

        if category in advice_templates:
            return advice_templates[category].get(language, advice_templates[category].get("ja"))

        return None
