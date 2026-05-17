"""Tests for backend/tools/web_search.py — keyword detection utility"""

from backend.tools.web_search import should_use_web_search


class TestShouldUseWebSearch:
    """Test should_use_web_search() function"""

    def test_japanese_latest_keyword(self):
        assert should_use_web_search("最新のAIニュース") is True

    def test_english_latest_keyword(self):
        assert should_use_web_search("latest AI news") is True

    def test_english_relative_date_updates_keyword(self):
        assert should_use_web_search("today technology updates") is True

    def test_weather_keyword_ja(self):
        assert should_use_web_search("今日の天気はどうですか") is True

    def test_weather_keyword_en(self):
        assert should_use_web_search("current weather") is True

    def test_news_with_relative_date_keyword(self):
        assert should_use_web_search("今日のニュースは?") is True

    def test_date_only_questions_do_not_search(self):
        assert should_use_web_search("今日は何月何日ですか?") is False
        assert should_use_web_search("今日の日付を教えて") is False
        assert should_use_web_search("明日は何日ですか") is False

    def test_bare_relative_dates_do_not_search(self):
        assert should_use_web_search("今日") is False
        assert should_use_web_search("明日") is False
        assert should_use_web_search("昨日") is False
        assert should_use_web_search("今週") is False

    def test_today_events_do_not_trigger_web_search(self):
        assert should_use_web_search("今日のイベントは？") is False

    def test_cafe_question_no_match(self):
        assert should_use_web_search("エンジニアカフェの営業時間") is False

    def test_general_greeting_no_match(self):
        assert should_use_web_search("hello world") is False
