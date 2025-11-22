"""
メインLangGraphワークフロー
既存のMastraエージェントのロジックをPython版LangGraphで実装
"""

from typing import Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage

# WorkflowStateはmodels/types.pyからインポート
from models.types import WorkflowState


class MainWorkflow:
    """メインLangGraphワークフロー"""
    
    def __init__(self):
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
            }
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
        return {
            "context": {
                **state.get("context", {}),
                "memory": {}
            }
        }
    
    def _router_node(self, state: WorkflowState) -> dict:
        """ルーターノード: クエリを適切なエージェントにルーティング"""
        # TODO: ルーターエージェントの実装
        query = state.get("query", "").lower()
        
        if any(keyword in query for keyword in ["営業", "時間", "料金", "場所"]):
            routed_to = "business_info"
        elif any(keyword in query for keyword in ["設備", "施設", "wifi", "wi-fi"]):
            routed_to = "facility"
        elif any(keyword in query for keyword in ["イベント", "カレンダー", "予約"]):
            routed_to = "event"
        elif any(keyword in query for keyword in ["?", "？", "どちら", "どっち"]):
            routed_to = "clarification"
        else:
            routed_to = "general_knowledge"
        
        return {
            "routed_to": routed_to,
            "metadata": {
                **state.get("metadata", {}),
                "routing": {"routed_to": routed_to}
            }
        }
    
    def _route_decision(self, state: WorkflowState) -> Literal[
        "clarification", "business_info", "facility", "event", "general_knowledge"
    ]:
        """ルーティング決定"""
        return state.get("routed_to", "general_knowledge")
    
    def _clarification_node(self, state: WorkflowState) -> dict:
        """明確化ノード: 曖昧なクエリを明確化"""
        # TODO: 明確化エージェントの実装
        return {
            "answer": "もう少し詳しく教えていただけますか？",
            "emotion": "neutral"
        }
    
    def _business_info_node(self, state: WorkflowState) -> dict:
        """営業情報ノード: 営業情報を処理"""
        # TODO: 営業情報エージェントの実装
        return {
            "answer": "営業情報の取得中です。",
            "emotion": "neutral"
        }
    
    def _facility_node(self, state: WorkflowState) -> dict:
        """施設ノード: 施設情報を処理"""
        # TODO: 施設エージェントの実装
        return {
            "answer": "施設情報の取得中です。",
            "emotion": "neutral"
        }
    
    def _event_node(self, state: WorkflowState) -> dict:
        """イベントノード: イベント情報を処理"""
        # TODO: イベントエージェントの実装
        return {
            "answer": "イベント情報の取得中です。",
            "emotion": "neutral"
        }
    
    def _general_knowledge_node(self, state: WorkflowState) -> dict:
        """一般知識ノード: 一般的な知識を処理"""
        # TODO: 一般知識エージェントの実装
        return {
            "answer": "情報の取得中です。",
            "emotion": "neutral"
        }
    
    def _format_response_node(self, state: WorkflowState) -> dict:
        """応答フォーマットノード: 最終的な応答をフォーマット"""
        query = state.get("query", "")
        answer = state.get("answer", "回答を生成できませんでした。")
        
        return {
            "messages": [
                *state.get("messages", []),
                HumanMessage(content=query),
                AIMessage(content=answer)
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
            "context": input_data.get("context", {})
        }
        
        result = await self.graph.ainvoke(state)
        
        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": result.get("metadata", {})
        }


# シングルトンインスタンス
_workflow_instance: MainWorkflow | None = None


def get_workflow() -> MainWorkflow:
    """ワークフローインスタンスを取得"""
    global _workflow_instance
    if _workflow_instance is None:
        _workflow_instance = MainWorkflow()
    return _workflow_instance

