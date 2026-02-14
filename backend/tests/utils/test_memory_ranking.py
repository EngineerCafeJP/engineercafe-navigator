"""
メモリランキングのユニットテスト
"""

import pytest
from datetime import datetime
from unittest.mock import patch, Mock

from backend.utils.memory_helper import SimplifiedMemoryHelper


class TestMemoryRanking:
    """SimplifiedMemoryHelper._rank_messages のテスト"""

    @pytest.fixture
    def helper(self):
        """メモリヘルパーのフィクスチャ（Supabase接続なし）"""
        with patch("backend.utils.memory_helper.create_client") as mock_create:
            mock_create.return_value = Mock()
            instance = SimplifiedMemoryHelper()
            instance.supabase = None  # DB接続なし
            return instance

    def test_rank_recent_message_higher(self, helper):
        """最近のメッセージがスコア高いことを確認"""
        now = datetime.now()
        recent_ts = int(now.timestamp() * 1000)  # 今
        old_ts = int((now.timestamp() - 3600 * 48) * 1000)  # 48時間前

        messages = [
            {
                "role": "user",
                "content": "Wi-Fiのパスワード",
                "metadata": {"timestamp": old_ts},
            },
            {
                "role": "user",
                "content": "Wi-Fiの接続方法",
                "metadata": {"timestamp": recent_ts},
            },
        ]

        ranked = helper._rank_messages(messages, "Wi-Fi")

        # 最近のメッセージが先に来る
        assert ranked[0]["metadata"]["timestamp"] == recent_ts

    def test_rank_relevant_message_higher(self, helper):
        """クエリに関連するメッセージがスコア高いことを確認"""
        now = datetime.now()
        same_ts = int(now.timestamp() * 1000)

        messages = [
            {
                "role": "user",
                "content": "イベントの情報が知りたい",
                "metadata": {"timestamp": same_ts},
            },
            {
                "role": "user",
                "content": "Wi-Fiのパスワードを教えて",
                "metadata": {"timestamp": same_ts},
            },
        ]

        ranked = helper._rank_messages(messages, "Wi-Fiのパスワード")

        # Wi-Fi関連メッセージが先に来る
        assert "Wi-Fi" in ranked[0]["content"]

    def test_rank_frequent_topic_bonus(self, helper):
        """頻出トピックにボーナスがあることを確認"""
        now = datetime.now()
        ts = int(now.timestamp() * 1000)

        messages = [
            {
                "role": "user",
                "content": "営業時間は何時まで？",
                "metadata": {"timestamp": ts},
            },
            {
                "role": "assistant",
                "content": "営業時間は9時から22時です",
                "metadata": {"timestamp": ts},
            },
            {
                "role": "user",
                "content": "まったく別の話題について",
                "metadata": {"timestamp": ts},
            },
        ]

        ranked = helper._rank_messages(messages, "テスト")

        # 営業時間トピックのメッセージは互いにオーバーラップ → frequency高い
        # 「別の話題」はオーバーラップ低い → frequency低い
        business_scores = [r["_rank_score"] for r in ranked if "営業時間" in r["content"]]
        other_scores = [r["_rank_score"] for r in ranked if "別の話題" in r["content"]]

        if business_scores and other_scores:
            assert max(business_scores) >= min(other_scores)

    def test_rank_empty_messages(self, helper):
        """空リストでエラーにならないことを確認"""
        ranked = helper._rank_messages([], "テスト")
        assert ranked == []

    def test_rank_preserves_original_data(self, helper):
        """元のメッセージデータが保持されることを確認"""
        now = datetime.now()
        ts = int(now.timestamp() * 1000)

        messages = [
            {
                "role": "user",
                "content": "テストメッセージ",
                "metadata": {"timestamp": ts, "emotion": "neutral"},
            },
        ]

        ranked = helper._rank_messages(messages, "テスト")

        assert len(ranked) == 1
        assert ranked[0]["role"] == "user"
        assert ranked[0]["content"] == "テストメッセージ"
        assert ranked[0]["metadata"]["emotion"] == "neutral"
        assert "_rank_score" in ranked[0]
        assert 0.0 <= ranked[0]["_rank_score"] <= 1.0
