"""
Tests for ConnpassService

Testing backend/tools/connpass_service.py
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.tools.connpass_service import ConnpassService


class TestConnpassInit:
    """Tests for ConnpassService initialization"""

    def test_init_with_api_key(self, monkeypatch):
        """Test initialization with API key from environment"""
        monkeypatch.setenv("CONNPASS_API_KEY", "test_api_key_123")
        service = ConnpassService()
        assert service.api_key == "test_api_key_123"

    def test_init_without_api_key(self, monkeypatch, caplog):
        """Test initialization without API key logs warning"""
        monkeypatch.delenv("CONNPASS_API_KEY", raising=False)
        with caplog.at_level("WARNING", logger="tools.connpass_service"):
            service = ConnpassService()
        assert service.api_key == ""
        assert "CONNPASS_API_KEY not configured" in caplog.text


class TestSearchEvents:
    """Tests for search_events method"""

    @pytest.fixture
    def mock_connpass_response(self):
        """Sample Connpass API response"""
        return {
            "results_returned": 2,
            "events": [
                {
                    "event_id": 12345,
                    "title": "Python勉強会",
                    "description": "Python入門セミナー",
                    "place": "エンジニアカフェ",
                    "started_at": "2026-02-20T19:00:00+09:00",
                    "ended_at": "2026-02-20T21:00:00+09:00",
                    "event_url": "https://connpass.com/event/12345/",
                    "accepted": 30,
                    "limit": 50,
                    "waiting": 5,
                    "owner_nickname": "testuser",
                    "series": {"title": "Python Fukuoka"},
                },
                {
                    "event_id": 67890,
                    "title": "JavaScript勉強会",
                    "description": "React入門",
                    "place": "天神オフィス",
                    "started_at": "2026-02-22T14:00:00+09:00",
                    "ended_at": "2026-02-22T17:00:00+09:00",
                    "event_url": "https://connpass.com/event/67890/",
                    "accepted": 20,
                    "limit": 30,
                    "waiting": 0,
                    "owner_nickname": "jsmaster",
                    "series": {"title": "JS Study Group"},
                },
            ],
        }

    async def test_search_events_success(self, monkeypatch, mock_connpass_response):
        """Test successful event search with mocked API response"""
        monkeypatch.setenv("CONNPASS_API_KEY", "test_key")

        service = ConnpassService()

        # Mock the HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_connpass_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await service.search_events(time_range="thisWeek")

            assert result["success"] is True
            assert result["data"]["eventCount"] == 2
            assert result["data"]["source"] == "connpass"
            assert result["data"]["timeRange"] == "thisWeek"
            assert len(result["data"]["events"]) == 2

            # Check first event formatting
            first_event = result["data"]["events"][0]
            assert first_event["id"] == "12345"
            assert first_event["title"] == "Python勉強会"
            assert first_event["location"] == "エンジニアカフェ"
            assert first_event["source"] == "connpass"
            assert first_event["accepted"] == 30
            assert first_event["limit"] == 50
            assert first_event["group_name"] == "Python Fukuoka"

    async def test_search_events_with_keyword(self, monkeypatch, mock_connpass_response):
        """Test search with keyword parameter"""
        monkeypatch.setenv("CONNPASS_API_KEY", "test_key")

        service = ConnpassService()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_connpass_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await service.search_events(time_range="today", keyword="Python", count=10)

            assert result["success"] is True
            assert result["data"]["eventCount"] == 2

            # Verify the API call was made with correct parameters
            call_args = mock_get.call_args
            assert call_args is not None
            params = call_args.kwargs["params"]
            assert params["keyword"] == "Python"
            assert params["count"] == 10

    async def test_search_events_empty_results(self, monkeypatch):
        """Test search with empty results"""
        monkeypatch.setenv("CONNPASS_API_KEY", "test_key")

        service = ConnpassService()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results_returned": 0, "events": []}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await service.search_events(time_range="nextWeek")

            assert result["success"] is True
            assert result["data"]["eventCount"] == 0
            assert result["data"]["events"] == []

    async def test_search_events_no_api_key(self, monkeypatch):
        """Test search without API key returns failure"""
        monkeypatch.delenv("CONNPASS_API_KEY", raising=False)

        service = ConnpassService()
        result = await service.search_events(time_range="today")

        assert result["success"] is False
        assert "CONNPASS_API_KEY not configured" in result["error"]
        assert result["data"]["eventCount"] == 0
        assert result["data"]["events"] == []


class TestGetYmdList:
    """Tests for _get_ymd_list method"""

    def test_get_ymd_list_today(self):
        """Test 'today' returns single date"""
        service = ConnpassService()
        result = service._get_ymd_list("today")

        assert len(result) == 1
        today = datetime.now().date().strftime("%Y%m%d")
        assert result[0] == today

    def test_get_ymd_list_this_week(self):
        """Test 'thisWeek' returns 7 dates"""
        service = ConnpassService()
        result = service._get_ymd_list("thisWeek")

        assert len(result) == 7

        # Verify it starts with Monday
        today = datetime.now().date()
        weekday = today.weekday()
        week_start = today - timedelta(days=weekday)
        assert result[0] == week_start.strftime("%Y%m%d")

        # Verify consecutive dates
        for i in range(7):
            expected_date = (week_start + timedelta(days=i)).strftime("%Y%m%d")
            assert result[i] == expected_date

    def test_get_ymd_list_next_week(self):
        """Test 'nextWeek' returns 7 dates"""
        service = ConnpassService()
        result = service._get_ymd_list("nextWeek")

        assert len(result) == 7

        # Verify it starts with next Monday
        today = datetime.now().date()
        weekday = today.weekday()
        next_week_start = today - timedelta(days=weekday) + timedelta(weeks=1)
        assert result[0] == next_week_start.strftime("%Y%m%d")

        # Verify consecutive dates
        for i in range(7):
            expected_date = (next_week_start + timedelta(days=i)).strftime("%Y%m%d")
            assert result[i] == expected_date

    def test_get_ymd_list_this_month(self):
        """Test 'thisMonth' returns correct number of days"""
        service = ConnpassService()
        result = service._get_ymd_list("thisMonth")

        today = datetime.now().date()
        month_start = today.replace(day=1)

        # Calculate days in month
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        days_in_month = (next_month - month_start).days

        assert len(result) == days_in_month
        assert result[0] == month_start.strftime("%Y%m%d")

        # Verify last day of month
        last_day = next_month - timedelta(days=1)
        assert result[-1] == last_day.strftime("%Y%m%d")


class TestFormatEvents:
    """Tests for _format_events method"""

    def test_format_events_single_event(self):
        """Test formatting single event correctly"""
        service = ConnpassService()

        raw_events = [
            {
                "event_id": 12345,
                "title": "Python勉強会",
                "description": "Python入門セミナー",
                "place": "エンジニアカフェ",
                "started_at": "2026-02-20T19:00:00+09:00",
                "ended_at": "2026-02-20T21:00:00+09:00",
                "event_url": "https://connpass.com/event/12345/",
                "accepted": 30,
                "limit": 50,
                "waiting": 5,
                "owner_nickname": "testuser",
                "series": {"title": "Python Fukuoka"},
            }
        ]

        result = service._format_events(raw_events)

        assert len(result) == 1
        event = result[0]

        # Check all required fields
        assert event["id"] == "12345"
        assert event["title"] == "Python勉強会"
        assert event["description"] == "Python入門セミナー"
        assert event["location"] == "エンジニアカフェ"
        assert event["start"] == "2026-02-20T19:00:00+09:00"
        assert event["end"] == "2026-02-20T21:00:00+09:00"
        assert event["htmlLink"] == "https://connpass.com/event/12345/"
        assert event["source"] == "connpass"
        assert event["accepted"] == 30
        assert event["limit"] == 50
        assert event["waiting"] == 5
        assert event["owner_nickname"] == "testuser"
        assert event["group_name"] == "Python Fukuoka"

    def test_format_events_multiple_events(self):
        """Test formatting multiple events"""
        service = ConnpassService()

        raw_events = [
            {
                "event_id": 111,
                "title": "Event 1",
                "description": "Desc 1",
                "place": "Place 1",
                "started_at": "2026-02-20T19:00:00+09:00",
                "ended_at": "2026-02-20T21:00:00+09:00",
                "event_url": "https://connpass.com/event/111/",
                "accepted": 10,
                "limit": 20,
                "waiting": 0,
                "owner_nickname": "user1",
                "series": {"title": "Series 1"},
            },
            {
                "event_id": 222,
                "title": "Event 2",
                "description": "Desc 2",
                "place": "Place 2",
                "started_at": "2026-02-21T14:00:00+09:00",
                "ended_at": "2026-02-21T17:00:00+09:00",
                "event_url": "https://connpass.com/event/222/",
                "accepted": 15,
                "limit": 25,
                "waiting": 3,
                "owner_nickname": "user2",
                "series": {"title": "Series 2"},
            },
        ]

        result = service._format_events(raw_events)

        assert len(result) == 2
        assert result[0]["id"] == "111"
        assert result[0]["title"] == "Event 1"
        assert result[1]["id"] == "222"
        assert result[1]["title"] == "Event 2"

    def test_format_events_missing_fields(self):
        """Test formatting events with missing fields (no series, no place)"""
        service = ConnpassService()

        raw_events = [
            {
                "event_id": 999,
                "title": "Minimal Event",
                "description": "",
                "address": "Alternate Address",
                "started_at": "2026-02-25T10:00:00+09:00",
                "ended_at": "2026-02-25T12:00:00+09:00",
                "event_url": "https://connpass.com/event/999/",
                "accepted": 5,
                "waiting": 0,
                "owner_nickname": "",
                # series is missing
                # place is missing
                # limit is missing
            }
        ]

        result = service._format_events(raw_events)

        assert len(result) == 1
        event = result[0]

        assert event["id"] == "999"
        assert event["title"] == "Minimal Event"
        assert event["location"] == "Alternate Address"  # Falls back to address
        assert event["group_name"] == ""  # Missing series
        assert event["limit"] is None  # Missing limit
        assert event["owner_nickname"] == ""


class TestExtractKeyword:
    """Tests for extract_keyword_from_query method"""

    def test_extract_keyword_python(self):
        """Test extracting 'Python' from query"""
        service = ConnpassService()

        result = service.extract_keyword_from_query("Pythonのイベントは？")
        assert result == "Python"

        result = service.extract_keyword_from_query("今週のpython勉強会")
        assert result == "Python"

    def test_extract_keyword_no_tech_keyword(self):
        """Test query with no tech keyword returns None"""
        service = ConnpassService()

        result = service.extract_keyword_from_query("今週のイベント")
        assert result is None

        result = service.extract_keyword_from_query("エンジニアカフェのイベント")
        assert result is None


class TestExtractTimeRange:
    """Tests for extract_time_range_from_query method"""

    def test_extract_time_range_today(self):
        """Test extracting 'today' from query"""
        service = ConnpassService()

        assert service.extract_time_range_from_query("今日のイベント") == "today"
        assert service.extract_time_range_from_query("本日のイベント") == "today"
        assert service.extract_time_range_from_query("today's events") == "today"

    def test_extract_time_range_this_week(self):
        """Test extracting 'thisWeek' from query"""
        service = ConnpassService()

        assert service.extract_time_range_from_query("今週のイベント") == "thisWeek"
        assert service.extract_time_range_from_query("this week events") == "thisWeek"

    def test_extract_time_range_next_week(self):
        """Test extracting 'nextWeek' from query"""
        service = ConnpassService()

        assert service.extract_time_range_from_query("来週のイベント") == "nextWeek"
        assert service.extract_time_range_from_query("next week events") == "nextWeek"

    def test_extract_time_range_this_month(self):
        """Test extracting 'thisMonth' from query"""
        service = ConnpassService()

        assert service.extract_time_range_from_query("今月のイベント") == "thisMonth"
        assert service.extract_time_range_from_query("this month events") == "thisMonth"

    def test_extract_time_range_default(self):
        """Test default time range is 'thisWeek'"""
        service = ConnpassService()

        assert service.extract_time_range_from_query("イベントを探して") == "thisWeek"
        assert service.extract_time_range_from_query("Pythonイベント") == "thisWeek"
