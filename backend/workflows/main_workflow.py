"""
メインLangGraphワークフロー - Supervisor Pattern 実装

LangGraphのSupervisor Agentパターンに従い、OrchestratorAgentが
マルチエージェントシステムを動的に制御する。

参考:
- https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- https://langchain-ai.github.io/langgraph/concepts/persistence/
"""

import asyncio
import base64
import logging
import os
import re
import time
import uuid

import cv2
import httpx as _httpx
import numpy as np
from dataclasses import dataclass
from typing import Annotated, Any, Optional, TypedDict, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime
from langgraph.types import Command, RetryPolicy

from backend.agents.character_control_agent import CharacterControlAgent
from backend.agents.orchestrator_agent import (
    OrchestratorAgent,
    OrchestratorDecision,
    RoutingTarget,
)
from backend.agents.orchestrator_agent import OrchestratorAgent as RoutingLogicAgent
from backend.config.routing_constants import GREETING_KEYWORDS, match_keywords
from backend.services.memory_promoter import MemoryPromoter
from backend.utils.postgres_sanitizer import sanitize_for_postgres
from backend.utils.store import store_with_retry

logger = logging.getLogger(__name__)

# 非同期シングルトン用ロック
_workflow_lock = asyncio.Lock()

# tRAG: Reusable httpx client for KO/ZH translation
_trag_http_client: Optional["_httpx.AsyncClient"] = None

# tRAG: Japanese kana detection for translation validation
# NOTE: Intentionally kana-only (no CJK U+4E00-9FFF). Kanji-only
# translations like "営業時間" are false-negatives, but including
# CJK would also accept untranslated Chinese input. This trade-off
# is documented in commit 72e42c974. Most natural Japanese sentences
# contain at least one kana character.
_JA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")

# tRAG: Preamble pattern to strip from LLM translation output
# Require delimiter (colon/space) after keyword to avoid stripping
# valid Japanese like "以下の情報をお伝えします"
_TRAG_PREAMBLE_RE = re.compile(
    r"^(Translation:\s*|翻訳[：:]\s*|Here is[^:]*:\s*|以下[はがの]翻訳[：:]?\s*)",
    re.IGNORECASE,
)


def _get_trag_client() -> "_httpx.AsyncClient":
    """Return a shared httpx client for tRAG translation."""
    global _trag_http_client
    if _trag_http_client is None or _trag_http_client.is_closed:
        _trag_http_client = _httpx.AsyncClient(
            timeout=_httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        )
    return _trag_http_client


async def _translate_llm_with_retry(
    query: str,
    language: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
) -> str:
    """Translate KO/ZH query to JA via OpenRouter with exponential backoff."""
    _TRAG_MODEL = os.getenv("TRAG_TRANSLATION_MODEL", "google/gemini-3.1-flash-lite-preview")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set, skipping %s->ja", language)
        return ""

    client = _get_trag_client()
    payload = {
        "model": _TRAG_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a translation "
                    "engine. Translate the "
                    "user's text to Japanese."
                    " Return ONLY the "
                    "Japanese translation."
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": 200,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries + 1):
        try:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                translated = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                )
                translated = _TRAG_PREAMBLE_RE.sub("", translated).strip()
                if re.search(r"^[A-Za-z]{5,}", translated):
                    logger.warning("tRAG preamble: '%s'", translated[:60])
                    translated = ""
                return translated
            logger.warning(
                "OpenRouter %d (attempt %d/%d): %s",
                resp.status_code,
                attempt + 1,
                max_retries + 1,
                resp.text[:200],
            )
        except Exception as exc:
            logger.warning(
                "LLM translation %s->ja request error (attempt %d/%d): %s",
                language,
                attempt + 1,
                max_retries + 1,
                exc,
            )
        if attempt < max_retries:
            await asyncio.sleep(backoff_base * (2**attempt))
    logger.error(
        "LLM translation %s->ja failed after %d attempts",
        language,
        max_retries + 1,
    )
    return ""


class WorkflowStateDict(TypedDict):
    """ワークフローの状態定義"""

    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    session_id: str
    language: str
    routing: dict
    answer: Optional[str]
    emotion: Optional[str]
    metadata: dict
    context: dict
    reception_status: dict
    image_data: Optional[Any]  # np.ndarray (optional vision input)
    ocr_result: Optional[dict]  # OCR result from VisionAgent


@dataclass
class WorkflowContext:
    """ワークフローのランタイムコンテキスト"""

    user_id: str  # visitor_id from frontend, or session_id as fallback


class MainWorkflow:
    """
    メインLangGraphワークフロー - Supervisor Patternによるマルチエージェント制御

    アーキテクチャ:
    - OrchestratorAgent (Supervisor): クエリを分析し、適切なエージェントを選択
    - 各エージェント: 専門領域の処理を行い、結果をOrchestratorに返す
    - Command pattern: 明示的な制御フローでルーティング
    - AsyncPostgresSaver: 会話状態の永続化
    """

    def __init__(self, checkpointer=None, store=None):
        # debug_modeは環境変数で制御（本番ではFalse推奨）
        debug_mode = os.getenv("ORCHESTRATOR_DEBUG_MODE", "false").lower() == "true"
        self.orchestrator = OrchestratorAgent(debug_mode=debug_mode)
        self.checkpointer = checkpointer
        self.store = store

        # 全エージェントをシングルトンインスタンスとして保持
        from backend.agents.business_info_agent import BusinessInfoAgent
        from backend.agents.event_agent import EventAgent
        from backend.agents.facility_agent import FacilityAgent
        from backend.agents.farewell_agent import FarewellAgent
        from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
        from backend.agents.slide_agent import SlideAgent

        self._business_info_agent = BusinessInfoAgent()
        self._facility_agent = FacilityAgent()
        self._event_agent = EventAgent()
        self._farewell_agent = FarewellAgent()
        self._slide_agent = SlideAgent()
        try:
            self._character_control_agent = CharacterControlAgent()
        except Exception as e:
            logger.warning("CharacterControlAgent unavailable: %s", e, exc_info=True)
            self._character_control_agent = None

        # GKAにメモリシステムを注入（Supabase依存のため安全にtry/except）
        try:
            from backend.utils.memory_helper import get_memory_helper

            memory_system = get_memory_helper()
        except Exception as e:
            logger.warning("Memory system unavailable for GKA: %s", e, exc_info=True)
            memory_system = None
        self._general_knowledge_agent = GeneralKnowledgeAgent(memory_system=memory_system)

        # VisionAgentをシングルトンとしてキャッシュ（毎回生成するとLLM接続が無駄）
        try:
            from backend.agents.ocr_agent import VisionAgent

            self._vision_agent = VisionAgent()
        except Exception as e:
            logger.warning("VisionAgent unavailable: %s", e)
            self._vision_agent = None

        self.graph = self._build_graph()

    async def _store_reception_session(
        self,
        *,
        session_id: str,
        stage: str,
        language: str,
        trigger_type: str = "voice",
        status: str = "active",
        metadata: Optional[dict[str, Any]] = None,
        purpose: Optional[dict[str, Any]] = None,
        visitor_identity: Optional[dict[str, Any]] = None,
    ) -> None:
        """Persist reception state for /api/chat-driven multi-turn flows."""
        if not session_id:
            return

        if not hasattr(self, "_reception_repo"):
            from backend.utils.reception_repository import ReceptionRepository

            self._reception_repo = ReceptionRepository()

        payload: dict[str, Any] = {
            "session_id": session_id,
            "stage": stage,
            "language": language,
            "trigger_type": trigger_type,
            "status": status,
        }
        if metadata is not None:
            payload["metadata"] = metadata
        if purpose is not None:
            payload["purpose"] = purpose
        if visitor_identity is not None:
            payload["visitor_identity"] = visitor_identity

        try:
            await self._reception_repo.store_session(session_id, payload)
        except Exception as exc:
            logger.warning("Reception session persistence failed: %s", exc)

    # LLMノード用リトライポリシー: 一時的な障害(レート制限, タイムアウト等)に対応
    LLM_RETRY_POLICY = RetryPolicy(
        initial_interval=1.0,
        backoff_factor=2.0,
        max_interval=10.0,
        max_attempts=3,
    )
    _CLARIFICATION_CATEGORIES = (
        "cafe-clarification-needed",
        "meeting-room-clarification-needed",
        "event-clarification-needed",
        "space-clarification-needed",
        "general-clarification-needed",
    )
    _PRE_MEMORY_DIRECT_AGENTS = {"facility", "general_knowledge"}
    _PRE_MEMORY_INLINE_CATEGORIES = {"emergency", "greeting", *_CLARIFICATION_CATEGORIES}
    _ANAPHORA_MARKERS = (
        "それについて",
        "それって",
        "それのこと",
        "あれについて",
        "これについて",
        "that one",
        "about that",
        "about it",
        "more about that",
        "more about it",
        "tell me more about that",
        "tell me more about it",
    )

    def _build_graph(self) -> StateGraph:
        """Supervisor Patternに基づくグラフ構造を構築"""
        workflow = StateGraph(WorkflowStateDict, context_schema=WorkflowContext)

        # LLM依存ノード: retry_policyを適用
        llm_retry = self.LLM_RETRY_POLICY

        # ノードの追加
        # memory_loader, format_response: LLM非依存のためリトライ不要
        workflow.add_node("reception_check", self._reception_check_node)
        workflow.add_node("keyword_router", self._keyword_router_node)
        workflow.add_node("memory_loader", self._memory_loader_node)
        workflow.add_node("vision", self._vision_node, retry_policy=llm_retry)
        workflow.add_node("format_response", self._format_response_node)

        # LLM依存ノード
        workflow.add_node("orchestrator", self._orchestrator_node, retry_policy=llm_retry)
        workflow.add_node("business_info", self._business_info_node, retry_policy=llm_retry)
        workflow.add_node("facility", self._facility_node, retry_policy=llm_retry)
        workflow.add_node("event", self._event_node, retry_policy=llm_retry)
        workflow.add_node("slide", self._slide_node, retry_policy=llm_retry)
        workflow.add_node("general_knowledge", self._general_knowledge_node, retry_policy=llm_retry)
        workflow.add_node("farewell", self._farewell_node, retry_policy=llm_retry)

        # エッジの定義（Supervisor Pattern）
        # START → (text: reception_check, image: vision)
        workflow.add_conditional_edges(
            START,
            self._input_type_decision,
            {
                "text": "reception_check",
                "image": "vision",
            },
        )
        workflow.add_conditional_edges(
            "reception_check",
            self._reception_check_decision,
            {
                "active_reception": "memory_loader",
                "no_reception": "keyword_router",
            },
        )
        workflow.add_conditional_edges(
            "keyword_router",
            self._keyword_router_decision,
            {
                "normal": "memory_loader",
                "facility": "facility",
                "general_knowledge": "general_knowledge",
            },
        )
        workflow.add_edge("vision", "memory_loader")
        workflow.add_edge("memory_loader", "orchestrator")

        # 各エージェント → format_response → END
        workflow.add_edge("business_info", "format_response")
        workflow.add_edge("facility", "format_response")
        workflow.add_edge("event", "format_response")
        workflow.add_edge("slide", "format_response")
        workflow.add_edge("general_knowledge", "format_response")
        workflow.add_edge("farewell", "format_response")
        workflow.add_edge("format_response", END)

        compile_kwargs = {}
        if self.checkpointer:
            compile_kwargs["checkpointer"] = self.checkpointer
        if self.store:
            compile_kwargs["store"] = self.store

        if compile_kwargs:
            logger.info("Compiling workflow with %s", list(compile_kwargs.keys()))
            return workflow.compile(**compile_kwargs)
        else:
            logger.warning("Compiling workflow without checkpointer/store (no persistence)")
            return workflow.compile()

    def _input_type_decision(self, state: WorkflowStateDict) -> str:
        """入力タイプに基づいてルーティング（テキスト or 画像）"""
        if state.get("image_data") is not None:
            return "image"
        return "text"

    @staticmethod
    def _reception_is_active(reception_status: Optional[dict[str, Any]]) -> bool:
        if not reception_status:
            return False
        return not reception_status.get("completed") and reception_status.get("stage") not in (
            "none",
            "error",
        )

    def _has_mixed_intent_greeting(self, query: str) -> bool:
        lower_query = query.lower().strip()
        if not match_keywords(lower_query, GREETING_KEYWORDS):
            return False

        remaining = lower_query
        for keyword in sorted(GREETING_KEYWORDS, key=len, reverse=True):
            remaining = remaining.replace(keyword.lower(), " ").strip()

        remaining = remaining.strip("!！?？。、.,  ")
        return len(remaining) > 3

    def _requires_memory_loader_before_fast_path(self, query: str) -> bool:
        stripped_query = query.strip()
        lower_query = stripped_query.lower()

        if len(stripped_query) < 5:
            return True

        if any(marker in lower_query for marker in self._ANAPHORA_MARKERS):
            return True

        if self._has_mixed_intent_greeting(stripped_query):
            return True

        return RoutingLogicAgent._is_memory_related_question(self, stripped_query)

    def _get_response_language(self, query: str, fallback_language: str) -> str:
        from backend.utils.language_processor import LanguageProcessor

        language_processor = LanguageProcessor()
        language_result = language_processor.detect_language(query)
        response_language = language_processor.determine_response_language(language_result)
        return response_language or fallback_language

    async def _store_fast_path_user_message(self, session_id: str, query: str) -> None:
        if not session_id or not query:
            return

        try:
            from backend.utils.memory_helper import get_memory_helper

            memory_helper = get_memory_helper()
            await memory_helper.store_message(
                session_id=session_id,
                role="user",
                content=query,
            )
        except Exception as exc:
            logger.warning("Failed to store fast-path user message: %s", exc)

    async def _reception_check_node(self, state: WorkflowStateDict) -> dict[str, Any]:
        from backend.utils.reception_status import check_reception_status

        session_id = state.get("session_id", "")
        reception_status = await check_reception_status(session_id)
        return {"reception_status": reception_status}

    def _reception_check_decision(self, state: WorkflowStateDict) -> str:
        if self._reception_is_active(state.get("reception_status")):
            return "active_reception"
        return "no_reception"

    async def _keyword_router_node(self, state: WorkflowStateDict) -> dict[str, Any]:
        query = state.get("query", "")
        fallback_language = state.get("language", "ja")

        if self._requires_memory_loader_before_fast_path(query):
            return {"routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None}}

        response_language = self._get_response_language(query, fallback_language)
        fast_route = RoutingLogicAgent._try_fast_routing(self, query)
        if fast_route is None:
            return {
                "language": response_language,
                "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
            }

        if fast_route["category"] in self._PRE_MEMORY_INLINE_CATEGORIES:
            return {
                "language": response_language,
                "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
            }

        try:
            from backend.utils.topic_guard import check_topic_adherence

            on_topic, _ = check_topic_adherence(
                query=query,
                routing_category=fast_route["category"],
                language=response_language,
            )
            if not on_topic:
                return {
                    "language": response_language,
                    "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
                }
        except Exception as guard_err:
            logger.debug("Pre-memory topic guard skipped: %s", guard_err)

        fast_path_agent = fast_route["agent"]
        if fast_path_agent not in self._PRE_MEMORY_DIRECT_AGENTS:
            return {
                "language": response_language,
                "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
            }

        await self._store_fast_path_user_message(state.get("session_id", ""), query)

        return {
            "language": response_language,
            "routing": {
                **state.get("routing", {}),
                **fast_route,
                "pre_memory_fast_path_agent": fast_path_agent,
                "confidence": 0.9,
                "debug_info": {
                    "fast_path": True,
                    "path": "keyword_router",
                },
            },
        }

    def _keyword_router_decision(self, state: WorkflowStateDict) -> str:
        routing = state.get("routing", {})
        fast_path_agent = routing.get("pre_memory_fast_path_agent")
        if fast_path_agent in self._PRE_MEMORY_DIRECT_AGENTS:
            return cast(str, fast_path_agent)
        return "normal"

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
        from backend.utils.memory_helper import get_memory_helper

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
                # knowledge base search. EN uses CTranslate2; KO/ZH use
                # LLM-based translation via OpenRouter.
                rag_query = query
                if language == "en":
                    try:
                        from backend.services.translation_service import (
                            get_translation_service,
                        )

                        ts = get_translation_service()
                        rag_query = await ts.translate(query, "en_to_ja")
                        logger.info(
                            "tRAG en->ja: '%s' -> '%s'",
                            query[:40],
                            rag_query[:40],
                        )
                    except Exception as trans_err:
                        logger.warning(
                            "Query translation failed, using original: %s",
                            trans_err,
                        )
                elif language in ("ko", "zh"):
                    try:
                        translated = await _translate_llm_with_retry(query, language)
                        if translated and _JA_RE.search(translated):
                            rag_query = translated
                            logger.info(
                                "tRAG %s->ja: '%s' -> '%s'",
                                language,
                                query[:40],
                                rag_query[:40],
                            )
                        elif translated:
                            logger.warning(
                                "tRAG not Japanese: '%s'",
                                translated[:60],
                            )
                    except Exception as trans_err:
                        logger.warning(
                            "LLM translation (%s->ja) failed: %s",
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
                    memories = await store_with_retry(
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

    @staticmethod
    def _build_routing_payload(
        decision: OrchestratorDecision,
        *,
        agent: str,
        category: Optional[str] = None,
        request_type: Optional[str] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "agent": agent,
            "category": category or decision.category,
            "request_type": request_type or decision.request_type,
            "confidence": confidence if confidence is not None else decision.confidence,
            "reasoning": reasoning or decision.reasoning,
            "debug_info": decision.debug_info,
        }

    async def _handle_emergency(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
    ) -> Optional[Command[RoutingTarget]]:
        if decision.category != "emergency":
            return None

        from backend.utils.emergency_templates import get_emergency_response

        query = state.get("query", "")
        logger.info(
            "Inline emergency: lang=%s, query=%s",
            decision.language,
            query[:80],
        )
        result = get_emergency_response(query, decision.language)
        asyncio.create_task(self._notify_discord_emergency(query, result))
        return Command(
            goto="format_response",
            update={
                "language": decision.language,
                "routing": self._build_routing_payload(
                    decision,
                    agent="orchestrator_inline",
                    category="emergency",
                ),
                "answer": result["response"],
                "emotion": result["emotion"],
                "metadata": {
                    **state.get("metadata", {}),
                    "emergency": result["metadata"],
                },
            },
        )

    async def _handle_greeting(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
        session_id: str,
    ) -> Optional[Command[RoutingTarget]]:
        if decision.category != "greeting":
            return None

        from backend.config.routing_constants import TIME_GREETING_TEMPLATES
        from backend.utils.time_utils import get_current_time_period, get_now_jst

        query = state.get("query", "")
        lang = decision.language or "ja"
        if lang not in ("ja", "en", "zh", "ko"):
            logger.warning("Greeting: unsupported language '%s', falling back to 'ja'", lang)
            lang = "ja"
        now = get_now_jst()
        period = get_current_time_period(now.hour)
        templates = TIME_GREETING_TEMPLATES.get(period, TIME_GREETING_TEMPLATES["afternoon"])
        base_greeting = templates.get(lang, templates["ja"])

        greeting_bodies = {
            "ja": (
                "ここはエンジニアのための無料コワーキングスペースです。"
                "お気軽にご利用ください。何かお手伝いできることはありますか？"
            ),
            "en": (
                "This is a free coworking space for engineers. "
                "Feel free to make yourself at home. "
                "How can I help you?"
            ),
            "zh": ("这里是面向工程师的免费共享工作空间。请随意使用。有什么可以帮助您的吗？"),
            "ko": (
                "이곳은 엔지니어를 위한 무료 코워킹 스페이스입니다. "
                "편하게 이용해 주세요. 무엇을 도와드릴까요?"
            ),
        }
        body = greeting_bodies.get(lang, greeting_bodies["ja"])
        sep = " " if lang == "en" else ""
        greeting_msg = f"{base_greeting}{sep}{body}"

        logger.info(
            "Inline greeting: lang=%s, period=%s, query=%s",
            lang,
            period,
            query[:80],
        )
        await self._store_reception_session(
            session_id=session_id,
            stage="greeting",
            language=lang,
            metadata={"reception_action": "start_reception"},
        )

        return Command(
            goto="format_response",
            update={
                "language": lang,
                "routing": self._build_routing_payload(
                    decision,
                    agent="orchestrator_inline",
                    category="greeting",
                ),
                "answer": greeting_msg,
                "emotion": "happy",
                "metadata": {
                    **state.get("metadata", {}),
                    "agent": "reception",
                    "reception_stage": "greeting",
                    "reception_action": "start_reception",
                },
            },
        )

    async def _handle_clarification(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
    ) -> Optional[Command[RoutingTarget]]:
        if decision.category not in self._CLARIFICATION_CATEGORIES:
            return None

        from backend.utils.clarification_templates import get_clarification_response

        query = state.get("query", "")
        logger.info(
            "Inline clarification: category=%s, lang=%s, query=%s",
            decision.category,
            decision.language,
            query[:80],
        )
        result = get_clarification_response(
            category=decision.category,
            language=decision.language,
        )
        return Command(
            goto="format_response",
            update={
                "language": decision.language,
                "routing": self._build_routing_payload(
                    decision,
                    agent="orchestrator_inline",
                ),
                "answer": result["response"],
                "emotion": result["emotion"],
                "metadata": {
                    **state.get("metadata", {}),
                    "clarification": {
                        **result["metadata"],
                        "clarification_type": decision.category,
                    },
                    "requires_followup": True,
                },
            },
        )

    async def _handle_topic_guard(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
    ) -> Optional[Command[RoutingTarget]]:
        query = state.get("query", "")
        try:
            from backend.utils.topic_guard import check_topic_adherence

            on_topic, off_topic_response = check_topic_adherence(
                query=query,
                routing_category=decision.category,
                language=decision.language,
            )
        except Exception as guard_err:
            logger.debug("Topic guard skipped: %s", guard_err)
            return None

        if on_topic:
            return None

        logger.info("Off-topic query filtered: %.50s", query)
        return Command(
            goto="format_response",
            update={
                "language": decision.language,
                "routing": self._build_routing_payload(
                    decision,
                    agent="topic_guard",
                    category="off_topic",
                    request_type="redirect",
                    confidence=1.0,
                    reasoning="Query is outside Engineer Cafe scope",
                ),
                "answer": off_topic_response,
                "emotion": "neutral",
            },
        )

    async def _orchestrator_node(self, state: WorkflowStateDict) -> Command[RoutingTarget]:
        """
        オーケストレーターノード（Supervisor）

        OrchestratorAgentを使用してクエリを分析し、
        適切なエージェントにCommand patternでルーティング。
        clarification カテゴリはインラインでテンプレート応答を生成し、
        format_response に直接ルーティングする。

        Reception integration: before the LLM routing call, check if the
        session has an active (incomplete) reception flow. If so, short-circuit
        with the appropriate reception stage response.
        """
        from backend.workflows.reception_workflow import invoke_reception_subgraph
        from backend.utils.reception_status import check_reception_status

        query = state.get("query", "")
        session_id = state.get("session_id", "")

        # --- Reception status gate (before LLM call) ---
        reception_status = state.get("reception_status")
        if reception_status is None or not reception_status:
            reception_status = await check_reception_status(session_id)

        if self._reception_is_active(reception_status):
            reception_result = await invoke_reception_subgraph(
                state,
                reception_status,
                self._store_reception_session,
            )
            if reception_result.get("target_agent"):
                return Command(
                    goto=cast(RoutingTarget, reception_result["target_agent"]),
                    update={
                        "language": state.get("language", "ja"),
                        "routing": reception_result["routing"],
                        "metadata": reception_result["metadata"],
                    },
                )

            return Command(
                goto="format_response",
                update={
                    "answer": reception_result["answer"],
                    "emotion": reception_result["emotion"],
                    "metadata": reception_result["metadata"],
                },
            )

        # --- Normal orchestrator LLM routing ---
        memory_context = state.get("context", {}).get("memory")

        decision = await self.orchestrator.decide_next_agent(
            query=query,
            session_id=session_id,
            memory_context=memory_context,
        )

        for handler in (
            lambda current_state, current_decision: self._handle_emergency(
                current_state,
                current_decision,
            ),
            lambda current_state, current_decision: self._handle_greeting(
                current_state,
                current_decision,
                session_id,
            ),
            lambda current_state, current_decision: self._handle_clarification(
                current_state,
                current_decision,
            ),
            lambda current_state, current_decision: self._handle_topic_guard(
                current_state,
                current_decision,
            ),
        ):
            cmd = await handler(state, decision)
            if cmd is not None:
                return cmd

        return Command(
            goto=decision.next_agent,
            update={
                "language": decision.language,
                "routing": self._build_routing_payload(
                    decision,
                    agent=decision.next_agent,
                ),
            },
        )

    async def _business_info_node(self, state: WorkflowStateDict) -> dict:
        """営業情報ノード: 営業情報を処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        request_type = state.get("routing", {}).get("request_type")

        # Get cached knowledge results from state
        state_context = state.get("context", {}).get("knowledge_results")
        priority_signals = state.get("context", {}).get("priority_signals")
        long_term_memory = state.get("context", {}).get("long_term_memory", [])
        if long_term_memory:
            state_context = {**(state_context or {}), "long_term_memory": long_term_memory}

        result = await self._business_info_agent.answer_business_query(
            query,
            request_type,
            language,
            session_id,
            state_context=state_context,
            context_signals=priority_signals,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _farewell_node(self, state: WorkflowStateDict) -> dict:
        """退館ノード: 退館フローを処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")

        result = await self._farewell_agent.handle_farewell(
            query=query,
            language=language,
            session_id=session_id,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "happy"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _facility_node(self, state: WorkflowStateDict) -> dict:
        """施設ノード: 施設情報を処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        request_type = state.get("routing", {}).get("request_type")

        # Get cached knowledge results from state
        state_context = state.get("context", {}).get("knowledge_results")
        priority_signals = state.get("context", {}).get("priority_signals")
        long_term_memory = state.get("context", {}).get("long_term_memory", [])
        if long_term_memory:
            state_context = {**(state_context or {}), "long_term_memory": long_term_memory}

        result = await self._facility_agent.answer_facility_query(
            query,
            request_type,
            language,
            session_id,
            state_context=state_context,
            context_signals=priority_signals,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _event_node(self, state: WorkflowStateDict) -> dict:
        """イベントノード: イベント情報を処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        result = await self._event_agent.answer_event_query(query, language, session_id)

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _slide_node(self, state: WorkflowStateDict) -> dict:
        """スライドノード: スライドナレーションと質問応答を処理"""
        from backend.agents.slide_agent import SlideAction

        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "default")
        request_type = state.get("routing", {}).get("request_type", "narrate")

        # アクションマッピング
        action_map: dict[str, SlideAction] = {
            "narrate": "narrate",
            "next": "next",
            "previous": "previous",
            "goto": "goto",
            "question": "question",
        }

        slide_action: SlideAction = action_map.get(request_type, "narrate")

        result = await self._slide_agent.handle_slide_action(
            action=slide_action,
            query=query if slide_action == "question" else None,
            language=language,
            session_id=session_id,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _general_knowledge_node(self, state: WorkflowStateDict) -> dict:
        """一般知識ノード: 一般的な知識およびメモリクエリを処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        query_type = state.get("routing", {}).get("request_type", "general")
        state_context = state.get("context", {}).get("knowledge_results")
        priority_signals = state.get("context", {}).get("priority_signals")
        long_term_memory = state.get("context", {}).get("long_term_memory", [])

        result = await self._general_knowledge_agent.answer_query(
            query=query,
            language=language,
            session_id=session_id,
            query_type=query_type,
            state_context=state_context,
            context_signals=priority_signals,
            long_term_memory=long_term_memory,  # NEW
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _notify_discord_emergency(self, query: str, result: dict) -> None:
        """Discord Webhook に緊急通知を送信（fire-and-forget）"""
        try:
            from backend.services.discord_notification_service import (
                get_discord_notification_service,
            )

            svc = get_discord_notification_service()
            await svc.send_notification(
                title="緊急通報",
                message=f"来館者からの緊急メッセージ: {query}",
                severity="critical",
                metadata=result.get("metadata", {}),
            )
        except Exception:
            logger.warning("Discord emergency notification failed", exc_info=True)

    async def _format_response_node(
        self, state: WorkflowStateDict, runtime: Runtime[WorkflowContext]
    ) -> dict:
        """応答フォーマットノード: 最終的な応答をフォーマット"""
        from backend.utils.emotion_utils import strip_emotion_tags
        from backend.utils.memory_helper import get_memory_helper
        from backend.utils.message_windowing import apply_message_window
        from backend.utils.pii_scanner import scan_and_mask

        query = state.get("query", "")
        raw_answer = state.get("answer", "回答を生成できませんでした。")
        answer = strip_emotion_tags(raw_answer)
        session_id = state.get("session_id", "")
        state_metadata = state.get("metadata", {})
        state_context = state.get("context", {})
        if not isinstance(state_context, dict):
            state_context = {}

        vrm_control = None
        lipsync_data: list[dict[str, Any]] = []
        if self._character_control_agent is not None:
            try:
                audio_duration = state_context.get("audio_duration") or state_context.get(
                    "audioDuration"
                )
                vrm_control = await self._character_control_agent.process(
                    state.get("emotion") or "neutral",
                    raw_answer,
                    audio_duration=audio_duration,
                    context=state_context,
                )
                lipsync_data = vrm_control.get("keyframes", [])
            except Exception as character_error:
                logger.warning(
                    "Character control generation failed, continuing without VRM metadata: %s",
                    character_error,
                    exc_info=True,
                )

        metadata = {
            **state_metadata,
            "vrm_control": vrm_control,
            "lipsync_data": lipsync_data,
        }
        # PII Defense-in-Depth: ワークフロー層でもスキャン（API層に加えて二重防御）
        try:
            masked, pii_items = scan_and_mask(answer)
            if pii_items:
                logger.warning(
                    "PII detected in workflow output (%d items), masking",
                    len(pii_items),
                )
                answer = masked
        except Exception:
            pass  # Non-critical — API層でもスキャンするため

        # Response translation: translate JA response to EN for English users
        # zh/ko: rely on LLM's native multilingual output (LANGUAGE_INSTRUCTION)
        # CTranslate2 only supports en<->ja, so no translation for zh/ko
        language = state.get("language", "ja")
        if language == "en" and self._should_translate_answer_to_english(answer):
            try:
                from backend.services.translation_service import (
                    get_translation_service,
                )

                ts = get_translation_service()
                translated_answer = await ts.translate(answer, "ja_to_en")
                if translated_answer != answer:
                    logger.info(
                        "Translated response for lang=%s: '%s' -> '%s'",
                        language,
                        answer[:40],
                        translated_answer[:40],
                    )
                answer = translated_answer
            except Exception as trans_err:
                logger.warning(
                    "Response translation failed, using original: %s",
                    trans_err,
                )

        # アシスタント応答を保存
        try:
            memory_helper = get_memory_helper()
            await memory_helper.store_message(
                session_id=session_id,
                role="assistant",
                content=answer,
            )
        except Exception as store_error:
            logger.warning("Failed to store assistant message: %s", store_error)

        # NEW: Extract and store long-term memories
        try:
            user_id = runtime.context.user_id if runtime.context else None
            if user_id and user_id != "anonymous" and runtime.store:
                from backend.utils.memory_extractor import (
                    extract_memories,
                    extract_memory_candidates,
                )
                from backend.utils.memory_feature_flags import get_memory_feature_flags

                memory_flags = get_memory_feature_flags()
                safe_user_id = sanitize_for_postgres(user_id)
                long_term_namespace = ("visitor_memories", safe_user_id)
                candidate_namespace = ("visitor_memory_candidates", safe_user_id)

                def _is_fast_path_memory(memory: dict[str, Any]) -> bool:
                    memory_type = memory.get("candidate_type") or memory.get("type")
                    confidence = float(memory.get("confidence", 0.0) or 0.0)
                    content = str(memory.get("content", "")).strip()
                    evidence = memory.get("evidence", {})
                    evidence_query = ""
                    if isinstance(evidence, dict):
                        evidence_query = str(evidence.get("query", ""))
                    explicit_text = f"{content} {evidence_query} {query}".lower()
                    explicit_keywords = (
                        "覚えて",
                        "記憶して",
                        "忘れないで",
                        "remember",
                        "don't forget",
                        "keep in mind",
                    )

                    # Gate fast-path with the same actionable-content rule as
                    # MemoryPromoter so that empty / filler strings (e.g. "please",
                    # "ください", single characters) never reach LTM.
                    if not MemoryPromoter._has_actionable_content(memory):
                        return False

                    if memory_type == "explicit_remember":
                        return confidence >= 0.5
                    if any(keyword in explicit_text for keyword in explicit_keywords):
                        return confidence >= 0.8
                    return memory_type == "visitor_name" and confidence >= 0.9

                async def _write_long_term_memory(memory: dict[str, Any], source: str) -> None:
                    key = str(uuid.uuid4())
                    value = {
                        "data": memory.get("content", ""),
                        "type": memory.get("candidate_type") or memory.get("type", "unknown"),
                        "confidence": memory.get("confidence", 0.5),
                        "timestamp": time.time(),
                        "source": source,
                    }
                    value = sanitize_for_postgres(value)
                    await store_with_retry(
                        lambda s, k=key, v=value: s.aput(long_term_namespace, k, v),
                        store=runtime.store,
                        operation_name="long-term memory store",
                    )

                # Candidate system writes shadow candidates, while high-confidence
                # explicit facts also enter LTM immediately for cross-session recall.
                # When disabled, use legacy direct writes for backward compat.
                if memory_flags.enable_memory_candidates:
                    try:
                        candidates = extract_memory_candidates(
                            query=query,
                            answer=answer,
                            language=state.get("language", "ja"),
                        )
                        if candidates:
                            fast_path_count = 0
                            for candidate in candidates:
                                candidate_key = str(uuid.uuid4())
                                candidate_value = sanitize_for_postgres(dict(candidate))
                                await store_with_retry(
                                    lambda s, k=candidate_key, v=candidate_value: s.aput(
                                        candidate_namespace,
                                        k,
                                        v,
                                    ),
                                    store=runtime.store,
                                    operation_name="long-term memory store",
                                )
                                if _is_fast_path_memory(candidate_value):
                                    await _write_long_term_memory(
                                        candidate_value,
                                        "candidate_fast_path",
                                    )
                                    fast_path_count += 1
                            logger.info(
                                "Stored %d memory candidates for user %s",
                                len(candidates),
                                user_id,
                            )
                            if fast_path_count:
                                logger.info(
                                    "Fast-path stored %d long-term memories for user %s",
                                    fast_path_count,
                                    user_id,
                                )
                    except Exception as candidate_err:
                        logger.warning(
                            "Memory candidate write failed: %s",
                            candidate_err,
                        )
                else:
                    facts = extract_memories(query, answer, state.get("language", "ja"))
                    if facts:
                        for fact in facts:
                            await _write_long_term_memory(fact, "legacy_direct")
                        logger.info(
                            "Stored %d long-term memories for user %s",
                            len(facts),
                            user_id,
                        )

                # Promote candidates to long-term memory (best effort).
                if memory_flags.enable_memory_promotion:
                    try:
                        from backend.services.memory_promoter import (
                            get_memory_promoter,
                        )

                        promoter = get_memory_promoter()
                        promotion_stats = await promoter.promote_for_user(
                            runtime.store,
                            safe_user_id,
                            delete_promoted_candidates=False,
                        )
                        if promotion_stats.get("promoted", 0) > 0:
                            logger.info(
                                "Promoted memories for user %s: %s",
                                user_id,
                                promotion_stats,
                            )
                    except Exception as promote_err:
                        logger.warning("Memory promotion failed: %s", promote_err)
        except Exception as e:
            logger.warning("Long-term memory store failed: %s", e)

        # Message Windowing: 長セッションでのコンテキストオーバーフロー防止
        existing_msgs = state.get("messages", [])
        windowed = apply_message_window(existing_msgs)

        # 時間帯情報と閉館警告をmetadataに追加
        try:
            from backend.config.routing_constants import CLOSING_WARNING_TEMPLATES
            from backend.utils.time_utils import (
                get_current_time_period,
                get_minutes_until_closing,
                get_now_jst,
                get_today_business_hours,
                is_closing_soon,
            )

            now = get_now_jst()
            time_period = get_current_time_period(now.hour)
            metadata["time_period"] = time_period

            business_hours = get_today_business_hours(now.weekday())
            closing_warning: dict[str, object] = {"is_closing_soon": False}

            if business_hours is not None:
                _, close_time = business_hours
                closing_hour = close_time.hour
                closing_minute = close_time.minute

                if is_closing_soon(now, closing_hour, closing_minute):
                    remaining = get_minutes_until_closing(now, closing_hour, closing_minute)
                    closing_warning = {
                        "is_closing_soon": True,
                        "minutes_remaining": remaining,
                    }
                    # 応答に閉館警告を付加
                    template = CLOSING_WARNING_TEMPLATES.get(
                        language, CLOSING_WARNING_TEMPLATES["ja"]
                    )
                    warning_text = template.format(minutes=remaining)
                    answer = f"{answer}\n\n{warning_text}"

            metadata["closing_warning"] = closing_warning
        except Exception as time_err:
            logger.warning("Time period/closing warning processing failed: %s", time_err)

        return {
            "answer": answer,
            "metadata": metadata,
            "messages": windowed
            + [
                HumanMessage(content=query),
                AIMessage(content=answer),
            ],
        }

    @staticmethod
    def _should_translate_answer_to_english(answer: str) -> bool:
        """Return true only when an English turn still has Japanese text."""
        if not answer:
            return False
        return any(
            ("\u3040" <= char <= "\u30ff") or ("\u4e00" <= char <= "\u9fff") for char in answer
        )

    def _decode_image_data(self, image_data: Any) -> Any:
        """Convert base64 image string to np.ndarray for VisionAgent.

        Other types pass through unchanged.
        """
        if not isinstance(image_data, str):
            return image_data
        try:
            raw = base64.b64decode(image_data)
            arr = np.frombuffer(raw, dtype=np.uint8)
            decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return decoded if decoded is not None else image_data
        except Exception:
            return image_data

    def _prepare_state(self, input_data: dict) -> tuple[WorkflowStateDict, dict | None]:
        """ainvoke/astream共通: 入力データからstate + configを構築"""
        session_id = input_data.get("session_id", "default")
        raw_image = input_data.get("image_data")
        state: WorkflowStateDict = {
            "messages": [],
            "query": input_data.get("query", ""),
            "session_id": session_id,
            "language": input_data.get("language", "ja"),
            "routing": {},
            "answer": None,
            "emotion": None,
            "metadata": {},
            "context": input_data.get("context", {}),
            "reception_status": {},
            "image_data": self._decode_image_data(raw_image) if raw_image is not None else None,
            "ocr_result": None,
        }
        config = None
        if self.checkpointer:
            config = {"configurable": {"thread_id": session_id}}

        # Store visitor_id for context injection
        self._current_visitor_id = input_data.get("visitor_id") or session_id

        return state, config

    async def _ensure_checkpointer_ready(self, config: dict | None, session_id: str) -> None:
        """Cold-start後の切断済み接続を graph 実行前に一度だけ張り直す。"""
        if not self.checkpointer or not config:
            return

        aget_tuple = getattr(self.checkpointer, "aget_tuple", None)
        if not callable(aget_tuple):
            return

        await aget_tuple(config)

    _AGENT_NODE_MAP: dict[str, str] = {
        "facility": "_facility_node",
        "event": "_event_node",
        "slide": "_slide_node",
        "general_knowledge": "_general_knowledge_node",
        "business_info": "_business_info_node",
        "farewell": "_farewell_node",
    }

    async def ainvoke_from_reception(self, handoff: Any) -> dict:
        """Invoke an agent node directly, bypassing the orchestrator.

        Used by the autonomous reception flow after ReceptionHandoffService
        has already determined the target agent and built the workflow state.

        Args:
            handoff: A HandoffResult from ReceptionHandoffService.

        Returns:
            A dict with answer, emotion, metadata, and reception-specific fields.

        Raises:
            ValueError: If the target agent is not a known node.
        """
        target = handoff.target_agent
        node_attr = self._AGENT_NODE_MAP.get(target)
        if node_attr is None:
            raise ValueError(
                f"Unknown target agent '{target}'. Valid agents: {sorted(self._AGENT_NODE_MAP)}"
            )

        state = handoff.workflow_state
        self._current_visitor_id = state.get("session_id", "anonymous")

        agent_node = getattr(self, node_attr)
        agent_result = await agent_node(state)

        # Merge agent output into state for format_response
        merged_state = cast(WorkflowStateDict, {**state, **agent_result})

        # format_response expects Runtime context — call directly with a
        # lightweight shim since we're outside the graph execution.
        try:
            context = WorkflowContext(user_id=self._current_visitor_id)

            class _RuntimeShim:
                def __init__(self, ctx: WorkflowContext) -> None:
                    self.context = ctx
                    self.store = None  # No store available outside graph execution

            formatted = await self._format_response_node(merged_state, _RuntimeShim(context))
        except Exception:
            logger.warning("format_response failed in reception invoke, using raw agent result")
            formatted = agent_result

        result = {
            "answer": formatted.get("answer", agent_result.get("answer", "")),
            "emotion": formatted.get("emotion", agent_result.get("emotion", "neutral")),
            "metadata": formatted.get("metadata", agent_result.get("metadata", {})),
            "purpose_flow_response": handoff.purpose_flow.response_text,
            "requires_staff": handoff.requires_staff,
        }

        return result

    async def ainvoke(self, input_data: dict) -> dict:
        """ワークフローを非同期実行"""
        state, config = self._prepare_state(input_data)
        await self._ensure_checkpointer_ready(config, state["session_id"])
        visitor_id = input_data.get("visitor_id") or input_data.get("session_id", "anonymous")
        context = WorkflowContext(user_id=visitor_id)

        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(state, config=config, context=context),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Workflow timed out after 30s for session %s",
                state["session_id"],
            )
            return {
                "answer": "申し訳ございません。処理がタイムアウトしました。",
                "emotion": "neutral",
                "metadata": {"error": "Request timed out after 30 seconds"},
            }

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": result.get("metadata", {}),
        }

    async def astream(self, input_data: dict):
        """
        ストリーミング実行 - astream_events() によるイベント発行

        将来のフロントエンド SSE 対応のための基盤。
        LLMノードの中間トークンと最終結果をyieldする。

        Args:
            input_data: ainvoke() と同じ入力データ

        Yields:
            dict: {"type": "token", "content": str} or {"type": "complete", "data": dict}
        """
        state, config = self._prepare_state(input_data)
        await self._ensure_checkpointer_ready(config, state["session_id"])
        visitor_id = input_data.get("visitor_id") or input_data.get("session_id", "anonymous")
        context = WorkflowContext(user_id=visitor_id)
        event_stream = self.graph.astream_events(
            state,
            config=config,
            version="v2",
            context=context,
        )
        try:
            async for event in event_stream:
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        yield {"type": "token", "content": content}
                elif kind == "on_chain_end" and event.get("name") == "format_response":
                    yield {"type": "complete", "data": event["data"].get("output", {})}
        finally:
            # Ensure upstream async generator is closed when the client disconnects
            # or the consumer stops iteration early (SSE test path).
            aclose = getattr(event_stream, "aclose", None)
            if callable(aclose):
                try:
                    await aclose()
                except Exception:
                    logger.debug("Failed to close astream_events generator cleanly", exc_info=True)

    async def close(self):
        """リソースのクリーンアップ"""
        await self.orchestrator.close()
        if self.checkpointer:
            try:
                # AsyncPostgresSaverの適切なクローズメソッドを使用
                if hasattr(self.checkpointer, "aclose"):
                    await self.checkpointer.aclose()
                elif hasattr(self.checkpointer, "conn") and hasattr(
                    self.checkpointer.conn, "close"
                ):
                    await self.checkpointer.conn.close()
                logger.info("Checkpointer connection closed")
            except Exception as e:
                logger.warning("Error closing checkpointer: %s", e)


# シングルトンインスタンス
_workflow_instance: MainWorkflow | None = None


async def get_workflow() -> MainWorkflow:
    """
    ワークフローインスタンスを取得（非同期、スレッドセーフ）

    CheckpointerがSUPABASE_DB_URI環境変数から初期化されます。
    環境変数が設定されていない場合はCheckpointerなしで動作します。
    asyncio.Lockを使用してrace conditionを防止。
    """
    global _workflow_instance
    if _workflow_instance is None:
        async with _workflow_lock:
            # Double-check after acquiring lock
            if _workflow_instance is None:
                checkpointer = None
                store = None

                try:
                    from backend.utils.checkpointer import get_checkpointer

                    checkpointer = await get_checkpointer()
                    logger.info("Workflow initialized with AsyncPostgresSaver")
                except ValueError:
                    logger.warning("SUPABASE_DB_URI not set, running without persistence.")
                except Exception as e:
                    logger.warning("Failed to create checkpointer: %s", e)

                try:
                    from backend.utils.store import get_store

                    store = await get_store()
                    logger.info("Workflow initialized with AsyncPostgresStore")
                except ValueError:
                    logger.warning("SUPABASE_DB_URI not set, running without store.")
                except Exception as e:
                    logger.warning("Failed to create store: %s", e)

                _workflow_instance = MainWorkflow(checkpointer=checkpointer, store=store)
    return _workflow_instance


def get_workflow_sync() -> MainWorkflow:
    """
    ワークフローインスタンスを同期的に取得（テスト用/レガシー互換）

    注意: Checkpointerなしで動作します。本番環境では get_workflow() を使用してください。
    """
    global _workflow_instance
    if _workflow_instance is None:
        logger.warning("Using sync workflow without checkpointer")
        _workflow_instance = MainWorkflow(checkpointer=None)
    return _workflow_instance


def reset_workflow() -> None:
    """ワークフローインスタンスをリセット（テスト用）"""
    global _workflow_instance
    _workflow_instance = None
