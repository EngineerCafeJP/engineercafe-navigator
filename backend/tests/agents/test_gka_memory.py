"""GeneralKnowledgeAgent メモリ統合テスト"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestGKAMemoryInit:
    """GKA メモリ初期化テスト"""

    def setup_method(self):
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

    def test_gka_init_with_memory_system(self):
        """memory_system付きで初期化"""
        mock_memory = MagicMock()
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.OpenRouterProvider"):
                with patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"):
                    from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

                    agent = GeneralKnowledgeAgent(memory_system=mock_memory)
                    assert agent.memory_system is mock_memory

    def test_gka_init_without_memory_system(self):
        """memory_systemなしで初期化"""
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.OpenRouterProvider"):
                with patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"):
                    from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

                    agent = GeneralKnowledgeAgent()
                    assert agent.memory_system is None


class TestGKAAnswerQueryDispatch:
    """answer_query ディスパッチテスト"""

    def setup_method(self):
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

    def _create_agent(self, memory_system=None):
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.OpenRouterProvider"):
                with patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"):
                    from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

                    return GeneralKnowledgeAgent(memory_system=memory_system)

    @pytest.mark.asyncio
    async def test_answer_query_dispatches_to_memory(self):
        """query_type='memory'でメモリハンドラ呼び出し"""
        agent = self._create_agent(memory_system=MagicMock())
        agent._handle_memory_query = AsyncMock(
            return_value={"answer": "メモリ回答", "emotion": "relaxed", "metadata": {}}
        )
        long_term_memory = [{"data": "ユーザーの名前は山田次郎です", "type": "visitor_name"}]

        result = await agent.answer_query(
            "さっき何を聞いた？",
            query_type="memory",
            long_term_memory=long_term_memory,
        )
        agent._handle_memory_query.assert_called_once_with(
            "さっき何を聞いた？",
            "",
            "ja",
            long_term_memory=long_term_memory,
        )
        assert result["answer"] == "メモリ回答"

    @pytest.mark.asyncio
    async def test_answer_query_dispatches_to_general(self):
        """query_type='general'で一般ハンドラ呼び出し"""
        agent = self._create_agent()
        agent.answer_general_query = AsyncMock(
            return_value={"answer": "一般回答", "emotion": "neutral", "metadata": {}}
        )

        long_term_memory = [{"data": "ユーザーは展示に興味があります", "type": "interest"}]
        result = await agent.answer_query(
            "エンジニアカフェとは？",
            query_type="general",
            long_term_memory=long_term_memory,
        )
        agent.answer_general_query.assert_called_once_with(
            "エンジニアカフェとは？",
            "ja",
            None,
            None,
            None,
            long_term_memory=long_term_memory,
            query_type="general",
        )
        assert result["answer"] == "一般回答"


class TestGKAHandleMemoryQuery:
    """メモリクエリ処理テスト"""

    def setup_method(self):
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

    def _create_agent(self, memory_system=None):
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.OpenRouterProvider") as mock_prov:
                mock_prov.return_value.generate = AsyncMock(return_value="テスト回答")
                with patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"):
                    from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

                    return GeneralKnowledgeAgent(memory_system=memory_system)

    @pytest.mark.asyncio
    async def test_handle_memory_query_success(self):
        """メモリクエリ成功"""
        mock_memory = MagicMock()
        mock_memory.get_context = AsyncMock(
            return_value={
                "recent_messages": [{"role": "user", "content": "テスト"}],
                "context_string": "テスト会話",
            }
        )

        agent = self._create_agent(memory_system=mock_memory)
        result = await agent._handle_memory_query("さっき何を聞いた？", "session1", "ja")

        assert result["metadata"]["status"] == "success"
        assert result["metadata"]["query_type"] == "question_history"
        assert result["metadata"]["message_count"] == 1

    @pytest.mark.asyncio
    async def test_handle_memory_query_no_memory_system(self):
        """メモリシステムなし"""
        agent = self._create_agent(memory_system=None)
        result = await agent._handle_memory_query("さっき何を聞いた？", "session1", "ja")

        assert result["emotion"] == "sad"
        assert result["metadata"]["status"] == "memory_unavailable"

    @pytest.mark.asyncio
    async def test_handle_memory_query_no_history(self):
        """履歴なし"""
        mock_memory = MagicMock()
        mock_memory.get_context = AsyncMock(return_value={"recent_messages": []})

        agent = self._create_agent(memory_system=mock_memory)
        result = await agent._handle_memory_query("さっき何を聞いた？", "session1", "ja")

        assert result["emotion"] == "sad"
        assert result["metadata"]["status"] == "no_history"

    @pytest.mark.asyncio
    async def test_handle_memory_write_query_without_history_acknowledges(self):
        """初回の記憶登録依頼は履歴なし応答にしない"""
        mock_memory = MagicMock()
        mock_memory.get_context = AsyncMock(return_value={"recent_messages": []})

        agent = self._create_agent(memory_system=mock_memory)
        result = await agent._handle_memory_query(
            "私の名前は佐藤花子です。覚えてください。",
            "session1",
            "ja",
        )

        assert result["emotion"] == "helpful"
        assert result["metadata"]["status"] == "success"
        assert result["metadata"]["query_type"] == "memory_write"
        assert "覚えて" in result["answer"]
        agent.provider.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_memory_query_uses_long_term_memory_without_session_history(self):
        """別セッション由来の長期メモリを会話履歴プロンプトへ注入する"""
        mock_memory = MagicMock()
        mock_memory.get_context = AsyncMock(
            return_value={
                "recent_messages": [],
                "context_string": "",
            }
        )

        agent = self._create_agent(memory_system=mock_memory)
        result = await agent._handle_memory_query(
            "私の名前を覚えてますか？",
            "session2",
            "ja",
            long_term_memory=[
                {
                    "data": "ユーザーの名前は山田次郎です",
                    "type": "visitor_name",
                    "confidence": 0.95,
                }
            ],
        )

        assert result["metadata"]["status"] == "success"
        assert result["metadata"]["long_term_memory_count"] == 1
        call_kwargs = agent.provider.generate.call_args.kwargs
        prompt = call_kwargs["messages"][0].content
        assert "長期メモリ" in prompt
        assert "山田次郎" in prompt

    @pytest.mark.asyncio
    async def test_handle_memory_query_error(self):
        """メモリクエリエラー"""
        mock_memory = MagicMock()
        mock_memory.get_context = AsyncMock(side_effect=Exception("DB Error"))

        agent = self._create_agent(memory_system=mock_memory)
        result = await agent._handle_memory_query("さっき何を聞いた？", "session1", "ja")

        assert result["emotion"] == "surprised"
        assert result["metadata"]["status"] == "error"


class TestGKADetectMemoryQueryType:
    """メモリ質問タイプ判定テスト"""

    def setup_method(self):
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

    def _create_agent(self):
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.OpenRouterProvider"):
                with patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"):
                    from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

                    return GeneralKnowledgeAgent()

    def test_detect_question_history(self):
        agent = self._create_agent()
        assert agent._detect_memory_query_type("さっき何を聞いた？") == "question_history"
        assert agent._detect_memory_query_type("what did i ask?") == "question_history"

    def test_detect_answer_history(self):
        agent = self._create_agent()
        assert agent._detect_memory_query_type("さっきの答えは？") == "answer_history"
        assert agent._detect_memory_query_type("what did you say?") == "answer_history"

    def test_detect_other_option(self):
        agent = self._create_agent()
        assert agent._detect_memory_query_type("もう一つの方は？") == "other_option"
        assert agent._detect_memory_query_type("the other one please") == "other_option"

    def test_detect_general_memory(self):
        agent = self._create_agent()
        assert agent._detect_memory_query_type("覚えてる？") == "general_memory"
        assert agent._detect_memory_query_type("remember anything?") == "general_memory"


class TestGKADetermineMemoryEmotion:
    """メモリ感情決定テスト"""

    def setup_method(self):
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

    def _create_agent(self):
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.OpenRouterProvider"):
                with patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"):
                    from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

                    return GeneralKnowledgeAgent()

    def test_no_messages_returns_sad(self):
        agent = self._create_agent()
        assert agent._determine_memory_emotion({"recent_messages": []}, "general_memory") == "sad"

    def test_other_option_returns_happy(self):
        agent = self._create_agent()
        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        assert agent._determine_memory_emotion(context, "other_option") == "happy"

    def test_question_history_returns_relaxed(self):
        agent = self._create_agent()
        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        assert agent._determine_memory_emotion(context, "question_history") == "relaxed"

    def test_answer_history_returns_relaxed(self):
        agent = self._create_agent()
        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        assert agent._determine_memory_emotion(context, "answer_history") == "relaxed"

    def test_general_memory_returns_neutral(self):
        agent = self._create_agent()
        context = {"recent_messages": [{"role": "user", "content": "test"}]}
        assert agent._determine_memory_emotion(context, "general_memory") == "neutral"


class TestOrchestratorMemoryRouting:
    """orchestratorがmemory→general_knowledgeにルーティングするテスト"""

    def setup_method(self):
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

    @pytest.mark.asyncio
    async def test_routing_memory_to_gka(self):
        """メモリ関連質問がgeneral_knowledgeにルーティングされること"""
        with patch("backend.agents.orchestrator_agent.OpenRouterProvider"):
            from backend.agents.orchestrator_agent import OrchestratorAgent

            orchestrator = OrchestratorAgent()
            decision = await orchestrator.decide_next_agent(
                query="さっき何を聞いた？", session_id="test"
            )

            assert decision.next_agent == "general_knowledge"
            assert decision.category == "memory"
            assert decision.request_type == "memory"
