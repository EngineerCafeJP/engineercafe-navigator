"""
ルーティング定数

エージェントルーティングに使用するキーワードとテンプレートを定義する。
"""

# 挨拶キーワード（ルーターで挨拶意図を検出するために使用）
GREETING_KEYWORDS: list[str] = [
    "おはよう",
    "こんにちは",
    "こんばんは",
    "hello",
    "good morning",
    "good afternoon",
    "good evening",
    "hi",
    "hey",
]

# 時間帯別挨拶テンプレート
TIME_GREETING_TEMPLATES: dict[str, dict[str, str]] = {
    "morning": {
        "ja": "おはようございます！エンジニアカフェへようこそ。",
        "en": "Good morning! Welcome to Engineer Cafe.",
    },
    "afternoon": {
        "ja": "こんにちは！エンジニアカフェへようこそ。",
        "en": "Good afternoon! Welcome to Engineer Cafe.",
    },
    "evening": {
        "ja": "こんばんは！エンジニアカフェへようこそ。",
        "en": "Good evening! Welcome to Engineer Cafe.",
    },
    "night": {
        "ja": "こんばんは！エンジニアカフェへようこそ。",
        "en": "Good evening! Welcome to Engineer Cafe.",
    },
}

# 閉館警告テンプレート
CLOSING_WARNING_TEMPLATES: dict[str, str] = {
    "ja": "なお、閉館まであと約{minutes}分です。お忘れ物のないようご注意ください。",
    "en": "Please note that we will be closing in about {minutes} minutes. "
    "Please make sure you have all your belongings.",
}

# 休館日メッセージテンプレート
CLOSED_DAY_TEMPLATES: dict[str, str] = {
    "ja": "本日は休館日です。次の営業日にお越しください。",
    "en": "We are closed today. Please visit us on the next business day.",
}
