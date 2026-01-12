"""
EventAgent のユニットテスト
"""

from agents.event_agent import EventAgent


class TestEventAgent:
    """EventAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = EventAgent()

    def test_format_calendar_events_japanese(self):
        """日本語のイベント整形をテスト"""
        events = [
            {
                "title": "LT会",
                "start": "2025-01-15T19:00:00Z",
                "description": "Lightning Talk Event",
                "location": "Engineer Cafe",
            },
            {"title": "勉強会", "start": "2025-01-20", "description": "", "location": ""},
        ]

        formatted = self.agent._format_calendar_events(events, "ja")

        assert "LT会" in formatted
        assert "2025-01-15" in formatted
        assert "Lightning Talk Event" in formatted
        assert "勉強会" in formatted
        assert "2025-01-20" in formatted

    def test_format_calendar_events_english(self):
        """英語のイベント整形をテスト"""
        events = [
            {
                "title": "Tech Meetup",
                "start": "2025-01-25T18:00:00Z",
                "description": "Monthly meetup",
                "location": "",
            }
        ]

        formatted = self.agent._format_calendar_events(events, "en")

        assert "Tech Meetup" in formatted
        assert "2025-01-25" in formatted
        assert "Monthly meetup" in formatted

    def test_format_calendar_events_empty(self):
        """空のイベントリストをテスト"""
        formatted = self.agent._format_calendar_events([], "ja")
        assert formatted == ""

    def test_get_no_events_response_japanese(self):
        """日本語のイベントなし応答をテスト"""
        response = self.agent._get_no_events_response("ja", "thisWeek")

        assert response["answer"].startswith("[sad]")
        assert "今週" in response["answer"]
        assert response["emotion"] == "sad"
        assert response["metadata"]["agent"] == "EventAgent"
        assert response["metadata"]["time_range"] == "thisWeek"
        assert response["metadata"]["event_count"] == 0

    def test_get_no_events_response_english(self):
        """英語のイベントなし応答をテスト"""
        response = self.agent._get_no_events_response("en", "today")

        assert response["answer"].startswith("[sad]")
        assert "today" in response["answer"].lower()
        assert response["emotion"] == "sad"
        assert response["metadata"]["agent"] == "EventAgent"

    def test_get_no_events_response_various_time_ranges(self):
        """各時間範囲のイベントなし応答をテスト"""
        for time_range in ["today", "thisWeek", "nextWeek", "thisMonth"]:
            response_ja = self.agent._get_no_events_response("ja", time_range)
            response_en = self.agent._get_no_events_response("en", time_range)

            assert response_ja["metadata"]["time_range"] == time_range
            assert response_en["metadata"]["time_range"] == time_range
            assert response_ja["emotion"] == "sad"
            assert response_en["emotion"] == "sad"
