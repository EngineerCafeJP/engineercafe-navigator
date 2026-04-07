"""Web Search - Keyword detection utility

Determines whether a user query requires web search based on keyword matching.
The actual web search is performed by TavilySearchTool.
"""

_WEB_SEARCH_KEYWORDS: list[str] = [
    # 最新情報・ニュース関連（日本語）
    "最新",
    "現在",
    "今",
    "今日",
    "昨日",
    "ニュース",
    "トレンド",
    # スタートアップ・技術関連（日本語）
    "スタートアップ",
    "ベンチャー",
    "技術",
    "ai",
    "人工知能",
    "機械学習",
    "プログラミング",
    # スポーツ関連（日本語）
    "野球",
    "サッカー",
    "試合",
    "結果",
    "スコア",
    "ホークス",
    "ソフトバンク",
    # 天気関連（日本語）
    "天気",
    "気温",
    "雨",
    # 最新情報・ニュース関連（英語）
    "latest",
    "current",
    "now",
    "today",
    "yesterday",
    "news",
    "trend",
    # スタートアップ・技術関連（英語）
    "startup",
    "venture",
    "technology",
    "artificial intelligence",
    "machine learning",
    "programming",
    # スポーツ関連（英語）
    "baseball",
    "soccer",
    "game",
    "result",
    "score",
    "hawks",
    "softbank",
    # 天気関連（英語）
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
