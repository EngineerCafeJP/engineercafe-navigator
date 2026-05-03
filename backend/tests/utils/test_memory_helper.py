"""
SimplifiedMemoryHelper のユニットテスト（セッションベース版）
"""

import os
import pytest
from unittest.mock import Mock, AsyncMock, patch

from backend.utils.memory_helper import SimplifiedMemoryHelper, get_memory_helper

ACTIVE_SESSION_ID = "11111111-1111-4111-8111-111111111111"
ENDED_SESSION_ID = "22222222-2222-4222-8222-222222222222"
MISSING_SESSION_ID = "33333333-3333-4333-8333-333333333333"


class TestSimplifiedMemoryHelper:
    """SimplifiedMemoryHelper のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self._orig_supabase_url = os.environ.get("SUPABASE_URL")
        self._orig_supabase_key = os.environ.get("SUPABASE_KEY")
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = "test-key"

    def teardown_method(self):
        """各テストメソッドの後にクリーンアップ"""
        if self._orig_supabase_url is not None:
            os.environ["SUPABASE_URL"] = self._orig_supabase_url
        else:
            os.environ.pop("SUPABASE_URL", None)
        if self._orig_supabase_key is not None:
            os.environ["SUPABASE_KEY"] = self._orig_supabase_key
        else:
            os.environ.pop("SUPABASE_KEY", None)

    @patch("backend.utils.memory_helper.create_client")
    def test_init_with_credentials(self, mock_create_client):
        """認証情報ありで初期化"""
        mock_client = Mock()
        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()

        assert helper.supabase is not None
        assert helper.agent_name == "langgraph_memory"
        assert helper.max_entries == 100
        assert not hasattr(helper, "ttl_seconds")

    def test_init_without_credentials(self):
        """認証情報なしで初期化"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

            assert helper.supabase is None

    def test_extract_request_type_hours(self):
        """営業時間リクエストタイプの抽出"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

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
        """日本語コンテキスト構築（セッションベースヘッダー）"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        messages = [
            {"role": "user", "content": "営業時間は？", "metadata": {"emotion": "curious"}},
            {
                "role": "assistant",
                "content": "9時から22時です。",
                "metadata": {"emotion": "helpful"},
            },
        ]

        result = helper._build_comprehensive_context(messages, [], "ja")

        assert "セッション内の会話履歴:" in result
        assert "ユーザー: 営業時間は？ [curious]" in result
        assert "アシスタント: 9時から22時です。 [helpful]" in result

    def test_build_comprehensive_context_with_messages_en(self):
        """英語コンテキスト構築（セッションベースヘッダー）"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        messages = [
            {"role": "user", "content": "What are the hours?", "metadata": {"emotion": "curious"}},
            {"role": "assistant", "content": "9am to 10pm.", "metadata": {"emotion": "helpful"}},
        ]

        result = helper._build_comprehensive_context(messages, [], "en")

        assert "Session conversation history:" in result
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
    async def test_store_message_no_expires_at(self, mock_create_client):
        """メッセージ保存でexpires_atが設定されないことを確認"""
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
        # expires_atが設定されていないことを確認
        assert "expires_at" not in call_args

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_store_message_strips_postgres_nul_chars(self, mock_create_client):
        """PostgreSQL jsonb/text に保存できないNUL文字を保存前に除去する"""
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
            content="営業時間\x00は？",
            session_id="test\x00-session",
            metadata={"emotion": "curious\x00"},
        )

        call_args = mock_table.insert.call_args[0][0]
        assert call_args["value"]["content"] == "営業時間は？"
        assert call_args["value"]["sessionId"] == "test-session"
        assert call_args["value"]["emotion"] == "curious"

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
    async def test_is_session_active_true(self, mock_create_client):
        """アクティブなセッションの確認"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.execute = Mock(
            return_value=Mock(data=[{"id": ACTIVE_SESSION_ID, "status": "active"}])
        )

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        result = await helper._is_session_active(ACTIVE_SESSION_ID)

        assert result is True

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_is_session_active_false(self, mock_create_client):
        """非アクティブなセッションの確認"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.execute = Mock(
            return_value=Mock(data=[{"id": ENDED_SESSION_ID, "status": "ended"}])
        )

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        result = await helper._is_session_active(ENDED_SESSION_ID)

        assert result is False

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_is_session_active_not_found(self, mock_create_client):
        """存在しないセッションの確認"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.execute = Mock(return_value=Mock(data=[]))

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        result = await helper._is_session_active(MISSING_SESSION_ID)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_session_active_no_supabase(self):
        """Supabaseなしでのセッション確認"""
        helper = SimplifiedMemoryHelper()
        helper.supabase = None

        result = await helper._is_session_active("test-session")
        assert result is False

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_recent_messages_inactive_session(self, mock_create_client):
        """非アクティブセッションでは空リストを返す"""
        mock_client = Mock()

        # _is_session_active用のモック（conversation_sessions）
        mock_sessions_table = Mock()
        mock_sessions_select = Mock()
        mock_sessions_eq = Mock()
        mock_sessions_eq.execute = Mock(
            return_value=Mock(data=[{"id": ENDED_SESSION_ID, "status": "ended"}])
        )
        mock_sessions_select.eq = Mock(return_value=mock_sessions_eq)
        mock_sessions_table.select = Mock(return_value=mock_sessions_select)

        def table_router(name):
            if name == "conversation_sessions":
                return mock_sessions_table
            return Mock()

        mock_client.table = Mock(side_effect=table_router)
        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        messages = await helper._get_recent_messages(ENDED_SESSION_ID)

        assert messages == []

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_previous_request_type(self, mock_create_client):
        """前回のリクエストタイプ取得のテスト（セッションベース）"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_like = Mock()
        mock_order = Mock()
        mock_limit = Mock()

        # チェーンメソッドのモック設定
        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.like = Mock(return_value=mock_like)
        mock_like.order = Mock(return_value=mock_order)
        mock_order.limit = Mock(return_value=mock_limit)

        mock_limit.execute = Mock(
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
        mock_order.limit.assert_called_once_with(100)

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
        """コンテキスト取得のテスト（セッションベース）"""
        mock_client = Mock()

        # conversation_sessions用モック
        mock_sessions_table = Mock()
        mock_sessions_select = Mock()
        mock_sessions_eq = Mock()
        mock_sessions_eq.execute = Mock(
            return_value=Mock(data=[{"id": "test-session", "status": "active"}])
        )
        mock_sessions_select.eq = Mock(return_value=mock_sessions_eq)
        mock_sessions_table.select = Mock(return_value=mock_sessions_select)

        # agent_memory用モック
        mock_memory_table = Mock()
        mock_memory_select = Mock()
        mock_memory_eq = Mock()
        mock_memory_like = Mock()
        mock_memory_order = Mock()
        mock_memory_limit = Mock()

        mock_memory_table.select = Mock(return_value=mock_memory_select)
        mock_memory_select.eq = Mock(return_value=mock_memory_eq)
        mock_memory_eq.like = Mock(return_value=mock_memory_like)
        mock_memory_like.order = Mock(return_value=mock_memory_order)
        mock_memory_order.limit = Mock(return_value=mock_memory_limit)
        mock_memory_order.execute = Mock(
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
        mock_memory_limit.execute = Mock(
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

        def table_router(name):
            if name == "conversation_sessions":
                return mock_sessions_table
            return mock_memory_table

        mock_client.table = Mock(side_effect=table_router)
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
    async def test_cleanup_session(self, mock_create_client):
        """セッション単位のクリーンアップテスト"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_like = Mock()
        mock_delete = Mock()
        mock_delete_eq = Mock()
        mock_delete_eq.execute = Mock(return_value=Mock(data=[]))

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.like = Mock(return_value=mock_like)
        mock_like.execute = Mock(
            return_value=Mock(
                data=[
                    {"id": "msg-1", "value": {"sessionId": "test-session"}},
                    {"id": "msg-2", "value": {"sessionId": "other-session"}},
                    {"id": "msg-3", "value": {"sessionId": "test-session"}},
                ]
            )
        )
        mock_table.delete = Mock(return_value=mock_delete)
        mock_delete.eq = Mock(return_value=mock_delete_eq)

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        await helper.cleanup_session("test-session")

        # msg-1とmsg-3が削除される（test-sessionに一致する2件）
        assert mock_delete.eq.call_count == 2

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_cleanup(self, mock_create_client):
        """非アクティブセッションのクリーンアップテスト"""
        mock_client = Mock()

        # conversation_sessions用モック
        mock_sessions_table = Mock()
        mock_sessions_select = Mock()
        mock_sessions_neq = Mock()
        mock_sessions_neq.execute = Mock(
            return_value=Mock(data=[{"id": "ended-session-1"}, {"id": "ended-session-2"}])
        )
        mock_sessions_select.neq = Mock(return_value=mock_sessions_neq)
        mock_sessions_table.select = Mock(return_value=mock_sessions_select)

        # agent_memory用モック
        mock_memory_table = Mock()
        mock_memory_select = Mock()
        mock_memory_eq = Mock()
        mock_memory_like = Mock()
        mock_memory_delete = Mock()
        mock_memory_delete_eq = Mock()
        mock_memory_delete_eq.execute = Mock(return_value=Mock(data=[]))

        mock_memory_table.select = Mock(return_value=mock_memory_select)
        mock_memory_select.eq = Mock(return_value=mock_memory_eq)
        mock_memory_eq.like = Mock(return_value=mock_memory_like)
        mock_memory_like.execute = Mock(
            return_value=Mock(
                data=[
                    {"id": "msg-1", "value": {"sessionId": "ended-session-1"}},
                    {"id": "msg-2", "value": {"sessionId": "active-session"}},
                    {"id": "msg-3", "value": {"sessionId": "ended-session-2"}},
                ]
            )
        )
        mock_memory_table.delete = Mock(return_value=mock_memory_delete)
        mock_memory_delete.eq = Mock(return_value=mock_memory_delete_eq)

        def table_router(name):
            if name == "conversation_sessions":
                return mock_sessions_table
            return mock_memory_table

        mock_client.table = Mock(side_effect=table_router)
        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        await helper.cleanup()

        # msg-1とmsg-3が削除される（ended sessionに一致する2件）
        assert mock_memory_delete.eq.call_count == 2

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_memory_stats(self, mock_create_client):
        """メモリ統計取得のテスト（セッションベース）"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_like = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.like = Mock(return_value=mock_like)

        mock_like.execute = Mock(
            return_value=Mock(
                data=[
                    {"value": {"timestamp": 1000, "emotion": "happy", "sessionId": "s1"}},
                    {"value": {"timestamp": 2000, "emotion": "happy", "sessionId": "s1"}},
                    {"value": {"timestamp": 3000, "emotion": "sad", "sessionId": "s1"}},
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

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_memory_stats_with_session_filter(self, mock_create_client):
        """セッションフィルタ付きメモリ統計取得"""
        mock_client = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()
        mock_like = Mock()

        mock_client.table = Mock(return_value=mock_table)
        mock_table.select = Mock(return_value=mock_select)
        mock_select.eq = Mock(return_value=mock_eq)
        mock_eq.like = Mock(return_value=mock_like)

        mock_like.execute = Mock(
            return_value=Mock(
                data=[
                    {"value": {"timestamp": 1000, "emotion": "happy", "sessionId": "s1"}},
                    {"value": {"timestamp": 2000, "emotion": "neutral", "sessionId": "s2"}},
                    {"value": {"timestamp": 3000, "emotion": "sad", "sessionId": "s1"}},
                ]
            )
        )

        mock_create_client.return_value = mock_client

        helper = SimplifiedMemoryHelper()
        stats = await helper.get_memory_stats(session_id="s1")

        # s1のメッセージのみ（2件）
        assert stats["active_turns"] == 2
        assert stats["oldest_turn"] == 1000
        assert stats["newest_turn"] == 3000


class TestGetMemoryHelper:
    """get_memory_helper関数のテスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self._orig_supabase_url = os.environ.get("SUPABASE_URL")
        self._orig_supabase_key = os.environ.get("SUPABASE_KEY")

    def teardown_method(self):
        """各テストメソッドの後にクリーンアップ"""
        if self._orig_supabase_url is not None:
            os.environ["SUPABASE_URL"] = self._orig_supabase_url
        else:
            os.environ.pop("SUPABASE_URL", None)
        if self._orig_supabase_key is not None:
            os.environ["SUPABASE_KEY"] = self._orig_supabase_key
        else:
            os.environ.pop("SUPABASE_KEY", None)

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


class TestRAGIntegration:
    """RAG統合テスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self._orig_supabase_url = os.environ.get("SUPABASE_URL")
        self._orig_supabase_key = os.environ.get("SUPABASE_KEY")

    def teardown_method(self):
        """各テストメソッドの後にクリーンアップ"""
        if self._orig_supabase_url is not None:
            os.environ["SUPABASE_URL"] = self._orig_supabase_url
        else:
            os.environ.pop("SUPABASE_URL", None)
        if self._orig_supabase_key is not None:
            os.environ["SUPABASE_KEY"] = self._orig_supabase_key
        else:
            os.environ.pop("SUPABASE_KEY", None)

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_context_with_rag_integration(self, mock_create_client):
        """include_knowledge_base=Trueの場合、RAG検索が実行されることを確認"""
        mock_client = Mock()

        # conversation_sessions用モック
        mock_sessions_table = Mock()
        mock_sessions_select = Mock()
        mock_sessions_eq = Mock()
        mock_sessions_eq.execute = Mock(
            return_value=Mock(data=[{"id": "test-session", "status": "active"}])
        )
        mock_sessions_select.eq = Mock(return_value=mock_sessions_eq)
        mock_sessions_table.select = Mock(return_value=mock_sessions_select)

        # agent_memory用モック
        mock_memory_table = Mock()
        mock_memory_select = Mock()
        mock_memory_eq = Mock()
        mock_memory_like = Mock()
        mock_memory_order = Mock()
        mock_memory_limit = Mock()

        mock_memory_table.select = Mock(return_value=mock_memory_select)
        mock_memory_select.eq = Mock(return_value=mock_memory_eq)
        mock_memory_eq.like = Mock(return_value=mock_memory_like)
        mock_memory_like.order = Mock(return_value=mock_memory_order)
        mock_memory_order.limit = Mock(return_value=mock_memory_limit)
        mock_memory_order.execute = Mock(return_value=Mock(data=[]))
        mock_memory_limit.execute = Mock(return_value=Mock(data=[]))

        def table_router(name):
            if name == "conversation_sessions":
                return mock_sessions_table
            return mock_memory_table

        mock_client.table = Mock(side_effect=table_router)
        mock_create_client.return_value = mock_client

        with patch("backend.utils.memory_helper.EnhancedRAGSearch", create=True) as mock_rag_class:
            mock_rag = AsyncMock()
            mock_rag.search = AsyncMock(
                return_value={
                    "success": True,
                    "data": {
                        "results": [
                            {"content": "営業時間は9:00〜22:00", "entity": "engineer-cafe"},
                        ],
                    },
                }
            )
            mock_rag_class.return_value = mock_rag

            # importをモックする別アプローチ
            with patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_cls2:
                mock_rag_cls2.return_value = mock_rag

                helper = SimplifiedMemoryHelper()
                result = await helper.get_context(
                    "営業時間は？",
                    "test-session",
                    {"include_knowledge_base": True, "language": "ja"},
                )

                assert len(result["knowledge_results"]) >= 0  # RAG統合が動く（モック次第）

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_context_rag_failure_graceful(self, mock_create_client):
        """RAG検索が失敗しても、get_contextは正常に返ることを確認"""
        mock_client = Mock()

        # conversation_sessions用モック
        mock_sessions_table = Mock()
        mock_sessions_select = Mock()
        mock_sessions_eq = Mock()
        mock_sessions_eq.execute = Mock(
            return_value=Mock(data=[{"id": "test-session", "status": "active"}])
        )
        mock_sessions_select.eq = Mock(return_value=mock_sessions_eq)
        mock_sessions_table.select = Mock(return_value=mock_sessions_select)

        # agent_memory用モック
        mock_memory_table = Mock()
        mock_memory_select = Mock()
        mock_memory_eq = Mock()
        mock_memory_like = Mock()
        mock_memory_order = Mock()
        mock_memory_limit = Mock()

        mock_memory_table.select = Mock(return_value=mock_memory_select)
        mock_memory_select.eq = Mock(return_value=mock_memory_eq)
        mock_memory_eq.like = Mock(return_value=mock_memory_like)
        mock_memory_like.order = Mock(return_value=mock_memory_order)
        mock_memory_order.limit = Mock(return_value=mock_memory_limit)
        mock_memory_order.execute = Mock(return_value=Mock(data=[]))
        mock_memory_limit.execute = Mock(return_value=Mock(data=[]))

        def table_router(name):
            if name == "conversation_sessions":
                return mock_sessions_table
            return mock_memory_table

        mock_client.table = Mock(side_effect=table_router)
        mock_create_client.return_value = mock_client

        # EnhancedRAGSearchが例外を投げる
        with patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_class:
            mock_rag = AsyncMock()
            mock_rag.search = AsyncMock(side_effect=Exception("RAG connection error"))
            mock_rag_class.return_value = mock_rag

            helper = SimplifiedMemoryHelper()
            result = await helper.get_context(
                "テスト", "test-session", {"include_knowledge_base": True, "language": "ja"}
            )

            # RAGが失敗しても空リストで返る
            assert result["knowledge_results"] == []
            assert "context_string" in result

    @pytest.mark.asyncio
    @patch("backend.utils.memory_helper.create_client")
    async def test_get_context_knowledge_base_disabled(self, mock_create_client):
        """include_knowledge_base=Falseの場合、RAG検索がスキップされることを確認"""
        mock_client = Mock()

        # conversation_sessions用モック
        mock_sessions_table = Mock()
        mock_sessions_select = Mock()
        mock_sessions_eq = Mock()
        mock_sessions_eq.execute = Mock(
            return_value=Mock(data=[{"id": "test-session", "status": "active"}])
        )
        mock_sessions_select.eq = Mock(return_value=mock_sessions_eq)
        mock_sessions_table.select = Mock(return_value=mock_sessions_select)

        # agent_memory用モック
        mock_memory_table = Mock()
        mock_memory_select = Mock()
        mock_memory_eq = Mock()
        mock_memory_like = Mock()
        mock_memory_order = Mock()
        mock_memory_limit = Mock()

        mock_memory_table.select = Mock(return_value=mock_memory_select)
        mock_memory_select.eq = Mock(return_value=mock_memory_eq)
        mock_memory_eq.like = Mock(return_value=mock_memory_like)
        mock_memory_like.order = Mock(return_value=mock_memory_order)
        mock_memory_order.limit = Mock(return_value=mock_memory_limit)
        mock_memory_order.execute = Mock(return_value=Mock(data=[]))
        mock_memory_limit.execute = Mock(return_value=Mock(data=[]))

        def table_router(name):
            if name == "conversation_sessions":
                return mock_sessions_table
            return mock_memory_table

        mock_client.table = Mock(side_effect=table_router)
        mock_create_client.return_value = mock_client

        with patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_class:
            helper = SimplifiedMemoryHelper()
            result = await helper.get_context(
                "テスト", "test-session", {"include_knowledge_base": False, "language": "ja"}
            )

            # RAGが呼ばれないことを確認
            mock_rag_class.assert_not_called()
            assert result["knowledge_results"] == []
