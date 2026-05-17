"""
GeneralKnowledgeAgent のユニットテスト
"""

import os
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
from backend.llm.openrouter import LLMResponseText


class TestGeneralKnowledgeAgent:
    """GeneralKnowledgeAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        # 環境変数を設定してモックする
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

        # WebSearchToolとOpenRouterProviderをモック
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.OpenRouterProvider"):
                with patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"):
                    self.agent = GeneralKnowledgeAgent()

    def test_should_use_web_search_with_latest_keyword(self):
        """「最新」キーワードでWeb検索が必要と判定されるかテスト"""
        assert self.agent._should_use_web_search("最新のAI技術について教えて") is True
        assert self.agent._should_use_web_search("latest AI trends") is True

    def test_should_use_web_search_with_news_keyword(self):
        """「ニュース」キーワードでWeb検索が必要と判定されるかテスト"""
        assert self.agent._should_use_web_search("今日のニュースは?") is True
        assert self.agent._should_use_web_search("latest news about startups") is True

    def test_should_use_web_search_with_trend_keyword(self):
        """「トレンド」キーワードでWeb検索が必要と判定されるかテスト"""
        assert self.agent._should_use_web_search("現在のAI動向は?") is True
        assert self.agent._should_use_web_search("current technology updates") is True

    def test_should_not_use_web_search_for_general_query(self):
        """一般的な質問ではWeb検索不要と判定されるかテスト"""
        assert self.agent._should_use_web_search("エンジニアカフェについて教えて") is False
        assert self.agent._should_use_web_search("what is engineer cafe") is False
        assert self.agent._should_use_web_search("AIとは何ですか？") is False

    def test_calculate_confidence_with_kb_and_web(self):
        """ナレッジベース + Web検索の信頼度をテスト"""
        sources = ["knowledge_base", "web_search"]
        assert self.agent._calculate_confidence(sources) == 0.9

    def test_calculate_confidence_with_kb_only(self):
        """ナレッジベースのみの信頼度をテスト"""
        sources = ["knowledge_base"]
        assert self.agent._calculate_confidence(sources) == 0.8

    def test_calculate_confidence_with_web_only(self):
        """Web検索のみの信頼度をテスト"""
        sources = ["web_search"]
        assert self.agent._calculate_confidence(sources) == 0.6

    def test_calculate_confidence_with_no_sources(self):
        """ソースなしの信頼度をテスト"""
        sources = []
        assert self.agent._calculate_confidence(sources) == 0.3

    def test_extract_emotion_sad(self):
        """[sad]タグの抽出をテスト"""
        text = "[sad]申し訳ございません、情報が見つかりませんでした。"
        assert self.agent._extract_emotion(text) == "sad"

    def test_extract_emotion_happy(self):
        """[happy]タグの抽出をテスト"""
        text = "[happy]見つかりました!"
        assert self.agent._extract_emotion(text) == "happy"

    def test_extract_emotion_relaxed(self):
        """[relaxed]タグの抽出をテスト"""
        text = "[relaxed]ゆっくり説明しますね。"
        assert self.agent._extract_emotion(text) == "relaxed"

    def test_extract_emotion_surprised(self):
        """[surprised]タグの抽出をテスト"""
        text = "[surprised]おや、興味深い質問ですね!"
        assert self.agent._extract_emotion(text) == "surprised"

    def test_extract_emotion_apologetic(self):
        """[apologetic]タグの抽出をテスト"""
        text = "[apologetic]申し訳ございません。"
        assert self.agent._extract_emotion(text) == "apologetic"

    def test_extract_emotion_default_neutral(self):
        """感情タグなしの場合neutralが返されるかテスト"""
        text = "普通の回答です。"
        assert self.agent._extract_emotion(text) == "neutral"

    def test_handle_error_japanese(self):
        """日本語エラーハンドリングをテスト"""
        response = self.agent._handle_error("ja")

        assert "申し訳ございません" in response["answer"]
        assert "エラーが発生しました" in response["answer"]
        assert response["emotion"] == "apologetic"
        assert response["metadata"]["agent"] == "GeneralKnowledgeAgent"
        assert response["metadata"]["status"] == "error"
        assert response["metadata"]["error"] == "internal_error"

    def test_handle_error_english(self):
        """英語エラーハンドリングをテスト"""
        response = self.agent._handle_error("en")

        assert "sorry" in response["answer"].lower()
        assert "wrong" in response["answer"].lower()
        assert response["emotion"] == "apologetic"
        assert response["metadata"]["agent"] == "GeneralKnowledgeAgent"
        assert response["metadata"]["status"] == "error"

    def test_assistant_profile_response_never_self_discloses_provider(self):
        response = self.agent._assistant_profile_response("ja")

        assert "エンナビ" in response["answer"]
        assert "Google" not in response["answer"]
        assert "OpenAI" not in response["answer"]
        assert response["metadata"]["query_type"] == "assistant_profile"
        assert response["metadata"]["provider_called"] is False

    def test_daily_conversation_response_is_deterministic_no_search(self):
        response = self.agent._daily_conversation_response("少し雑談して", "ja")

        assert response["metadata"]["query_type"] == "daily_conversation"
        assert response["metadata"]["web_search_used"] is False
        assert response["metadata"]["provider_called"] is False

    def test_resolve_general_mode_splits_current_info_and_general_light(self):
        assert self.agent._resolve_general_mode("今日の福岡の天気は？", "general") == "current_info"
        assert self.agent._resolve_general_mode("Pythonって何？", "general") == "general_light"
        assert (
            self.agent._resolve_general_mode("弁証法的に比較分析してください", "general")
            == "deep_reasoning"
        )

    def test_normalize_weather_query_defaults_to_fukuoka_tenjin(self):
        normalized = self.agent._normalize_current_info_query("今日の天気は？")

        assert "福岡市" in normalized
        assert "天神" in normalized


class TestGeneralKnowledgeAgentIntegration:
    """GeneralKnowledgeAgent の統合テスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

        # 統合テスト用のモック（AsyncMock使用）
        # RAG検索のモック
        self.mock_rag_search = MagicMock()
        self.mock_rag_search.search = AsyncMock(
            return_value={
                "success": True,
                "data": {"context": "Engineer Cafeは福岡のテックコミュニティです。"},
            }
        )

        # Web検索のモック
        self.mock_web_search = MagicMock()
        self.mock_web_search.search = AsyncMock(
            return_value={
                "success": True,
                "text": "最新のAI技術に関する情報です。",
                "sources": [{"uri": "https://example.com", "title": "Example"}],
            }
        )

        # OpenRouterProviderのモック
        self.mock_provider = MagicMock()
        self.mock_provider.generate = AsyncMock(
            return_value=LLMResponseText(
                "[helpful]これはテスト回答です。Engineer Cafeについての情報をお伝えします。",
                {
                    "provider": "openrouter",
                    "model": "google/gemini-3.1-flash-lite-preview",
                    "llm_latency_ms": 45,
                },
            )
        )

        # エージェント初期化
        with patch(
            "backend.agents.general_knowledge_agent.TavilySearchTool",
            return_value=self.mock_web_search,
        ):
            with patch(
                "backend.agents.general_knowledge_agent.OpenRouterProvider",
                return_value=self.mock_provider,
            ):
                with patch(
                    "backend.agents.general_knowledge_agent.EnhancedRAGSearch",
                    return_value=self.mock_rag_search,
                ):
                    self.agent = GeneralKnowledgeAgent()

    @pytest.mark.asyncio
    async def test_answer_general_query_basic(self):
        """基本的な一般質問への回答をテスト"""
        result = await self.agent.answer_general_query(
            query="エンジニアカフェについて教えてください", language="ja", session_id="test_session"
        )

        # 回答が返されることを確認
        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

        # 感情タグが設定されていることを確認
        assert "emotion" in result
        assert result["emotion"] in [
            "neutral",
            "happy",
            "sad",
            "surprised",
            "relaxed",
            "apologetic",
            "helpful",
        ]

        # メタデータが設定されていることを確認
        assert "metadata" in result
        assert result["metadata"]["agent"] == "GeneralKnowledgeAgent"
        assert "confidence" in result["metadata"]
        assert 0 <= result["metadata"]["confidence"] <= 1
        assert result["metadata"]["provider"] == "openrouter"
        assert result["metadata"]["model"] == "google/gemini-3.1-flash-lite-preview"
        assert result["metadata"]["llm_latency_ms"] == 45

    @pytest.mark.asyncio
    async def test_answer_general_query_english(self):
        """英語の一般質問への回答をテスト"""
        result = await self.agent.answer_general_query(
            query="What is Engineer Cafe?", language="en", session_id="test_session"
        )

        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert result["metadata"]["agent"] == "GeneralKnowledgeAgent"

    @pytest.mark.asyncio
    async def test_answer_general_query_with_session_id(self):
        """セッションIDを含む質問への回答をテスト"""
        session_id = "test_session_123"
        result = await self.agent.answer_general_query(
            query="福岡のテックシーンについて教えて", language="ja", session_id=session_id
        )

        assert "answer" in result
        assert "metadata" in result

    @pytest.mark.asyncio
    async def test_answer_query_assistant_profile_does_not_call_provider_or_search(self):
        result = await self.agent.answer_query(
            query="あなたの名前は？",
            language="ja",
            session_id="test_session",
            query_type="assistant_profile",
        )

        assert result["metadata"]["query_type"] == "assistant_profile"
        assert result["metadata"]["web_search_used"] is False
        self.mock_provider.generate.assert_not_called()
        self.mock_web_search.search.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_answer_query_daily_conversation_does_not_call_provider_or_search(self):
        started = time.perf_counter()
        result = await self.agent.answer_query(
            query="今日は少し疲れた",
            language="ja",
            session_id="test_session",
            query_type="daily_conversation",
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        assert result["metadata"]["query_type"] == "daily_conversation"
        assert result["metadata"]["web_search_used"] is False
        assert result["metadata"]["rag_used"] is False
        assert result["metadata"]["provider_called"] is False
        assert elapsed_ms < 100
        self.mock_provider.generate.assert_not_called()
        self.mock_web_search.search.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_answer_query_current_weather_uses_web_search(self):
        self.mock_web_search.search = AsyncMock(
            return_value={
                "success": True,
                "text": "福岡市天神の今日の天気は晴れ、気温は20度前後です。",
                "sources": [{"uri": "https://example.com/weather", "title": "Weather"}],
            }
        )

        result = await self.agent.answer_query(
            query="今日の福岡の天気は？",
            language="ja",
            session_id="test_session",
            query_type="current_info",
        )

        assert result["metadata"]["query_type"] == "current_info"
        assert result["metadata"]["web_search_used"] is True
        self.mock_web_search.search.assert_awaited_once()
        self.mock_provider.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_general_light_does_not_search_when_rag_misses(self):
        self.mock_rag_search.search = AsyncMock(
            return_value={"success": False, "data": {"context": "", "results": []}}
        )

        result = await self.agent.answer_query(
            query="Pythonって何？",
            language="ja",
            session_id="test_session",
            query_type="general",
        )

        assert result["metadata"]["query_type"] == "general_light"
        assert result["metadata"]["web_search_used"] is False
        self.mock_web_search.search.assert_not_called()
        self.mock_provider.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_consultation_query_type_uses_consultation_rag_category(self):
        result = await self.agent.answer_query(
            query="コミュニティマネージャーに相談できることは？",
            language="ja",
            session_id="test_session",
            query_type="consultation",
        )

        assert result["metadata"]["sources"] == ["knowledge_base"]
        self.mock_rag_search.search.assert_awaited_once()
        assert self.mock_rag_search.search.await_args.kwargs["category"] == "consultation"

    @pytest.mark.asyncio
    async def test_deep_reasoning_uses_explicit_model_case(self):
        result = await self.agent.answer_query(
            query="弁証法的に比較分析してください",
            language="ja",
            session_id="test_session",
            query_type="general",
        )

        assert result["metadata"]["query_type"] == "deep_reasoning"
        assert result["metadata"]["model_use_case"] == "deep_reasoning"
        self.mock_web_search.search.assert_not_called()
        called_config = self.mock_provider.generate.await_args.kwargs["config"]
        assert called_config is not self.agent.model_config
