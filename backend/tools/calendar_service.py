"""
Calendar Service Tool
ICS/iCal形式によるイベント情報取得

Google Calendar APIを使用せず、公開ICSフィードからイベントを取得します。
これにより、Google Cloud APIキーなしで利用可能です。
"""

import logging
import os
import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Literal, Optional
from zoneinfo import ZoneInfo
import httpx

logger = logging.getLogger(__name__)

TimeRange = Literal["today", "tomorrow", "thisWeek", "nextWeek", "thisMonth"]
_JST = ZoneInfo("Asia/Tokyo")


class CalendarService:
    """ICS/iCalカレンダーサービス"""

    def __init__(self):
        """初期化"""
        self.ical_url = os.getenv("GOOGLE_CALENDAR_ICAL_URL", "")

    async def search_events(self, time_range: TimeRange = "thisWeek") -> Dict:
        """
        指定期間のイベントを検索

        Args:
            time_range: 検索期間（today, tomorrow, thisWeek, nextWeek, thisMonth）

        Returns:
            イベント情報辞書 {success, data: {events, timeRange, eventCount}}
        """
        try:
            logger.info("Searching events for time_range: %s", time_range)

            # 期間の開始日と終了日を計算
            time_min, time_max = self._calculate_time_range(time_range)

            # ICSからイベント取得
            events = await self._fetch_ics_events(time_min, time_max)

            return {
                "success": True,
                "data": {
                    "events": events,
                    "timeRange": time_range,
                    "eventCount": len(events),
                },
            }

        except Exception as e:
            logger.exception("CalendarService error: %s", e)
            return {"success": False, "error": str(e)}

    def _calculate_time_range(self, time_range: TimeRange) -> tuple[datetime, datetime]:
        """
        時間範囲を計算

        Returns:
            (time_min, time_max)のタプル
        """
        now = datetime.now(_JST).replace(tzinfo=None)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        if time_range == "today":
            return (today_start, today_end)

        elif time_range == "tomorrow":
            tomorrow_start = today_start + timedelta(days=1)
            tomorrow_end = today_end + timedelta(days=1)
            return (tomorrow_start, tomorrow_end)

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

    async def _fetch_ics_events(self, time_min: datetime, time_max: datetime) -> List[Dict]:
        """
        ICSフィードからイベントを取得

        Args:
            time_min: 検索開始日時
            time_max: 検索終了日時

        Returns:
            イベントのリスト
        """
        if not self.ical_url:
            logger.warning("GOOGLE_CALENDAR_ICAL_URL not configured")
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.ical_url, timeout=30.0)

                if response.status_code != 200:
                    logger.error("ICS fetch error: status=%d", response.status_code)
                    return []

                ics_content = response.text
                all_events = self._parse_ics_content(ics_content)

                # 時間範囲でフィルタリング
                filtered_events = self._filter_events_by_time(all_events, time_min, time_max)

                # 開始日時でソート
                filtered_events.sort(key=lambda e: e.get("start") or "", reverse=False)

                return filtered_events

        except Exception as e:
            logger.exception("ICS fetch error: %s", e)
            return []

    def _parse_ics_content(self, content: str) -> List[Dict]:
        """
        ICSコンテンツをパース

        Args:
            content: ICSファイルの内容

        Returns:
            パースされたイベントのリスト
        """
        events = []

        # VEVENTブロックを抽出
        vevent_pattern = r"BEGIN:VEVENT(.*?)END:VEVENT"
        vevent_matches = re.findall(vevent_pattern, content, re.DOTALL)

        for vevent in vevent_matches:
            event = self._parse_vevent(vevent)
            if event:
                events.append(event)

        return events

    def _parse_vevent(self, vevent_content: str) -> Optional[Dict]:
        """
        VEVENTブロックをパース

        Args:
            vevent_content: VEVENTの内容

        Returns:
            パースされたイベント辞書
        """
        try:
            # 行継続（折り返し）を処理
            # ICSでは長い行は改行+空白で継続される
            content = re.sub(r"\r?\n[ \t]", "", vevent_content)
            lines = content.strip().split("\n")

            event_data: Dict[str, str] = {}

            for line in lines:
                line = line.strip()
                if not line or ":" not in line:
                    continue

                # プロパティ名と値を分離
                # 形式: PROPERTY;PARAM=VALUE:VALUE または PROPERTY:VALUE
                if ";" in line.split(":")[0]:
                    prop_part = line.split(":")[0]
                    prop_name = prop_part.split(";")[0]
                    value = ":".join(line.split(":")[1:])
                else:
                    parts = line.split(":", 1)
                    prop_name = parts[0]
                    value = parts[1] if len(parts) > 1 else ""

                event_data[prop_name.upper()] = value

            # 必須フィールドの確認
            if "DTSTART" not in event_data:
                return None

            # IDの生成（UIDがない場合はハッシュ生成）
            uid = event_data.get("UID", "")
            if not uid:
                uid = hashlib.md5(
                    f"{event_data.get('SUMMARY', '')}{event_data.get('DTSTART', '')}".encode()
                ).hexdigest()

            # 日付のパース
            start_str = self._parse_ics_date(event_data.get("DTSTART", ""))
            end_str = self._parse_ics_date(event_data.get("DTEND", ""))

            # 説明文のエスケープ解除
            description = event_data.get("DESCRIPTION", "")
            description = description.replace("\\n", "\n").replace("\\,", ",")

            return {
                "id": uid,
                "title": event_data.get("SUMMARY", "No Title"),
                "description": description,
                "location": event_data.get("LOCATION", ""),
                "start": start_str,
                "end": end_str,
                "htmlLink": event_data.get("URL", ""),
            }

        except Exception as e:
            logger.exception("VEVENT parse error: %s", e)
            return None

    def _parse_ics_date(self, date_str: str) -> str:
        """
        ICS日付文字列をISO形式に変換

        ICSの日付形式:
        - 20240115T090000Z (UTC)
        - 20240115T090000 (ローカル)
        - 20240115 (終日イベント)

        Args:
            date_str: ICS形式の日付文字列

        Returns:
            ISO 8601形式の日付文字列
        """
        if not date_str:
            return ""

        try:
            # Z付きUTC時刻
            if date_str.endswith("Z"):
                date_str = date_str[:-1]
                if "T" in date_str:
                    dt = datetime.strptime(date_str, "%Y%m%dT%H%M%S")
                else:
                    dt = datetime.strptime(date_str, "%Y%m%d")
                return dt.isoformat() + "Z"

            # ローカル時刻（T付き）
            if "T" in date_str:
                dt = datetime.strptime(date_str, "%Y%m%dT%H%M%S")
                return dt.isoformat()

            # 終日イベント
            dt = datetime.strptime(date_str, "%Y%m%d")
            return dt.date().isoformat()

        except Exception as e:
            logger.exception("Date parse error: %s - %s", date_str, e)
            return date_str

    def _filter_events_by_time(
        self, events: List[Dict], time_min: datetime, time_max: datetime
    ) -> List[Dict]:
        """
        時間範囲でイベントをフィルタリング

        Args:
            events: イベントリスト
            time_min: 開始日時
            time_max: 終了日時

        Returns:
            フィルタリングされたイベントリスト
        """
        filtered = []

        for event in events:
            start_str = event.get("start", "")
            if not start_str:
                continue

            try:
                # ISO形式からdatetimeに変換
                if "T" in start_str:
                    if start_str.endswith("Z"):
                        event_start = datetime.fromisoformat(start_str[:-1])
                    else:
                        event_start = datetime.fromisoformat(start_str)
                else:
                    # 終日イベント
                    event_start = datetime.fromisoformat(start_str)

                # 時間範囲内かチェック
                if time_min <= event_start <= time_max:
                    filtered.append(event)

            except Exception as e:
                logger.exception("Filter error: %s - %s", start_str, e)
                continue

        return filtered

    def extract_time_range_from_query(self, query: str) -> TimeRange:
        """
        クエリから時間範囲を抽出

        Args:
            query: ユーザークエリ

        Returns:
            時間範囲（today, tomorrow, thisWeek, nextWeek, thisMonth）
        """
        query_lower = query.lower()

        # 今日
        if "今日" in query_lower or "today" in query_lower or "本日" in query_lower:
            return "today"

        # 明日
        if "明日" in query_lower or "tomorrow" in query_lower:
            return "tomorrow"

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
