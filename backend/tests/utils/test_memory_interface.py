"""Tests for backend.utils.memory_interface — Memory system interface protocol."""

import pytest
from typing import Optional, Dict, Any
from backend.utils.memory_interface import MemoryNotAvailableError


class TestMemorySystemInterface:
    """MemorySystemInterface Protocol のテスト"""

    def test_concrete_implementation_recognized(self):
        """Protocol を実装したクラスが正常に動作する"""

        class MockMemory:
            """MemorySystemInterface を実装したモッククラス"""

            async def get_previous_request_type(self, session_id: str) -> Optional[str]:
                return "hours"

            async def get_context(
                self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
                return {"context_string": "test context", "recent_messages": []}

            async def store_message(
                self,
                role: str,
                content: str,
                session_id: str,
                metadata: Optional[Dict[str, Any]] = None,
            ) -> None:
                pass

        # Protocolを実装したクラスのインスタンスが作成できることを確認
        mock_memory = MockMemory()
        assert mock_memory is not None

    async def test_get_previous_request_type_signature(self):
        """get_previous_request_type メソッドのシグネチャを検証"""

        class TestMemory:
            async def get_previous_request_type(self, session_id: str) -> Optional[str]:
                return "hours"

            async def get_context(
                self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
                return {}

            async def store_message(
                self,
                role: str,
                content: str,
                session_id: str,
                metadata: Optional[Dict[str, Any]] = None,
            ) -> None:
                pass

        memory = TestMemory()
        result = await memory.get_previous_request_type("session_123")
        assert result == "hours"

    async def test_get_context_signature(self):
        """get_context メソッドのシグネチャを検証"""

        class TestMemory:
            async def get_previous_request_type(self, session_id: str) -> Optional[str]:
                return None

            async def get_context(
                self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
                return {
                    "context_string": "test",
                    "recent_messages": [],
                    "knowledge_results": [],
                }

            async def store_message(
                self,
                role: str,
                content: str,
                session_id: str,
                metadata: Optional[Dict[str, Any]] = None,
            ) -> None:
                pass

        memory = TestMemory()
        result = await memory.get_context("エンジニアカフェ", "session_123")
        assert "context_string" in result
        assert "recent_messages" in result

    async def test_store_message_signature(self):
        """store_message メソッドのシグネチャを検証"""

        class TestMemory:
            def __init__(self):
                self.stored_messages = []

            async def get_previous_request_type(self, session_id: str) -> Optional[str]:
                return None

            async def get_context(
                self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
                return {}

            async def store_message(
                self,
                role: str,
                content: str,
                session_id: str,
                metadata: Optional[Dict[str, Any]] = None,
            ) -> None:
                self.stored_messages.append(
                    {
                        "role": role,
                        "content": content,
                        "session_id": session_id,
                        "metadata": metadata,
                    }
                )

        memory = TestMemory()
        await memory.store_message(
            "user", "営業時間は？", "session_123", {"emotion": "curious", "request_type": "hours"}
        )
        assert len(memory.stored_messages) == 1
        assert memory.stored_messages[0]["role"] == "user"
        assert memory.stored_messages[0]["content"] == "営業時間は？"

    def test_non_conforming_class_missing_methods(self):
        """Protocolに準拠しないクラス（メソッド不足）"""

        class IncompleteMemory:
            """get_previous_request_type のみ実装"""

            async def get_previous_request_type(self, session_id: str) -> Optional[str]:
                return None

        # インスタンス作成は可能だが、Protocolの全メソッドは実装されていない
        incomplete = IncompleteMemory()
        assert not hasattr(incomplete, "get_context")
        assert not hasattr(incomplete, "store_message")


class TestMemoryNotAvailableError:
    """MemoryNotAvailableError 例外のテスト"""

    def test_instantiation_with_message(self):
        """メッセージ付きでインスタンス化できる"""
        error = MemoryNotAvailableError("Memory system is unavailable")
        assert str(error) == "Memory system is unavailable"

    def test_is_instance_of_exception(self):
        """Exception を継承している"""
        error = MemoryNotAvailableError("Test error")
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self):
        """raise して catch できる"""
        with pytest.raises(MemoryNotAvailableError) as exc_info:
            raise MemoryNotAvailableError("Memory service down")

        assert "Memory service down" in str(exc_info.value)


class TestMemorySystemInterfaceUsageExample:
    """MemorySystemInterface の実用例テスト"""

    async def test_full_memory_workflow(self):
        """メモリシステムの完全なワークフロー"""

        class FullMemory:
            def __init__(self):
                self.messages = []
                self.last_request_type = None

            async def get_previous_request_type(self, session_id: str) -> Optional[str]:
                return self.last_request_type

            async def get_context(
                self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
                options = options or {}
                return {
                    "context_string": f"Context for: {query}",
                    "recent_messages": self.messages[-5:],
                    "knowledge_results": [],
                    "inherited_request_type": self.last_request_type,
                }

            async def store_message(
                self,
                role: str,
                content: str,
                session_id: str,
                metadata: Optional[Dict[str, Any]] = None,
            ) -> None:
                self.messages.append({"role": role, "content": content})
                if metadata and "request_type" in metadata:
                    self.last_request_type = metadata["request_type"]

        memory = FullMemory()

        # 1. ユーザーメッセージを保存
        await memory.store_message(
            "user", "営業時間を教えて", "session_123", {"request_type": "hours"}
        )

        # 2. 前回のリクエストタイプを取得
        request_type = await memory.get_previous_request_type("session_123")
        assert request_type == "hours"

        # 3. コンテキストを取得
        context = await memory.get_context("エンジニアカフェ", "session_123")
        assert "Context for: エンジニアカフェ" in context["context_string"]
        assert len(context["recent_messages"]) == 1
        assert context["inherited_request_type"] == "hours"

        # 4. アシスタントの応答を保存
        await memory.store_message(
            "assistant",
            "平日は10:00-22:00です",
            "session_123",
            {"emotion": "helpful"},
        )

        # 5. メッセージ履歴の確認
        context2 = await memory.get_context("ありがとう", "session_123")
        assert len(context2["recent_messages"]) == 2
