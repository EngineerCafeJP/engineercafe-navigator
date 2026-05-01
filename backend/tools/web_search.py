"""Web Search - Keyword detection utility

Determines whether a user query requires web search based on keyword matching.
The actual web search is performed by TavilySearchTool.
"""

_WEB_SEARCH_KEYWORDS: list[str] = [
    # Explicit current-information markers only.
    "最新",
    "現在",
    "今日",
    "明日",
    "昨日",
    "今朝",
    "今夜",
    "今週",
    "ニュース",
    "天気",
    "気温",
    "雨",
    "latest",
    "current",
    "today",
    "tomorrow",
    "yesterday",
    "this week",
    "news",
    "weather",
    "temperature",
    "rain",
]


def should_use_web_search(query: str) -> bool:
    """
    Web検索が必要かどうか判定

    Args:
        query: ユーザーの質問

    Returns:
        True: Web検索が必要, False: ナレッジベースのみで十分
    """
    lower_query = query.lower()
    return any(keyword in lower_query for keyword in _WEB_SEARCH_KEYWORDS)
