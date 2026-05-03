"""
Enhanced RAG Search Tool
Supabase + OpenAI Embeddings統合による高精度RAG検索
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Optional

import httpx
from supabase import create_client, Client
import yaml

logger = logging.getLogger(__name__)

# Embedding model configuration
# text-embedding-3-small: 1536 dims (OpenAI)
# text-embedding-3-large: 3072 dims (OpenAI)
# The DB column dimension must match the model output dimension.
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536

# RPC similarity thresholds per category
# Lower threshold = broader recall; higher = stricter precision
RPC_SIMILARITY_THRESHOLDS: Dict[str, float] = {
    "hours": 0.25,
    "pricing": 0.25,
    "location": 0.25,
    "facility-info": 0.30,
    "event": 0.35,
    "general": 0.30,
    "consultation": 0.30,
    "community": 0.30,
    "smoking": 0.30,
    "food_drink": 0.30,
    "parking": 0.30,
    "bicycle": 0.30,
}
DEFAULT_RPC_SIMILARITY_THRESHOLD = 0.30
RPC_TIMEOUT_SECONDS = 10.0

# カテゴリ別品質グレーディング閾値
CATEGORY_THRESHOLDS = {
    "hours": {"high": 0.75, "medium": 0.50, "term_match": 0.25},
    "pricing": {"high": 0.75, "medium": 0.50, "term_match": 0.25},
    "facility-info": {"high": 0.78, "medium": 0.58, "term_match": 0.25},
    "location": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
    "event": {"high": 0.80, "medium": 0.60, "term_match": 0.30},
    "general": {"high": 0.72, "medium": 0.52, "term_match": 0.20},
    "consultation": {"high": 0.65, "medium": 0.45, "term_match": 0.18},
    "community": {"high": 0.73, "medium": 0.53, "term_match": 0.20},
    "smoking": {"high": 0.65, "medium": 0.45, "term_match": 0.18},
    "food_drink": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
    "parking": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
    "bicycle": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
}
DEFAULT_THRESHOLDS = {"high": 0.78, "medium": 0.58, "term_match": 0.25}


class CircuitBreaker:
    """Simple circuit breaker to prevent cascading RAG/LLM failures."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"  # closed, open, half_open

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if (
                self._last_failure_time
                and (time.time() - self._last_failure_time) > self.recovery_timeout
            ):
                self._state = "half_open"
                return False
            return True
        return False

    def record_success(self):
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"

    def reset(self):
        """Reset circuit breaker to closed state (useful for testing)."""
        self._failure_count = 0
        self._last_failure_time = None
        self._state = "closed"


_rag_circuit_breaker = CircuitBreaker()

# Query expansion mappings for Japanese/English synonyms
QUERY_EXPANSION_MAP: Dict[str, List[str]] = {
    "営業時間": ["opening hours", "business hours", "営業", "時間", "何時から", "何時まで", "開館"],
    "料金": ["pricing", "price", "cost", "fee", "料金", "値段", "いくら", "無料"],
    "アクセス": ["access", "location", "directions", "場所", "行き方", "住所", "最寄り駅"],
    "wifi": ["Wi-Fi", "WiFi", "wireless", "ネットワーク", "インターネット"],
    "会議室": ["meeting room", "conference room", "部屋", "予約"],
    "予約なし": ["予約不要", "予約なし", "no reservation", "受付", "利用登録", "初回"],
    "予約不要": ["予約不要", "予約なし", "no reservation", "受付", "利用登録", "初回"],
    "再受付": ["再受付", "会員番号", "受付カード", "2回目以降", "returning visitor"],
    "受付": ["受付", "利用登録", "初回", "会員番号", "受付カード"],
    "設備": ["facility", "facilities", "equipment", "機材", "備品"],
    "イベント": ["event", "events", "セミナー", "勉強会", "ワークショップ"],
    "opening hours": ["営業時間", "business hours", "operating hours"],
    "price": ["料金", "pricing", "cost", "fee"],
    "location": ["アクセス", "場所", "address", "directions"],
    "いくら": ["料金", "pricing", "price", "cost", "fee", "値段", "無料", "有料"],
    "何時": ["営業時間", "opening hours", "business hours", "開館", "閉館"],
    "どこ": ["場所", "アクセス", "location", "access", "住所", "所在地"],
    # Korean → Japanese keyword expansion (tRAG Phase 2)
    "이용 시간": ["営業時間", "開館時間", "利用時間"],
    "운영 시간": ["営業時間", "開館時間"],
    "어디": ["場所", "アクセス", "住所", "所在地"],
    "위치": ["場所", "アクセス", "住所", "所在地"],
    "시설": ["設備", "施設", "facility"],
    "요금": ["料金", "値段", "無料"],
    "무료": ["無料", "料金", "pricing"],
    "등록": ["利用方法", "登録", "初回", "初めて"],
    "방문": ["来訪", "初めて", "利用方法"],
    "와이파이": ["Wi-Fi", "WiFi", "ネットワーク"],
    "이벤트": ["イベント", "セミナー", "勉強会"],
    "회의실": ["会議室", "meeting room", "予約"],
    # English → Japanese keyword expansion (registration / membership)
    "register": ["利用登録", "登録", "会員", "初回", "受付"],
    "registration": ["利用登録", "登録", "会員", "初回", "受付"],
    "membership": ["会員", "利用登録", "無料", "受付", "会員番号"],
    "member benefits": ["無料", "利用料", "会員", "利用登録", "受付"],
    "sign up": ["利用登録", "登録", "初回", "会員"],
    "signing up": ["利用登録", "登録", "初回"],
    "become a member": ["会員", "利用登録", "登録", "初回"],
    "how to join": ["利用方法", "利用登録", "参加", "登録"],
    "first time": ["初回", "初めて", "利用登録"],
    "first-time": ["初回", "初めて", "利用登録", "受付"],
    "first-time visitor": ["初回", "初めて", "利用登録", "受付"],
    "first time visitor": ["初回", "初めて", "利用登録", "受付"],
    "first time here": ["初回", "初めて", "利用登録", "受付"],
    "what should i do": ["利用方法", "受付", "利用登録", "初回"],
    "member": ["会員", "利用登録", "会員番号", "受付", "無料"],
    "member number": ["会員番号", "受付", "受付カード"],
    "returning visitor": ["2回目以降", "会員番号", "受付カード", "再受付"],
    "registered before": ["2回目以降", "会員番号", "受付カード", "再受付"],
    "without a reservation": ["予約不要", "予約なし", "受付", "利用登録"],
    "no reservation": ["予約不要", "予約なし", "受付", "利用登録"],
    # Chinese → Japanese keyword expansion
    "营业时间": ["営業時間", "開館時間"],
    "费用": ["料金", "値段", "無料"],
    "位置": ["場所", "アクセス", "住所"],
    "设施": ["設備", "施設", "facility"],
    "登记": ["利用方法", "登録", "初回"],
    # Policy / space queries
    "spaces": ["スペース", "施設", "設備", "メインホール", "集中スペース"],
    "available spaces": ["スペース", "施設", "設備", "メインホール", "集中スペース"],
    "what spaces": ["スペース", "施設", "設備", "メインホール", "集中スペース"],
    "smoking": ["喫煙", "禁煙", "喫煙所"],
    "흡연": ["喫煙", "禁煙", "喫煙所"],
    "금연": ["禁煙", "喫煙"],
    "담배": ["喫煙", "禁煙", "喫煙所"],
}


class EnhancedRAGSearch:
    """Enhanced RAG検索ツール

    Supabaseのベクトル検索とテキストベースのフォールバック検索を組み合わせて、
    高精度なRAG検索を提供する。

    Attributes:
        supabase: Supabaseクライアント
        api_key: OpenRouter APIキー（embedding生成用）
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
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set, embedding search will fail")
        self.embedding_model = embedding_model or os.getenv(
            "EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )
        self.embedding_dimensions = embedding_dimensions or int(
            os.getenv("EMBEDDING_DIMENSIONS", str(DEFAULT_EMBEDDING_DIMENSIONS))
        )

    def _get_rpc_threshold(self, category: str) -> float:
        """カテゴリに基づくRPC類似度閾値を取得"""
        return RPC_SIMILARITY_THRESHOLDS.get(category, DEFAULT_RPC_SIMILARITY_THRESHOLD)

    async def search(
        self,
        query: str,
        category: str,
        language: str = "ja",
        include_advice: bool = True,
        max_results: int = 10,
        context_signals=None,
    ) -> Dict:
        """
        Enhanced RAG検索を実行

        Args:
            query: 検索クエリ
            category: クエリカテゴリ（hours, pricing, location, facility-info等）
            language: 言語（ja or en）
            include_advice: 実用的なアドバイスを含めるか
            max_results: 最大結果数
            context_signals: コンテキストシグナル（動的閾値調整用）

        Returns:
            検索結果辞書 {success, data: {context, results, totalResults, topEntity}}
        """
        if _rag_circuit_breaker.is_open:
            logger.warning("RAG circuit breaker is open, skipping search")
            return await self._fallback_search_response(
                query=query,
                category=category,
                language=language,
                include_advice=include_advice,
                max_results=max_results,
                error="Circuit breaker is open",
            )

        try:
            logger.info("Starting search: category=%s, language=%s", category, language)

            # 1. クエリ拡張（同義語・多言語キーワードを追加）
            expanded_query = self._expand_query(query, category, language)
            logger.debug("Expanded query length: %d chars", len(expanded_query))

            # 2. OpenAI Embeddings APIでクエリをエンベディング化
            try:
                embedding = await self._generate_embedding(expanded_query)
            except Exception as e:
                _rag_circuit_breaker.record_failure()
                logger.error("Embedding generation failed, trying fallback search: %s", e)
                return await self._fallback_search_response(
                    query=query,
                    category=category,
                    language=language,
                    include_advice=include_advice,
                    max_results=max_results,
                    error=str(e),
                )

            # 3. Supabase RPCでベクトル検索（カテゴリ別閾値を使用）
            try:
                search_results = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.supabase.rpc(
                            "search_knowledge_base",
                            {
                                "query_embedding": embedding,
                                "similarity_threshold": self._get_rpc_threshold(category),
                                "match_count": max_results * 3,  # スコアリング用に多めに取得
                            },
                        ).execute()
                    ),
                    timeout=RPC_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error("Supabase RPC timed out after %.0fs", RPC_TIMEOUT_SECONDS)
                _rag_circuit_breaker.record_failure()
                return await self._fallback_search_response(
                    query=query,
                    category=category,
                    language=language,
                    include_advice=include_advice,
                    max_results=max_results,
                    error="Supabase RPC timeout",
                )

            # 4. ベクトル検索で結果が不十分な場合、テキストベースのフォールバック
            if not search_results.data or len(search_results.data) < 2:
                logger.info("Vector search insufficient, trying text fallback")
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
                else:
                    local_results = self._local_knowledge_fallback_search(
                        query, category, language, max_results
                    )
                    if local_results:
                        if search_results.data is None:
                            search_results.data = []  # type: ignore[assignment]
                        search_results.data.extend(local_results)

            if not search_results.data:
                _rag_circuit_breaker.record_success()
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

            # 5.5. 品質グレーディング（軽量CRAG）
            scored_results = self._grade_result_relevance(
                scored_results, query, category, context_signals=context_signals
            )
            if not scored_results:
                local_results = self._local_knowledge_fallback_search(
                    query, category, language, max_results
                )
                if local_results:
                    scored_results = self._score_results(local_results, query, category, language)
                    scored_results = self._grade_result_relevance(
                        scored_results, query, category, context_signals=context_signals
                    )

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
            logger.debug("Top results after scoring: %s", top_summary)

            # 7. コンテキストを構築
            context = self._build_context_from_results(top_results, category, language)

            # 8. 実用的なアドバイスを追加（オプション）
            if include_advice:
                advice = self._generate_practical_advice(top_results, query, category, language)
                if advice:
                    context += f"\n\n{advice}"

            _rag_circuit_breaker.record_success()
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
            _rag_circuit_breaker.record_failure()
            logger.error("Search error: %s", e)
            return await self._fallback_search_response(
                query=query,
                category=category,
                language=language,
                include_advice=include_advice,
                max_results=max_results,
                error=str(e),
            )

    async def search_hierarchical(
        self,
        query: str,
        category: str,
        language: str = "ja",
        include_advice: bool = True,
        max_results: int = 10,
        context_signals=None,
    ) -> Dict:
        """Hierarchical RAG検索を実行。

        チャンクレベルの検索を行い、親チャンクのコンテキストを展開して
        より豊富なコンテキストを提供する。専用RPCが利用できない場合は
        標準検索にフォールバックする。

        Args:
            query: 検索クエリ
            category: クエリカテゴリ
            language: 言語（ja or en）
            include_advice: 実用的なアドバイスを含めるか
            max_results: 最大結果数
            context_signals: コンテキストシグナル（動的閾値調整用）

        Returns:
            検索結果辞書 {success, data: {context, results, totalResults, topEntity}}
        """
        try:
            logger.info(
                "Starting hierarchical search: category=%s, language=%s", category, language
            )

            # 1. クエリ拡張とembedding生成
            expanded_query = self._expand_query(query, category, language)
            embedding = await self._generate_embedding(expanded_query)

            # 2. Hierarchical RPC呼び出し（フォールバック付き）
            try:
                search_results = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.supabase.rpc(
                            "search_knowledge_base_hierarchical",
                            {
                                "query_embedding": embedding,
                                "similarity_threshold": self._get_rpc_threshold(category),
                                "match_count": max_results * 2,
                                "filter_chunk_level": "chunk",
                            },
                        ).execute()
                    ),
                    timeout=RPC_TIMEOUT_SECONDS,
                )
            except Exception:
                return await self.search(
                    query=query,
                    category=category,
                    language=language,
                    include_advice=include_advice,
                    max_results=max_results,
                    context_signals=context_signals,
                )

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

            # 3. スコアリング
            results_list: List[Dict] = (
                list(search_results.data) if isinstance(search_results.data, list) else []
            )
            scored_results = self._score_results(results_list, query, category, language)

            # 4. 親チャンク展開
            scored_results = self._expand_parent_context(scored_results)

            # 5. 品質グレーディング
            scored_results = self._grade_result_relevance(
                scored_results, query, category, context_signals=context_signals
            )

            # 6. トップ結果
            top_results = scored_results[:max_results]

            # 7. Hierarchicalコンテキスト構築
            context = self._build_hierarchical_context(top_results, language)

            # 8. アドバイス追加
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
            logger.error("Hierarchical search error: %s", e)
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

        # Entity anchoring: short queries get "エンジニアカフェ" prepended
        # Skip for "general" category to avoid biasing non-cafe queries (e.g. "Rust", "LLM")
        if category != "general" and len(query) < 15 and "エンジニアカフェ" not in query:
            query = f"エンジニアカフェ {query}"

        # クエリ内のキーワードに基づく拡張
        query_lower = query.lower()
        for key, synonyms in QUERY_EXPANSION_MAP.items():
            if key.lower() in query_lower:
                expansions.extend(synonyms)

        # カテゴリベースの拡張キーワード
        category_keywords: Dict[str, List[str]] = {
            "hours": ["営業時間", "opening hours", "business hours", "開館時間"],
            "pricing": ["料金", "price", "pricing", "cost", "利用料金"],
            "location": ["場所", "アクセス", "location", "access", "住所", "address"],
            "facility-info": [
                "設備",
                "facility",
                "facilities",
                "space",
                "spaces",
                "施設",
                "equipment",
            ],
            "consultation": ["相談", "コミュニティマネージャー", "career", "consultation"],
            "smoking": ["喫煙", "禁煙", "smoking", "흡연", "금연"],
            "food_drink": ["飲食", "食べ物", "drink", "food"],
            "parking": ["駐車場", "parking"],
            "bicycle": ["駐輪場", "bicycle parking"],
        }

        if category in category_keywords:
            expansions.extend(category_keywords[category])

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
            query_builder = (
                self.supabase.table("knowledge_base")
                .select("id, content, category, subcategory, language, source, metadata")
                .filter("content_embedding", "not.is", None)
            )

            # カテゴリフィルタ（generalカテゴリ以外の場合）
            if category and category != "general":
                query_builder = query_builder.eq("category", category)

            # KB is Japanese-only; filter to ja for reliable results
            # (English content_en chunks are stored with language='en')
            if language == "en":
                query_builder = query_builder.in_("language", ["en", "ja"])
            else:
                query_builder = query_builder.eq("language", "ja")

            result = query_builder.limit(max_results).execute()

            result_data = result.data if isinstance(result.data, list) else []

            if not result_data:
                # カテゴリフィルタなしで再試行
                result = (
                    self.supabase.table("knowledge_base")
                    .select("id, content, category, subcategory, language, source, metadata")
                    .filter("content_embedding", "not.is", None)
                    .eq("language", "ja")
                    .limit(max_results)
                    .execute()
                )
                result_data = result.data if isinstance(result.data, list) else []

            if result_data:
                # テキストマッチングでスコア付け
                scored: list[Dict] = []
                for row in result_data:
                    match_score = self._calculate_text_match_score(row, query, category, language)
                    if match_score > 0:
                        scored.append({**row, "similarity": min(match_score, 0.7)})

                scored.sort(key=lambda x: x.get("similarity", 0), reverse=True)
                return scored[:max_results]

            return []

        except Exception as e:
            logger.error("Text fallback search error: %s", e)
            return []

    async def _fallback_search_response(
        self,
        query: str,
        category: str,
        language: str,
        include_advice: bool,
        max_results: int,
        error: str,
    ) -> Dict:
        """Build a normal search response from non-vector fallbacks."""
        results = await self._text_fallback_search(query, category, language, max_results)
        if not results:
            results = self._local_knowledge_fallback_search(query, category, language, max_results)

        if not results:
            return {"success": False, "error": error}

        scored_results = self._score_results(results, query, category, language)
        scored_results = self._grade_result_relevance(scored_results, query, category)
        if not scored_results:
            local_results = self._local_knowledge_fallback_search(
                query, category, language, max_results
            )
            if local_results:
                scored_results = self._score_results(local_results, query, category, language)
                scored_results = self._grade_result_relevance(scored_results, query, category)
        top_results = scored_results[:max_results]
        context = self._build_context_from_results(top_results, category, language)

        if include_advice:
            advice = self._generate_practical_advice(top_results, query, category, language)
            if advice:
                context += f"\n\n{advice}"

        _rag_circuit_breaker.record_success()
        return {
            "success": True,
            "data": {
                "context": context,
                "results": top_results,
                "totalResults": len(scored_results),
                "topEntity": top_results[0].get("entity", "general") if top_results else "general",
            },
        }

    def _local_knowledge_fallback_search(
        self,
        query: str,
        category: str,
        language: str,
        max_results: int,
    ) -> List[Dict]:
        """Search the checked-in official YAML knowledge used to seed live RAG."""
        try:
            data_dir = Path(__file__).resolve().parents[1] / "knowledge" / "data"
            rows: list[Dict] = []
            for path in sorted(data_dir.glob("*.yaml")):
                with open(path, encoding="utf-8") as fh:
                    payload = yaml.safe_load(fh) or {}
                for entry in payload.get("entries", []):
                    content = entry.get("content_en") if language == "en" else entry.get("content")
                    if not content:
                        content = entry.get("content") or entry.get("content_en") or ""
                    row = {
                        "id": entry.get("id"),
                        "title": entry.get("title_en") if language == "en" else entry.get("title"),
                        "content": content,
                        "category": entry.get("category", "general"),
                        "subcategory": entry.get("subcategory"),
                        "language": language,
                        "source": entry.get("source") or "official-yaml",
                        "metadata": {
                            "entity": "engineer-cafe",
                            "tags": entry.get("tags", []),
                            "priority": entry.get("priority", 50),
                            "verified": entry.get("verified", False),
                            "local_fallback": True,
                        },
                    }
                    score = self._calculate_text_match_score(row, query, category, language)
                    if score > 0:
                        rows.append({**row, "similarity": min(score, 0.7)})

            rows.sort(
                key=lambda row: (
                    row.get("similarity", 0.0),
                    row.get("metadata", {}).get("priority", 0),
                ),
                reverse=True,
            )
            return rows[:max_results]
        except Exception as e:
            logger.error("Local YAML fallback search error: %s", e)
            return []

    def _calculate_text_match_score(
        self,
        row: Dict,
        query: str,
        category: str,
        language: str,
    ) -> float:
        searchable = " ".join(
            str(part)
            for part in (
                row.get("title", ""),
                row.get("content", ""),
                (
                    " ".join(row.get("metadata", {}).get("tags", []))
                    if isinstance(row.get("metadata"), dict)
                    else ""
                ),
            )
        ).lower()
        terms = self._extract_text_query_terms(query, category, language)

        row_category = row.get("category")
        if category != "general" and row_category != category:
            return 0.0
        if category == "general" and row_category not in {
            "general",
            "hours",
            "pricing",
            "access",
            "contact",
            "policy",
            "parking",
            "bicycle",
            "food_drink",
            "smoking",
        }:
            return 0.0

        match_score = 0.0
        has_content_match = False
        for term in terms:
            if term in searchable:
                match_score += 0.08 if self._contains_cjk(term) else 0.12
                has_content_match = True

        query_lower = query.lower()
        if any(term in query_lower for term in ("wi-fi", "wifi", "ssid", "接続")) and any(
            term in searchable for term in ("ssid", "engnecf", "password", "パスワード")
        ):
            match_score += 0.28
            has_content_match = True
        if any(term in query for term in ("料金", "いくら", "無料")) and any(
            term in searchable for term in ("無料", "free")
        ):
            match_score += 0.24
            has_content_match = True
        if (
            any(term in query for term in ("予約", "予約なし", "予約不要"))
            or any(
                term in query_lower
                for term in ("reservation", "without a reservation", "no reservation")
            )
        ) and any(
            term in searchable
            for term in (
                "予約不要",
                "予約なし",
                "does not require a reservation",
                "no reservation",
            )
        ):
            match_score += 0.35
            has_content_match = True
        if any(term in query for term in ("受付", "初めて", "再受付", "登録")) and any(
            term in searchable for term in ("受付", "registration", "会員番号", "reception")
        ):
            match_score += 0.2
            has_content_match = True
        if any(term in query for term in ("再受付", "以前登録", "登録した", "2回目")) and any(
            term in searchable for term in ("2回目以降", "会員番号", "受付カード", "受付")
        ):
            match_score += 0.3
            has_content_match = True

        if not has_content_match:
            return 0.0

        if row_category == category:
            match_score += 0.18

        priority = row.get("metadata", {}).get("priority", 50)
        if isinstance(priority, int):
            match_score += min(priority, 100) / 1000

        return match_score

    def _extract_text_query_terms(self, query: str, category: str, language: str) -> list[str]:
        text = self._expand_query(query, category, language).lower()
        terms = set(
            re.findall(
                r"[a-z0-9][a-z0-9_.+-]*|[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]{2,}",
                text,
            )
        )

        domain_terms = (
            "wi-fi",
            "wifi",
            "ssid",
            "料金",
            "無料",
            "利用",
            "受付",
            "初めて",
            "登録",
            "会員",
            "予約",
            "営業時間",
            "開館",
            "駐車",
            "電源",
            "喫煙",
            "禁煙",
            "흡연",
            "금연",
            "담배",
        )
        query_lower = query.lower()
        for term in domain_terms:
            if term.lower() in query_lower:
                terms.add(term.lower())

        cjk_compounds = [term for term in terms if self._contains_cjk(term)]
        for term in cjk_compounds:
            terms.update(term[i : i + 2] for i in range(len(term) - 1))

        stop_terms = {
            "です",
            "ます",
            "ませ",
            "さい",
            "くだ",
            "テスト",
            "テス",
            "スト",
            "教え",
            "えて",
            "して",
            "した",
            "the",
            "can",
            "how",
            "what",
            "where",
            "is",
            "to",
            "i",
        }
        return sorted(term for term in terms if len(term) >= 2 and term not in stop_terms)

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return any(
            "\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff" or "\uac00" <= c <= "\ud7af"
            for c in text
        )

    async def _generate_embedding(self, text: str) -> List[float]:
        """OpenRouter API経由でエンベディングを生成。

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
        if "text-embedding-3-" in self.embedding_model:
            request_body["dimensions"] = self.embedding_dimensions

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=30.0,
            )

            if response.status_code != 200:
                raise Exception(f"Embedding API error: {response.text}")

            data = response.json()
            return data["data"][0]["embedding"]

    def _grade_result_relevance(
        self,
        scored_results: List[Dict],
        query: str,
        category: str = "general",
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

        query_lower = query.lower()

        # CJK文字（日本語・中国語・韓国語）の検出
        has_cjk = any(
            "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff"
            for c in query_lower
        )

        if has_cjk:
            # 日本語: 2文字スライディングウィンドウマッチング
            query_terms = [query_lower[i : i + 2] for i in range(len(query_lower) - 1)]
            # 助詞・一般的な文字を除外
            stop_bigrams = {
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
            }
            query_terms = [t for t in query_terms if t not in stop_bigrams]
        else:
            query_terms = query_lower.split()

        graded_results: List[Dict] = []

        for result in scored_results:
            score = result.get("priority_score", 0.0)

            # HIGH: 常に保持
            if score >= high_threshold:
                graded_results.append({**result, "grade": "HIGH"})
                continue

            # MEDIUM: クエリ用語マッチがある場合保持
            if score >= medium_threshold:
                content = result.get("content", "").lower()
                title = result.get("title", "").lower()
                combined = f"{title} {content}"

                if query_terms:
                    match_count = sum(1 for term in query_terms if term in combined)
                    match_ratio = match_count / len(query_terms)

                    if match_ratio > term_match_threshold:
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
