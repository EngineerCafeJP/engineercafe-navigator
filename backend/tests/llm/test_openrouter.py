"""
OpenRouterProvider のユニットテスト
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from langchain_core.messages import HumanMessage

from backend.llm.openrouter import OpenRouterProvider, OpenRouterError
from backend.llm.models import ModelConfig, SupportedModel


class TestOpenRouterProvider:
    """OpenRouterProvider のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key"
        self.provider = OpenRouterProvider()

    @pytest.mark.asyncio
    async def test_fallback_on_http_status_error(self):
        """HTTPステータスエラー時のフォールバック動作テスト"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )

        # HTTPステータスエラーをシミュレート
        mock_response_error = MagicMock()
        mock_response_error.status_code = 500
        mock_response_error.text = "Internal Server Error"

        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Fallback response"}}]
        }

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 1回目はHTTPエラー
                raise httpx.HTTPStatusError(
                    "500 Error", request=MagicMock(), response=mock_response_error
                )
            else:
                # 2回目（フォールバック）は成功
                return mock_response_success

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            response = await self.provider.generate(messages, config)

            # フォールバックが成功し、レスポンスが返る
            assert response == "Fallback response"
            # 2回呼び出されていることを確認（1回目: プライマリ失敗、2回目: フォールバック成功）
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_on_network_error(self):
        """ネットワークエラー時のフォールバック動作テスト"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )

        # ネットワークエラーをシミュレート
        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Fallback after network error"}}]
        }

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 1回目はネットワークエラー
                raise httpx.RequestError("Connection timeout", request=MagicMock())
            else:
                # 2回目（フォールバック）は成功
                return mock_response_success

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            response = await self.provider.generate(messages, config)

            # フォールバックが成功し、レスポンスが返る
            assert response == "Fallback after network error"
            # 2回呼び出されていることを確認
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_fallback_without_fallback_model(self):
        """フォールバックモデルなしの場合、エラーが発生することを確認"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=None,  # フォールバックなし
        )

        # ネットワークエラーをシミュレート
        async def mock_post(*args, **kwargs):
            raise httpx.RequestError("Connection timeout", request=MagicMock())

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            with pytest.raises(OpenRouterError, match="Network error"):
                await self.provider.generate(messages, config)

    @pytest.mark.asyncio
    async def test_fallback_count_limit(self):
        """フォールバック回数制限のテスト（無限ループ防止）"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )

        # 常にネットワークエラーをシミュレート
        async def mock_post(*args, **kwargs):
            raise httpx.RequestError("Connection timeout", request=MagicMock())

        with patch.object(self.provider._http_client, "post", side_effect=mock_post) as mock:
            with pytest.raises(OpenRouterError, match="Network error"):
                await self.provider.generate(messages, config)

            # 最大2回呼び出し（1回目: プライマリ失敗、2回目: フォールバック失敗）
            assert mock.call_count == 2

    @pytest.mark.asyncio
    async def test_successful_primary_model(self):
        """プライマリモデルが成功する場合のテスト"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Primary model response"}}]
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        with patch.object(self.provider._http_client, "post", side_effect=mock_post) as mock:
            response = await self.provider.generate(messages, config)

            # プライマリモデルが成功し、レスポンスが返る
            assert response == "Primary model response"
            # 1回だけ呼び出されることを確認（フォールバック不要）
            assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_cerebras_fast_primary_before_openrouter(self):
        """FAST_LLM_PRIMARY_PROVIDER=cerebras の場合、OpenRouterより先にCerebrasを使う"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
            allow_cerebras_primary=True,
            cerebras_primary_use_case="qa_response",
        )

        with (
            patch.dict(
                os.environ,
                {
                    "FAST_LLM_ENABLED": "true",
                    "FAST_LLM_PRIMARY_PROVIDER": "cerebras",
                    "CEREBRAS_API_KEY": "test_cerebras_key",
                    "CEREBRAS_FAST_MODEL": "gpt-oss-120b",
                },
            ),
            patch.object(
                self.provider,
                "_cerebras_generate",
                new=AsyncMock(return_value="Cerebras fast response"),
            ) as cerebras_mock,
            patch.object(self.provider._http_client, "post", new=AsyncMock()) as openrouter_mock,
        ):
            response = await self.provider.generate(messages, config)

        assert response == "Cerebras fast response"
        cerebras_mock.assert_awaited_once()
        openrouter_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_cerebras_fast_primary_falls_back_to_openrouter(self):
        """Cerebras first pass が失敗した場合は既存のOpenRouter primaryへ戻る"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
            allow_cerebras_primary=True,
            cerebras_primary_use_case="qa_response",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter fallback response"}}]
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        with (
            patch.dict(
                os.environ,
                {
                    "FAST_LLM_ENABLED": "true",
                    "FAST_LLM_PRIMARY_PROVIDER": "cerebras",
                    "CEREBRAS_API_KEY": "test_cerebras_key",
                },
            ),
            patch.object(
                self.provider,
                "_cerebras_generate",
                new=AsyncMock(side_effect=OpenRouterError("Cerebras unavailable")),
            ) as cerebras_mock,
            patch.object(
                self.provider._http_client, "post", side_effect=mock_post
            ) as openrouter_mock,
        ):
            response = await self.provider.generate(messages, config)

        assert response == "OpenRouter fallback response"
        cerebras_mock.assert_awaited_once()
        assert openrouter_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_cerebras_direct_call_uses_fast_timeout_env(self):
        """Cerebras direct path should not inherit the old 60s minimum wait."""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
            allow_cerebras_primary=True,
            cerebras_primary_use_case="qa_response",
            timeout=30.0,
        )

        class FakeCerebrasResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "fast cerebras"}}]}

        class FakeAsyncClient:
            timeouts = []

            def __init__(self, *, timeout, headers):
                self.timeouts.append(timeout)
                self.headers = headers

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def post(self, url, json):
                return FakeCerebrasResponse()

        with (
            patch.dict(
                os.environ,
                {
                    "CEREBRAS_API_KEY": "test_cerebras_key",
                    "CEREBRAS_TIMEOUT_SECONDS": "1.25",
                },
            ),
            patch("backend.llm.openrouter.httpx.AsyncClient", FakeAsyncClient),
        ):
            response = await self.provider._cerebras_generate(messages, config)

        assert response == "fast cerebras"
        assert FakeAsyncClient.timeouts == [1.25]

    @pytest.mark.asyncio
    async def test_cerebras_fast_primary_requires_config_opt_in(self):
        """施設・イベント系のfast configへCerebras primaryが波及しないこと"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter primary response"}}]
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        with (
            patch.dict(
                os.environ,
                {
                    "FAST_LLM_ENABLED": "true",
                    "FAST_LLM_PRIMARY_PROVIDER": "cerebras",
                    "CEREBRAS_API_KEY": "test_cerebras_key",
                },
            ),
            patch.object(
                self.provider,
                "_cerebras_generate",
                new=AsyncMock(return_value="Unexpected Cerebras response"),
            ) as cerebras_mock,
            patch.object(
                self.provider._http_client, "post", side_effect=mock_post
            ) as openrouter_mock,
        ):
            response = await self.provider.generate(messages, config)

        assert response == "OpenRouter primary response"
        cerebras_mock.assert_not_called()
        assert openrouter_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_http_error_with_status_code(self):
        """特定のHTTPステータスコードでのフォールバック"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        )

        # 503 Service Unavailableエラーをシミュレート
        mock_response_error = MagicMock()
        mock_response_error.status_code = 503
        mock_response_error.text = "Service Unavailable"

        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {
            "choices": [{"message": {"content": "Fallback after 503"}}]
        }

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.HTTPStatusError(
                    "503 Error", request=MagicMock(), response=mock_response_error
                )
            else:
                return mock_response_success

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            response = await self.provider.generate(messages, config)

            assert response == "Fallback after 503"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_close_method(self):
        """closeメソッドのテスト"""
        # closeメソッドが正常に実行できることを確認
        await self.provider.close()
        # 再度作成
        self.provider = OpenRouterProvider()
