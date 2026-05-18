"""Vision and memory-loading nodes for MainWorkflow."""

from __future__ import annotations

import logging

from langgraph.runtime import Runtime

from backend.config.routing_constants import extract_request_type
from backend.utils.postgres_sanitizer import sanitize_for_postgres
from backend.workflows.main.evidence import _is_acceptable_trag_japanese
from backend.workflows.main.types import WorkflowContext, WorkflowStateDict

logger = logging.getLogger(__name__)


def _public():
    from backend.workflows import main_workflow

    return main_workflow


class MemoryWorkflowMixin:
    async def _vision_node(self, state: WorkflowStateDict) -> dict:
        """ビジョンノード: 画像からOCR/表情認識を実行し、queryに変換"""
        from backend.utils.language_processor import LanguageProcessor

        if self._vision_agent is None:
            raise RuntimeError("VisionAgent is not available")

        result = await self._vision_agent.run(
            {
                "image": state["image_data"],
                "recognition_type": "text",
            }
        )

        # OCRテキストをqueryに追加
        ocr_text = result.get("text", {}).get("text", "")
        expression = result.get("face", {}).get("expression", {}).get("emotion")

        # ---------- 言語検出 ----------
        lp = LanguageProcessor()

        if ocr_text:
            lang = lp.detect_language(ocr_text)
        else:
            lang = {"detected": "ja", "confidence": 1.0}

        return {
            # Router / Memory 用
            "query": ocr_text or state.get("query", ""),
            "language": lang["detected"],
            # OCR情報保持
            "ocr_result": result,
            "metadata": {
                **state.get("metadata", {}),
                "detected_expression": expression,
            },
        }

    async def _memory_loader_node(
        self, state: WorkflowStateDict, runtime: Runtime[WorkflowContext]
    ) -> dict:
        """
        メモリローダーノード: 会話履歴とコンテキストを取得

        全クエリの前処理として、SimplifiedMemoryHelperから会話履歴を取得し、
        stateのcontextに追加する。
        """
        from backend.utils.memory_helper import (
            get_memory_helper,
            infer_previous_request_type_from_messages,
        )

        memory_helper = get_memory_helper()
        session_id = state.get("session_id", "")
        query = state.get("query", "")
        language = state.get("language", "ja")

        try:
            memory_context = await memory_helper.get_context(
                query=query,
                session_id=session_id,
                options={
                    "include_knowledge_base": False,
                    "language": language,
                    "inherit_context": True,
                },
            )
            try:
                from backend.utils.memory_feature_flags import get_memory_feature_flags

                memory_flags = get_memory_feature_flags()
                if not memory_flags.enable_agent_memory_stm_writes:
                    checkpoint_messages = self._checkpoint_messages_to_recent_memory(
                        state.get("messages", [])
                    )
                    checkpoint_inherited_request_type = None
                    if checkpoint_messages:
                        checkpoint_messages = memory_helper._rank_messages(
                            checkpoint_messages,
                            query,
                        )
                        if not extract_request_type(query):
                            checkpoint_inherited_request_type = (
                                infer_previous_request_type_from_messages(checkpoint_messages)
                            )
                    checkpoint_overlay = {
                        "recent_messages": checkpoint_messages,
                        "context_string": memory_helper._build_comprehensive_context(
                            checkpoint_messages,
                            memory_context.get("knowledge_results", []),
                            language,
                        ),
                        "stm_source": "langgraph_checkpointer",
                    }
                    if checkpoint_inherited_request_type and not memory_context.get(
                        "inherited_request_type"
                    ):
                        checkpoint_overlay["inherited_request_type"] = (
                            checkpoint_inherited_request_type
                        )
                    memory_context = {
                        **memory_context,
                        **checkpoint_overlay,
                    }
            except Exception as checkpoint_context_error:
                logger.debug(
                    "Checkpointer STM context overlay skipped: %s",
                    checkpoint_context_error,
                )

            # ユーザーメッセージを保存
            if query:  # 空でないことを確認
                try:
                    await memory_helper.store_message(
                        session_id=session_id,
                        role="user",
                        content=query,
                    )
                except Exception as store_error:
                    logger.warning("Failed to store user message: %s", store_error)

            # RAG pre-fetch and cache in state
            try:
                from backend.tools.enhanced_rag import EnhancedRAGSearch
                from backend.utils.query_classifier import QueryClassifier

                # tRAG: Translate non-Japanese queries to Japanese for
                # knowledge base search. Use the LLM retry path for EN/KO/ZH;
                # local opus-mt en->ja produced low-information garbage in
                # production and must not be used for retrieval queries.
                rag_query = query
                if language in ("en", "ko", "zh"):
                    try:
                        translated = await _public()._translate_llm_with_retry(query, language)
                        if translated and _is_acceptable_trag_japanese(translated):
                            rag_query = translated
                            logger.info(
                                "tRAG %s->ja: '%s' -> '%s'",
                                language,
                                query[:40],
                                rag_query[:40],
                            )
                        elif translated:
                            logger.warning(
                                "tRAG %s->ja rejected non-Japanese translation: '%s'",
                                language,
                                translated[:60],
                            )
                    except Exception as trans_err:
                        logger.warning(
                            "LLM translation (%s->ja) failed, using original: %s",
                            language,
                            trans_err,
                        )

                classifier = QueryClassifier()
                classification = await classifier.classify_with_details(query)
                category = (
                    classification.category if hasattr(classification, "category") else "general"
                )

                rag = EnhancedRAGSearch()
                rag_result = await rag.search(
                    query=rag_query,
                    category=category,
                    language=language,  # User's language for presentation (labels/advice)
                    max_results=10,
                )

                knowledge_results = {
                    "success": rag_result.get("success", False),
                    "results": rag_result.get("data", {}).get("results", []),
                    "context_string": rag_result.get("data", {}).get("context", ""),
                    "category": category,
                    "query": query,
                    "translated_query": rag_query if rag_query != query else None,
                }
            except Exception as e:
                logger.warning("RAG pre-fetch failed: %s", e)
                knowledge_results = {
                    "success": False,
                    "results": [],
                    "context_string": "",
                    "category": "general",
                    "query": query,
                }

            # Extract context priority signals
            priority_signals = None
            try:
                from backend.utils.context_priority import ContextPriorityEngine

                engine = ContextPriorityEngine()
                priority_signals = engine.extract_signals_from_context(
                    memory_context=memory_context,
                    knowledge_results=knowledge_results,
                )
            except Exception as sig_err:
                logger.debug("Priority signal extraction skipped: %s", sig_err)

            # NEW: Cross-thread memory from Store (long-term visitor memory)
            long_term_memories = []
            try:
                user_id = runtime.context.user_id if runtime.context else None
                if user_id and user_id != "anonymous" and runtime.store:
                    from backend.utils.memory_feature_flags import get_memory_feature_flags

                    safe_user_id = sanitize_for_postgres(user_id)
                    namespace = ("visitor_memories", safe_user_id)
                    safe_query = sanitize_for_postgres(state.get("query", ""))
                    memories = await _public().store_with_retry(
                        lambda s: s.asearch(namespace, query=safe_query, limit=5),
                        store=runtime.store,
                        operation_name="long-term memory load",
                    )
                    flags = get_memory_feature_flags()
                    if flags.enable_long_term_memory_rerank and memories:
                        try:
                            from backend.utils.long_term_memory_reranker import (
                                rerank_store_memory_items,
                            )

                            memories = rerank_store_memory_items(state.get("query", ""), memories)
                        except Exception as rerank_err:
                            logger.warning("Long-term memory rerank failed: %s", rerank_err)
                    long_term_memories = [m.value for m in memories]
                    if long_term_memories:
                        logger.info(
                            "Loaded %d long-term memories for user %s",
                            len(long_term_memories),
                            user_id,
                        )
            except Exception as e:
                logger.warning("Long-term memory load failed: %s", e)

            return {
                "context": {
                    **state.get("context", {}),
                    "memory": memory_context,
                    "knowledge_results": knowledge_results,
                    "priority_signals": priority_signals,
                    "long_term_memory": long_term_memories,  # NEW
                }
            }
        except Exception as e:
            logger.warning("Memory loading failed: %s", e)
            return {"context": {**state.get("context", {}), "memory": {}, "long_term_memory": []}}
