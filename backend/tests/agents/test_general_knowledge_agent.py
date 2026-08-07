"""
GeneralKnowledgeAgent のユニットテスト
"""

import os
import time
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from zoneinfo import ZoneInfo
from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
from backend.llm.openrouter import LLMResponseText

DATE_ONLY_AGENT_CASES = [
    pytest.param("ja", "今日", "2026年5月18日", id="ja:bare-today"),
    pytest.param("ja", "本日", "2026年5月18日", id="ja:bare-honjitstu"),
    pytest.param("ja", "今日は何月何日ですか?", "2026年5月18日", id="ja:today-full"),
    pytest.param("ja", "今日の日付を教えて", "2026年5月18日", id="ja:today-date"),
    pytest.param("ja", "明日は何日ですか", "2026年5月19日", id="ja:tomorrow-day"),
    pytest.param("ja", "昨日は何曜日でしたか", "2026年5月17日", id="ja:yesterday-weekday"),
    pytest.param("ja", "今週は何日から何日まで?", "5月18日から5月24日", id="ja:this-week"),
    pytest.param("ja", "本日は何曜日ですか", "月曜日", id="ja:weekday"),
    pytest.param("ja", "明日の日付を教えて", "2026年5月19日", id="ja:tomorrow-date"),
    pytest.param("ja", "昨日の日付は?", "2026年5月17日", id="ja:yesterday-date"),
    pytest.param("en", "today", "Monday, May 18, 2026", id="en:bare-today"),
    pytest.param("en", "today's date?", "Monday, May 18, 2026", id="en:today-date"),
    pytest.param("en", "What is the date today?", "Monday, May 18, 2026", id="en:today-full"),
    pytest.param("en", "What date is it tomorrow?", "Tuesday, May 19, 2026", id="en:tomorrow-date"),
    pytest.param("en", "What day is it today?", "Monday, May 18, 2026", id="en:today-day"),
    pytest.param(
        "en",
        "What day of the week is tomorrow?",
        "Tuesday, May 19, 2026",
        id="en:tomorrow-weekday",
    ),
    pytest.param("en", "yesterday's date?", "Sunday, May 17, 2026", id="en:yesterday-date"),
    pytest.param("en", "What date was yesterday?", "Sunday, May 17, 2026", id="en:yesterday-full"),
    pytest.param("en", "this week", "May 18, 2026 through May 24, 2026", id="en:this-week"),
    pytest.param(
        "en", "What dates are this week?", "May 18, 2026 through May 24, 2026", id="en:week-dates"
    ),
    pytest.param("zh", "今天", "今天是日本时间2026年5月18日", id="zh:bare-today"),
    pytest.param("zh", "今天是几月几号？", "今天是日本时间2026年5月18日", id="zh:today-full"),
    pytest.param("zh", "今天日期是什么？", "今天是日本时间2026年5月18日", id="zh:today-date"),
    pytest.param("zh", "今天星期几？", "星期一", id="zh:weekday"),
    pytest.param("zh", "今天周几？", "星期一", id="zh:weekday-short"),
    pytest.param("zh", "明天是几号？", "明天是日本时间2026年5月19日", id="zh:tomorrow-day"),
    pytest.param("zh", "明天是幾月幾日？", "明天是日本时间2026年5月19日", id="zh:tomorrow-full"),
    pytest.param("zh", "昨天是星期几？", "昨天是日本时间2026年5月17日", id="zh:yesterday-weekday"),
    pytest.param("zh", "本周是哪几天？", "本周是日本时间2026年5月18日到5月24日", id="zh:this-week"),
    pytest.param(
        "zh",
        "這周是幾號到幾號？",
        "本周是日本时间2026年5月18日到5月24日",
        id="zh:week-range",
    ),
    pytest.param("ko", "오늘", "오늘은 일본 시간 기준 2026년 5월 18일", id="ko:bare-today"),
    pytest.param(
        "ko",
        "오늘 날짜 알려줘",
        "오늘은 일본 시간 기준 2026년 5월 18일",
        id="ko:today-date",
    ),
    pytest.param(
        "ko",
        "오늘은 몇 월 며칠인가요?",
        "오늘은 일본 시간 기준 2026년 5월 18일",
        id="ko:today-full",
    ),
    pytest.param("ko", "오늘은 무슨 요일인가요?", "월요일", id="ko:weekday"),
    pytest.param(
        "ko",
        "내일은 며칠이에요?",
        "내일은 일본 시간 기준 2026년 5월 19일",
        id="ko:tomorrow-day",
    ),
    pytest.param(
        "ko",
        "내일 날짜 알려줘",
        "내일은 일본 시간 기준 2026년 5월 19일",
        id="ko:tomorrow-date",
    ),
    pytest.param(
        "ko",
        "어제는 무슨 요일이었나요?",
        "어제는 일본 시간 기준 2026년 5월 17일",
        id="ko:yesterday-weekday",
    ),
    pytest.param(
        "ko",
        "어제 날짜가 뭐였죠?",
        "어제는 일본 시간 기준 2026년 5월 17일",
        id="ko:yesterday-date",
    ),
    pytest.param(
        "ko",
        "이번 주는 며칠부터 며칠까지예요?",
        "2026년 5월 18일부터 5월 24일까지",
        id="ko:this-week",
    ),
    pytest.param("ko", "금주 날짜 알려줘", "2026년 5월 18일부터 5월 24일까지", id="ko:week-date"),
]


class TestGeneralKnowledgeAgent:
    """GeneralKnowledgeAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        # 環境変数を設定してモックする
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_openrouter_key"

        # WebSearchToolとOpenRouterProviderをモック
        with patch("backend.agents.general_knowledge_agent.TavilySearchTool"):
            with patch("backend.agents.general_knowledge_agent.resolve_llm_provider"):
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

    def test_date_only_is_not_current_info(self):
        assert self.agent._is_current_info_query("今日は何月何日ですか？") is False
        assert self.agent._is_current_info_query("今日") is False
        assert self.agent._is_current_info_query("明日") is False
        assert self.agent._is_current_info_query("今週") is False
        assert self.agent._is_current_info_query("今日の福岡の天気は？") is True
        assert self.agent._is_current_info_query("今日のニュースは？") is True
        assert self.agent._is_current_info_query("today technology updates") is True

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
                "backend.agents.general_knowledge_agent.resolve_llm_provider",
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
    async def test_memory_query_recalls_session_seat_and_purpose_from_state_context(self):
        result = await self.agent.answer_query(
            query="この会話の最初に伝えた希望席と目的を覚えていますか。",
            language="ja",
            session_id="alpha-m-stm-session-test",
            query_type="memory",
            state_context={
                "recent_messages": [
                    {
                        "role": "user",
                        "content": (
                            "この会話では、私の希望席は窓側で、"
                            "目的は集中作業です。覚えてください。"
                        ),
                        "metadata": {},
                    },
                ],
                "context_string": "セッション内の会話履歴: ユーザー: 希望席は窓側、目的は集中作業",
                "stm_source": "langgraph_checkpointer",
            },
        )

        assert "窓" in result["answer"]
        assert "集中" in result["answer"]
        assert result["metadata"]["provider_called"] is False
        self.mock_provider.generate.assert_not_called()
        self.mock_web_search.search.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_query_recalls_window_summary_user_facts(self):
        result = await self.agent.answer_query(
            query="この会話の最初に伝えた希望席と目的を覚えていますか。",
            language="ja",
            session_id="alpha-m-stm-session-test",
            query_type="memory",
            state_context={
                "recent_messages": [
                    {
                        "role": "assistant",
                        "content": (
                            "[Previous 22 messages summarized: Important earlier user facts: "
                            "この会話では、私の希望席は窓側で、目的は集中作業です。覚えてください。]"
                        ),
                        "metadata": {},
                    },
                ],
                "context_string": "",
                "stm_source": "langgraph_checkpointer",
            },
        )

        assert "窓" in result["answer"]
        assert "集中" in result["answer"]
        assert result["metadata"]["provider_called"] is False
        self.mock_provider.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_query_recalls_reception_practical_context(self):
        result = await self.agent.answer_query(
            query="私の希望席と利用目的を確認してください。",
            language="ja",
            session_id="alpha-m-recv-session-test",
            query_type="memory",
            state_context={
                "recent_messages": [
                    {
                        "role": "user",
                        "content": "窓側の席がいいです。コワーキングスペースを使いたいです。",
                        "metadata": {},
                    },
                ],
                "context_string": "",
                "stm_source": "langgraph_checkpointer",
            },
        )

        assert "窓" in result["answer"]
        assert "コワーキング" in result["answer"]
        assert result["metadata"]["provider_called"] is False
        self.mock_provider.generate.assert_not_called()
        self.mock_web_search.search.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_query_does_not_treat_assistant_clarification_as_user_fact(self):
        result = await self.agent.answer_query(
            query="私の希望席と利用目的を確認してください。",
            language="ja",
            session_id="alpha-m-recv-session-test",
            query_type="memory",
            state_context={
                "recent_messages": [
                    {
                        "role": "assistant",
                        "content": "希望席は窓側、利用目的はコワーキングでよろしいですか？",
                        "metadata": {},
                    },
                ],
                "context_string": (
                    "セッション内の会話履歴:\n"
                    "アシスタント: 希望席は窓側、利用目的はコワーキングでよろしいですか？"
                ),
                "stm_source": "langgraph_checkpointer",
            },
        )

        assert result["metadata"]["provider"] == "openrouter"
        assert "希望席は窓側、利用目的はコワーキングです" not in result["answer"]
        self.mock_provider.generate.assert_called_once()

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
    async def test_answer_query_date_only_uses_system_clock_without_search(self):
        fixed_now = datetime(2026, 5, 18, 10, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

        with patch("backend.agents.general_knowledge_agent.get_now_jst", return_value=fixed_now):
            result = await self.agent.answer_query(
                query="今日は何月何日ですか？",
                language="ja",
                session_id="test_session",
                query_type="current_info",
            )

        assert "2026年5月18日" in result["answer"]
        assert result["metadata"]["query_type"] == "current-time"
        assert result["metadata"]["sources"] == ["system_clock"]
        assert result["metadata"]["web_search_used"] is False
        assert result["metadata"]["provider_called"] is False
        self.mock_web_search.search.assert_not_called()
        self.mock_provider.generate.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_answer_query_tomorrow_date_only_uses_system_clock_without_search(self):
        fixed_now = datetime(2026, 5, 18, 10, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

        with patch("backend.agents.general_knowledge_agent.get_now_jst", return_value=fixed_now):
            result = await self.agent.answer_query(
                query="明日は何日ですか",
                language="ja",
                session_id="test_session",
                query_type="current_info",
            )

        assert "2026年5月19日" in result["answer"]
        assert result["metadata"]["query_type"] == "current-time"
        self.mock_web_search.search.assert_not_called()
        self.mock_provider.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_answer_query_current_time_uses_system_clock_without_search(self):
        fixed_now = datetime(2026, 5, 24, 21, 40, 11, tzinfo=ZoneInfo("Asia/Tokyo"))

        with patch("backend.agents.general_knowledge_agent.get_now_jst", return_value=fixed_now):
            result = await self.agent.answer_query(
                query="今何時ですか?",
                language="ja",
                session_id="test_session",
                query_type="current-time",
            )

        assert "2026年5月24日" in result["answer"]
        assert "21時40分" in result["answer"]
        assert result["metadata"]["query_type"] == "current-time"
        assert result["metadata"]["sources"] == ["system_clock"]
        assert result["metadata"]["web_search_used"] is False
        assert result["metadata"]["rag_used"] is False
        assert result["metadata"]["provider_called"] is False
        assert result["metadata"]["timezone"] == "Asia/Tokyo"
        self.mock_web_search.search.assert_not_called()
        self.mock_provider.generate.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_answer_query_current_time_natural_english_uses_system_clock(self):
        fixed_now = datetime(2026, 5, 24, 21, 40, 11, tzinfo=ZoneInfo("Asia/Tokyo"))

        with patch("backend.agents.general_knowledge_agent.get_now_jst", return_value=fixed_now):
            result = await self.agent.answer_query(
                query="What time is it now?",
                language="en",
                session_id="test_session",
                query_type="general",
            )

        assert "21:40" in result["answer"]
        assert "Japan Standard Time" in result["answer"]
        assert result["metadata"]["query_type"] == "current-time"
        self.mock_web_search.search.assert_not_called()
        self.mock_provider.generate.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("language,query,expected_fragment", DATE_ONLY_AGENT_CASES)
    async def test_multilingual_date_only_queries_use_system_clock_without_external_calls(
        self, language, query, expected_fragment
    ):
        fixed_now = datetime(2026, 5, 18, 10, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

        with patch("backend.agents.general_knowledge_agent.get_now_jst", return_value=fixed_now):
            result = await self.agent.answer_query(
                query=query,
                language=language,
                session_id="test_session",
                query_type="current_info",
            )

        assert expected_fragment in result["answer"]
        assert result["emotion"] == "helpful"
        assert result["metadata"]["query_type"] == "current-time"
        assert result["metadata"]["sources"] == ["system_clock"]
        assert result["metadata"]["web_search_used"] is False
        assert result["metadata"]["rag_used"] is False
        assert result["metadata"]["provider_called"] is False
        self.mock_web_search.search.assert_not_called()
        self.mock_provider.generate.assert_not_called()
        self.mock_rag_search.search.assert_not_called()

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
