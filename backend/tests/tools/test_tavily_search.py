"""TavilySearchTool のユニットテスト"""

import pytest
from unittest.mock import Mock, patch


class TestTavilySearchToolInit:
    """TavilySearchTool 初期化テスト"""

    @patch.dict("os.environ", {"TAVILY_API_KEY": ""}, clear=False)
    def test_init_without_api_key(self):
        """APIキーなしで初期化するとclient=Noneになること"""
        from backend.tools.tavily_search import TavilySearchTool

        tool = TavilySearchTool()
        assert tool.client is None
        assert tool.name == "tavily_search"

    @patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}, clear=False)
    def test_init_with_api_key_but_no_tavily_package(self):
        """tavily-pythonが未インストールの場合client=Noneになること"""
        with patch.dict("sys.modules", {"tavily": None}):
            from backend.tools.tavily_search import TavilySearchTool

            tool = TavilySearchTool()
            assert tool.client is None

    @patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}, clear=False)
    def test_init_with_api_key_success(self):
        """APIキーありかつtavilyパッケージありで正常初期化"""
        mock_client = Mock()
        mock_tavily_module = Mock()
        mock_tavily_module.TavilyClient.return_value = mock_client

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            from backend.tools.tavily_search import TavilySearchTool

            tool = TavilySearchTool()
            assert tool.client is mock_client


class TestTavilySearchToolSearch:
    """TavilySearchTool 検索テスト"""

    @pytest.mark.asyncio
    async def test_search_success(self):
        """Tavily検索成功"""
        from backend.tools.tavily_search import TavilySearchTool

        tool = TavilySearchTool.__new__(TavilySearchTool)
        tool.name = "tavily_search"
        tool.client = Mock()
        tool.client.search.return_value = {
            "answer": "テスト回答",
            "results": [{"url": "https://example.com", "title": "テスト", "content": "テスト内容"}],
        }

        result = await tool.search("テストクエリ")

        assert result["success"] is True
        assert "テスト回答" in result["text"]
        assert len(result["sources"]) == 1
        assert result["sources"][0]["uri"] == "https://example.com"
        assert result["sources"][0]["title"] == "テスト"
        called_query = tool.client.search.call_args.kwargs["query"]
        assert called_query.startswith("現在日時(JST): ")
        assert "検索クエリ: テストクエリ" in called_query

    @pytest.mark.asyncio
    async def test_search_success_no_answer(self):
        """Tavily検索成功(answerなし)"""
        from backend.tools.tavily_search import TavilySearchTool

        tool = TavilySearchTool.__new__(TavilySearchTool)
        tool.name = "tavily_search"
        tool.client = Mock()
        tool.client.search.return_value = {
            "answer": "",
            "results": [
                {"url": "https://example.com", "title": "テスト", "content": "内容A"},
                {"url": "https://example2.com", "title": "テスト2", "content": "内容B"},
            ],
        }

        result = await tool.search("テストクエリ")

        assert result["success"] is True
        assert "内容A" in result["text"]
        assert "内容B" in result["text"]
        assert len(result["sources"]) == 2

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_no_client(self):
        """クライアントなしの場合空結果を返す"""
        from backend.tools.tavily_search import TavilySearchTool

        tool = TavilySearchTool.__new__(TavilySearchTool)
        tool.name = "tavily_search"
        tool.client = None

        result = await tool.search("テスト")
        assert result["success"] is False
        assert result["text"] == ""
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        """Tavilyエラー時も空結果を返す"""
        from backend.tools.tavily_search import TavilySearchTool

        tool = TavilySearchTool.__new__(TavilySearchTool)
        tool.name = "tavily_search"
        tool.client = Mock()
        tool.client.search.side_effect = Exception("API Error")

        result = await tool.search("テスト")
        assert result["success"] is False
        assert result["text"] == ""


class TestTavilySearchToolShouldUseWebSearch:
    """should_use_web_search テスト"""

    def test_should_use_web_search_delegates(self):
        """Web検索判定がweb_searchモジュールに委譲されること"""
        from backend.tools.tavily_search import TavilySearchTool

        with patch("backend.tools.web_search.should_use_web_search", return_value=True) as mock_fn:
            assert TavilySearchTool.should_use_web_search("最新ニュース") is True
            mock_fn.assert_called_once_with("最新ニュース")

    def test_should_not_use_web_search(self):
        """Web検索不要と判定"""
        from backend.tools.tavily_search import TavilySearchTool

        with patch("backend.tools.web_search.should_use_web_search", return_value=False):
            assert TavilySearchTool.should_use_web_search("エンジニアカフェとは") is False
