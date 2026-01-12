"""
モック作成ユーティリティ

テストで使用するモックオブジェクトを作成するヘルパー関数を提供します。
"""

from typing import Dict, Any, Optional, Callable
from unittest.mock import Mock, AsyncMock, patch


def create_mock_openrouter_provider(
    response_text: str = "モックレスポンス", usage: Optional[Dict[str, int]] = None
) -> Mock:
    """
    モックOpenRouterProviderを作成

    Args:
        response_text: レスポンステキスト
        usage: トークン使用量

    Returns:
        Mock: OpenRouterProviderのモック
    """
    if usage is None:
        usage = {"prompt_tokens": 10, "completion_tokens": 20}

    provider = Mock()
    provider.generate = AsyncMock(return_value={"text": response_text, "usage": usage})

    return provider


def create_mock_memory_system(
    context: Optional[Dict[str, Any]] = None, previous_request_type: Optional[str] = None
) -> Mock:
    """
    モックメモリシステムを作成

    Args:
        context: コンテキスト情報
        previous_request_type: 前回のリクエストタイプ

    Returns:
        Mock: メモリシステムのモック
    """
    if context is None:
        context = {"recent_messages": [], "context_string": "", "total_messages": 0}

    memory = Mock()
    memory.get_context = AsyncMock(return_value=context)
    memory.get_previous_request_type = AsyncMock(return_value=previous_request_type)
    memory.store_message = AsyncMock(return_value=None)

    return memory


def create_mock_rag_system(search_results: Optional[list] = None) -> Mock:
    """
    モックRAGシステムを作成

    Args:
        search_results: 検索結果リスト

    Returns:
        Mock: RAGシステムのモック
    """
    if search_results is None:
        search_results = [
            {"content": "テスト文書1", "score": 0.95},
            {"content": "テスト文書2", "score": 0.85},
        ]

    rag = Mock()
    rag.search = AsyncMock(return_value=search_results)

    return rag


def create_mock_calendar_service(events: Optional[list] = None) -> Mock:
    """
    モックカレンダーサービスを作成

    Args:
        events: イベントリスト

    Returns:
        Mock: カレンダーサービスのモック
    """
    if events is None:
        events = [
            {
                "summary": "テストイベント1",
                "start": {"dateTime": "2025-01-15T10:00:00"},
                "end": {"dateTime": "2025-01-15T12:00:00"},
            }
        ]

    calendar = Mock()
    calendar.get_events = AsyncMock(return_value=events)

    return calendar


def patch_openrouter_provider(
    response_text: str = "モックレスポンス", usage: Optional[Dict[str, int]] = None
):
    """
    OpenRouterProviderをパッチするデコレータ

    Usage:
        @patch_openrouter_provider("テスト回答")
        async def test_something():
            # テスト内容
            pass

    Args:
        response_text: レスポンステキスト
        usage: トークン使用量

    Returns:
        Decorator: パッチデコレータ
    """
    if usage is None:
        usage = {"prompt_tokens": 10, "completion_tokens": 20}

    def decorator(func):
        async def wrapper(*args, **kwargs):
            provider = create_mock_openrouter_provider(response_text, usage)
            with patch("llm.openrouter.OpenRouterProvider", return_value=provider):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def create_async_mock_with_side_effect(side_effect: Callable) -> AsyncMock:
    """
    副作用を持つAsyncMockを作成

    Args:
        side_effect: 副作用関数

    Returns:
        AsyncMock: 副作用を持つAsyncMock
    """
    return AsyncMock(side_effect=side_effect)


def create_mock_with_exception(exception: Exception) -> Mock:
    """
    例外を発生させるモックを作成

    Args:
        exception: 発生させる例外

    Returns:
        Mock: 例外を発生させるモック
    """
    mock = Mock()
    mock.side_effect = exception
    return mock
