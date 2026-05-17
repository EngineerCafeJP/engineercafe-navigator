"""Web Search - Keyword detection utility

Determines whether a user query requires web search based on keyword matching.
The actual web search is performed by TavilySearchTool.
"""

import re

_WEB_SEARCH_KEYWORDS: list[str] = [
    # Explicit current-information markers only.
    "最新",
    "現在",
    "ニュース",
    "天気",
    "気温",
    "雨",
    "検索",
    "動向",
    "トレンド",
    "latest",
    "current",
    "news",
    "weather",
    "temperature",
    "rain",
    "search",
    "trend",
    "updates",
]

_RELATIVE_DATE_CONTEXT_MARKERS: list[str] = [
    "今日",
    "明日",
    "昨日",
    "今朝",
    "今夜",
    "今週",
    "today",
    "tomorrow",
    "yesterday",
    "this week",
]

_LIVE_INFO_MARKERS: list[str] = [
    "最新",
    "現在",
    "ニュース",
    "天気",
    "気温",
    "雨",
    "検索",
    "動向",
    "トレンド",
    "latest",
    "current",
    "news",
    "weather",
    "temperature",
    "rain",
    "search",
    "trend",
    "updates",
]


def _compact_query(query: str) -> str:
    return re.sub(r"[\s　]+", "", query.lower()).strip("!?？。、.,")


def _is_date_only_query(query: str) -> bool:
    compact = _compact_query(query)
    if compact in {
        "今日",
        "本日",
        "明日",
        "昨日",
        "今週",
        "today",
        "tomorrow",
        "yesterday",
        "thisweek",
    }:
        return True

    if any(marker in compact for marker in ("イベント", "event", "予定", "schedule")):
        return False

    if any(marker in compact for marker in _LIVE_INFO_MARKERS):
        return False

    relative_date_markers = (
        "今日",
        "本日",
        "明日",
        "昨日",
        "今週",
        "today",
        "tomorrow",
        "yesterday",
        "thisweek",
    )
    date_question_markers = (
        "日付",
        "何月何日",
        "何日",
        "何曜日",
        "曜日",
        "date",
        "dayisit",
        "dayis",
        "whatday",
    )
    if any(marker in compact for marker in relative_date_markers) and any(
        marker in compact for marker in date_question_markers
    ):
        return True

    return any(
        marker in compact
        for marker in (
            "whatisthedate",
            "whatsthedate",
            "todaysdate",
            "tomorrowsdate",
            "yesterdaysdate",
        )
    )


def should_use_web_search(query: str) -> bool:
    """
    Web検索が必要かどうか判定

    Args:
        query: ユーザーの質問

    Returns:
        True: Web検索が必要, False: ナレッジベースのみで十分
    """
    lower_query = query.lower()
    if _is_date_only_query(lower_query):
        return False

    if any(keyword in lower_query for keyword in _WEB_SEARCH_KEYWORDS):
        return True

    has_relative_date = any(keyword in lower_query for keyword in _RELATIVE_DATE_CONTEXT_MARKERS)
    has_live_info = any(keyword in lower_query for keyword in _LIVE_INFO_MARKERS)
    return has_relative_date and has_live_info
