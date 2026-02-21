"""
Connpass Service Tool
Connpass API v2連携によるイベント情報取得
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional, Literal
import httpx

logger = logging.getLogger(__name__)

TimeRange = Literal["today", "thisWeek", "nextWeek", "thisMonth"]


class ConnpassService:
    """Connpass API v2サービス

    Connpass API v2からイベント情報を取得します。
    エンジニアカフェ関連のイベントや福岡エリアのイベントを検索できます。

    Attributes:
        api_key (str): Connpass APIキー
        base_url (str): Connpass API v2エンドポイント

    Examples:
        >>> service = ConnpassService()
        >>> result = await service.search_events(
        ...     time_range="thisWeek",
        ...     keyword="エンジニアカフェ"
        ... )
        >>> print(result["data"]["eventCount"])
        5

    Notes:
        - API v2では X-API-Key ヘッダーが必須
        - 1リクエストあたり最大100件まで取得可能
        - 福岡県（prefecture=40）をデフォルトで指定
    """

    BASE_URL = "https://connpass.com/api/v2/events/"
    FUKUOKA_PREFECTURE = "fukuoka"  # API v2では文字列で指定

    def __init__(self):
        """ConnpassServiceを初期化

        環境変数からAPIキーを取得します。
        """
        self.api_key = os.getenv("CONNPASS_API_KEY", "")
        if not self.api_key:
            logger.warning("CONNPASS_API_KEY not configured")

    async def search_events(
        self,
        time_range: TimeRange = "thisWeek",
        keyword: Optional[str] = None,
        prefecture: Optional[str] = None,
        count: int = 20,
    ) -> Dict:
        """
        Connpassからイベントを検索

        Args:
            time_range: 検索期間（today, thisWeek, nextWeek, thisMonth）
            keyword: 検索キーワード（オプション）
            prefecture: 都道府県コード（オプション、デフォルトは福岡）
            count: 取得件数（最大100）

        Returns:
            イベント情報辞書 {success, data: {events, timeRange, eventCount, source}}

        Examples:
            >>> service = ConnpassService()
            >>> result = await service.search_events(
            ...     time_range="thisWeek",
            ...     keyword="Python"
            ... )
            >>> print(result["success"])
            True
        """
        try:
            logger.info("Searching events: time_range=%s, keyword=%s", time_range, keyword)

            if not self.api_key:
                logger.warning("API key not configured, returning empty result")
                return {
                    "success": False,
                    "error": "CONNPASS_API_KEY not configured",
                    "data": {
                        "events": [],
                        "timeRange": time_range,
                        "eventCount": 0,
                        "source": "connpass",
                    },
                }

            # 時間範囲から日付リストを生成
            ymd_list = self._get_ymd_list(time_range)

            # Connpass APIでイベント取得
            events = await self._fetch_connpass_events(
                ymd_list=ymd_list,
                keyword=keyword,
                prefecture=prefecture or self.FUKUOKA_PREFECTURE,
                count=count,
            )

            # イベントを整形
            formatted_events = self._format_events(events)

            return {
                "success": True,
                "data": {
                    "events": formatted_events,
                    "timeRange": time_range,
                    "eventCount": len(formatted_events),
                    "source": "connpass",
                },
            }

        except Exception as e:
            logger.exception("ConnpassService error: %s", e)
            return {
                "success": False,
                "error": str(e),
                "data": {
                    "events": [],
                    "timeRange": time_range,
                    "eventCount": 0,
                    "source": "connpass",
                },
            }

    def _get_ymd_list(self, time_range: TimeRange) -> List[str]:
        """
        時間範囲からYYYYMMDD形式の日付リストを生成

        Args:
            time_range: 検索期間

        Returns:
            日付リスト（YYYYMMDD形式）

        Examples:
            >>> service = ConnpassService()
            >>> dates = service._get_ymd_list("today")
            >>> print(dates)
            ["20260125"]
        """
        now = datetime.now()
        today = now.date()

        if time_range == "today":
            return [today.strftime("%Y%m%d")]

        elif time_range == "thisWeek":
            # 今週の月曜日から日曜日
            weekday = today.weekday()
            week_start = today - timedelta(days=weekday)
            return [(week_start + timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]

        elif time_range == "nextWeek":
            # 来週の月曜日から日曜日
            weekday = today.weekday()
            week_start = today - timedelta(days=weekday) + timedelta(weeks=1)
            return [(week_start + timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]

        elif time_range == "thisMonth":
            # 今月の1日から月末
            month_start = today.replace(day=1)
            if month_start.month == 12:
                next_month = month_start.replace(year=month_start.year + 1, month=1)
            else:
                next_month = month_start.replace(month=month_start.month + 1)
            days_in_month = (next_month - month_start).days
            return [
                (month_start + timedelta(days=i)).strftime("%Y%m%d") for i in range(days_in_month)
            ]

        # デフォルトは今週
        weekday = today.weekday()
        week_start = today - timedelta(days=weekday)
        return [(week_start + timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]

    async def _fetch_connpass_events(
        self,
        ymd_list: List[str],
        keyword: Optional[str] = None,
        prefecture: str = FUKUOKA_PREFECTURE,
        count: int = 20,
    ) -> List[Dict]:
        """
        Connpass API v2からイベントを取得

        Args:
            ymd_list: 検索日付リスト（YYYYMMDD形式）
            keyword: 検索キーワード
            prefecture: 都道府県コード
            count: 取得件数

        Returns:
            イベントのリスト
        """
        try:
            headers = {
                "X-API-Key": self.api_key,
                "User-Agent": "EngineerCafeNavigator/1.0",
            }

            params: Dict[str, str | int] = {
                "prefecture": prefecture,
                "order": 2,  # 開催日時順
                "count": min(count, 100),
            }

            # 日付を指定（カンマ区切り）
            if ymd_list:
                params["ymd"] = ",".join(ymd_list)

            # キーワード指定
            if keyword:
                params["keyword"] = keyword

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.BASE_URL,
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(
                        "API error: status=%d, response=%s", response.status_code, response.text
                    )
                    return []

                data = response.json()
                events: List[Dict[Any, Any]] = data.get("events", [])
                return events

        except Exception as e:
            logger.exception("Fetch error: %s", e)
            return []

    def _format_events(self, events: List[Dict]) -> List[Dict]:
        """
        Connpassイベントを整形

        Args:
            events: Connpass APIの生データ

        Returns:
            整形されたイベントのリスト（CalendarServiceと同じフォーマット）

        Notes:
            CalendarServiceと同じフォーマットに統一することで、
            EventAgentでの処理を共通化できる
        """
        formatted_events = []

        for event in events:
            formatted_event = {
                "id": str(event.get("event_id", "")),
                "title": event.get("title", "No Title"),
                "description": event.get("description", "")[:500],  # 長すぎる説明を制限
                "location": event.get("place", "") or event.get("address", ""),
                "start": event.get("started_at", ""),
                "end": event.get("ended_at", ""),
                "htmlLink": event.get("event_url", ""),
                # Connpass固有フィールド
                "source": "connpass",
                "accepted": event.get("accepted", 0),
                "limit": event.get("limit"),
                "waiting": event.get("waiting", 0),
                "owner_nickname": event.get("owner_nickname", ""),
                "group_name": (
                    event.get("series", {}).get("title", "") if event.get("series") else ""
                ),
            }

            formatted_events.append(formatted_event)

        return formatted_events

    def extract_time_range_from_query(self, query: str) -> TimeRange:
        """
        クエリから時間範囲を抽出（CalendarServiceと同じロジック）

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

    def extract_keyword_from_query(self, query: str) -> Optional[str]:
        """
        クエリから検索キーワードを抽出

        Args:
            query: ユーザークエリ

        Returns:
            キーワード（なければNone）

        Examples:
            >>> service = ConnpassService()
            >>> keyword = service.extract_keyword_from_query("Pythonのイベントは？")
            >>> print(keyword)
            "Python"
        """
        # 技術キーワードのリスト
        tech_keywords = [
            "Python",
            "JavaScript",
            "TypeScript",
            "React",
            "Vue",
            "Next.js",
            "Go",
            "Rust",
            "Java",
            "Kotlin",
            "Swift",
            "Flutter",
            "AWS",
            "GCP",
            "Azure",
            "Docker",
            "Kubernetes",
            "AI",
            "機械学習",
            "ML",
            "LLM",
            "生成AI",
            "ChatGPT",
            "データ分析",
            "データサイエンス",
            "Web",
            "フロントエンド",
            "バックエンド",
            "インフラ",
            "セキュリティ",
            "DevOps",
            "SRE",
            "スタートアップ",
            "起業",
            "キャリア",
        ]

        query_lower = query.lower()
        for keyword in tech_keywords:
            if keyword.lower() in query_lower:
                return keyword

        return None
