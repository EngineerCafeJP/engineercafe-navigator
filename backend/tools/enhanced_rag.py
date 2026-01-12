"""
Enhanced RAG Search Tool
Supabase + OpenAI Embeddings統合による高精度RAG検索
"""

import os
from typing import List, Dict, Optional
import httpx
from supabase import create_client, Client


class EnhancedRAGSearch:
    """Enhanced RAG検索ツール"""

    def __init__(self):
        """初期化"""
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
        )
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")

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
            print(f"[EnhancedRAGSearch] Starting search with query: {query}")
            print(f"[EnhancedRAGSearch] Category: {category}, Language: {language}")

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
            scored_results = self._score_results(search_results.data, query, category, language)

            # 4. トップ結果を取得
            top_results = scored_results[:max_results]

            print(
                f"[EnhancedRAGSearch] Top results after scoring: {[{'title': r.get('title'), 'entity': r.get('entity'), 'priority_score': r.get('priority_score')} for r in top_results]}"
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
            print(f"[EnhancedRAGSearch] Error: {e}")
            return {"success": False, "error": str(e)}

    async def _generate_embedding(self, text: str) -> List[float]:
        """OpenAI APIでエンベディングを生成"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": "text-embedding-3-small", "input": text},
                timeout=30.0,
            )

            if response.status_code != 200:
                raise Exception(f"Embedding API error: {response.text}")

            data = response.json()
            return data["data"][0]["embedding"]

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
