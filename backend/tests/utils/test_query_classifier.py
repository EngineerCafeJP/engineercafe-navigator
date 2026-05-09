"""
QueryClassifier のユニットテスト
"""

import pytest
from backend.utils.query_classifier import QueryClassifier, QueryClassificationResult


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
    async def test_cafe_ambiguity_needs_clarification(self):
        """カフェの曖昧性クエリ（明確化が必要）"""
        result = await self.classifier.classify_with_details("カフェの場所はどこですか?")

        assert result.category == "cafe-clarification-needed"
        assert result.confidence == 0.7
        assert result.debug_info["cafe_entity_resolution"]["entity"] == "ambiguous"

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
        assert self.classifier._is_calendar_query("今日")
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
