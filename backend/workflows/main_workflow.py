"""
メインLangGraphワークフロー - Supervisor Pattern 実装

LangGraphのSupervisor Agentパターンに従い、OrchestratorAgentが
マルチエージェントシステムを動的に制御する。

参考:
- https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- https://langchain-ai.github.io/langgraph/concepts/persistence/
"""

import asyncio
import logging
import os
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from backend.agents.character_control_agent import CharacterControlAgent
from backend.agents import orchestrator_agent as _orchestrator_agent
from backend.services import memory_promoter as _memory_promoter
from backend.utils import postgres_sanitizer as _postgres_sanitizer
from backend.utils import store as _store_utils
from backend.workflows.main import evidence as _workflow_evidence
from backend.workflows.main.agent_nodes import AgentNodesWorkflowMixin
from backend.workflows.main.memory import MemoryWorkflowMixin
from backend.workflows.main.orchestration import OrchestrationWorkflowMixin
from backend.workflows.main.response import ResponseWorkflowMixin
from backend.workflows.main.routing import RoutingWorkflowMixin
from backend.workflows.main.types import WorkflowContext, WorkflowStateDict

logger = logging.getLogger(__name__)

OrchestratorAgent = _orchestrator_agent.OrchestratorAgent
OrchestratorDecision = _orchestrator_agent.OrchestratorDecision
RoutingTarget = _orchestrator_agent.RoutingTarget
RoutingLogicAgent = _orchestrator_agent.OrchestratorAgent
MemoryPromoter = _memory_promoter.MemoryPromoter
sanitize_for_postgres = _postgres_sanitizer.sanitize_for_postgres
store_with_retry = _store_utils.store_with_retry

RAG_EVIDENCE_MAX_CONTEXT_CHARS = _workflow_evidence.RAG_EVIDENCE_MAX_CONTEXT_CHARS
RAG_EVIDENCE_MAX_CONTEXT_STRING_CHARS = _workflow_evidence.RAG_EVIDENCE_MAX_CONTEXT_STRING_CHARS
RAG_EVIDENCE_MAX_CONTEXTS = _workflow_evidence.RAG_EVIDENCE_MAX_CONTEXTS
_BOOLEAN_FALSE_VALUES = _workflow_evidence._BOOLEAN_FALSE_VALUES
_BOOLEAN_TRUE_VALUES = _workflow_evidence._BOOLEAN_TRUE_VALUES
_HALLUCINATION_CAUTION_RE = _workflow_evidence._HALLUCINATION_CAUTION_RE
_HALLUCINATION_CONCRETE_CLAIM_RE = _workflow_evidence._HALLUCINATION_CONCRETE_CLAIM_RE
_JA_RE = _workflow_evidence._JA_RE
_TRAG_CJK_RE = _workflow_evidence._TRAG_CJK_RE
_TRAG_DISALLOWED_SCRIPT_RE = _workflow_evidence._TRAG_DISALLOWED_SCRIPT_RE
_TRAG_JA_KANJI_TERMS = _workflow_evidence._TRAG_JA_KANJI_TERMS
_TRAG_PREAMBLE_RE = _workflow_evidence._TRAG_PREAMBLE_RE
_TRAG_REPEAT_PUNCT_RE = _workflow_evidence._TRAG_REPEAT_PUNCT_RE
_build_agent_response_evidence_metadata = _workflow_evidence._build_agent_response_evidence_metadata
_build_rag_evidence_metadata = _workflow_evidence._build_rag_evidence_metadata
_clean_trag_translation = _workflow_evidence._clean_trag_translation
_clip_evidence_text = _workflow_evidence._clip_evidence_text
_coerce_optional_bool = _workflow_evidence._coerce_optional_bool
_detect_hallucination_flag = _workflow_evidence._detect_hallucination_flag
_get_trag_client = _workflow_evidence._get_trag_client
_is_acceptable_trag_japanese = _workflow_evidence._is_acceptable_trag_japanese
_is_pathological_translation = _workflow_evidence._is_pathological_translation
_is_static_source_backed_response = _workflow_evidence._is_static_source_backed_response
_merge_rag_evidence_metadata = _workflow_evidence._merge_rag_evidence_metadata
_metadata_sources = _workflow_evidence._metadata_sources
_rag_evidence_result = _workflow_evidence._rag_evidence_result
_truthy_context_flag = _workflow_evidence._truthy_context_flag

# 非同期シングルトン用ロック
_workflow_lock = asyncio.Lock()
_workflow_lock_loop: asyncio.AbstractEventLoop | None = None


async def _translate_llm_with_retry(
    query: str,
    language: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
) -> str:
    """Translate non-Japanese tRAG query to JA via OpenRouter with exponential backoff."""
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
                return _clean_trag_translation(translated)
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


class MainWorkflow(
    RoutingWorkflowMixin,
    MemoryWorkflowMixin,
    OrchestrationWorkflowMixin,
    AgentNodesWorkflowMixin,
    ResponseWorkflowMixin,
):
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
    _MEMORY_CONTEXT_QUERY_MARKERS = (
        "覚えていますか",
        "覚えてますか",
        "覚えている",
        "覚えて",
        "前回",
        "前に",
        "以前",
        "この会話",
        "最初に伝えた",
        "希望席",
        "好きな席",
        "利用目的",
        "目的を確認",
        "名前を覚え",
        "名前を知っていますか",
        "do you remember",
        "previously",
        "last time",
        "my preference",
        "my name",
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


_workflow_instance: MainWorkflow | None = None
_workflow_loop: asyncio.AbstractEventLoop | None = None


def _get_workflow_lock() -> asyncio.Lock:
    """Return a lock bound to the current event loop."""
    global _workflow_lock, _workflow_lock_loop

    loop = asyncio.get_running_loop()
    if _workflow_lock_loop is not loop:
        _workflow_lock = asyncio.Lock()
        _workflow_lock_loop = loop
    return _workflow_lock


async def _discard_workflow_instance(reason: str) -> None:
    """Drop the cached workflow, best-effort closing loop-bound resources."""
    global _workflow_instance, _workflow_loop

    workflow = _workflow_instance
    workflow_loop = _workflow_loop
    _workflow_instance = None
    _workflow_loop = None
    if workflow is None:
        return
    if workflow_loop is not None and workflow_loop is not asyncio.get_running_loop():
        logger.warning("Discarding workflow without close because %s", reason)
        return
    try:
        await workflow.close()
    except Exception:
        logger.warning("Error closing workflow while discarding it: %s", reason, exc_info=True)


async def get_workflow() -> MainWorkflow:
    """
    ワークフローインスタンスを取得（非同期、スレッドセーフ）

    CheckpointerがSUPABASE_DB_URI環境変数から初期化されます。
    環境変数が設定されていない場合はCheckpointerなしで動作します。
    asyncio.Lockを使用してrace conditionを防止。
    """
    global _workflow_instance, _workflow_loop
    loop = asyncio.get_running_loop()
    if _workflow_instance is not None and _workflow_loop is not loop:
        logger.warning("Workflow event loop changed; recreating singleton instance")
        await _discard_workflow_instance("event loop changed")

    if _workflow_instance is None:
        async with _get_workflow_lock():
            loop = asyncio.get_running_loop()
            if _workflow_instance is not None and _workflow_loop is not loop:
                logger.warning("Workflow event loop changed while waiting; recreating")
                await _discard_workflow_instance("event loop changed while waiting")
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
                _workflow_loop = loop
    return _workflow_instance


def get_workflow_sync() -> MainWorkflow:
    """
    ワークフローインスタンスを同期的に取得（テスト用/レガシー互換）

    注意: Checkpointerなしで動作します。本番環境では get_workflow() を使用してください。
    """
    global _workflow_instance, _workflow_loop
    if _workflow_instance is None:
        logger.warning("Using sync workflow without checkpointer")
        _workflow_instance = MainWorkflow(checkpointer=None)
        _workflow_loop = None
    return _workflow_instance


def reset_workflow() -> None:
    """ワークフローインスタンスをリセット（テスト用）"""
    global _workflow_instance, _workflow_loop
    _workflow_instance = None
    _workflow_loop = None
