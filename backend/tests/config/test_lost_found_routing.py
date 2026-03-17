"""
忘れ物・落とし物ルーティングのユニットテスト (#110)
"""

import pytest

from backend.config.routing_constants import (
    CATEGORY_TO_AGENT_MAP,
    extract_request_type,
)


class TestLostFoundRouting:
    """忘れ物・落とし物クエリが lost_found カテゴリにルーティングされることを確認"""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("忘れ物をしたのですが", "lost_found"),
            ("財布をなくしました", "lost_found"),
            ("鍵を落とした", "lost_found"),
            ("バッグを置き忘れてしまいました", "lost_found"),
            ("落とし物の窓口はどこですか", "lost_found"),
            ("I lost my bag", "lost_found"),
            ("Is there a lost and found?", "lost_found"),
            ("I forgot my umbrella", "lost_found"),
            ("My keys are missing", "lost_found"),
        ],
    )
    def test_lost_found_keywords(self, query, expected):
        """忘れ物・落とし物キーワードが lost_found にルーティングされることを確認"""
        assert extract_request_type(query) == expected

    def test_lost_found_mapped_to_facility_agent(self):
        """CATEGORY_TO_AGENT_MAP で lost_found が facility にマッピングされることを確認"""
        assert CATEGORY_TO_AGENT_MAP["lost_found"] == "facility"
