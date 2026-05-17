"""
EventAgent タイムアウト・障害耐性テスト
asyncio.wait_for によるタイムアウトと return_exceptions による個別障害ハンドリングを検証
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.event_agent import EventAgent


def _make_success_result(events=None, time_range="thisWeek"):
    """成功レスポンスを作成"""
    if events is None:
        events = [
            {
                "id": "1",
                "title": "Test Event",
                "start": "2026-03-01T10:00:00Z",
                "description": "A test event",
                "location": "Engineer Cafe",
            }
        ]
    return {
        "success": True,
        "data": {
            "events": events,
            "timeRange": time_range,
            "eventCount": len(events),
        },
    }


# ==============================================================================
# answer_event_query タイムアウトテスト
# ==============================================================================


class TestAnswerEventQueryTimeout:
    """answer_event_query のタイムアウト・障害テスト"""

    def setup_method(self):
        self.agent = EventAgent()

    @pytest.mark.asyncio
    async def test_answer_event_query_timeout(self):
        """asyncio.gather が 35秒を超えた場合、フォールバック応答を返す"""
        with patch(
            "backend.agents.event_agent.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            result = await self.agent.answer_event_query("今週のイベント", language="ja")

        assert result["emotion"] == "sad"
        assert result["metadata"]["event_count"] == 0
        assert result["metadata"]["agent"] == "EventAgent"
        assert result["metadata"]["sources"] == []

    @pytest.mark.asyncio
    async def test_answer_event_query_calendar_failure(self):
        """Calendar が例外を返しても Connpass の結果で応答できる"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
                side_effect=Exception("Calendar API down"),
            ),
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
                return_value=_make_success_result(),
            ),
            patch.object(
                self.agent.connpass_service,
                "extract_keyword_from_query",
                return_value=None,
            ),
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
                return_value="[happy] Here are the events.",
            ),
        ):
            result = await self.agent.answer_event_query("今週のイベント", language="ja")

        # Connpass の結果が使われてイベントが見つかる
        assert result["emotion"] == "happy"
        assert result["metadata"]["event_count"] > 0
        assert result["metadata"]["sources"] == ["connpass"]

    @pytest.mark.asyncio
    async def test_answer_event_query_connpass_failure(self):
        """Connpass が例外を返しても Calendar の結果で応答できる"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
                return_value=_make_success_result(),
            ),
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
                side_effect=Exception("Connpass API down"),
            ),
            patch.object(
                self.agent.connpass_service,
                "extract_keyword_from_query",
                return_value=None,
            ),
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
                return_value="[happy] Here are the events.",
            ),
        ):
            result = await self.agent.answer_event_query("今週のイベント", language="ja")

        # Calendar の結果が使われてイベントが見つかる
        assert result["emotion"] == "happy"
        assert result["metadata"]["event_count"] > 0
        assert result["metadata"]["sources"] == ["google_calendar"]


# ==============================================================================
# get_today_events タイムアウトテスト
# ==============================================================================


class TestGetTodayEventsTimeout:
    """get_today_events のタイムアウト・障害テスト"""

    def setup_method(self):
        self.agent = EventAgent()

    @pytest.mark.asyncio
    async def test_get_today_events_timeout(self):
        """get_today_events で asyncio.TimeoutError が発生した場合、エラーレスポンスを返す"""
        with patch(
            "backend.agents.event_agent.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            result = await self.agent.get_today_events()

        # TimeoutError は Exception の外側 try/except でキャッチされる
        assert result["has_events"] is False
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_get_today_events_calendar_failure(self):
        """get_today_events で Calendar が例外を返しても Connpass の結果を返す"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
                side_effect=Exception("Calendar API down"),
            ),
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
                return_value=_make_success_result(
                    events=[
                        {
                            "id": "c1",
                            "title": "Connpass Event",
                            "start": "2026-02-28T18:00:00Z",
                            "description": "Tech meetup",
                            "location": "Online",
                            "source": "connpass",
                        }
                    ]
                ),
            ),
        ):
            result = await self.agent.get_today_events()

        assert result["has_events"] is True
        assert result["count"] == 1
        assert result["events"][0]["title"] == "Connpass Event"

    @pytest.mark.asyncio
    async def test_get_today_events_both_succeed(self):
        """get_today_events で両サービスが成功した場合、統合結果を返す"""
        calendar_events = [
            {
                "id": "g1",
                "title": "Calendar Event",
                "start": "2026-02-28T10:00:00Z",
                "description": "Morning session",
                "location": "Engineer Cafe",
            }
        ]
        connpass_events = [
            {
                "id": "c1",
                "title": "Connpass Event",
                "start": "2026-02-28T18:00:00Z",
                "description": "Evening meetup",
                "location": "Online",
                "source": "connpass",
            }
        ]

        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
                return_value=_make_success_result(events=calendar_events),
            ),
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
                return_value=_make_success_result(events=connpass_events),
            ),
        ):
            result = await self.agent.get_today_events()

        assert result["has_events"] is True
        assert result["count"] == 2
        titles = [e["title"] for e in result["events"]]
        assert "Calendar Event" in titles
        assert "Connpass Event" in titles
