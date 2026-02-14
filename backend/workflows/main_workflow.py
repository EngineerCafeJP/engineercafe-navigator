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
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

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

        # SlideAgentをシングルトンインスタンスとして保持
        from backend.agents.slide_agent import SlideAgent
        self._slide_agent = SlideAgent()

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Supervisor Patternに基づくグラフ構造を構築"""
        workflow = StateGraph(WorkflowStateDict)

        # ノードの追加
        workflow.add_node("memory_loader", self._memory_loader_node)
        workflow.add_node("orchestrator", self._orchestrator_node)
        workflow.add_node("business_info", self._business_info_node)
        workflow.add_node("facility", self._facility_node)
        workflow.add_node("event", self._event_node)
        workflow.add_node("slide", self._slide_node)
        workflow.add_node("general_knowledge", self._general_knowledge_node)
        workflow.add_node("memory_agent", self._memory_agent_node)
        workflow.add_node("clarification", self._clarification_node)
        workflow.add_node("format_response", self._format_response_node)

        # エッジの定義（Supervisor Pattern）
        # START → memory_loader → orchestrator
        workflow.add_edge(START, "memory_loader")
        workflow.add_edge("memory_loader", "orchestrator")

        # 各エージェント → format_response → END
        workflow.add_edge("business_info", "format_response")
        workflow.add_edge("facility", "format_response")
        workflow.add_edge("event", "format_response")
        workflow.add_edge("slide", "format_response")
        workflow.add_edge("general_knowledge", "format_response")
        workflow.add_edge("memory_agent", "format_response")
        workflow.add_edge("clarification", "format_response")
        workflow.add_edge("format_response", END)

        # Checkpointerが指定されている場合は永続化を有効化
        if self.checkpointer:
            logger.info("Compiling workflow with checkpointer for persistence")
            return workflow.compile(checkpointer=self.checkpointer)
        else:
            logger.warning("Compiling workflow without checkpointer (no persistence)")
            return workflow.compile()

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
                    logger.warning(f"Failed to store user message: {store_error}")

            return {
                "context": {
                    **state.get("context", {}),
                    "memory": memory_context,
                }
            }
        except Exception as e:
            logger.warning(f"Memory loading failed: {e}")
            return {"context": {**state.get("context", {}), "memory": {}}}

    async def _orchestrator_node(
        self, state: WorkflowStateDict
    ) -> Command[RoutingTarget]:
        """
        オーケストレーターノード（Supervisor）

        OrchestratorAgentを使用してクエリを分析し、
        適切なエージェントにCommand patternでルーティング。
        """
        query = state.get("query", "")
        session_id = state.get("session_id", "")
        memory_context = state.get("context", {}).get("memory")

        decision = await self.orchestrator.decide_next_agent(
            query=query,
            session_id=session_id,
            memory_context=memory_context,
        )

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
        from backend.agents.business_info_agent import BusinessInfoAgent

        agent = BusinessInfoAgent()
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        request_type = state.get("routing", {}).get("request_type")

        result = await agent.answer_business_query(
            query, request_type, language, session_id
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _facility_node(self, state: WorkflowStateDict) -> dict:
        """施設ノード: 施設情報を処理"""
        from backend.agents.facility_agent import FacilityAgent

        agent = FacilityAgent()
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        request_type = state.get("routing", {}).get("request_type")

        result = await agent.answer_facility_query(
            query, request_type, language, session_id
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _event_node(self, state: WorkflowStateDict) -> dict:
        """イベントノード: イベント情報を処理"""
        from backend.agents.event_agent import EventAgent

        agent = EventAgent()
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")

        result = await agent.answer_event_query(query, language, session_id)

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _slide_node(self, state: WorkflowStateDict) -> dict:
        """スライドノード: スライドナレーションと質問応答を処理"""
        from backend.agents.slide_agent import SlideAction

        # シングルトンインスタンスを使用
        agent = self._slide_agent
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

        result = await agent.handle_slide_action(
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
        """一般知識ノード: 一般的な知識を処理"""
        from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

        agent = GeneralKnowledgeAgent()
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")

        result = await agent.answer_general_query(query, language, session_id)

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _memory_agent_node(self, state: WorkflowStateDict) -> dict:
        """
        メモリエージェントノード: 会話履歴に関する質問に回答

        「さっき何を聞いた？」「前に話したことを覚えてる？」などの
        メモリ関連の質問に対してMemoryAgentが回答を生成する。
        """
        from backend.agents.memory_agent import MemoryAgent
        from backend.utils.memory_helper import get_memory_helper

        agent = MemoryAgent(memory_system=get_memory_helper())
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")

        result = await agent.process_memory_query(query, session_id, language)

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _clarification_node(self, state: WorkflowStateDict) -> dict:
        """明確化ノード: 曖昧なクエリを明確化"""
        from backend.agents.clarification_agent import ClarificationAgent

        agent = ClarificationAgent()
        query = state.get("query", "")
        language = state.get("language", "ja")
        category = state.get("routing", {}).get("category", "general-clarification-needed")

        # categoryがclarification系でない場合はデフォルトにフォールバック
        if category not in [
            "cafe-clarification-needed",
            "meeting-room-clarification-needed",
            "general-clarification-needed",
        ]:
            category = "general-clarification-needed"

        result = await agent.handle_clarification(
            query=query,
            category=category,
            language=language,
        )

        return {
            "answer": result["response"],
            "emotion": result["emotion"],
            "metadata": {
                **state.get("metadata", {}),
                "clarification": {
                    **result["metadata"],
                    "clarification_type": category,
                },
                "requires_followup": True,
            },
        }

    async def _format_response_node(self, state: WorkflowStateDict) -> dict:
        """応答フォーマットノード: 最終的な応答をフォーマット"""
        from backend.utils.memory_helper import get_memory_helper

        query = state.get("query", "")
        answer = state.get("answer", "回答を生成できませんでした。")
        session_id = state.get("session_id", "")

        # アシスタント応答を保存
        try:
            memory_helper = get_memory_helper()
            await memory_helper.store_message(
                session_id=session_id,
                role="assistant",
                content=answer,
            )
        except Exception as store_error:
            logger.warning(f"Failed to store assistant message: {store_error}")

        return {
            "messages": [
                HumanMessage(content=query),
                AIMessage(content=answer),
            ]
        }

    async def ainvoke(self, input_data: dict) -> dict:
        """ワークフローを非同期実行"""
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
        }

        # Checkpointer使用時はthread_idを設定してセッション分離
        config = None
        if self.checkpointer:
            config = {"configurable": {"thread_id": session_id}}

        result = await self.graph.ainvoke(state, config=config)

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": result.get("metadata", {}),
        }

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
                logger.warning(f"Error closing checkpointer: {e}")


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
                    logger.warning(f"Failed to create checkpointer: {e}")

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
