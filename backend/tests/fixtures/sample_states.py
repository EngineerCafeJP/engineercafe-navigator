"""Sample WorkflowStateDict instances for testing."""

from typing import Optional, Dict, Any, List
import numpy as np


def create_text_query_state(
    query: str = "営業時間は？",
    session_id: str = "test-session",
    language: str = "ja",
) -> Dict[str, Any]:
    """Create a minimal text query state.

    Args:
        query: User query text
        session_id: Session identifier
        language: Language code (ja, en, zh, ko)

    Returns:
        WorkflowStateDict for text query

    Examples:
        >>> state = create_text_query_state(query="What time do you open?", language="en")
        >>> assert state["query"] == "What time do you open?"
        >>> assert state["language"] == "en"
    """
    return {
        "messages": [],
        "query": query,
        "session_id": session_id,
        "language": language,
        "routing": {},
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": {},
        "image_data": None,
        "ocr_result": None,
    }


def create_image_query_state(
    image: Optional[np.ndarray] = None,
    query: str = "",
    session_id: str = "test-session",
) -> Dict[str, Any]:
    """Create an image input state.

    Args:
        image: Image data as numpy array (H, W, C)
            If None, creates a blank 100x100 black image
        query: Optional text query accompanying the image
        session_id: Session identifier

    Returns:
        WorkflowStateDict with image data

    Examples:
        >>> state = create_image_query_state(query="What's in this image?")
        >>> assert state["image_data"] is not None
        >>> assert state["query"] == "What's in this image?"
    """
    if image is None:
        image = np.zeros((100, 100, 3), dtype=np.uint8)

    base_state = create_text_query_state(query=query, session_id=session_id)
    base_state["image_data"] = image
    return base_state


def create_memory_context(
    conversation_history: Optional[List[Dict[str, str]]] = None,
    knowledge_base: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create a sample memory context dict.

    Args:
        conversation_history: List of conversation turns
            Each turn: {"role": "user|assistant", "content": "text"}
        knowledge_base: List of knowledge base entries
            Each entry: {"content": "text", "metadata": {...}}

    Returns:
        Memory context dictionary

    Examples:
        >>> context = create_memory_context(
        ...     conversation_history=[
        ...         {"role": "user", "content": "営業時間は？"},
        ...         {"role": "assistant", "content": "10:00-22:00です"}
        ...     ]
        ... )
        >>> assert len(context["conversation_history"]) == 2
    """
    if conversation_history is None:
        conversation_history = []

    if knowledge_base is None:
        knowledge_base = []

    return {
        "conversation_history": conversation_history,
        "knowledge_base": knowledge_base,
        "last_query": "",
        "last_response": "",
        "session_metadata": {
            "start_time": "2024-01-01T00:00:00Z",
            "turn_count": len(conversation_history),
        },
    }


def create_routing_decision(
    agent: str = "business_info",
    category: str = "business-info",
    language: str = "ja",
    request_type: Optional[str] = "hours",
    confidence: float = 0.95,
) -> Dict[str, Any]:
    """Create a sample routing dict.

    Args:
        agent: Target agent name
        category: Query category
        language: Language code
        request_type: Specific request type (hours, price, wifi, etc.)
        confidence: Routing confidence (0.0-1.0)

    Returns:
        Routing decision dictionary

    Examples:
        >>> routing = create_routing_decision(
        ...     agent="facility",
        ...     category="facility",
        ...     request_type="wifi"
        ... )
        >>> assert routing["agent"] == "facility"
        >>> assert routing["request_type"] == "wifi"
    """
    return {
        "agent": agent,
        "category": category,
        "language": language,
        "request_type": request_type,
        "confidence": confidence,
        "reasoning": "test routing decision",
        "debug_info": {},
    }


def create_agent_response(
    answer: str = "これはテスト回答です",
    emotion: str = "neutral",
    agent: str = "TestAgent",
    confidence: float = 0.9,
) -> Dict[str, Any]:
    """Create a sample agent response dict.

    Args:
        answer: Response text
        emotion: Emotion tag
        agent: Agent name
        confidence: Response confidence

    Returns:
        Agent response dictionary

    Examples:
        >>> response = create_agent_response(
        ...     answer="営業時間は10:00-22:00です",
        ...     emotion="informative",
        ...     agent="BusinessInfoAgent"
        ... )
        >>> assert response["answer"] == "営業時間は10:00-22:00です"
    """
    return {
        "answer": answer,
        "emotion": emotion,
        "metadata": {
            "agent": agent,
            "confidence": confidence,
            "timestamp": "2024-01-01T00:00:00Z",
        },
    }


def create_workflow_state_with_routing(
    query: str = "営業時間は？",
    next_agent: str = "business_info",
    category: str = "business-info",
    language: str = "ja",
) -> Dict[str, Any]:
    """Create a workflow state with routing decision already made.

    Args:
        query: User query
        next_agent: Routed agent name
        category: Query category
        language: Language code

    Returns:
        WorkflowStateDict with routing populated

    Examples:
        >>> state = create_workflow_state_with_routing(
        ...     query="Wi-Fiのパスワードは？",
        ...     next_agent="facility",
        ...     category="facility"
        ... )
        >>> assert state["routing"]["agent"] == "facility"
    """
    state = create_text_query_state(query=query, language=language)
    state["routing"] = create_routing_decision(
        agent=next_agent,
        category=category,
        language=language,
    )
    return state


def create_workflow_state_with_answer(
    query: str = "営業時間は？",
    answer: str = "10:00-22:00です",
    emotion: str = "informative",
    agent: str = "BusinessInfoAgent",
) -> Dict[str, Any]:
    """Create a workflow state with answer already populated.

    Args:
        query: User query
        answer: Agent answer
        emotion: Emotion tag
        agent: Agent that provided the answer

    Returns:
        WorkflowStateDict with answer populated

    Examples:
        >>> state = create_workflow_state_with_answer(
        ...     query="料金は？",
        ...     answer="1時間500円です",
        ...     emotion="helpful"
        ... )
        >>> assert state["answer"] == "1時間500円です"
    """
    state = create_text_query_state(query=query)
    state["answer"] = answer
    state["emotion"] = emotion
    state["metadata"]["agent"] = agent
    return state


def create_multilingual_query_states() -> Dict[str, Dict[str, Any]]:
    """Create sample query states in multiple languages.

    Returns:
        Dictionary mapping language codes to query states

    Examples:
        >>> states = create_multilingual_query_states()
        >>> assert states["ja"]["query"] == "営業時間は何時ですか？"
        >>> assert states["en"]["language"] == "en"
    """
    return {
        "ja": create_text_query_state(
            query="営業時間は何時ですか？",
            language="ja",
        ),
        "en": create_text_query_state(
            query="What time do you open?",
            language="en",
        ),
        "zh": create_text_query_state(
            query="营业时间是几点？",
            language="zh",
        ),
        "ko": create_text_query_state(
            query="영업 시간은 몇 시입니까?",
            language="ko",
        ),
    }


def create_error_state(
    query: str = "test query",
    error_message: str = "An error occurred",
    error_type: str = "TestError",
) -> Dict[str, Any]:
    """Create a workflow state with error information.

    Args:
        query: User query
        error_message: Error message
        error_type: Error type/class name

    Returns:
        WorkflowStateDict with error metadata

    Examples:
        >>> state = create_error_state(
        ...     query="test",
        ...     error_message="LLM timeout",
        ...     error_type="TimeoutError"
        ... )
        >>> assert state["metadata"]["error"]["type"] == "TimeoutError"
    """
    state = create_text_query_state(query=query)
    state["metadata"]["error"] = {
        "type": error_type,
        "message": error_message,
        "timestamp": "2024-01-01T00:00:00Z",
    }
    return state
