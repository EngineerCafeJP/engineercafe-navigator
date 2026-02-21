"""Mock LLM response factories."""

from unittest.mock import AsyncMock, MagicMock
from typing import Optional, Dict, Any
from langchain_core.messages import AIMessage


def create_mock_llm(content: str = "Test response") -> MagicMock:
    """Create a mock LLM that returns predictable responses.

    Args:
        content: Response content to return

    Returns:
        Mock LLM with ainvoke method

    Examples:
        >>> mock_llm = create_mock_llm(content="Hello, world!")
        >>> response = await mock_llm.ainvoke([HumanMessage(content="Hi")])
        >>> assert response.content == "Hello, world!"
    """
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=content))
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    return mock_llm


def create_mock_openrouter_provider(llm: Optional[MagicMock] = None) -> MagicMock:
    """Create a mock OpenRouterProvider.

    Args:
        llm: Optional mock LLM to return from get_langchain_llm
            If None, creates a default mock LLM

    Returns:
        Mock OpenRouterProvider with get_langchain_llm method

    Examples:
        >>> provider = create_mock_openrouter_provider()
        >>> llm = provider.get_langchain_llm()
        >>> response = await llm.ainvoke([HumanMessage(content="test")])
        >>> assert isinstance(response, AIMessage)
    """
    if llm is None:
        llm = create_mock_llm()

    mock_provider = MagicMock()
    mock_provider.get_langchain_llm = MagicMock(return_value=llm)
    return mock_provider


def create_mock_chat_response(
    content: str = "Test",
    emotion: str = "neutral",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a structured chat response dict.

    Args:
        content: Answer text
        emotion: Emotion tag
        metadata: Additional metadata

    Returns:
        Chat response dictionary matching agent return format

    Examples:
        >>> response = create_mock_chat_response(
        ...     content="営業時間は10:00-22:00です",
        ...     emotion="informative"
        ... )
        >>> assert response["answer"] == "営業時間は10:00-22:00です"
        >>> assert response["emotion"] == "informative"
    """
    default_metadata = {
        "agent": "MockAgent",
        "confidence": 0.9,
        "timestamp": "2024-01-01T00:00:00Z",
    }
    if metadata:
        default_metadata.update(metadata)

    return {
        "answer": content,
        "emotion": emotion,
        "metadata": default_metadata,
    }


def create_mock_structured_llm(
    response_dict: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    """Create a mock LLM that returns structured JSON responses.

    Args:
        response_dict: Dictionary to return as JSON
            If None, returns {"status": "ok"}

    Returns:
        Mock LLM that returns structured responses

    Examples:
        >>> mock_llm = create_mock_structured_llm({"next_agent": "business_info"})
        >>> response = await mock_llm.ainvoke([HumanMessage(content="test")])
        >>> import json
        >>> data = json.loads(response.content)
        >>> assert data["next_agent"] == "business_info"
    """
    import json

    if response_dict is None:
        response_dict = {"status": "ok"}

    content = json.dumps(response_dict, ensure_ascii=False)
    return create_mock_llm(content=content)


def create_mock_rag_search(
    results: Optional[list] = None,
    confidence: float = 0.9,
) -> MagicMock:
    """Create a mock RAG search tool.

    Args:
        results: List of search results to return
        confidence: Confidence score for results

    Returns:
        Mock RAG search with search method

    Examples:
        >>> rag = create_mock_rag_search(
        ...     results=[{"content": "営業時間は10:00-22:00です", "score": 0.95}]
        ... )
        >>> result = await rag.search("営業時間")
        >>> assert len(result) == 1
    """
    if results is None:
        results = [
            {
                "content": "Sample content",
                "score": confidence,
                "metadata": {"source": "knowledge_base"},
            }
        ]

    mock_rag = MagicMock()
    mock_rag.search = AsyncMock(return_value=results)
    mock_rag.enhanced_search = AsyncMock(return_value=results)
    return mock_rag


def create_mock_embedding_model(
    embeddings: Optional[list] = None,
) -> MagicMock:
    """Create a mock embedding model.

    Args:
        embeddings: List of embedding vectors to return
            If None, returns a single 384-dimensional vector

    Returns:
        Mock embedding model with embed_query and embed_documents methods

    Examples:
        >>> model = create_mock_embedding_model()
        >>> embedding = await model.embed_query("test query")
        >>> assert len(embedding) == 384
    """
    import numpy as np

    if embeddings is None:
        # Create a single 384-dimensional embedding
        embeddings = [np.random.rand(384).tolist()]

    mock_model = MagicMock()
    mock_model.embed_query = AsyncMock(return_value=embeddings[0])
    mock_model.embed_documents = AsyncMock(return_value=embeddings)
    return mock_model


def create_mock_langchain_tool(
    name: str = "test_tool",
    description: str = "A test tool",
    result: Any = "tool result",
) -> MagicMock:
    """Create a mock LangChain tool.

    Args:
        name: Tool name
        description: Tool description
        result: Result to return when tool is called

    Returns:
        Mock tool with ainvoke method

    Examples:
        >>> tool = create_mock_langchain_tool(name="search", result=["result1"])
        >>> result = await tool.ainvoke({"query": "test"})
        >>> assert result == ["result1"]
    """
    mock_tool = MagicMock()
    mock_tool.name = name
    mock_tool.description = description
    mock_tool.ainvoke = AsyncMock(return_value=result)
    mock_tool.invoke = MagicMock(return_value=result)
    return mock_tool
