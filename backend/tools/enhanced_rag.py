"""
Enhanced RAG Search Tool
Supabase + OpenAI Embeddings統合による高精度RAG検索
"""

import asyncio
import logging
import os
from typing import List, Dict, Optional

import httpx
from supabase import create_client, Client
from backend.tools.enhanced_rag_circuit import (
    CircuitBreaker as CircuitBreaker,
    _rag_circuit_breaker,
)
from backend.tools.enhanced_rag_constants import (
    CATEGORY_THRESHOLDS as CATEGORY_THRESHOLDS,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RPC_SIMILARITY_THRESHOLD,
    DEFAULT_THRESHOLDS as DEFAULT_THRESHOLDS,
    MEMBERSHIP_QUERY_TERMS as MEMBERSHIP_QUERY_TERMS,
    MEMBERSHIP_RESULT_TERMS as MEMBERSHIP_RESULT_TERMS,
    QUERY_EXPANSION_MAP as QUERY_EXPANSION_MAP,
    RAG_CATEGORY_ALIASES as RAG_CATEGORY_ALIASES,
    RPC_SIMILARITY_THRESHOLDS,
    RPC_TIMEOUT_SECONDS,
    SAINO_QUERY_TERMS as SAINO_QUERY_TERMS,
)
from backend.tools.enhanced_rag_fallbacks import RAGFallbackMixin
from backend.tools.enhanced_rag_scoring import RAGScoringMixin

logger = logging.getLogger(__name__)


class EnhancedRAGSearch(RAGFallbackMixin, RAGScoringMixin):
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
                scored_results,
                query,
                category,
                language=language,
                context_signals=context_signals,
            )
            needs_entity_fallback = (
                self._query_mentions_saino(query)
                and not self._query_mentions_engineer_cafe(query)
                and not any(r.get("entity") == "saino" for r in scored_results)
            )
            needs_membership_fallback = self._needs_membership_fallback(query, scored_results)
            if not scored_results or needs_entity_fallback or needs_membership_fallback:
                local_results = self._local_knowledge_fallback_search(
                    query, category, language, max_results
                )
                if local_results:
                    scored_results = self._score_results(local_results, query, category, language)
                    scored_results = self._grade_result_relevance(
                        scored_results,
                        query,
                        category,
                        language=language,
                        context_signals=context_signals,
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
                scored_results,
                query,
                category,
                language=language,
                context_signals=context_signals,
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
