"""Shared workflow state and runtime context types."""

from dataclasses import dataclass
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


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
