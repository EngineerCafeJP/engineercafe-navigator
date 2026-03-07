"""
近隣施設・交通案内ルーティングのユニットテスト (#109)
"""

import pytest

from backend.config.routing_constants import (
    CATEGORY_TO_AGENT_MAP,
    extract_request_type,
)


class TestNearbyFacilityRouting:
    """近隣施設クエリが facility エージェントにルーティングされることを確認"""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("近くのコンビニはどこ？", "nearby"),
            ("ATMはありますか", "nearby"),
            ("タクシーを呼びたい", "nearby"),
            ("Is there a pharmacy nearby?", "nearby"),
            ("周辺にホテルはありますか", "nearby"),
            ("バス停はどこですか？", "nearby"),
            ("近所にレストランはある？", "nearby"),
            ("Where is the nearest convenience store?", "nearby"),
            ("タクシー乗り場を教えてください", "nearby"),
            ("近隣の病院はありますか", "nearby"),
        ],
    )
    def test_nearby_facility_keywords(self, query, expected):
        """近隣施設キーワードが nearby にルーティングされることを確認"""
        assert extract_request_type(query) == expected

    def test_nearby_maps_to_facility_agent(self):
        """nearby カテゴリが facility エージェントにマッピングされることを確認"""
        assert CATEGORY_TO_AGENT_MAP["nearby"] == "facility"
