"""
OllamaProvider のユニットテスト

生成・ストリーミング・LangChain 連携、および LLM_PROVIDER 環境変数による
ファクトリ分岐を検証する。
"""

import os
import pytest
from unittest.mock import ANY, MagicMock, patch
import httpx
from langchain_core.messages import HumanMessage

from backend.llm.models import ModelConfig, SupportedModel
from backend.llm.ollama import OllamaError, OllamaProvider
from backend.llm.openrouter import LLMResponseText, OpenRouterProvider
from backend.llm.provider import get_llm_provider, reset_provider, resolve_llm_provider

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen3:8b"


class TestOllamaProvider:
    """OllamaProvider のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["OLLAMA_API_KEY"] = "test_dummy_api_key"
        os.environ["OLLAMA_BASE_URL"] = DEFAULT_BASE_URL
        os.environ["OLLAMA_MODEL"] = DEFAULT_MODEL
        self.provider = OllamaProvider()

    # ------------------------------------------------------------------
    # generate
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_generate_sends_reasoning_off_and_keep_alive(self, monkeypatch):
        """デモ向けチューニング: thinking 無効化 + keep_alive がペイロードに含まれること"""
        monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "5m")
        provider = OllamaProvider()
        posted: dict = {}

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        async def fake_post(url, json=None, timeout=None, **kwargs):
            posted.update(json or {})
            return mock_response

        with (
            patch.object(provider._http_client, "post", side_effect=fake_post),
            patch("backend.llm.ollama.record_llm_call_metadata"),
        ):
            await provider.generate([HumanMessage(content="hi")])

        assert posted["reasoning_effort"] == "none"
        assert posted["keep_alive"] == "5m"

    @pytest.mark.asyncio
    async def test_generate_success(self):
        """generate が LLMResponseText と正しいメタデータを返すこと"""
        messages = [HumanMessage(content="Test message")]

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Ollama response"}}]}

        posted = {}

        async def mock_post(url, json=None, **kwargs):
            posted["url"] = url
            posted["json"] = json
            return mock_response

        with (
            patch.object(self.provider._http_client, "post", side_effect=mock_post),
            patch("backend.llm.ollama.record_llm_call_metadata") as metadata_mock,
        ):
            response = await self.provider.generate(messages)

        assert response == "Ollama response"
        assert isinstance(response, LLMResponseText)
        assert response.llm_metadata["provider"] == "ollama"
        assert response.llm_metadata["model"] == DEFAULT_MODEL
        assert isinstance(response.llm_metadata["llm_latency_ms"], int)
        # /v1 のベースURL + chat/completions に POST されること
        assert posted["url"] == "/chat/completions"
        # ペイロードは qa_response のデフォルト設定で構築されること
        assert posted["json"]["model"] == DEFAULT_MODEL
        assert posted["json"]["messages"] == [{"role": "user", "content": "Test message"}]
        assert posted["json"]["temperature"] == 0.7
        assert posted["json"]["max_tokens"] == 1024
        assert posted["json"]["top_p"] == 0.9
        metadata_mock.assert_called_once_with(
            provider="ollama",
            model=DEFAULT_MODEL,
            llm_latency_ms=ANY,
        )

    @pytest.mark.asyncio
    async def test_generate_honors_custom_config(self):
        """generate がカスタム config の temperature/max_tokens を反映すること"""
        messages = [HumanMessage(content="Test message")]
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            temperature=0.1,
            max_tokens=64,
            top_p=0.5,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Config response"}}]}

        posted = {}

        async def mock_post(url, json=None, **kwargs):
            posted["json"] = json
            return mock_response

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            response = await self.provider.generate(messages, config)

        assert response == "Config response"
        assert posted["json"]["temperature"] == 0.1
        assert posted["json"]["max_tokens"] == 64
        assert posted["json"]["top_p"] == 0.5

    @pytest.mark.asyncio
    async def test_generate_returns_metadata_when_tracker_fails(self):
        """トークントラッカーが失敗してもレスポンスにメタデータが載ること"""
        messages = [HumanMessage(content="Test message")]

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Tracker-free response"}}]
        }

        async def mock_post(url, json=None, **kwargs):
            return mock_response

        with (
            patch.object(self.provider._http_client, "post", side_effect=mock_post),
            patch(
                "backend.llm.ollama.record_llm_call_metadata",
                side_effect=RuntimeError("context unavailable"),
            ),
        ):
            response = await self.provider.generate(messages)

        assert response == "Tracker-free response"
        assert response.llm_metadata["provider"] == "ollama"
        assert response.llm_metadata["model"] == DEFAULT_MODEL
        assert isinstance(response.llm_metadata["llm_latency_ms"], int)

    @pytest.mark.asyncio
    async def test_generate_raises_on_http_error(self):
        """HTTP エラー時に OllamaError を送出すること"""
        messages = [HumanMessage(content="Test message")]

        mock_response_error = MagicMock()
        mock_response_error.status_code = 500
        mock_response_error.text = "Internal Server Error"

        async def mock_post(url, json=None, **kwargs):
            raise httpx.HTTPStatusError(
                "500 Error", request=MagicMock(), response=mock_response_error
            )

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            with pytest.raises(OllamaError, match="API request failed"):
                await self.provider.generate(messages)

    @pytest.mark.asyncio
    async def test_generate_raises_on_network_error(self):
        """ネットワークエラー時に OllamaError を送出すること"""
        messages = [HumanMessage(content="Test message")]

        async def mock_post(url, json=None, **kwargs):
            raise httpx.RequestError("Connection refused", request=MagicMock())

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            with pytest.raises(OllamaError, match="Network error"):
                await self.provider.generate(messages)

    @pytest.mark.asyncio
    async def test_generate_raises_on_empty_choices(self):
        """choices が空の場合に OllamaError を送出すること"""
        messages = [HumanMessage(content="Test message")]

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": []}

        async def mock_post(url, json=None, **kwargs):
            return mock_response

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            with pytest.raises(OllamaError, match="No choices in response"):
                await self.provider.generate(messages)

    @pytest.mark.asyncio
    async def test_generate_raises_on_parse_failure(self):
        """JSON パース失敗時に OllamaError を送出すること"""
        messages = [HumanMessage(content="Test message")]

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        async def mock_post(url, json=None, **kwargs):
            return mock_response

        with patch.object(self.provider._http_client, "post", side_effect=mock_post):
            with pytest.raises(OllamaError, match="Failed to parse Ollama response"):
                await self.provider.generate(messages)

    # ------------------------------------------------------------------
    # stream
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stream_yields_content_chunks(self):
        """stream が SSE の content デルタを順に yield すること"""
        messages = [HumanMessage(content="Test message")]

        sse_lines = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            "data: ",
            'data: {"choices": [{"delta": {"content": " world"}}]}',
            'data: {"choices": [{"delta": {}}]}',
            'data: {"choices": [{"delta": {"content": null}}]}',
            "data: [DONE]",
            'data: {"choices": [{"delta": {"content": "IGNORED"}}]}',
            "event: ping",
        ]

        class FakeStreamResponse:
            def __init__(self, lines):
                self._lines = lines

            def raise_for_status(self):
                return None

            async def aiter_lines(self):
                for line in self._lines:
                    yield line

        class FakeStreamContext:
            def __init__(self, lines):
                self._lines = lines

            async def __aenter__(self):
                return FakeStreamResponse(self._lines)

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        with patch.object(
            self.provider._http_client,
            "stream",
            return_value=FakeStreamContext(sse_lines),
        ):
            chunks = []
            async for chunk in self.provider.stream(messages):
                chunks.append(chunk)

        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_stream_raises_on_http_error(self):
        """ストリーミング中に HTTP エラーが発生した場合 OllamaError を送出すること"""
        messages = [HumanMessage(content="Test message")]

        mock_response_error = MagicMock()
        mock_response_error.status_code = 503
        mock_response_error.text = "Service Unavailable"

        class FakeStreamResponse:
            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "503 Error",
                    request=MagicMock(),
                    response=mock_response_error,
                )

            async def aiter_lines(self):
                yield "data: [DONE]"

        class FakeStreamContext:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        with patch.object(
            self.provider._http_client,
            "stream",
            return_value=FakeStreamContext(),
        ):
            with pytest.raises(OllamaError, match="Streaming failed"):
                async for _ in self.provider.stream(messages):
                    pass

    # ------------------------------------------------------------------
    # get_langchain_llm
    # ------------------------------------------------------------------

    def test_get_langchain_llm_uses_ollama_base_url_and_model(self):
        """get_langchain_llm が Ollama 向け ChatOpenAI を返すこと"""
        llm = self.provider.get_langchain_llm()

        assert llm.model_name == DEFAULT_MODEL
        assert llm.openai_api_base == DEFAULT_BASE_URL
        # langchain-openai 1.x では SecretStr として保持される
        api_key = llm.openai_api_key
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        assert api_key == "test_dummy_api_key"
        # qa_response のデフォルト設定
        assert llm.temperature == 0.7
        assert llm.max_tokens == 1024

    def test_get_langchain_llm_honors_custom_config(self):
        """get_langchain_llm がカスタム config を反映すること"""
        config = ModelConfig(
            model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
            temperature=0.2,
            max_tokens=128,
        )
        llm = self.provider.get_langchain_llm(config)

        assert llm.model_name == DEFAULT_MODEL
        assert llm.temperature == 0.2
        assert llm.max_tokens == 128

    # ------------------------------------------------------------------
    # デフォルト値 / ライフサイクル
    # ------------------------------------------------------------------

    def test_env_defaults(self, monkeypatch):
        """環境変数未設定時のデフォルト値（dummy / localhost / qwen3:8b）"""
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)

        provider = OllamaProvider()

        assert provider.api_key == "dummy"
        assert provider.base_url == DEFAULT_BASE_URL
        assert provider.model == DEFAULT_MODEL

    @pytest.mark.asyncio
    async def test_close_method(self):
        """close メソッドが正常に実行できること"""
        await self.provider.close()
        # 再度作成（後続テスト用）
        self.provider = OllamaProvider()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """async with でクライアントが閉じられること"""
        async with OllamaProvider() as provider:
            assert isinstance(provider, OllamaProvider)
        # __aexit__ で close 済み


# ---------------------------------------------------------------------------
# get_llm_provider ファクトリテスト
# ---------------------------------------------------------------------------


class TestGetLLMProviderFactory:
    """LLM_PROVIDER 環境変数によるファクトリ分岐のテストクラス"""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        """各テストの前後でシングルトンをリセットする"""
        reset_provider()
        yield
        reset_provider()

    def test_ollama_provider_when_env_set(self, monkeypatch):
        """LLM_PROVIDER=ollama の場合 OllamaProvider を返すこと"""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        provider = get_llm_provider()
        assert isinstance(provider, OllamaProvider)

    def test_openrouter_provider_by_default(self, monkeypatch):
        """LLM_PROVIDER 未設定の場合は OpenRouterProvider を返すこと（本番挙動不変）"""
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        provider = get_llm_provider()
        assert isinstance(provider, OpenRouterProvider)

    def test_singleton_returns_same_ollama_instance(self, monkeypatch):
        """Ollama モードでもシングルトンが同じインスタンスを返すこと"""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        provider1 = get_llm_provider()
        provider2 = get_llm_provider()
        assert provider1 is provider2

    def test_reset_switches_provider_by_env(self, monkeypatch):
        """reset 後に環境変数を変えると別プロバイダへ切り替わること"""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        ollama_provider = get_llm_provider()
        assert isinstance(ollama_provider, OllamaProvider)

        reset_provider()
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        openrouter_provider = get_llm_provider()

        assert isinstance(openrouter_provider, OpenRouterProvider)
        assert ollama_provider is not openrouter_provider


class TestResolveLlmProvider:
    """resolve_llm_provider: 直接生成サイト向け解決ヘルパーのテスト"""

    def test_ollama_mode_returns_ollama_instance(self, monkeypatch):
        """LLM_PROVIDER=ollama 時は OllamaProvider を返すこと"""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        provider = resolve_llm_provider(api_key="ignored")
        assert isinstance(provider, OllamaProvider)

    def test_default_mode_returns_openrouter_instance(self, monkeypatch):
        """LLM_PROVIDER 未設定時は OpenRouterProvider を返すこと（本番挙動不変）"""
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        provider = resolve_llm_provider()
        assert isinstance(provider, OpenRouterProvider)

    def test_ollama_resolve_not_singleton(self, monkeypatch):
        """resolve_llm_provider はシングルトンとは別インスタンスを返し、
        close しても共有に影響しないこと"""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        resolved = resolve_llm_provider()
        shared = get_llm_provider()
        assert resolved is not shared

    def test_openrouter_resolve_passes_api_key(self, monkeypatch):
        """デフォルト時は api_key が OpenRouterProvider に渡ること"""
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        with patch("backend.llm.openrouter.OpenRouterProvider", autospec=True) as mock_cls:
            resolve_llm_provider(api_key="sk-test-key")
            mock_cls.assert_called_once_with(api_key="sk-test-key")
