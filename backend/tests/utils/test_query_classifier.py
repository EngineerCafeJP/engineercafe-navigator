"""
QueryClassifier のユニットテスト
"""

import pytest
from backend.utils.query_classifier import QueryClassifier, QueryClassificationResult

DATE_ONLY_QUERY_SAMPLES = {
    "ja": [
        "今日",
        "本日",
        "今日は何月何日ですか?",
        "今日の日付を教えて",
        "明日は何日ですか",
        "昨日は何曜日でしたか",
        "今週は何日から何日まで?",
        "本日は何曜日ですか",
        "明日の日付を教えて",
        "昨日の日付は?",
    ],
    "en": [
        "today",
        "today's date?",
        "What is the date today?",
        "What date is it tomorrow?",
        "What day is it today?",
        "What day of the week is tomorrow?",
        "yesterday's date?",
        "What date was yesterday?",
        "this week",
        "What dates are this week?",
    ],
    "zh": [
        "今天",
        "今天是几月几号？",
        "今天日期是什么？",
        "今天星期几？",
        "今天周几？",
        "明天是几号？",
        "明天是幾月幾日？",
        "昨天是星期几？",
        "本周是哪几天？",
        "這周是幾號到幾號？",
    ],
    "ko": [
        "오늘",
        "오늘 날짜 알려줘",
        "오늘은 몇 월 며칠인가요?",
        "오늘은 무슨 요일인가요?",
        "내일은 며칠이에요?",
        "내일 날짜 알려줘",
        "어제는 무슨 요일이었나요?",
        "어제 날짜가 뭐였죠?",
        "이번 주는 며칠부터 며칠까지예요?",
        "금주 날짜 알려줘",
    ],
}

DATE_ONLY_QUERY_CASES = [
    pytest.param(language, query, id=f"{language}:{index}")
    for language, queries in DATE_ONLY_QUERY_SAMPLES.items()
    for index, query in enumerate(queries, start=1)
]


class TestQueryClassifier:
    """QueryClassifier のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.classifier = QueryClassifier(debug_mode=False)

    @pytest.mark.asyncio
    async def test_current_time_query_japanese(self):
        """現在時刻クエリの分類（日本語）"""
        result = await self.classifier.classify_with_details("今何時ですか?")

        assert result.category == "current-time"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_current_time_query_english(self):
        """現在時刻クエリの分類（英語）"""
        result = await self.classifier.classify_with_details("whattimeisitnow")

        assert result.category == "current-time"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_calendar_query(self):
        """カレンダークエリの分類"""
        result = await self.classifier.classify_with_details("今日のイベントは何ですか?")

        assert result.category == "calendar"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "今日は何月何日ですか?",
            "今日の日付を教えて",
            "明日は何日ですか",
            "今日",
            "今週",
        ],
    )
    async def test_date_only_query_routes_to_current_time(self, query):
        """日付確認だけのクエリはカレンダーではなく現在時刻系に分類する"""
        result = await self.classifier.classify_with_details(query)

        assert result.category == "current-time"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("language,query", DATE_ONLY_QUERY_CASES)
    async def test_multilingual_date_only_queries_route_to_current_time(self, language, query):
        """JA/EN/ZH/KOの日付だけの質問はcalendarではなくsystem clock系へ回す"""
        assert len(DATE_ONLY_QUERY_SAMPLES[language]) == 10

        result = await self.classifier.classify_with_details(query)
        normalized = self.classifier._normalize_query(query)

        assert result.category == "current-time"
        assert result.confidence == 1.0
        assert self.classifier._is_calendar_query(normalized) is False

    @pytest.mark.asyncio
    async def test_engineer_cafe_specific_query(self):
        """エンジニアカフェ特定クエリの分類"""
        result = await self.classifier.classify_with_details("エンジニアカフェの営業時間は?")

        assert result.category == "facility-info"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_saino_cafe_query(self):
        """Sainoカフェクエリの分類"""
        result = await self.classifier.classify_with_details("sainoカフェのメニューは?")

        assert result.category == "saino-cafe"
        assert result.confidence == 0.9
        assert result.debug_info["cafe_entity_resolution"]["entity"] == "saino_cafe"

    @pytest.mark.asyncio
    async def test_heisetsu_cafe_query_resolves_to_saino(self):
        """併設のカフェはSainoとして分類する"""
        result = await self.classifier.classify_with_details("併設のカフェの営業時間は?")

        assert result.category == "saino-cafe"
        assert result.debug_info["cafe_entity_resolution"]["entity"] == "saino_cafe"

    @pytest.mark.asyncio
    async def test_bare_cafe_query_prefers_saino(self):
        """単独のカフェは併設Sainoを第一義として分類する"""
        result = await self.classifier.classify_with_details("カフェの場所はどこですか?")

        assert result.category == "saino-cafe"
        assert result.confidence == 0.9
        assert result.debug_info["cafe_entity_resolution"]["entity"] == "saino_cafe"

    @pytest.mark.asyncio
    async def test_cafe_facility_context_prefers_engineer_cafe(self):
        """コワーキング/イベント/施設利用語はEngineer Cafe文脈として分類する"""
        result = await self.classifier.classify_with_details("カフェで施設利用はできますか?")

        assert result.category == "facility-info"
        assert result.debug_info["cafe_entity_resolution"]["entity"] == "engineer_cafe"

    @pytest.mark.asyncio
    async def test_closed_days_query(self):
        """休館日クエリの分類"""
        result = await self.classifier.classify_with_details("休館日はいつですか?")

        assert result.category == "facility-info"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_history_query(self):
        """歴史クエリの分類"""
        result = await self.classifier.classify_with_details("エンジニアカフェの歴史を教えて")

        assert result.category == "facility-info"
        # エンジニアカフェ特定クエリなので1.0になる
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_meeting_room_ambiguity(self):
        """会議室の曖昧性クエリ"""
        result = await self.classifier.classify_with_details("会議室について教えて")

        assert result.category == "meeting-room-clarification-needed"
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_meeting_room_with_kanji_floor_is_not_ambiguous(self):
        """二階表記も2階指定として扱う"""
        result = await self.classifier.classify_with_details("二階の会議室の予約方法教えて")

        assert result.category != "meeting-room-clarification-needed"

    @pytest.mark.asyncio
    async def test_facility_query(self):
        """施設情報クエリの分類"""
        result = await self.classifier.classify_with_details("福岡市の施設について")

        assert result.category == "facility-info"
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_pricing_query(self):
        """料金クエリの分類"""
        result = await self.classifier.classify_with_details("料金はいくらですか?")

        assert result.category == "pricing"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_facilities_query(self):
        """設備クエリの分類"""
        result = await self.classifier.classify_with_details("設備について教えて")

        assert result.category == "facilities"
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_access_query(self):
        """アクセスクエリの分類"""
        result = await self.classifier.classify_with_details("アクセス方法は?")

        assert result.category == "access"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_hours_query(self):
        """営業時間クエリの分類"""
        result = await self.classifier.classify_with_details("営業時間を教えて")

        assert result.category == "hours"
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_general_query(self):
        """一般クエリの分類"""
        result = await self.classifier.classify_with_details("天気はどうですか?")

        assert result.category == "general"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_normalize_query_saino_variations(self):
        """Saino関連の正規化テスト"""
        # "coffee say no" -> "saino cafe"
        normalized = self.classifier._normalize_query("coffee say no")
        assert "saino cafe" in normalized

        # "才能" -> "saino"
        normalized = self.classifier._normalize_query("才能")
        assert "saino" in normalized

    @pytest.mark.asyncio
    async def test_normalize_query_remove_conjunctions(self):
        """接続詞除去の正規化テスト"""
        normalized = self.classifier._normalize_query("じゃあ営業時間は?")
        assert not normalized.startswith("じゃあ")

        normalized = self.classifier._normalize_query("well, what time is it?")
        assert not normalized.startswith("well")

    def test_is_current_time_query(self):
        """現在時刻クエリ判定のテスト"""
        assert self.classifier._is_current_time_query("今何時")
        assert self.classifier._is_current_time_query("現在時刻")
        assert not self.classifier._is_current_time_query("営業時間")

    def test_is_calendar_query(self):
        """カレンダークエリ判定のテスト"""
        assert self.classifier._is_calendar_query("イベント")
        assert not self.classifier._is_calendar_query("今日")
        assert not self.classifier._is_calendar_query("今日は何月何日")
        assert self.classifier._is_calendar_query("今日のイベント")
        assert self.classifier._is_calendar_query("カレンダー")

    def test_is_facility_query(self):
        """施設情報クエリ判定のテスト"""
        assert self.classifier._is_facility_query("エンジニアカフェ")
        assert self.classifier._is_facility_query("地下")
        assert self.classifier._is_facility_query("会議室")

    def test_is_saino_cafe_query(self):
        """Sainoカフェクエリ判定のテスト"""
        assert self.classifier._is_saino_cafe_query("saino")
        assert self.classifier._is_saino_cafe_query("サイノ")
        assert self.classifier._is_saino_cafe_query("併設カフェ")

    def test_is_closed_days_query(self):
        """休館日クエリ判定のテスト"""
        assert self.classifier._is_closed_days_query("休業日")
        assert self.classifier._is_closed_days_query("定休日")
        assert self.classifier._is_closed_days_query("閉まって")

    def test_is_engineer_cafe_specific(self):
        """エンジニアカフェ特定クエリ判定のテスト"""
        assert self.classifier._is_engineer_cafe_specific("エンジニアカフェ")
        assert self.classifier._is_engineer_cafe_specific("engineer cafe")
        assert not self.classifier._is_engineer_cafe_specific("カフェ")

    def test_is_history_query(self):
        """歴史クエリ判定のテスト"""
        assert self.classifier._is_history_query("歴史")
        assert self.classifier._is_history_query("history")
        assert self.classifier._is_history_query("設立")

    @pytest.mark.asyncio
    async def test_classify_simple_method(self):
        """簡易版classifyメソッドのテスト"""
        category = await self.classifier.classify("今何時ですか?")
        assert category == "current-time"

    def test_query_classification_result_structure(self):
        """QueryClassificationResultの構造テスト"""
        result = QueryClassificationResult(
            category="facility-info",
            confidence=0.9,
            debug_info={"reason": "Test"},
        )

        assert hasattr(result, "category")
        assert hasattr(result, "confidence")
        assert hasattr(result, "debug_info")
        assert result.category == "facility-info"
        assert result.confidence == 0.9
        assert result.debug_info == {"reason": "Test"}
