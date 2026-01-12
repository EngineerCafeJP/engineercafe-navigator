"""
メインLangGraphワークフロー
既存のMastraエージェントのロジックをPython版LangGraphで実装
"""

from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import operator

from backend.agents.router_agent import RouterAgent


class WorkflowState(TypedDict):
    """ワークフローの状態定義"""

    messages: Annotated[list[BaseMessage], operator.add]
    query: str
    session_id: str
    language: str
    routed_to: str | None
    answer: str | None
    emotion: str | None
    metadata: dict
    context: dict


class MainWorkflow:
    """メインLangGraphワークフロー"""

    def __init__(self):
        self.router_agent = RouterAgent(debug_mode=True)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """グラフ構造を構築"""
        workflow = StateGraph(WorkflowState)

        # ノードの追加
        workflow.add_node("memory", self._memory_node)
        workflow.add_node("router", self._router_node)
        workflow.add_node("clarification", self._clarification_node)
        workflow.add_node("business_info", self._business_info_node)
        workflow.add_node("facility", self._facility_node)
        workflow.add_node("event", self._event_node)
        workflow.add_node("general_knowledge", self._general_knowledge_node)
        workflow.add_node("format_response", self._format_response_node)

        # エッジの定義
        workflow.add_edge(START, "memory")
        workflow.add_edge("memory", "router")

        # 条件付きルーティング
        workflow.add_conditional_edges(
            "router",
            self._route_decision,
            {
                "clarification": "clarification",
                "business_info": "business_info",
                "facility": "facility",
                "event": "event",
                "general_knowledge": "general_knowledge",
            },
        )

        # すべてのエージェントノードからformat_responseへ
        workflow.add_edge("clarification", "format_response")
        workflow.add_edge("business_info", "format_response")
        workflow.add_edge("facility", "format_response")
        workflow.add_edge("event", "format_response")
        workflow.add_edge("general_knowledge", "format_response")

        workflow.add_edge("format_response", END)

        return workflow.compile()

    def _memory_node(self, state: WorkflowState) -> dict:
        """メモリノード: 会話履歴とコンテキストを取得"""
        # TODO: メモリシステムの実装
        return {"context": {**state.get("context", {}), "memory": {}}}

    async def _router_node(self, state: WorkflowState) -> dict:
        """ルーターノード: クエリを適切なエージェントにルーティング"""
        query = state.get("query", "")
        session_id = state.get("session_id", "")

        # RouterAgentでルーティング
        route_result = await self.router_agent.route_query(
            query=query, session_id=session_id, memory_system=None
        )

        # エージェント名をノード名にマッピング
        agent_to_node = {
            "BusinessInfoAgent": "business_info",
            "FacilityAgent": "facility",
            "EventAgent": "event",
            "MemoryAgent": "general_knowledge",  # Memory未実装時はgeneral_knowledgeへ
            "GeneralKnowledgeAgent": "general_knowledge",
            "ClarificationAgent": "clarification",
            "TimeAgent": "general_knowledge",  # Time未実装時はgeneral_knowledgeへ
        }

        routed_to = agent_to_node.get(route_result.agent, "general_knowledge")

        return {
            "routed_to": routed_to,
            "language": route_result.language,
            "metadata": {
                **state.get("metadata", {}),
                "routing": {
                    "agent": route_result.agent,
                    "category": route_result.category,
                    "request_type": route_result.request_type,
                    "confidence": route_result.confidence,
                    "debug_info": route_result.debug_info,
                },
            },
        }

    def _route_decision(
        self, state: WorkflowState
    ) -> Literal["clarification", "business_info", "facility", "event", "general_knowledge"]:
        """ルーティング決定"""
        return state.get("routed_to", "general_knowledge")

    def _clarification_node(self, state: WorkflowState) -> dict:
        """明確化ノード: 曖昧なクエリを明確化"""
        # TODO: 明確化エージェントの実装
        return {"answer": "もう少し詳しく教えていただけますか？", "emotion": "neutral"}

    def _business_info_node(self, state: WorkflowState) -> dict:
        """営業情報ノード: 営業情報を処理"""
        # TODO: 営業情報エージェントの実装
        return {"answer": "営業情報の取得中です。", "emotion": "neutral"}

    def _facility_node(self, state: WorkflowState) -> dict:
        """施設ノード: 施設情報を処理"""
        # TODO: 施設エージェントの実装
        return {"answer": "施設情報の取得中です。", "emotion": "neutral"}

    def _event_node(self, state: WorkflowState) -> dict:
        """イベントノード: イベント情報を処理"""
        # TODO: イベントエージェントの実装
        return {"answer": "イベント情報の取得中です。", "emotion": "neutral"}

    def _general_knowledge_node(self, state: WorkflowState) -> dict:
        """一般知識ノード: 一般的な知識を処理"""
        # TODO: 一般知識エージェントの実装
        return {"answer": "情報の取得中です。", "emotion": "neutral"}

    def _format_response_node(self, state: WorkflowState) -> dict:
        """応答フォーマットノード: 最終的な応答をフォーマット"""
        query = state.get("query", "")
        answer = state.get("answer", "回答を生成できませんでした。")

        return {
            "messages": [
                *state.get("messages", []),
                HumanMessage(content=query),
                AIMessage(content=answer),
            ]
        }

    async def ainvoke(self, input_data: dict) -> dict:
        """ワークフローを非同期実行"""
        state: WorkflowState = {
            "messages": [],
            "query": input_data.get("query", ""),
            "session_id": input_data.get("session_id", ""),
            "language": input_data.get("language", "ja"),
            "routed_to": None,
            "answer": None,
            "emotion": None,
            "metadata": {},
            "context": input_data.get("context", {}),
        }

        result = await self.graph.ainvoke(state)

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": result.get("metadata", {}),
        }


# シングルトンインスタンス
_workflow_instance: MainWorkflow | None = None


def get_workflow() -> MainWorkflow:
    """ワークフローインスタンスを取得"""
    global _workflow_instance
    if _workflow_instance is None:
        _workflow_instance = MainWorkflow()
    return _workflow_instance
