"""
SimplifiedMemoryHelper のユニットテスト
"""

import os
import pytest
from unittest.mock import Mock, patch

from backend.utils.memory_helper import SimplifiedMemoryHelper, get_memory_helper


class TestSimplifiedMemoryHelper:
    """SimplifiedMemoryHelper のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = "test-key"

    @patch("backend.utils.memory_helper.create_client")
    def test_init_with_credentials(self, mock_create_client):
        """認証情報ありで初期化"""
        mock_client = Mock()
        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()

        assert helper.supabase is not None
        assert helper.agent_name == "langgraph_memory"
        assert helper.ttl_seconds == 180
        assert helper.max_entries == 100

    def test_init_without_credentials(self):
        """認証情報なしで初期化"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

            assert helper.supabase is None

    def test_extract_request_type_hours(self):
        """営業時間リクエストタイプの抽出"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None  # Supabase不要

        assert helper._extract_request_type("営業時間は？") == "hours"
        assert helper._extract_request_type("What are your hours?") == "hours"
        assert helper._extract_request_type("何時まで開いてる？") == "hours"
        assert helper._extract_request_type("いつまで営業していますか？") == "hours"

    def test_extract_request_type_price(self):
        """料金リクエストタイプの抽出"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        assert helper._extract_request_type("料金はいくら？") == "price"
        assert helper._extract_request_type("How much does it cost?") == "price"
        assert helper._extract_request_type("値段を教えて") == "price"

    def test_extract_request_type_location(self):
        """場所リクエストタイプの抽出"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        assert helper._extract_request_type("場所はどこ？") == "location"
        assert helper._extract_request_type("Where is it?") == "location"
        assert helper._extract_request_type("アクセス方法は？") == "location"

    def test_extract_request_type_booking(self):
        """予約リクエストタイプの抽出"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        assert helper._extract_request_type("予約したい") == "booking"
        assert helper._extract_request_type("How do I book?") == "booking"
        assert helper._extract_request_type("reservation please") == "booking"

    def test_extract_request_type_facility(self):
        """設備リクエストタイプの抽出"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        assert helper._extract_request_type("設備について") == "facility"
        assert helper._extract_request_type("What facilities are available?") == "facility"
        assert helper._extract_request_type("何がありますか？") == "facility"

    def test_extract_request_type_events(self):
        """イベントリクエストタイプの抽出"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        assert helper._extract_request_type("イベント情報") == "event"
        assert helper._extract_request_type("Any events?") == "event"
        assert helper._extract_request_type("勉強会ありますか？") == "event"

    def test_extract_request_type_none(self):
        """マッチしない場合はNone"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        assert helper._extract_request_type("こんにちは") is None
        assert helper._extract_request_type("Hello") is None

    def test_build_comprehensive_context_with_messages_ja(self):
        """日本語コンテキスト構築（メッセージあり）"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        messages = [
            {"role": "user", "content": "営業時間は？", "metadata": {"emotion": "curious"}},
            {"role": "assistant", "content": "9時から22時です。", "metadata": {"emotion": "helpful"}},
        ]

        result = helper._build_comprehensive_context(messages, [], "ja")

        assert "最近の会話履歴（直近3分）:" in result
        assert "ユーザー: 営業時間は？ [curious]" in result
        assert "アシスタント: 9時から22時です。 [helpful]" in result

    def test_build_comprehensive_context_with_messages_en(self):
        """英語コンテキスト構築（メッセージあり）"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        messages = [
            {"role": "user", "content": "What are the hours?", "metadata": {"emotion": "curious"}},
            {"role": "assistant", "content": "9am to 10pm.", "metadata": {"emotion": "helpful"}},
        ]

        result = helper._build_comprehensive_context(messages, [], "en")

        assert "Recent conversation (last 3 minutes):" in result
        assert "User: What are the hours? [curious]" in result
        assert "Assistant: 9am to 10pm. [helpful]" in result

    def test_build_comprehensive_context_empty(self):
        """空のコンテキスト構築"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        result_ja = helper._build_comprehensive_context([], [], "ja")
        result_en = helper._build_comprehensive_context([], [], "en")

        assert result_ja == "会話履歴がありません。"
        assert result_en == "No conversation context."

    def test_build_comprehensive_context_with_knowledge(self):
        """ナレッジベース結果を含むコンテキスト構築"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        messages = [{"role": "user", "content": "営業時間は？", "metadata": {}}]
        knowledge = [
            {"content": "営業時間は9:00〜22:00です。", "category": "hours"},
            {"content": "土日祝も営業しています。", "category": "hours"},
        ]

        result = helper._build_comprehensive_context(messages, knowledge, "ja")

        assert "関連するエンジニアカフェ情報:" in result
        assert "1. 営業時間は9:00〜22:00です。 [hours]" in result
        assert "2. 土日祝も営業しています。 [hours]" in result

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_store_message(self, mock_create_client):
        """メッセージ保存のテスト"""
        mock_client = Mock()
        mock_table = Mock()
        mock_insert = Mock()
        mock_insert.execute = Mock(return_value=Mock(data=[{"id": 1}]))
        mock_table.insert = Mock(return_value=mock_insert)
        mock_client.table = Mock(return_value=mock_table)
        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()

        await helper.store_message(
            role="user",
            content="営業時間は？",
            session_id="test-session",
            metadata={"emotion": "curious"},
        )

        mock_client.table.assert_called_with("agent_memory")
        mock_table.insert.assert_called_once()
        call_args = mock_table.insert.call_args[0][0]
        assert call_args["agent_name"] == "langgraph_memory"
        assert "message_" in call_args["key"]
        assert call_args["value"]["role"] == "user"
        assert call_args["value"]["content"] == "営業時間は？"
        assert call_args["value"]["request_type"] == "hours"

    @pytest.mark.asyncio
    async def test_store_message_without_supabase(self):
        """Supabaseなしでのメッセージ保存（スキップされる）"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        # エラーなく完了することを確認
        await helper.store_message(
            role="user",
            content="テスト",
            session_id="test-session",
        )

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_previous_request_type(self, mock_create_client):
        """前回のリクエストタイプ取得のテスト"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_like = Mock()
        mock_gt = Mock()
        mock_order = Mock()

        # チェーンメソッドのモック設定
        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.like = Mock(return_value=mock_like)
        mock_like.gt = Mock(return_value=mock_gt)
        mock_gt.order = Mock(return_value=mock_order)

        mock_order.execute = Mock(
            return_value=Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "sessionId": "test-session",
                            "request_type": "hours",
                        }
                    }
                ]
            )
        )

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        result = await helper.get_previous_request_type("test-session")

        assert result == "hours"

    @pytest.mark.asyncio
    async def test_get_previous_request_type_without_supabase(self):
        """Supabaseなしでの前回リクエストタイプ取得"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        result = await helper.get_previous_request_type("test-session")
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_context(self, mock_create_client):
        """コンテキスト取得のテスト"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_like = Mock()
        mock_gt = Mock()
        mock_order = Mock()

        mock_limit = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.like = Mock(return_value=mock_like)
        mock_like.gt = Mock(return_value=mock_gt)
        mock_gt.order = Mock(return_value=mock_order)
        mock_order.limit = Mock(return_value=mock_limit)

        mock_limit.execute = Mock(
            return_value=Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "content": "営業時間は？",
                            "sessionId": "test-session",
                            "emotion": "curious",
                            "request_type": "hours",
                            "timestamp": 1234567890,
                        }
                    }
                ]
            )
        )

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        result = await helper.get_context("テスト", "test-session", {"language": "ja"})

        assert "recent_messages" in result
        assert "knowledge_results" in result
        assert "context_string" in result
        assert "inherited_request_type" in result
        assert len(result["recent_messages"]) == 1

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_cleanup(self, mock_create_client):
        """クリーンアップのテスト"""
        mock_client = Mock()
        mock_table = Mock()
        mock_delete = Mock()
        mock_eq = Mock()
        mock_lt = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.delete = Mock(return_value=mock_delete)
        mock_delete.eq = Mock(return_value=mock_eq)
        mock_eq.lt = Mock(return_value=mock_lt)
        mock_lt.execute = Mock(return_value=Mock(data=[]))

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        await helper.cleanup()

        mock_client.table.assert_called_with("agent_memory")
        mock_table.delete.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_memory_stats(self, mock_create_client):
        """メモリ統計取得のテスト"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_like = Mock()
        mock_gt = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.like = Mock(return_value=mock_like)
        mock_like.gt = Mock(return_value=mock_gt)

        mock_gt.execute = Mock(
            return_value=Mock(
                data=[
                    {"value": {"timestamp": 1000, "emotion": "happy"}},
                    {"value": {"timestamp": 2000, "emotion": "happy"}},
                    {"value": {"timestamp": 3000, "emotion": "sad"}},
                ]
            )
        )

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        stats = await helper.get_memory_stats()

        assert stats["active_turns"] == 3
        assert stats["oldest_turn"] == 1000
        assert stats["newest_turn"] == 3000
        assert stats["dominant_emotion"] == "happy"
        assert stats["time_span"] == (3000 - 1000) / (1000 * 60)


class TestGetMemoryHelper:
    """get_memory_helper関数のテスト"""

    @patch("backend.utils.memory_helper.create_client")
    def test_singleton_instance(self, mock_create_client):
        """シングルトンインスタンスの取得"""
        mock_create_client.return_value = Mock()

        # グローバル変数をリセット
        import backend.utils.memory_helper as module

        module._memory_helper_instance = None

        helper1 = get_memory_helper()
        helper2 = get_memory_helper()

        assert helper1 is helper2
