"""
routing_constants のユニットテスト - 新規キーワードルーティング
"""

import pytest

from backend.config.routing_constants import extract_request_type


class TestNewRoutingKeywords:
    """駐車場/駐輪場/喫煙/飲食の新規ルーティングキーワードテスト"""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("駐車場はありますか？", "parking"),
            ("Where can I park my car?", "parking"),
            ("パーキングについて教えて", "parking"),
        ],
    )
    def test_parking_keywords(self, query, expected):
        """駐車場キーワードがparkingにルーティングされることを確認"""
        assert extract_request_type(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("駐輪場はありますか？", "bicycle"),
            ("自転車はどこに停められますか？", "bicycle"),
            ("Is there bicycle parking?", "bicycle"),
        ],
    )
    def test_bicycle_keywords(self, query, expected):
        """駐輪場キーワードがbicycleにルーティングされることを確認"""
        assert extract_request_type(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("喫煙所はありますか？", "smoking"),
            ("タバコは吸えますか？", "smoking"),
            ("Is smoking allowed?", "smoking"),
        ],
    )
    def test_smoking_keywords(self, query, expected):
        """喫煙キーワードがsmokingにルーティングされることを確認"""
        assert extract_request_type(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("飲食は可能ですか？", "food_drink"),
            ("食べ物の持ち込みはできますか？", "food_drink"),
            ("Can I bring food?", "food_drink"),
            ("飲み物は持ってきていいですか？", "food_drink"),
        ],
    )
    def test_food_drink_keywords(self, query, expected):
        """飲食キーワードがfood_drinkにルーティングされることを確認"""
        assert extract_request_type(query) == expected
