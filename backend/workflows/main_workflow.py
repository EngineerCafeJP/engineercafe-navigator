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
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, RetryPolicy

from backend.agents.orchestrator_agent import (
    OrchestratorAgent,
    RoutingTarget,
)

logger = logging.getLogger(__name__)

# 非同期シングルトン用ロック
_workflow_lock = asyncio.Lock()


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
    image_data: Optional[Any]  # np.ndarray (optional vision input)
    ocr_result: Optional[dict]  # OCR result from VisionAgent


class MainWorkflow:
    """
    メインLangGraphワークフロー - Supervisor Patternによるマルチエージェント制御

    アーキテクチャ:
    - OrchestratorAgent (Supervisor): クエリを分析し、適切なエージェントを選択
    - 各エージェント: 専門領域の処理を行い、結果をOrchestratorに返す
    - Command pattern: 明示的な制御フローでルーティング
    - AsyncPostgresSaver: 会話状態の永続化
    """

    def __init__(self, checkpointer=None):
        # debug_modeは環境変数で制御（本番ではFalse推奨）
        debug_mode = os.getenv("ORCHESTRATOR_DEBUG_MODE", "false").lower() == "true"
        self.orchestrator = OrchestratorAgent(debug_mode=debug_mode)
        self.checkpointer = checkpointer

        # 全エージェントをシングルトンインスタンスとして保持
        from backend.agents.business_info_agent import BusinessInfoAgent
        from backend.agents.event_agent import EventAgent
        from backend.agents.facility_agent import FacilityAgent
        from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
        from backend.agents.slide_agent import SlideAgent

        self._business_info_agent = BusinessInfoAgent()
        self._facility_agent = FacilityAgent()
        self._event_agent = EventAgent()
        self._slide_agent = SlideAgent()

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

    # LLMノード用リトライポリシー: 一時的な障害(レート制限, タイムアウト等)に対応
    LLM_RETRY_POLICY = RetryPolicy(
        initial_interval=1.0,
        backoff_factor=2.0,
        max_interval=10.0,
        max_attempts=3,
    )

    def _build_graph(self) -> StateGraph:
        """Supervisor Patternに基づくグラフ構造を構築"""
        workflow = StateGraph(WorkflowStateDict)

        # LLM依存ノード: retry_policyを適用
        llm_retry = self.LLM_RETRY_POLICY

        # ノードの追加
        # memory_loader, format_response: LLM非依存のためリトライ不要
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

        # エッジの定義（Supervisor Pattern）
        # START → (text: memory_loader, image: vision) → memory_loader → orchestrator
        workflow.add_conditional_edges(
            START,
            self._input_type_decision,
            {
                "text": "memory_loader",
                "image": "vision",
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
        workflow.add_edge("format_response", END)

        # Checkpointerが指定されている場合は永続化を有効化
        if self.checkpointer:
            logger.info("Compiling workflow with checkpointer for persistence")
            return workflow.compile(checkpointer=self.checkpointer)
        else:
            logger.warning("Compiling workflow without checkpointer (no persistence)")
            return workflow.compile()

    def _input_type_decision(self, state: WorkflowStateDict) -> str:
        """入力タイプに基づいてルーティング（テキスト or 画像）"""
        if state.get("image_data") is not None:
            return "image"
        return "text"

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

    async def _memory_loader_node(self, state: WorkflowStateDict) -> dict:
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

                classifier = QueryClassifier()
                classification = await classifier.classify_with_details(query)
                category = (
                    classification.category if hasattr(classification, "category") else "general"
                )

                rag = EnhancedRAGSearch()
                rag_result = await rag.search(
                    query=query, category=category, language=language, max_results=10
                )

                knowledge_results = {
                    "success": rag_result.get("success", False),
                    "results": rag_result.get("data", {}).get("results", []),
                    "context_string": rag_result.get("data", {}).get("context", ""),
                    "category": category,
                    "query": query,
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

            return {
                "context": {
                    **state.get("context", {}),
                    "memory": memory_context,
                    "knowledge_results": knowledge_results,
                    "priority_signals": priority_signals,
                }
            }
        except Exception as e:
            logger.warning("Memory loading failed: %s", e)
            return {"context": {**state.get("context", {}), "memory": {}}}

    async def _orchestrator_node(self, state: WorkflowStateDict) -> Command[RoutingTarget]:
        """
        オーケストレーターノード（Supervisor）

        OrchestratorAgentを使用してクエリを分析し、
        適切なエージェントにCommand patternでルーティング。
        clarification カテゴリはインラインでテンプレート応答を生成し、
        format_response に直接ルーティングする。
        """
        from backend.utils.clarification_templates import get_clarification_response

        query = state.get("query", "")
        session_id = state.get("session_id", "")
        memory_context = state.get("context", {}).get("memory")

        decision = await self.orchestrator.decide_next_agent(
            query=query,
            session_id=session_id,
            memory_context=memory_context,
        )

        # clarification カテゴリをインライン処理
        if decision.category in (
            "cafe-clarification-needed",
            "meeting-room-clarification-needed",
            "general-clarification-needed",
        ):
            result = get_clarification_response(
                category=decision.category,
                language=decision.language,
            )
            return Command(
                goto="format_response",
                update={
                    "language": decision.language,
                    "routing": {
                        "agent": "orchestrator_inline",
                        "category": decision.category,
                        "request_type": decision.request_type,
                        "confidence": decision.confidence,
                        "reasoning": decision.reasoning,
                        "debug_info": decision.debug_info,
                    },
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

        # Topic adherence ガードレール: 明確にoff-topicなクエリをフィルタ
        try:
            from backend.utils.topic_guard import check_topic_adherence

            on_topic, off_topic_response = check_topic_adherence(
                query=query,
                routing_category=decision.category,
                language=decision.language,
            )
            if not on_topic:
                logger.info("Off-topic query filtered: %.50s", query)
                return Command(
                    goto="format_response",
                    update={
                        "language": decision.language,
                        "routing": {
                            "agent": "topic_guard",
                            "category": "off_topic",
                            "request_type": "redirect",
                            "confidence": 1.0,
                            "reasoning": "Query is outside Engineer Cafe scope",
                            "debug_info": decision.debug_info,
                        },
                        "answer": off_topic_response,
                        "emotion": "neutral",
                    },
                )
        except Exception as guard_err:
            logger.debug("Topic guard skipped: %s", guard_err)

        return Command(
            goto=decision.next_agent,
            update={
                "language": decision.language,
                "routing": {
                    "agent": decision.next_agent,
                    "category": decision.category,
                    "request_type": decision.request_type,
                    "confidence": decision.confidence,
                    "reasoning": decision.reasoning,
                    "debug_info": decision.debug_info,
                },
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

    async def _facility_node(self, state: WorkflowStateDict) -> dict:
        """施設ノード: 施設情報を処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        request_type = state.get("routing", {}).get("request_type")

        # Get cached knowledge results from state
        state_context = state.get("context", {}).get("knowledge_results")
        priority_signals = state.get("context", {}).get("priority_signals")

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

        result = await self._general_knowledge_agent.answer_query(
            query=query,
            language=language,
            session_id=session_id,
            query_type=query_type,
            state_context=state_context,
            context_signals=priority_signals,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _format_response_node(self, state: WorkflowStateDict) -> dict:
        """応答フォーマットノード: 最終的な応答をフォーマット"""
        from backend.utils.emotion_utils import strip_emotion_tags
        from backend.utils.memory_helper import get_memory_helper
        from backend.utils.message_windowing import apply_message_window
        from backend.utils.pii_scanner import scan_and_mask

        query = state.get("query", "")
        raw_answer = state.get("answer", "回答を生成できませんでした。")
        answer = strip_emotion_tags(raw_answer)
        session_id = state.get("session_id", "")

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

        # Message Windowing: 長セッションでのコンテキストオーバーフロー防止
        existing_msgs = state.get("messages", [])
        windowed = apply_message_window(existing_msgs)

        return {
            "messages": windowed
            + [
                HumanMessage(content=query),
                AIMessage(content=answer),
            ]
        }

    def _prepare_state(self, input_data: dict) -> tuple[WorkflowStateDict, dict | None]:
        """ainvoke/astream共通: 入力データからstate + configを構築"""
        session_id = input_data.get("session_id", "default")
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
            "image_data": input_data.get("image_data"),
            "ocr_result": None,
        }
        config = None
        if self.checkpointer:
            config = {"configurable": {"thread_id": session_id}}
        return state, config

    async def ainvoke(self, input_data: dict) -> dict:
        """ワークフローを非同期実行"""
        state, config = self._prepare_state(input_data)
        result = await self.graph.ainvoke(state, config=config)

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

        async for event in self.graph.astream_events(state, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield {"type": "token", "content": content}
            elif kind == "on_chain_end" and event.get("name") == "format_response":
                yield {"type": "complete", "data": event["data"].get("output", {})}

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
                try:
                    from backend.utils.checkpointer import create_checkpointer

                    checkpointer = await create_checkpointer()
                    logger.info("Workflow initialized with AsyncPostgresSaver")
                except ValueError:
                    logger.warning(
                        "SUPABASE_DB_URI not set, running without persistence. "
                        "Set SUPABASE_DB_URI for production use."
                    )
                except Exception as e:
                    logger.warning("Failed to create checkpointer: %s", e)

                _workflow_instance = MainWorkflow(checkpointer=checkpointer)
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
