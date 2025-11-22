"""
共通型定義
"""

from typing import TypedDict, Literal, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage
import operator

# サポート言語
SupportedLanguage = Literal["ja", "en"]

# ワークフロー状態
class WorkflowState(TypedDict):
    """LangGraphワークフローの状態定義"""
    messages: Annotated[list[BaseMessage], operator.add]
    query: str
    session_id: str
    language: SupportedLanguage  # "ja" または "en"
    routed_to: Optional[str]
    answer: Optional[str]
    emotion: Optional[str]
    metadata: Dict[str, Any]
    context: Dict[str, Any]


# 統一エージェント応答
class UnifiedAgentResponse(TypedDict):
    """統一されたエージェント応答形式"""
    answer: str
    emotion: Optional[str]
    metadata: Dict[str, Any]


# ルーティング結果
class RouteResult(TypedDict):
    """ルーティング結果"""
    agent: str
    category: str
    request_type: Optional[str]
    language: SupportedLanguage
    confidence: float
    debug_info: Dict[str, Any]


# クエリ分類
class QueryClassification(TypedDict):
    """クエリ分類結果"""
    category: str
    request_type: Optional[str]
    confidence: float
    debug_info: Dict[str, Any]

