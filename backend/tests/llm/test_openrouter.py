"""
OpenRouterProvider のユニットテスト
"""

import os
import pytest
from unittest.mock import MagicMock, patch
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
            model_id=SupportedModel.GEMINI_2_5_FLASH,
            fallback_model=SupportedModel.GPT_4O_MINI,
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
            model_id=SupportedModel.GEMINI_2_5_FLASH,
            fallback_model=SupportedModel.GPT_4O_MINI,
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
            model_id=SupportedModel.GEMINI_2_5_FLASH,
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
            model_id=SupportedModel.GEMINI_2_5_FLASH,
            fallback_model=SupportedModel.GPT_4O_MINI,
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
            model_id=SupportedModel.GEMINI_2_5_FLASH,
            fallback_model=SupportedModel.GPT_4O_MINI,
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
    async def test_http_error_with_status_code(self):
        """特定のHTTPステータスコードでのフォールバック"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_2_5_FLASH,
            fallback_model=SupportedModel.GPT_4O_MINI,
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
