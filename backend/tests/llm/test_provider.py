"""
backend.llm.provider モジュールのユニットテスト

LLMProvider 抽象基底クラス、get_llm_provider シングルトン関数、
および reset_provider 関数のテストを提供する。
"""

import pytest
from abc import ABC
from typing import AsyncGenerator, List
from unittest.mock import MagicMock, patch

from langchain_core.messages import BaseMessage

from backend.llm.provider import LLMProvider, get_llm_provider, reset_provider


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """各テストの前後でシングルトンをリセットし、テスト間の汚染を防止する"""
    reset_provider()
    yield
    reset_provider()


# ---------------------------------------------------------------------------
# LLMProvider 抽象クラステスト
# ---------------------------------------------------------------------------


class TestLLMProviderAbstract:
    """LLMProvider 抽象基底クラスのテストクラス"""

    def test_is_abstract_class(self):
        """LLMProvider が ABC のサブクラスであること"""
        assert issubclass(LLMProvider, ABC)

    def test_cannot_instantiate_directly(self):
        """LLMProvider を直接インスタンス化できないこと"""
        with pytest.raises(TypeError, match="abstract method"):
            LLMProvider()

    def test_has_abstract_generate_method(self):
        """LLMProvider に generate 抽象メソッドが定義されていること"""
        assert "generate" in LLMProvider.__abstractmethods__

    def test_has_abstract_stream_method(self):
        """LLMProvider に stream 抽象メソッドが定義されていること"""
        assert "stream" in LLMProvider.__abstractmethods__

    def test_has_abstract_get_langchain_llm_method(self):
        """LLMProvider に get_langchain_llm 抽象メソッドが定義されていること"""
        assert "get_langchain_llm" in LLMProvider.__abstractmethods__

    def test_abstract_methods_count(self):
        """LLMProvider の抽象メソッドが 3 つであること"""
        assert len(LLMProvider.__abstractmethods__) == 3


# ---------------------------------------------------------------------------
# LLMProvider 具象サブクラステスト
# ---------------------------------------------------------------------------


class _MockLLMProvider(LLMProvider):
    """テスト用の LLMProvider 具象実装"""

    async def generate(
        self,
        messages: List[BaseMessage],
        config=None,
    ) -> str:
        return "mock response"

    async def stream(
        self,
        messages: List[BaseMessage],
        config=None,
    ) -> AsyncGenerator[str, None]:
        yield "mock"
        yield " chunk"

    def get_langchain_llm(self, config=None):
        return MagicMock()


class TestConcreteSubclass:
    """LLMProvider 具象サブクラスのテストクラス"""

    def test_concrete_subclass_can_be_instantiated(self):
        """全抽象メソッドを実装したサブクラスをインスタンス化できること"""
        provider = _MockLLMProvider()
        assert isinstance(provider, LLMProvider)

    @pytest.mark.asyncio
    async def test_concrete_generate_returns_string(self):
        """具象サブクラスの generate が文字列を返すこと"""
        provider = _MockLLMProvider()
        result = await provider.generate([])
        assert result == "mock response"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_concrete_stream_yields_chunks(self):
        """具象サブクラスの stream がチャンクを yield すること"""
        provider = _MockLLMProvider()
        chunks = []
        async for chunk in provider.stream([]):
            chunks.append(chunk)
        assert chunks == ["mock", " chunk"]

    def test_concrete_get_langchain_llm_returns_value(self):
        """具象サブクラスの get_langchain_llm が値を返すこと"""
        provider = _MockLLMProvider()
        llm = provider.get_langchain_llm()
        assert llm is not None

    def test_partial_implementation_cannot_be_instantiated(self):
        """一部の抽象メソッドのみ実装したサブクラスはインスタンス化できないこと"""

        class _PartialProvider(LLMProvider):
            async def generate(self, messages, config=None):
                return ""

            # stream と get_langchain_llm が未実装

        with pytest.raises(TypeError):
            _PartialProvider()


# ---------------------------------------------------------------------------
# get_llm_provider シングルトンテスト
# ---------------------------------------------------------------------------


class TestGetLLMProvider:
    """get_llm_provider 関数のテストクラス"""

    @patch("backend.llm.openrouter.OpenRouterProvider.__init__", return_value=None)
    def test_returns_llm_provider_instance(self, mock_init):
        """get_llm_provider が LLMProvider インスタンスを返すこと"""
        provider = get_llm_provider()
        assert isinstance(provider, LLMProvider)

    @patch("backend.llm.openrouter.OpenRouterProvider.__init__", return_value=None)
    def test_returns_same_instance_on_second_call(self, mock_init):
        """get_llm_provider が 2 回目の呼び出しで同じインスタンスを返すこと（シングルトン）"""
        provider1 = get_llm_provider()
        provider2 = get_llm_provider()
        assert provider1 is provider2
        # OpenRouterProvider.__init__ は 1 回だけ呼ばれること
        assert mock_init.call_count == 1

    @patch("backend.llm.openrouter.OpenRouterProvider.__init__", return_value=None)
    def test_singleton_creates_openrouter_provider(self, mock_init):
        """get_llm_provider が OpenRouterProvider を生成すること"""
        get_llm_provider()
        mock_init.assert_called_once_with()


# ---------------------------------------------------------------------------
# reset_provider テスト
# ---------------------------------------------------------------------------


class TestResetProvider:
    """reset_provider 関数のテストクラス"""

    @patch("backend.llm.openrouter.OpenRouterProvider.__init__", return_value=None)
    def test_reset_clears_singleton(self, mock_init):
        """reset_provider がシングルトンインスタンスをクリアすること"""
        provider1 = get_llm_provider()
        reset_provider()

        # リセット後、新しいインスタンスが作成されること
        provider2 = get_llm_provider()

        assert provider1 is not provider2
        assert mock_init.call_count == 2

    def test_reset_without_prior_init_does_not_raise(self):
        """初期化前の reset_provider がエラーを送出しないこと"""
        # autouse fixture が既にリセットしているので、もう一度呼んでもエラーにならない
        reset_provider()  # 例外が発生しなければ成功

    @patch("backend.llm.openrouter.OpenRouterProvider.__init__", return_value=None)
    def test_multiple_resets_are_idempotent(self, mock_init):
        """reset_provider を複数回呼んでも冪等であること"""
        get_llm_provider()

        reset_provider()
        reset_provider()
        reset_provider()

        # 再取得で新しいインスタンスが作成される
        provider = get_llm_provider()
        assert provider is not None
        # 初回 + 再取得 = 2 回
        assert mock_init.call_count == 2

    @patch("backend.llm.openrouter.OpenRouterProvider.__init__", return_value=None)
    def test_after_reset_get_provider_creates_new_instance(self, mock_init):
        """reset 後の get_llm_provider が新しいインスタンスを生成すること"""
        p1 = get_llm_provider()
        assert isinstance(p1, LLMProvider)

        reset_provider()

        p2 = get_llm_provider()
        assert isinstance(p2, LLMProvider)
        assert p1 is not p2
        assert mock_init.call_count == 2
