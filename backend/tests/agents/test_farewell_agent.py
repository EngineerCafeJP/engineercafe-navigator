"""
FarewellAgent のユニットテスト
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.farewell_agent import FarewellAgent


class TestFarewellAgent:
    """FarewellAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = FarewellAgent()

    def test_get_default_farewell_response_japanese(self):
        """日本語のデフォルト退館応答をテスト"""
        response = self.agent._get_default_farewell_response("ja")

        assert response["answer"].startswith("[happy]")
        assert "受付カード" in response["answer"]
        assert response["emotion"] == "happy"
        assert response["metadata"]["agent"] == "FarewellAgent"
        assert response["metadata"]["confidence"] == 0.3
        assert response["metadata"]["sources"] == ["fallback"]

    def test_get_default_farewell_response_english(self):
        """英語のデフォルト退館応答をテスト"""
        response = self.agent._get_default_farewell_response("en")

        assert response["answer"].startswith("[happy]")
        assert "reception card" in response["answer"].lower()
        assert response["emotion"] == "happy"
        assert response["metadata"]["agent"] == "FarewellAgent"
        assert response["metadata"]["confidence"] == 0.3
        assert response["metadata"]["sources"] == ["fallback"]

    def test_build_farewell_prompt_japanese(self):
        """日本語の退館プロンプト構築をテスト"""
        prompt = self.agent._build_farewell_prompt(
            query="帰ります",
            context="",
            language="ja",
        )

        assert "退館" in prompt or "さようなら" in prompt or "帰" in prompt
        assert "[happy]" in prompt
        assert "受付カード" in prompt
        assert "帰ります" in prompt

    def test_build_farewell_prompt_english(self):
        """英語の退館プロンプト構築をテスト"""
        prompt = self.agent._build_farewell_prompt(
            query="goodbye",
            context="",
            language="en",
        )

        assert "farewell" in prompt.lower() or "leaving" in prompt.lower()
        assert "[happy]" in prompt
        assert "reception card" in prompt.lower()
        assert "goodbye" in prompt

    def test_build_farewell_prompt_with_context(self):
        """コンテキスト付きの退館プロンプト構築をテスト"""
        context = "受付カードは1階フロントにお返しください。"
        prompt = self.agent._build_farewell_prompt(
            query="帰ります",
            context=context,
            language="ja",
        )

        assert context in prompt

    def test_build_farewell_prompt_without_context(self):
        """コンテキストなしの退館プロンプト構築をテスト（コンテキストセクションなし）"""
        prompt = self.agent._build_farewell_prompt(
            query="帰ります",
            context="",
            language="ja",
        )

        assert "参考情報:" not in prompt

    @pytest.mark.asyncio
    async def test_handle_farewell_japanese_success(self):
        """日本語退館処理の成功ケースをテスト"""
        mock_rag_result = {
            "success": True,
            "data": {"context": "受付カードは1階フロントにお返しください。"},
        }
        mock_llm_response = "[happy]ありがとうございました！受付カードをお返しください。またのご来館をお待ちしております。"

        with (
            patch.object(
                self.agent.enhanced_rag,
                "search",
                new_callable=AsyncMock,
                return_value=mock_rag_result,
            ),
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
                return_value=mock_llm_response,
            ),
        ):
            result = await self.agent.handle_farewell(query="帰ります", language="ja")

        assert result["answer"] == mock_llm_response
        assert result["emotion"] == "happy"
        assert result["metadata"]["agent"] == "FarewellAgent"
        assert result["metadata"]["confidence"] == 0.85
        assert result["metadata"]["sources"] == ["enhanced_rag"]

    @pytest.mark.asyncio
    async def test_handle_farewell_english_success(self):
        """英語退館処理の成功ケースをテスト"""
        mock_rag_result = {
            "success": True,
            "data": {"context": "Please return the reception card at the front desk."},
        }
        mock_llm_response = (
            "[happy]Thank you for visiting! Please return your reception card. See you again!"
        )

        with (
            patch.object(
                self.agent.enhanced_rag,
                "search",
                new_callable=AsyncMock,
                return_value=mock_rag_result,
            ),
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
                return_value=mock_llm_response,
            ),
        ):
            result = await self.agent.handle_farewell(query="goodbye", language="en")

        assert result["answer"] == mock_llm_response
        assert result["emotion"] == "happy"
        assert result["metadata"]["agent"] == "FarewellAgent"

    @pytest.mark.asyncio
    async def test_handle_farewell_rag_failure_fallback(self):
        """RAG検索失敗時のフォールバックをテスト"""
        mock_rag_result = {"success": False}
        mock_llm_response = "[happy]ありがとうございました！受付カードをお返しください。"

        with (
            patch.object(
                self.agent.enhanced_rag,
                "search",
                new_callable=AsyncMock,
                return_value=mock_rag_result,
            ),
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
                return_value=mock_llm_response,
            ),
        ):
            result = await self.agent.handle_farewell(query="帰ります", language="ja")

        # RAG失敗でもLLMが動作すれば応答を返す
        assert result["emotion"] == "happy"
        assert result["metadata"]["agent"] == "FarewellAgent"

    @pytest.mark.asyncio
    async def test_handle_farewell_llm_error_fallback(self):
        """LLMエラー時のデフォルト退館応答フォールバックをテスト"""
        mock_rag_result = {
            "success": True,
            "data": {"context": "受付カードは1階フロントにお返しください。"},
        }

        with (
            patch.object(
                self.agent.enhanced_rag,
                "search",
                new_callable=AsyncMock,
                return_value=mock_rag_result,
            ),
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
                side_effect=Exception("LLM error"),
            ),
        ):
            result = await self.agent.handle_farewell(query="帰ります", language="ja")

        assert result["answer"].startswith("[happy]")
        assert result["emotion"] == "happy"
        assert result["metadata"]["agent"] == "FarewellAgent"
        assert result["metadata"]["confidence"] == 0.3
        assert result["metadata"]["sources"] == ["fallback"]

    @pytest.mark.asyncio
    async def test_handle_farewell_with_session_id(self):
        """セッションID付きの退館処理をテスト"""
        mock_rag_result = {"success": False}
        mock_llm_response = "[happy]ありがとうございました！"

        with (
            patch.object(
                self.agent.enhanced_rag,
                "search",
                new_callable=AsyncMock,
                return_value=mock_rag_result,
            ),
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
                return_value=mock_llm_response,
            ),
        ):
            result = await self.agent.handle_farewell(
                query="さようなら",
                language="ja",
                session_id="test-session-123",
            )

        assert result["emotion"] == "happy"
        assert result["metadata"]["agent"] == "FarewellAgent"
