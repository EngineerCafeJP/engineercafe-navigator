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
            ("ペットボトルの飲み物は持ち込めますか？", "food_drink"),
            ("외부 음식을 가져와도 되나요?", "food_drink"),
        ],
    )
    def test_food_drink_keywords(self, query, expected):
        """飲食キーワードがfood_drinkにルーティングされることを確認"""
        assert extract_request_type(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("How can I contact Engineer Cafe?", "contact"),
            ("エンジニアカフェの連絡先を教えてください", "contact"),
        ],
    )
    def test_contact_keywords(self, query, expected):
        """連絡先キーワードがcontactにルーティングされることを確認"""
        assert extract_request_type(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("一時外出のルールは？", "temporary_exit"),
            ("15分以上離席するときはどうすればいいですか？", "temporary_exit"),
            ("ペットを連れて入れますか？", "pets"),
            ("盲導犬は同伴できますか？", "pets"),
        ],
    )
    def test_live_ragas_policy_keywords(self, query, expected):
        """C/RAGAS live source guard cases should have deterministic policy request types."""
        assert extract_request_type(query) == expected

    @pytest.mark.parametrize(
        "query",
        [
            "ペットボトルは持ち込めますか？",
            "Tell me about the competition rules.",
        ],
    )
    def test_pet_policy_keywords_avoid_substring_false_positives(self, query):
        """Pet policy should not catch bottle or English substring matches."""
        assert extract_request_type(query) != "pets"


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

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("初めて来ました。フロアマップを見せてください。", "floor_layout"),
            ("初めて来ました。駐車場はありますか？", "parking"),
        ],
    )
    def test_hajimete_does_not_preempt_more_specific_intents(self, query, expected):
        """広い「初めて」は具体的な施設系意図を奪わない"""
        assert extract_request_type(query) == expected

    def test_reception_maps_to_business_info(self):
        """receptionカテゴリがbusiness_infoにマッピングされることを確認"""
        assert CATEGORY_TO_AGENT_MAP["reception"] == "business_info"


class TestFarewellRouting:
    """退館キーワードルーティングテスト"""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("see you", "farewell"),
            ("Goodbye!", "farewell"),
            ("Can I see your floor map?", "floor_layout"),
            ("Can I see your opening hours?", "hours"),
        ],
    )
    def test_english_farewell_requires_phrase_boundary(self, query, expected):
        """see your は see you 退館フレーズとして扱わない"""
        assert extract_request_type(query) == expected


class TestEmergencyRoutingIntegration:
    """緊急キーワードルーティング統合テスト"""

    def test_emergency_maps_to_facility(self):
        """emergencyカテゴリがfacilityにマッピングされることを確認"""
        assert CATEGORY_TO_AGENT_MAP["emergency"] == "facility"

    def test_emergency_priority_over_other_keywords(self):
        """emergencyは他のキーワードより優先される"""
        # "場所" is a location keyword but "AED" is emergency
        assert extract_request_type("AEDの場所はどこ？") == "emergency"
