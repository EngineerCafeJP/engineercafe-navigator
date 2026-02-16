"""
Tests for backend/utils/exceptions.py

カスタム例外階層の構造とメッセージ処理をテストする。
"""

import pytest

from backend.utils.exceptions import (
    AgentSystemError,
    ExternalServiceError,
    LLMGenerationError,
    MemorySystemError,
    RAGSearchError,
    RoutingError,
)


class TestExceptionHierarchy:
    """例外クラスの階層構造をテスト"""

    def test_routing_error_is_agent_system_error(self):
        """RoutingError は AgentSystemError のサブクラス"""
        error = RoutingError("test message")
        assert isinstance(error, AgentSystemError)
        assert isinstance(error, Exception)

    def test_llm_generation_error_is_agent_system_error(self):
        """LLMGenerationError は AgentSystemError のサブクラス"""
        error = LLMGenerationError("test message")
        assert isinstance(error, AgentSystemError)
        assert isinstance(error, Exception)

    def test_memory_system_error_is_agent_system_error(self):
        """MemorySystemError は AgentSystemError のサブクラス"""
        error = MemorySystemError("test message")
        assert isinstance(error, AgentSystemError)
        assert isinstance(error, Exception)

    def test_rag_search_error_is_agent_system_error(self):
        """RAGSearchError は AgentSystemError のサブクラス"""
        error = RAGSearchError("test message")
        assert isinstance(error, AgentSystemError)
        assert isinstance(error, Exception)

    def test_external_service_error_is_agent_system_error(self):
        """ExternalServiceError は AgentSystemError のサブクラス"""
        error = ExternalServiceError("test message")
        assert isinstance(error, AgentSystemError)
        assert isinstance(error, Exception)


class TestExceptionMessages:
    """例外メッセージの保持と伝播をテスト"""

    def test_agent_system_error_preserves_message(self):
        """AgentSystemError はメッセージを保持する"""
        message = "Something went wrong"
        error = AgentSystemError(message)
        assert str(error) == message
        assert error.args[0] == message

    def test_routing_error_preserves_message(self):
        """RoutingError はメッセージを保持する"""
        message = "Failed to route request"
        error = RoutingError(message)
        assert str(error) == message
        assert error.args[0] == message

    def test_llm_generation_error_preserves_message(self):
        """LLMGenerationError はメッセージを保持する"""
        message = "LLM failed to generate response"
        error = LLMGenerationError(message)
        assert str(error) == message
        assert error.args[0] == message

    def test_memory_system_error_preserves_message(self):
        """MemorySystemError はメッセージを保持する"""
        message = "Memory system failure"
        error = MemorySystemError(message)
        assert str(error) == message
        assert error.args[0] == message

    def test_rag_search_error_preserves_message(self):
        """RAGSearchError はメッセージを保持する"""
        message = "RAG search failed"
        error = RAGSearchError(message)
        assert str(error) == message
        assert error.args[0] == message

    def test_external_service_error_preserves_message(self):
        """ExternalServiceError はメッセージを保持する"""
        message = "External service unavailable"
        error = ExternalServiceError(message)
        assert str(error) == message
        assert error.args[0] == message


class TestExceptionCatching:
    """親クラスで例外をキャッチできることをテスト"""

    def test_can_catch_routing_error_as_agent_system_error(self):
        """RoutingError を AgentSystemError としてキャッチできる"""
        with pytest.raises(AgentSystemError) as exc_info:
            raise RoutingError("routing failed")
        assert isinstance(exc_info.value, RoutingError)
        assert str(exc_info.value) == "routing failed"

    def test_can_catch_llm_error_as_agent_system_error(self):
        """LLMGenerationError を AgentSystemError としてキャッチできる"""
        with pytest.raises(AgentSystemError) as exc_info:
            raise LLMGenerationError("generation failed")
        assert isinstance(exc_info.value, LLMGenerationError)

    def test_can_catch_memory_error_as_agent_system_error(self):
        """MemorySystemError を AgentSystemError としてキャッチできる"""
        with pytest.raises(AgentSystemError) as exc_info:
            raise MemorySystemError("memory failed")
        assert isinstance(exc_info.value, MemorySystemError)

    def test_can_catch_rag_error_as_agent_system_error(self):
        """RAGSearchError を AgentSystemError としてキャッチできる"""
        with pytest.raises(AgentSystemError) as exc_info:
            raise RAGSearchError("search failed")
        assert isinstance(exc_info.value, RAGSearchError)

    def test_can_catch_external_service_error_as_agent_system_error(self):
        """ExternalServiceError を AgentSystemError としてキャッチできる"""
        with pytest.raises(AgentSystemError) as exc_info:
            raise ExternalServiceError("service failed")
        assert isinstance(exc_info.value, ExternalServiceError)


class TestAllSubclassesExist:
    """すべての期待されるサブクラスが存在することをテスト"""

    def test_all_five_subclasses_are_defined(self):
        """5つのサブクラスすべてが定義されている"""
        expected_subclasses = {
            RoutingError,
            LLMGenerationError,
            MemorySystemError,
            RAGSearchError,
            ExternalServiceError,
        }

        # AgentSystemError.__subclasses__() で直接のサブクラスを取得
        actual_subclasses = set(AgentSystemError.__subclasses__())

        assert actual_subclasses == expected_subclasses
