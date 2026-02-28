"""
EventAgent のユニットテスト
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.event_agent import EventAgent


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


class TestEventDeduplication:
    """イベント重複排除テスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = EventAgent()

    def test_deduplicate_same_title_events(self):
        """同じタイトルのイベントが重複排除されることを確認"""
        calendar_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop #3",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "From Calendar",
                    }
                ]
            },
        }
        connpass_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop #3",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "From Connpass",
                        "source": "connpass",
                    }
                ]
            },
        }

        events = self.agent._merge_events(calendar_result, connpass_result)

        # 重複排除で1件になる
        assert len(events) == 1
        # Google Calendar優先
        assert events[0].get("source") == "google_calendar"
        assert events[0]["description"] == "From Calendar"

    def test_keep_different_events(self):
        """異なるタイトルのイベントは保持されることを確認"""
        calendar_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "Python event",
                    }
                ]
            },
        }
        connpass_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "React Meetup",
                        "start": "2025-02-16T18:00:00Z",
                        "description": "React event",
                        "source": "connpass",
                    }
                ]
            },
        }

        events = self.agent._merge_events(calendar_result, connpass_result)

        # 異なるイベントなので2件
        assert len(events) == 2
        titles = [e["title"] for e in events]
        assert "Python Workshop" in titles
        assert "React Meetup" in titles


class TestGetTodayEvents:
    """get_today_events() のテスト"""

    def setup_method(self):
        self.agent = EventAgent()

    @pytest.mark.asyncio
    async def test_returns_events_when_available(self):
        """イベントがある場合に正しく返すこと"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.return_value = {
                "success": True,
                "data": {
                    "events": [
                        {
                            "title": "Today's Workshop",
                            "start": "2026-02-28T14:00:00Z",
                            "description": "A workshop",
                        }
                    ]
                },
            }
            mock_conn.return_value = {"success": True, "data": {"events": []}}

            result = await self.agent.get_today_events("ja")

            assert result["has_events"] is True
            assert result["count"] == 1
            assert len(result["events"]) == 1
            assert result["events"][0]["title"] == "Today's Workshop"
            assert len(result["formatted_text"]) > 0
            mock_cal.assert_called_once_with("today")

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_events(self):
        """イベントがない場合に空を返すこと"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.return_value = {"success": True, "data": {"events": []}}
            mock_conn.return_value = {"success": True, "data": {"events": []}}

            result = await self.agent.get_today_events("ja")

            assert result["has_events"] is False
            assert result["count"] == 0
            assert result["formatted_text"] == ""

    @pytest.mark.asyncio
    async def test_merges_calendar_and_connpass(self):
        """CalendarとConnpassのイベントを統合すること"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.return_value = {
                "success": True,
                "data": {
                    "events": [
                        {
                            "title": "Cal Event",
                            "start": "2026-02-28T10:00:00Z",
                            "description": "",
                        }
                    ]
                },
            }
            mock_conn.return_value = {
                "success": True,
                "data": {
                    "events": [
                        {
                            "title": "Connpass Event",
                            "start": "2026-02-28T15:00:00Z",
                            "description": "",
                            "source": "connpass",
                        }
                    ]
                },
            }

            result = await self.agent.get_today_events("ja")

            assert result["count"] == 2
            titles = [e["title"] for e in result["events"]]
            assert "Cal Event" in titles
            assert "Connpass Event" in titles

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        """API失敗時にエラーなく空結果を返すこと"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.side_effect = Exception("API error")
            mock_conn.side_effect = Exception("API error")

            result = await self.agent.get_today_events("ja")

            assert result["has_events"] is False
            assert result["count"] == 0
