"""
GeneralKnowledgeAgent のユニットテスト
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent


class TestGeneralKnowledgeAgent:
    """GeneralKnowledgeAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        # 環境変数を設定してモックする
        os.environ["GOOGLE_API_KEY"] = "test_dummy_api_key"
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

        # WebSearchToolとOpenRouterProviderをモック
        with patch("backend.agents.general_knowledge_agent.WebSearchTool"):
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
        assert self.agent._should_use_web_search("recent news about startups") is True

    def test_should_use_web_search_with_trend_keyword(self):
        """「トレンド」キーワードでWeb検索が必要と判定されるかテスト"""
        assert self.agent._should_use_web_search("現在のトレンドは?") is True
        assert self.agent._should_use_web_search("current technology trends") is True

    def test_should_not_use_web_search_for_general_query(self):
        """一般的な質問ではWeb検索不要と判定されるかテスト"""
        assert self.agent._should_use_web_search("エンジニアカフェについて教えて") is False
        assert self.agent._should_use_web_search("what is engineer cafe") is False

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


class TestGeneralKnowledgeAgentIntegration:
    """GeneralKnowledgeAgent の統合テスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["GOOGLE_API_KEY"] = "test_dummy_api_key"
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
            return_value="[helpful]これはテスト回答です。Engineer Cafeについての情報をお伝えします。"
        )

        # エージェント初期化
        with patch(
            "backend.agents.general_knowledge_agent.WebSearchTool",
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
