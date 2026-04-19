"""
Test suite for CalendarService

Tests cover:
- Initialization and environment variable handling
- Time range calculation (today, thisWeek, nextWeek, thisMonth)
- ICS content parsing (normal, empty, malformed)
- Event search with mocked HTTP responses
- Time range extraction from query text
- ICS date parsing (UTC, local, date-only)
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from backend.tools.calendar_service import CalendarService

# Sample ICS content for testing
SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test Calendar//EN
BEGIN:VEVENT
DTSTART:20260215T100000Z
DTEND:20260215T120000Z
SUMMARY:Test Event
DESCRIPTION:A test event
LOCATION:Engineer Cafe
UID:test-uid-001
END:VEVENT
END:VCALENDAR"""

SAMPLE_ICS_MULTIPLE_EVENTS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test Calendar//EN
BEGIN:VEVENT
DTSTART:20260215T100000Z
DTEND:20260215T120000Z
SUMMARY:Morning Event
DESCRIPTION:First event
LOCATION:Engineer Cafe
UID:test-uid-001
END:VEVENT
BEGIN:VEVENT
DTSTART:20260215T140000Z
DTEND:20260215T160000Z
SUMMARY:Afternoon Event
DESCRIPTION:Second event
LOCATION:Coworking Space
UID:test-uid-002
END:VEVENT
END:VCALENDAR"""

SAMPLE_ICS_WITH_TIMEZONE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test Calendar//EN
BEGIN:VEVENT
DTSTART;TZID=Asia/Tokyo:20260215T190000
DTEND;TZID=Asia/Tokyo:20260215T210000
SUMMARY:Evening Event
DESCRIPTION:Event with timezone
LOCATION:Tokyo Office
UID:test-uid-003
END:VEVENT
END:VCALENDAR"""

EMPTY_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test Calendar//EN
END:VCALENDAR"""

MALFORMED_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test Calendar//EN
BEGIN:VEVENT
DTSTART:INVALID_DATE
SUMMARY:Malformed Event
END:VEVENT
END:VCALENDAR"""


class TestCalendarServiceInit:
    """Test CalendarService initialization and environment variable handling"""

    def test_init_with_env_var(self, monkeypatch):
        """Test initialization reads GOOGLE_CALENDAR_ICAL_URL from environment"""
        test_url = "https://calendar.google.com/test/ical/feed.ics"
        monkeypatch.setenv("GOOGLE_CALENDAR_ICAL_URL", test_url)

        service = CalendarService()

        assert service.ical_url == test_url

    def test_init_without_env_var(self, monkeypatch):
        """Test initialization when GOOGLE_CALENDAR_ICAL_URL is not set"""
        monkeypatch.delenv("GOOGLE_CALENDAR_ICAL_URL", raising=False)

        service = CalendarService()

        assert service.ical_url == ""


class TestCalculateTimeRange:
    """Test time range calculation for different periods"""

    @pytest.fixture
    def service(self):
        """Create CalendarService instance"""
        return CalendarService()

    @pytest.fixture
    def mock_now(self):
        """Mock current datetime to 2026-02-16 15:30:00 (Monday)"""
        return datetime(2026, 2, 16, 15, 30, 0)

    def test_calculate_today(self, service, mock_now, monkeypatch):
        """Test 'today' returns same-day start (00:00:00) and end (23:59:59)"""
        monkeypatch.setattr(
            "backend.tools.calendar_service.datetime",
            MagicMock(now=lambda *args, **kwargs: mock_now),
        )

        time_min, time_max = service._calculate_time_range("today")

        assert time_min == datetime(2026, 2, 16, 0, 0, 0, 0)
        assert time_max == datetime(2026, 2, 16, 23, 59, 59, 999999)

    def test_calculate_tomorrow(self, service, mock_now, monkeypatch):
        """Test 'tomorrow' returns next-day start (00:00:00) and end (23:59:59)"""
        monkeypatch.setattr(
            "backend.tools.calendar_service.datetime",
            MagicMock(now=lambda *args, **kwargs: mock_now),
        )

        time_min, time_max = service._calculate_time_range("tomorrow")

        assert time_min == datetime(2026, 2, 17, 0, 0, 0, 0)
        assert time_max == datetime(2026, 2, 17, 23, 59, 59, 999999)

    def test_calculate_this_week(self, service, mock_now, monkeypatch):
        """Test 'thisWeek' returns Monday to Sunday of current week"""
        monkeypatch.setattr(
            "backend.tools.calendar_service.datetime",
            MagicMock(now=lambda *args, **kwargs: mock_now),
        )

        time_min, time_max = service._calculate_time_range("thisWeek")

        # Monday 2026-02-16 00:00:00
        assert time_min == datetime(2026, 2, 16, 0, 0, 0, 0)
        # Sunday 2026-02-22 23:59:59
        assert time_max == datetime(2026, 2, 22, 23, 59, 59, 0)

    def test_calculate_next_week(self, service, mock_now, monkeypatch):
        """Test 'nextWeek' returns Monday to Sunday of next week"""
        monkeypatch.setattr(
            "backend.tools.calendar_service.datetime",
            MagicMock(now=lambda *args, **kwargs: mock_now),
        )

        time_min, time_max = service._calculate_time_range("nextWeek")

        # Next Monday 2026-02-23 00:00:00
        assert time_min == datetime(2026, 2, 23, 0, 0, 0, 0)
        # Next Sunday 2026-03-01 23:59:59
        assert time_max == datetime(2026, 3, 1, 23, 59, 59, 0)

    def test_calculate_this_month(self, service, mock_now, monkeypatch):
        """Test 'thisMonth' returns first day to last day of current month"""
        monkeypatch.setattr(
            "backend.tools.calendar_service.datetime",
            MagicMock(now=lambda *args, **kwargs: mock_now),
        )

        time_min, time_max = service._calculate_time_range("thisMonth")

        # First day of February 2026
        assert time_min == datetime(2026, 2, 1, 0, 0, 0, 0)
        # Last day of February 2026 (28 days in 2026)
        assert time_max.year == 2026
        assert time_max.month == 2
        assert time_max.day == 28
        assert time_max.hour == 23
        assert time_max.minute == 59
        assert time_max.second == 59


class TestParseICSContent:
    """Test ICS content parsing"""

    @pytest.fixture
    def service(self):
        """Create CalendarService instance"""
        return CalendarService()

    def test_parse_normal_ics(self, service):
        """Test parsing normal ICS content with VEVENT blocks"""
        events = service._parse_ics_content(SAMPLE_ICS)

        assert len(events) == 1
        assert events[0]["title"] == "Test Event"
        assert events[0]["description"] == "A test event"
        assert events[0]["location"] == "Engineer Cafe"
        assert events[0]["id"] == "test-uid-001"
        assert events[0]["start"] == "2026-02-15T10:00:00Z"
        assert events[0]["end"] == "2026-02-15T12:00:00Z"

    def test_parse_multiple_events(self, service):
        """Test parsing ICS with multiple VEVENT blocks"""
        events = service._parse_ics_content(SAMPLE_ICS_MULTIPLE_EVENTS)

        assert len(events) == 2
        assert events[0]["title"] == "Morning Event"
        assert events[1]["title"] == "Afternoon Event"

    def test_parse_empty_ics(self, service):
        """Test parsing empty ICS content (no VEVENTs)"""
        events = service._parse_ics_content(EMPTY_ICS)

        assert len(events) == 0

    def test_parse_malformed_ics(self, service):
        """Test parsing malformed ICS content"""
        events = service._parse_ics_content(MALFORMED_ICS)

        # Should handle malformed events gracefully
        # Either return empty list or skip malformed events
        assert isinstance(events, list)

    def test_parse_ics_with_timezone_param(self, service):
        """Test parsing VEVENT with timezone parameters"""
        events = service._parse_ics_content(SAMPLE_ICS_WITH_TIMEZONE)

        assert len(events) == 1
        assert events[0]["title"] == "Evening Event"
        assert events[0]["location"] == "Tokyo Office"
        # Timezone info in parameter should be handled
        assert events[0]["start"] == "2026-02-15T19:00:00"


class TestSearchEvents:
    """Test event search with mocked HTTP responses"""

    @pytest.fixture
    def service(self, monkeypatch):
        """Create CalendarService instance with mocked URL"""
        monkeypatch.setenv("GOOGLE_CALENDAR_ICAL_URL", "https://test.example.com/ical")
        return CalendarService()

    @pytest.mark.asyncio
    async def test_search_events_success(self, service):
        """Test successful event fetch with mocked ICS response"""
        with patch.object(service, "_fetch_ics_events", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "id": "test-uid-001",
                    "title": "Test Event",
                    "description": "A test event",
                    "location": "Engineer Cafe",
                    "start": "2026-02-15T10:00:00Z",
                    "end": "2026-02-15T12:00:00Z",
                    "htmlLink": "",
                }
            ]

            result = await service.search_events("today")

            assert result["success"] is True
            assert result["data"]["eventCount"] == 1
            assert result["data"]["timeRange"] == "today"
            assert len(result["data"]["events"]) == 1
            assert result["data"]["events"][0]["title"] == "Test Event"

    @pytest.mark.asyncio
    async def test_search_events_empty_response(self, service):
        """Test event search with empty ICS response"""
        with patch.object(service, "_fetch_ics_events", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            result = await service.search_events("today")

            assert result["success"] is True
            assert result["data"]["eventCount"] == 0
            assert result["data"]["events"] == []

    @pytest.mark.asyncio
    async def test_search_events_http_error(self, service):
        """Test event search with HTTP error"""
        with patch.object(service, "_fetch_ics_events", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("HTTP 500 Internal Server Error")

            result = await service.search_events("today")

            assert result["success"] is False
            assert "error" in result
            assert "HTTP 500" in result["error"]


class TestExtractTimeRange:
    """Test time range extraction from query text"""

    @pytest.fixture
    def service(self):
        """Create CalendarService instance"""
        return CalendarService()

    def test_extract_japanese_today(self, service):
        """Test Japanese query for 'today'"""
        assert service.extract_time_range_from_query("今日のイベント") == "today"
        assert service.extract_time_range_from_query("本日の予定") == "today"

    def test_extract_japanese_this_week(self, service):
        """Test Japanese query for 'thisWeek'"""
        assert service.extract_time_range_from_query("今週のイベント") == "thisWeek"

    def test_extract_japanese_tomorrow(self, service):
        """Test Japanese query for 'tomorrow'"""
        assert service.extract_time_range_from_query("明日のイベント") == "tomorrow"

    def test_extract_japanese_next_week(self, service):
        """Test Japanese query for 'nextWeek'"""
        assert service.extract_time_range_from_query("来週は?") == "nextWeek"
        assert service.extract_time_range_from_query("来週の予定") == "nextWeek"

    def test_extract_japanese_this_month(self, service):
        """Test Japanese query for 'thisMonth'"""
        assert service.extract_time_range_from_query("今月のイベント") == "thisMonth"

    def test_extract_english_today(self, service):
        """Test English query for 'today'"""
        assert service.extract_time_range_from_query("today") == "today"
        assert service.extract_time_range_from_query("events Today") == "today"

    def test_extract_english_this_week(self, service):
        """Test English query for 'thisWeek'"""
        assert service.extract_time_range_from_query("this week") == "thisWeek"
        assert service.extract_time_range_from_query("This Week events") == "thisWeek"

    def test_extract_english_tomorrow(self, service):
        """Test English query for 'tomorrow'"""
        assert service.extract_time_range_from_query("tomorrow") == "tomorrow"
        assert service.extract_time_range_from_query("Tomorrow events") == "tomorrow"

    def test_extract_english_next_week(self, service):
        """Test English query for 'nextWeek'"""
        assert service.extract_time_range_from_query("next week") == "nextWeek"
        assert service.extract_time_range_from_query("Next Week schedule") == "nextWeek"

    def test_extract_english_this_month(self, service):
        """Test English query for 'thisMonth'"""
        assert service.extract_time_range_from_query("this month") == "thisMonth"
        assert service.extract_time_range_from_query("This Month events") == "thisMonth"

    def test_extract_default_fallback(self, service):
        """Test default fallback to 'thisWeek' for unrecognized queries"""
        assert service.extract_time_range_from_query("イベント情報") == "thisWeek"
        assert service.extract_time_range_from_query("schedule") == "thisWeek"


class TestParseICSDate:
    """Test ICS date parsing to ISO format"""

    @pytest.fixture
    def service(self):
        """Create CalendarService instance"""
        return CalendarService()

    def test_parse_utc_format(self, service):
        """Test UTC format '20260215T100000Z' → ISO string with Z"""
        result = service._parse_ics_date("20260215T100000Z")

        assert result == "2026-02-15T10:00:00Z"

    def test_parse_utc_date_only_with_z(self, service):
        """Test UTC date-only format '20260215Z' → ISO string with Z"""
        result = service._parse_ics_date("20260215Z")

        assert result == "2026-02-15T00:00:00Z"

    def test_parse_local_format(self, service):
        """Test local format '20260215T100000' → ISO string"""
        result = service._parse_ics_date("20260215T100000")

        assert result == "2026-02-15T10:00:00"

    def test_parse_date_only_format(self, service):
        """Test date-only format '20260215' → date ISO string"""
        result = service._parse_ics_date("20260215")

        assert result == "2026-02-15"

    def test_parse_empty_string(self, service):
        """Test empty string returns empty string"""
        result = service._parse_ics_date("")

        assert result == ""

    def test_parse_invalid_format(self, service):
        """Test invalid format returns original string"""
        result = service._parse_ics_date("INVALID_DATE")

        assert result == "INVALID_DATE"
