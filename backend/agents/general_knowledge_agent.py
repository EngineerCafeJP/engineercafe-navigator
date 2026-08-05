"""
GeneralKnowledgeAgent完全実装

一般的な質問に対応するエージェント。
Engineer Cafeに関する一般情報、AI・技術トピック、福岡のテックシーンなどに回答。
メモリ関連クエリも統合して処理する。

参考:
- docs/migration/agents/general-knowledge-agent/README.md
- docs/migration/agents/general-knowledge-agent/MIGRATION-GUIDE.md

実装済み機能:
1. Web検索機能の実装(tavily_search.py統合) ✓
2. OpenRouter APIを使用した回答生成 ✓
3. ナレッジベースとWeb検索の組み合わせ ✓
4. should_use_web_search()ロジック実装 ✓
5. 信頼度計算の最適化 ✓
6. 感情タグの適切な設定 ✓
7. エラーハンドリングとフォールバック ✓
8. メモリクエリハンドリング統合 ✓
"""

import logging
from typing import Dict, Any, List, Optional, Literal

from backend.agents.general_knowledge.memory import GeneralKnowledgeMemoryMixin
from backend.agents.general_knowledge.responses import GeneralKnowledgeResponseMixin
from backend.agents.llm_metadata import merge_llm_metadata
from backend.llm.provider import resolve_llm_provider
from backend.llm.models import get_model_config
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.tools.tavily_search import TavilySearchTool
from backend.utils.language_types import SupportedLanguage
from backend.utils.memory_interface import MemorySystemInterface
from backend.utils.time_utils import get_now_jst  # noqa: F401

logger = logging.getLogger(__name__)

EmotionType = Literal["helpful", "apologetic", "neutral", "happy", "sad", "relaxed", "surprised"]


class GeneralKnowledgeAgent(GeneralKnowledgeMemoryMixin, GeneralKnowledgeResponseMixin):
    """
    GeneralKnowledgeAgent完全実装

    一般的な質問に対応し、ナレッジベースとWeb検索を組み合わせて回答を生成します。
    Engineer Cafeに関する一般情報、AI・技術トピック、福岡のテックシーンなどに対応。
    メモリ関連クエリ（会話履歴の参照）も統合して処理します。
    """

    def __init__(self, memory_system: Optional[MemorySystemInterface] = None):
        """
        初期化

        Args:
            memory_system: メモリシステムのインスタンス（オプショナル）
        """
        self.name = "GeneralKnowledgeAgent"
        logger.info("GeneralKnowledgeAgent初期化")

        self.provider = resolve_llm_provider()
        self.model_config = get_model_config("general_knowledge")
        self.web_search = TavilySearchTool()
        self.rag_search = EnhancedRAGSearch()
        self.memory_system = memory_system

        memory_status = "enabled" if memory_system else "disabled"
        logger.info(
            "GeneralKnowledgeAgent initialized with model: %s, memory: %s",
            self.model_config.model_id,
            memory_status,
        )

    async def answer_query(
        self,
        query: str,
        language: SupportedLanguage = "ja",
        session_id: Optional[str] = None,
        query_type: str = "general",
        state_context: Optional[Dict] = None,
        context_signals=None,
        long_term_memory: Optional[list] = None,
    ) -> Dict[str, Any]:
        """統合クエリハンドラ: query_typeに応じて処理を分岐"""
        if query_type == "memory":
            return await self._handle_memory_query(
                query,
                session_id or "",
                language,
                state_context=state_context,
                long_term_memory=long_term_memory,
            )
        if query_type == "assistant_profile":
            return self._assistant_profile_response(language)
        if query_type == "daily_conversation":
            return self._daily_conversation_response(query, language)
        if query_type == "current_info":
            return await self.answer_general_query(
                query,
                language,
                session_id,
                state_context,
                context_signals,
                long_term_memory=long_term_memory,
                query_type="current_info",
            )
        return await self.answer_general_query(
            query,
            language,
            session_id,
            state_context,
            context_signals,
            long_term_memory=long_term_memory,
            query_type=query_type,
        )

    async def answer_general_query(
        self,
        query: str,
        language: SupportedLanguage = "ja",
        session_id: Optional[str] = None,
        state_context: Optional[Dict] = None,
        context_signals=None,
        long_term_memory: Optional[list] = None,
        query_type: str = "general",
    ) -> Dict[str, Any]:
        """
        一般的な質問に回答

        Args:
            query: ユーザーからの質問
            language: 言語設定("ja" or "en")
            session_id: セッションID(オプショナル)
            state_context: RAGキャッシュからのコンテキスト（オプショナル）

        Returns:
            {"answer": str, "emotion": str, "metadata": Dict}
        """
        logger.info("一般質問処理開始: query=%s..., language=%s", query[:50], language)

        try:
            if self._is_date_only_query(query):
                return self._current_date_response(query, language)
            if query_type == "current-time" or self._is_current_time_query(query):
                return self._current_time_response(query, language)

            mode = self._resolve_general_mode(query, query_type)
            if mode == "assistant_profile":
                return self._assistant_profile_response(language)
            if mode == "daily_conversation":
                return self._daily_conversation_response(query, language)

            # 1. current-info のみ Web 検索を許可する。
            needs_web_search = mode == "current_info"
            logger.info("Web検索必要性判定: %s", needs_web_search)

            # 2. ナレッジベース検索（キャッシュチェック付き）
            context = ""
            sources: List[str] = []
            rag_category = self._rag_category_for_query_type(query_type)

            cached = state_context if state_context else None
            if cached and cached.get("success") and cached.get("category") == rag_category:
                context = cached.get("context_string", "")
                sources.append("knowledge_base_cached")
                logger.info("Using cached RAG results: %d chars", len(context))
            else:
                kb_result = await self.rag_search.search(
                    query=query,
                    category=rag_category,
                    language=language,
                    max_results=5,
                    context_signals=context_signals,
                )

                if kb_result.get("success") and kb_result.get("data"):
                    context = kb_result["data"].get("context", "")
                    sources.append("knowledge_base")
                    logger.info("ナレッジベース検索成功: %d chars", len(context))

            # 3. Web検索(条件付き)
            if needs_web_search:
                logger.info("Web検索を実行します")
                web_result = await self.web_search.search(
                    query=self._normalize_current_info_query(query),
                    language=language,
                )

                if web_result.get("success"):
                    web_text = web_result.get("text", "")
                    web_sources = web_result.get("sources", [])

                    if web_text:
                        if context:
                            context += f"\n\n【Web検索結果】\n{web_text}"
                        else:
                            context = web_text

                        sources.append("web_search")
                        logger.info(
                            "Web検索成功: %d chars, %d sources", len(web_text), len(web_sources)
                        )

            long_term_text = self._format_long_term_memory_context(long_term_memory, language)
            if long_term_text:
                context = f"{context}\n\n{long_term_text}".strip()
                sources.append("long_term_memory")

            # 4. current-info で外部情報が取れない場合だけ、古い情報で断言しない。
            if mode == "current_info" and "web_search" not in sources:
                return self._current_info_unavailable_response(language)

            # 5. プロンプト構築
            prompt = self._build_general_prompt(query, context, sources, language, mode=mode)

            # 6. LLM生成
            from langchain_core.messages import HumanMessage

            messages = [HumanMessage(content=prompt)]
            model_config = (
                get_model_config("deep_reasoning")
                if mode == "deep_reasoning"
                else self.model_config
            )
            response_text = await self.provider.generate(messages=messages, config=model_config)

            # 7. 感情・信頼度抽出
            emotion = self._extract_emotion(response_text)
            confidence = self._calculate_confidence(sources)

            logger.info("回答生成完了: emotion=%s, confidence=%s", emotion, confidence)

            metadata = merge_llm_metadata(
                {
                    "agent": self.name,
                    "status": "success",
                    "confidence": confidence,
                    "category": "general_knowledge",
                    "request_type": mode,
                    "route": "general_knowledge",
                    "query_type": mode,
                    "model_use_case": (
                        "deep_reasoning" if mode == "deep_reasoning" else "general_knowledge"
                    ),
                    "sources": sources,
                    "web_search_used": "web_search" in sources,
                    "rag_used": any(source.startswith("knowledge_base") for source in sources),
                },
                response_text,
            )

            return {
                "answer": str(response_text),
                "emotion": emotion,
                "metadata": metadata,
            }

        except Exception as e:
            logger.exception("GeneralKnowledgeAgent処理エラー: %s", e)
            return self._handle_error(language)

    @staticmethod
    def _rag_category_for_query_type(query_type: str) -> str:
        """Keep general-knowledge routes on specific local KB slices when known."""
        category_by_query_type = {
            "consultation": "consultation",
            "community": "community",
        }
        return category_by_query_type.get(query_type, "general")

    # =========================================================================
    # メモリクエリ処理
    # =========================================================================
