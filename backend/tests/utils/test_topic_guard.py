"""トピック遵守ガードレールのテスト"""

import pytest

from backend.utils.topic_guard import (
    check_topic_adherence,
    get_off_topic_response,
    is_on_topic,
)


class TestIsOnTopic:
    """is_on_topic() のテスト"""

    # --- on-topicクエリ ---
    @pytest.mark.parametrize(
        "query,category",
        [
            ("エンジニアカフェの営業時間は？", "business_info"),
            ("会議室の予約方法を教えてください", "facility"),
            ("次のイベントはいつですか？", "event"),
            ("スライドの内容について質問", "slide"),
            ("Pythonの学習方法を教えて", "general_knowledge"),
            ("キャリア相談をしたい", "consultation"),
            ("コミュニティイベントについて", "community"),
            ("エンジニアとしてのキャリアパス", "career"),
            ("利用料金はいくらですか？", "pricing"),
            ("アクセス方法を教えてください", "access"),
        ],
    )
    def test_on_topic_queries(self, query: str, category: str):
        assert is_on_topic(query, category) is True

    # --- off-topicクエリ ---
    @pytest.mark.parametrize(
        "query,category",
        [
            ("今日の天気はどうですか？", ""),
            ("おすすめのレシピを教えて", ""),
            ("サッカーの試合結果は？", ""),
            ("ビットコインの価格は？", ""),
            ("政治についてどう思いますか？", ""),
            ("明日の天候予報を教えて", "general_knowledge"),
            ("パチンコで勝つ方法", ""),
            ("What's the weather like?", ""),
            ("Give me a recipe for pasta", ""),
            ("What are the stock market trends?", ""),
        ],
    )
    def test_off_topic_queries(self, query: str, category: str):
        assert is_on_topic(query, category) is False

    # --- 曖昧ケース（on-topic寄り判定） ---
    @pytest.mark.parametrize(
        "query,category",
        [
            ("エンジニアカフェの天気対策は？", "facility"),
            ("プログラミングの勉強", "general_knowledge"),
            ("コワーキングスペースについて", "facility"),
            ("テクノロジーのトレンド", "general_knowledge"),
            ("福岡のIT企業について", "career"),
        ],
    )
    def test_ambiguous_queries_favor_on_topic(self, query: str, category: str):
        assert is_on_topic(query, category) is True

    def test_empty_query_is_on_topic(self):
        assert is_on_topic("", "") is True

    def test_category_override_off_topic_keyword(self):
        """カテゴリがon-topicならoff-topicキーワードを含んでいてもTrue"""
        assert is_on_topic("エンジニアカフェの天気対策", "facility") is True


class TestGetOffTopicResponse:
    """get_off_topic_response() のテスト"""

    def test_japanese_response(self):
        resp = get_off_topic_response("ja")
        assert "エンジニアカフェ" in resp
        assert "業務範囲外" in resp

    def test_english_response(self):
        resp = get_off_topic_response("en")
        assert "Engineer Cafe" in resp

    def test_chinese_response(self):
        resp = get_off_topic_response("zh")
        assert "Engineer Cafe" in resp

    def test_korean_response(self):
        resp = get_off_topic_response("ko")
        assert "엔지니어 카페" in resp

    def test_unknown_language_falls_back_to_english(self):
        resp = get_off_topic_response("fr")
        assert "Engineer Cafe" in resp


class TestCheckTopicAdherence:
    """check_topic_adherence() のテスト"""

    def test_on_topic_returns_true_and_empty(self):
        on_topic, response = check_topic_adherence("営業時間は？", "business_info", "ja")
        assert on_topic is True
        assert response == ""

    def test_off_topic_returns_false_and_response(self):
        on_topic, response = check_topic_adherence("天気はどうですか？", "", "ja")
        assert on_topic is False
        assert "エンジニアカフェ" in response

    def test_off_topic_english_response(self):
        on_topic, response = check_topic_adherence("What's the weather?", "", "en")
        assert on_topic is False
        assert "Engineer Cafe" in response
