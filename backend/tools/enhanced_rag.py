"""
Enhanced RAG Search Tool
Supabase + OpenAI Embeddings統合による高精度RAG検索
"""

import os
from typing import List, Dict, Optional
import httpx
from supabase import create_client, Client

# Embedding model configuration
# text-embedding-3-small: 1536 dims (OpenAI)
# text-embedding-3-large: 3072 dims (OpenAI)
# The DB column dimension must match the model output dimension.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536

# Query expansion mappings for Japanese/English synonyms
QUERY_EXPANSION_MAP: Dict[str, List[str]] = {
    "営業時間": ["opening hours", "business hours", "営業", "時間", "何時から", "何時まで", "開館"],
    "料金": ["pricing", "price", "cost", "fee", "料金", "値段", "いくら", "無料"],
    "アクセス": ["access", "location", "directions", "場所", "行き方", "住所", "最寄り駅"],
    "wifi": ["Wi-Fi", "WiFi", "wireless", "ネットワーク", "インターネット"],
    "会議室": ["meeting room", "conference room", "部屋", "予約"],
    "設備": ["facility", "facilities", "equipment", "機材", "備品"],
    "イベント": ["event", "events", "セミナー", "勉強会", "ワークショップ"],
    "opening hours": ["営業時間", "business hours", "operating hours"],
    "price": ["料金", "pricing", "cost", "fee"],
    "location": ["アクセス", "場所", "address", "directions"],
}


class EnhancedRAGSearch:
    """Enhanced RAG検索ツール

    Supabaseのベクトル検索とテキストベースのフォールバック検索を組み合わせて、
    高精度なRAG検索を提供する。

    Attributes:
        supabase: Supabaseクライアント
        openai_api_key: OpenAI APIキー
        embedding_model: 使用するembeddingモデル名
        embedding_dimensions: embeddingの次元数
    """

    def __init__(
        self,
        supabase_client: Optional[Client] = None,
        embedding_model: Optional[str] = None,
        embedding_dimensions: Optional[int] = None,
    ):
        """初期化

        Args:
            supabase_client: Supabaseクライアント（テスト用にDI可能）
            embedding_model: embeddingモデル名（環境変数 EMBEDDING_MODEL で上書き可）
            embedding_dimensions: embedding次元数（環境変数 EMBEDDING_DIMENSIONS で上書き可）
        """
        if supabase_client is not None:
            self.supabase = supabase_client
        else:
            self.supabase: Client = create_client(
                os.getenv("SUPABASE_URL", ""),
                os.getenv("SUPABASE_KEY", ""),
            )
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.embedding_model = embedding_model or os.getenv(
            "EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )
        self.embedding_dimensions = embedding_dimensions or int(
            os.getenv("EMBEDDING_DIMENSIONS", str(DEFAULT_EMBEDDING_DIMENSIONS))
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
            print(f"[EnhancedRAGSearch] Starting search with query: {query}")
            print(f"[EnhancedRAGSearch] Category: {category}, Language: {language}")

            # 1. クエリ拡張（同義語・多言語キーワードを追加）
            expanded_query = self._expand_query(query, category, language)
            print(f"[EnhancedRAGSearch] Expanded query: {expanded_query}")

            # 2. OpenAI Embeddings APIでクエリをエンベディング化
            embedding = await self._generate_embedding(expanded_query)

            # 3. Supabase RPCでベクトル検索（閾値を低めに設定して取りこぼしを防ぐ）
            search_results = self.supabase.rpc(
                "search_knowledge_base",
                {
                    "query_embedding": embedding,
                    "similarity_threshold": 0.3,
                    "match_count": max_results * 3,  # スコアリング用に多めに取得
                },
            ).execute()

            # 4. ベクトル検索で結果が不十分な場合、テキストベースのフォールバック
            if not search_results.data or len(search_results.data) < 2:
                print("[EnhancedRAGSearch] Vector search insufficient, trying text fallback")
                text_results = await self._text_fallback_search(
                    query, category, language, max_results
                )
                if text_results:
                    existing_ids = {r.get("id") for r in (search_results.data or [])}
                    for tr in text_results:
                        if tr.get("id") not in existing_ids:
                            if search_results.data is None:
                                search_results.data = []  # type: ignore[assignment]
                            search_results.data.append(tr)

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

            # 5. エンティティ認識とスコアリング
            scored_results = self._score_results(search_results.data, query, category, language)

            # 6. トップ結果を取得
            top_results = scored_results[:max_results]

            top_summary = [
                {
                    "title": r.get("title"),
                    "entity": r.get("entity"),
                    "priority_score": r.get("priority_score"),
                }
                for r in top_results
            ]
            print(f"[EnhancedRAGSearch] Top results after scoring: {top_summary}")

            # 7. コンテキストを構築
            context = self._build_context_from_results(top_results, category, language)

            # 8. 実用的なアドバイスを追加（オプション）
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

    def _expand_query(self, query: str, category: str, language: str) -> str:
        """クエリを同義語・多言語キーワードで拡張する。

        短いクエリやドメイン固有の用語に対してベクトル検索の精度を向上させる。

        Args:
            query: 元のクエリ
            category: クエリカテゴリ
            language: 言語コード

        Returns:
            拡張されたクエリ文字列
        """
        expansions: list[str] = []

        # カテゴリベースの拡張キーワード
        category_keywords: Dict[str, List[str]] = {
            "hours": ["営業時間", "opening hours", "business hours", "開館時間"],
            "pricing": ["料金", "price", "pricing", "cost", "利用料金"],
            "location": ["場所", "アクセス", "location", "access", "住所", "address"],
            "facility-info": ["設備", "facility", "施設", "equipment"],
        }

        if category in category_keywords:
            expansions.extend(category_keywords[category])

        # クエリ内のキーワードに基づく拡張
        query_lower = query.lower()
        for key, synonyms in QUERY_EXPANSION_MAP.items():
            if key.lower() in query_lower:
                expansions.extend(synonyms)

        # 重複除去して元クエリと結合
        seen: set[str] = set()
        unique_expansions: list[str] = []
        for exp in expansions:
            if exp.lower() not in seen and exp.lower() not in query_lower:
                seen.add(exp.lower())
                unique_expansions.append(exp)

        if unique_expansions:
            # 拡張キーワードを元クエリに付加（最大5個）
            return f"{query} ({' '.join(unique_expansions[:5])})"

        return query

    async def _text_fallback_search(
        self,
        query: str,
        category: str,
        language: str,
        max_results: int,
    ) -> List[Dict]:
        """テキストベースのフォールバック検索。

        ベクトル検索で十分な結果が得られない場合に、カテゴリとキーワードで
        knowledge_baseを直接検索する。

        Args:
            query: 検索クエリ
            category: カテゴリ
            language: 言語コード
            max_results: 最大結果数

        Returns:
            検索結果のリスト
        """
        try:
            # カテゴリベースの検索
            query_builder = self.supabase.table("knowledge_base").select(
                "id, content, category, subcategory, language, source, metadata"
            )

            # カテゴリフィルタ（generalカテゴリ以外の場合）
            if category and category != "general":
                query_builder = query_builder.eq("category", category)

            # 言語フィルタ
            if language:
                query_builder = query_builder.eq("language", language)

            result = query_builder.limit(max_results).execute()

            if not result.data:
                # カテゴリフィルタなしで再試行
                result = (
                    self.supabase.table("knowledge_base")
                    .select("id, content, category, subcategory, language, source, metadata")
                    .eq("language", language)
                    .limit(max_results)
                    .execute()
                )

            if result.data:
                # テキストマッチングでスコア付け
                scored: list[Dict] = []
                for row in result.data:
                    content_lower = row.get("content", "").lower()
                    query_lower = query.lower()
                    # 簡易テキストマッチスコア
                    match_score = 0.0
                    query_terms = query_lower.replace("？", "").replace("?", "").split()
                    for term in query_terms:
                        if len(term) >= 2 and term in content_lower:
                            match_score += 0.15
                    # カテゴリ一致ボーナス
                    if row.get("category") == category:
                        match_score += 0.2
                    if match_score > 0:
                        scored.append({**row, "similarity": min(match_score, 0.7)})

                scored.sort(key=lambda x: x.get("similarity", 0), reverse=True)
                return scored[:max_results]

            return []

        except Exception as e:
            print(f"[EnhancedRAGSearch] Text fallback error: {e}")
            return []

    async def _generate_embedding(self, text: str) -> List[float]:
        """OpenAI APIでエンベディングを生成。

        Args:
            text: エンベディング対象テキスト

        Returns:
            エンベディングベクトル

        Raises:
            Exception: API呼び出しが失敗した場合
        """
        request_body: Dict = {
            "model": self.embedding_model,
            "input": text,
        }

        # text-embedding-3-* モデルは dimensions パラメータをサポート
        if self.embedding_model.startswith("text-embedding-3-"):
            request_body["dimensions"] = self.embedding_dimensions

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
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
                "ja": (
                    "💡 営業時間は日によって異なる場合があります。"
                    "訪問前に確認することをお勧めします。"
                ),
                "en": (
                    "💡 Operating hours may vary by day."
                    " We recommend checking before your visit."
                ),
            },
            "pricing": {
                "ja": (
                    "💡 料金プランは変更される場合があります。"
                    "最新情報はスタッフにお問い合わせください。"
                ),
                "en": (
                    "💡 Pricing plans may change."
                    " Please contact staff for the latest information."
                ),
            },
            "facility-info": {
                "ja": "💡 設備の利用方法がわからない場合は、スタッフにお気軽にお声がけください。",
                "en": "💡 If you're unsure how to use the facilities, feel free to ask our staff.",
            },
        }

        if category in advice_templates:
            return advice_templates[category].get(language, advice_templates[category].get("ja"))

        return None
