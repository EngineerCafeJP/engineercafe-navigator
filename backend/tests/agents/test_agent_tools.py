"""
Agent Tools テスト

@toolデコレーターで包んだエージェントツールのテスト。
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestAgentToolsBasic:
    """基本的なツール機能のテスト"""

    def test_get_all_agent_tools_returns_list(self):
        """get_all_agent_toolsがツールリストを返すことを確認"""
        from backend.agents.agent_tools import get_all_agent_tools

        tools = get_all_agent_tools()
        assert isinstance(tools, list)
        assert len(tools) == 6  # 6つのエージェントツール

    def test_get_domain_agent_tools_returns_subset(self):
        """get_domain_agent_toolsがドメインツールのみを返すことを確認"""
        from backend.agents.agent_tools import get_domain_agent_tools

        tools = get_domain_agent_tools()
        assert isinstance(tools, list)
        assert len(tools) == 4  # facility, business_info, event, general_knowledge

    def test_clear_agent_cache(self):
        """clear_agent_cacheがキャッシュをクリアすることを確認"""
        from backend.agents import agent_tools

        # キャッシュに何か入れる
        agent_tools._agent_cache["test"] = "value"
        assert "test" in agent_tools._agent_cache

        # クリア
        agent_tools.clear_agent_cache()
        assert "test" not in agent_tools._agent_cache


class TestFacilityQueryTool:
    """facility_query_toolのテスト"""

    @pytest.mark.asyncio
    @patch("backend.agents.agent_tools._get_facility_agent")
    async def test_facility_query_tool_calls_agent(self, mock_get_agent):
        """facility_query_toolがFacilityAgentを呼び出すことを確認"""
        from backend.agents.agent_tools import facility_query_tool, clear_agent_cache

        clear_agent_cache()

        mock_agent = AsyncMock()
        mock_agent.answer_facility_query = AsyncMock(
            return_value={"answer": "Wi-Fiは無料でご利用いただけます。", "emotion": "relaxed"}
        )
        mock_get_agent.return_value = mock_agent

        # ツール関数を直接呼び出し（@toolラッパーの内部関数）
        result = await facility_query_tool.coroutine(
            query="Wi-Fiは使えますか？", request_type="wifi", language="ja"
        )

        assert result == "Wi-Fiは無料でご利用いただけます。"
        mock_agent.answer_facility_query.assert_called_once_with(
            "Wi-Fiは使えますか？", "wifi", "ja", None
        )


class TestBusinessInfoTool:
    """business_info_toolのテスト"""

    @pytest.mark.asyncio
    @patch("backend.agents.agent_tools._get_business_info_agent")
    async def test_business_info_tool_calls_agent(self, mock_get_agent):
        """business_info_toolがBusinessInfoAgentを呼び出すことを確認"""
        from backend.agents.agent_tools import business_info_tool, clear_agent_cache

        clear_agent_cache()

        mock_agent = AsyncMock()
        mock_agent.answer_business_query = AsyncMock(
            return_value={"answer": "9時から22時まで営業しています。", "emotion": "informative"}
        )
        mock_get_agent.return_value = mock_agent

        result = await business_info_tool.coroutine(
            query="営業時間は？", request_type="hours", language="ja"
        )

        assert result == "9時から22時まで営業しています。"


class TestEventInfoTool:
    """event_info_toolのテスト"""

    @pytest.mark.asyncio
    @patch("backend.agents.agent_tools._get_event_agent")
    async def test_event_info_tool_calls_agent(self, mock_get_agent):
        """event_info_toolがEventAgentを呼び出すことを確認"""
        from backend.agents.agent_tools import event_info_tool, clear_agent_cache

        clear_agent_cache()

        mock_agent = AsyncMock()
        mock_agent.answer_event_query = AsyncMock(
            return_value={"answer": "今月はAI勉強会があります。", "emotion": "happy"}
        )
        mock_get_agent.return_value = mock_agent

        result = await event_info_tool.coroutine(query="今月のイベントは？", language="ja")

        assert result == "今月はAI勉強会があります。"


class TestGeneralKnowledgeTool:
    """general_knowledge_toolのテスト"""

    @pytest.mark.asyncio
    @patch("backend.agents.agent_tools._get_general_knowledge_agent")
    async def test_general_knowledge_tool_calls_agent(self, mock_get_agent):
        """general_knowledge_toolがGeneralKnowledgeAgentを呼び出すことを確認"""
        from backend.agents.agent_tools import general_knowledge_tool, clear_agent_cache

        clear_agent_cache()

        mock_agent = AsyncMock()
        mock_agent.answer_general_query = AsyncMock(
            return_value={"answer": "AIの最新トレンドは...", "emotion": "relaxed"}
        )
        mock_get_agent.return_value = mock_agent

        result = await general_knowledge_tool.coroutine(query="AIの最新トレンドは？", language="ja")

        assert result == "AIの最新トレンドは..."


class TestSlideActionTool:
    """slide_action_toolのテスト"""

    @pytest.mark.asyncio
    @patch("backend.agents.agent_tools._get_slide_agent")
    async def test_slide_action_tool_calls_agent(self, mock_get_agent):
        """slide_action_toolがSlideAgentを呼び出すことを確認"""
        from backend.agents.agent_tools import slide_action_tool, clear_agent_cache

        clear_agent_cache()

        mock_agent = AsyncMock()
        mock_agent.handle_slide_action = AsyncMock(
            return_value={"answer": "このスライドは...", "emotion": "neutral"}
        )
        mock_get_agent.return_value = mock_agent

        result = await slide_action_tool.coroutine(action="narrate", language="ja")

        assert result == "このスライドは..."


class TestMemoryQueryTool:
    """memory_query_toolのテスト"""

    @pytest.mark.asyncio
    @patch("backend.agents.agent_tools._get_memory_query_agent")
    async def test_memory_query_tool_calls_agent(self, mock_get_agent):
        """memory_query_toolがメモリ対応GeneralKnowledgeAgentを呼び出すことを確認"""
        from backend.agents.agent_tools import memory_query_tool, clear_agent_cache

        clear_agent_cache()

        mock_agent = AsyncMock()
        mock_agent.answer_query = AsyncMock(
            return_value={"answer": "営業時間について質問されていました。", "emotion": "relaxed"}
        )
        mock_get_agent.return_value = mock_agent

        result = await memory_query_tool.coroutine(
            query="さっき何を聞いた？", session_id="test-session", language="ja"
        )

        assert result == "営業時間について質問されていました。"
        mock_agent.answer_query.assert_awaited_once_with(
            query="さっき何を聞いた？",
            language="ja",
            session_id="test-session",
            query_type="memory",
        )


class TestToolMetadata:
    """ツールメタデータのテスト"""

    def test_facility_tool_has_docstring(self):
        """facility_query_toolにdocstringがあることを確認"""
        from backend.agents.agent_tools import facility_query_tool

        assert facility_query_tool.description is not None
        assert "Wi-Fi" in facility_query_tool.description

    def test_business_info_tool_has_docstring(self):
        """business_info_toolにdocstringがあることを確認"""
        from backend.agents.agent_tools import business_info_tool

        assert business_info_tool.description is not None
        assert "営業" in business_info_tool.description

    def test_all_tools_are_callable(self):
        """全ツールがcoroutine属性を持つことを確認"""
        from backend.agents.agent_tools import get_all_agent_tools

        for tool in get_all_agent_tools():
            assert hasattr(tool, "coroutine")
            assert callable(tool.coroutine)


class TestLazyInitialization:
    """遅延初期化のテスト"""

    @patch("backend.agents.facility_agent.FacilityAgent")
    def test_facility_agent_lazy_init(self, mock_agent_class):
        """FacilityAgentが遅延初期化されることを確認"""
        from backend.agents import agent_tools

        agent_tools.clear_agent_cache()

        # キャッシュが空であることを確認
        assert "facility" not in agent_tools._agent_cache

        # _get_facility_agentを呼び出すとエージェントが作成される
        mock_agent_class.return_value = Mock()
        agent = agent_tools._get_facility_agent()

        mock_agent_class.assert_called_once()
        assert "facility" in agent_tools._agent_cache

        # 2回目の呼び出しではキャッシュから返される
        agent2 = agent_tools._get_facility_agent()
        assert agent is agent2
        mock_agent_class.assert_called_once()  # 1回のみ
