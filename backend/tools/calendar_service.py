"""
Calendar Service Tool
Google Calendar API連携によるイベント情報取得
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Literal
import httpx

TimeRange = Literal["today", "thisWeek", "nextWeek", "thisMonth"]


class CalendarService:
    """Google Calendar APIサービス"""

    def __init__(self):
        """初期化"""
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "")
        self.api_key = os.getenv("GOOGLE_API_KEY", "")

    async def search_events(self, time_range: TimeRange = "thisWeek") -> Dict:
        """
        指定期間のイベントを検索

        Args:
            time_range: 検索期間（today, thisWeek, nextWeek, thisMonth）

        Returns:
            イベント情報辞書 {success, data: {events, timeRange, eventCount}}
        """
        try:
            print(f"[CalendarService] Searching events for time_range: {time_range}")

            # 期間の開始日と終了日を計算
            time_min, time_max = self._calculate_time_range(time_range)

            # Google Calendar APIでイベント取得
            events = await self._fetch_calendar_events(time_min, time_max)

            # イベントを整形
            formatted_events = self._format_events(events)

            return {
                "success": True,
                "data": {
                    "events": formatted_events,
                    "timeRange": time_range,
                    "eventCount": len(formatted_events),
                },
            }

        except Exception as e:
            print(f"[CalendarService] Error: {e}")
            return {"success": False, "error": str(e)}

    def _calculate_time_range(self, time_range: TimeRange) -> tuple[datetime, datetime]:
        """
        時間範囲を計算

        Returns:
            (time_min, time_max)のタプル
        """
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        if time_range == "today":
            return (today_start, today_end)

        elif time_range == "thisWeek":
            # 今週の月曜日から日曜日
            weekday = today_start.weekday()
            week_start = today_start - timedelta(days=weekday)
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            return (week_start, week_end)

        elif time_range == "nextWeek":
            # 来週の月曜日から日曜日
            weekday = today_start.weekday()
            week_start = today_start - timedelta(days=weekday) + timedelta(weeks=1)
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            return (week_start, week_end)

        elif time_range == "thisMonth":
            # 今月の1日から月末
            month_start = today_start.replace(day=1)
            # 次の月の1日 - 1秒 = 今月の最終日時
            if month_start.month == 12:
                next_month = month_start.replace(year=month_start.year + 1, month=1)
            else:
                next_month = month_start.replace(month=month_start.month + 1)
            month_end = next_month - timedelta(seconds=1)
            return (month_start, month_end)

        # デフォルトは今週
        weekday = today_start.weekday()
        week_start = today_start - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        return (week_start, week_end)

    async def _fetch_calendar_events(self, time_min: datetime, time_max: datetime) -> List[Dict]:
        """
        Google Calendar APIからイベントを取得

        Args:
            time_min: 検索開始日時
            time_max: 検索終了日時

        Returns:
            イベントのリスト
        """
        if not self.calendar_id or not self.api_key:
            print("[CalendarService] Calendar ID or API Key not configured")
            return []

        try:
            # ISO 8601形式に変換
            time_min_str = time_min.isoformat() + "Z"
            time_max_str = time_max.isoformat() + "Z"

            # Google Calendar API v3エンドポイント
            url = f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events"

            params = {
                "key": self.api_key,
                "timeMin": time_min_str,
                "timeMax": time_max_str,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 50,
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30.0)

                if response.status_code != 200:
                    print(f"[CalendarService] API error: {response.text}")
                    return []

                data = response.json()
                return data.get("items", [])

        except Exception as e:
            print(f"[CalendarService] Fetch error: {e}")
            return []

    def _format_events(self, events: List[Dict]) -> List[Dict]:
        """
        イベントを整形

        Args:
            events: 生のイベントデータ

        Returns:
            整形されたイベントのリスト
        """
        formatted_events = []

        for event in events:
            # 開始日時と終了日時を取得
            start = event.get("start", {})
            end = event.get("end", {})

            start_datetime = start.get("dateTime") or start.get("date")
            end_datetime = end.get("dateTime") or end.get("date")

            formatted_event = {
                "id": event.get("id", ""),
                "title": event.get("summary", "No Title"),
                "description": event.get("description", ""),
                "location": event.get("location", ""),
                "start": start_datetime,
                "end": end_datetime,
                "htmlLink": event.get("htmlLink", ""),
            }

            formatted_events.append(formatted_event)

        return formatted_events

    def extract_time_range_from_query(self, query: str) -> TimeRange:
        """
        クエリから時間範囲を抽出

        Args:
            query: ユーザークエリ

        Returns:
            時間範囲（today, thisWeek, nextWeek, thisMonth）
        """
        query_lower = query.lower()

        # 今日
        if "今日" in query_lower or "today" in query_lower or "本日" in query_lower:
            return "today"

        # 今週
        if "今週" in query_lower or "this week" in query_lower:
            return "thisWeek"

        # 来週
        if "来週" in query_lower or "next week" in query_lower:
            return "nextWeek"

        # 今月
        if "今月" in query_lower or "this month" in query_lower:
            return "thisMonth"

        # デフォルトは今週
        return "thisWeek"
