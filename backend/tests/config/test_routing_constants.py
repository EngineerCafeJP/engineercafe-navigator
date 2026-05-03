"""
routing_constants のユニットテスト - 新規キーワードルーティング
"""

import pytest

from backend.config.routing_constants import (
    CATEGORY_TO_AGENT_MAP,
    extract_request_type,
)


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
            ("실내에서 흡연할 수 있나요?", "smoking"),
        ],
    )
    def test_smoking_keywords(self, query, expected):
        """喫煙キーワードがsmokingにルーティングされることを確認"""
        assert extract_request_type(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("What spaces are available at Engineer Cafe?", "facility"),
            ("Tell me about available spaces.", "facility"),
        ],
    )
    def test_available_spaces_keywords(self, query, expected):
        """英語のスペース一覧質問がfacilityにルーティングされることを確認"""
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


class TestReceptionRouting:
    """受付キーワードルーティングテスト"""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("初めて来ました", "reception"),
            ("利用方法を教えてください", "reception"),
            ("チェックインしたいです", "reception"),
            ("How do I check-in?", "reception"),
        ],
    )
    def test_reception_keywords(self, query, expected):
        """受付キーワードがreceptionにルーティングされることを確認"""
        assert extract_request_type(query) == expected

    def test_reception_place_query_stays_location(self):
        """受付の場所を聞く質問は来館受付フローではなく施設案内として扱う"""
        assert extract_request_type("受付はどこにありますか？") == "location"

    def test_reception_maps_to_business_info(self):
        """receptionカテゴリがbusiness_infoにマッピングされることを確認"""
        assert CATEGORY_TO_AGENT_MAP["reception"] == "business_info"


class TestEmergencyRoutingIntegration:
    """緊急キーワードルーティング統合テスト"""

    def test_emergency_maps_to_facility(self):
        """emergencyカテゴリがfacilityにマッピングされることを確認"""
        assert CATEGORY_TO_AGENT_MAP["emergency"] == "facility"

    def test_emergency_priority_over_other_keywords(self):
        """emergencyは他のキーワードより優先される"""
        # "場所" is a location keyword but "AED" is emergency
        assert extract_request_type("AEDの場所はどこ？") == "emergency"
