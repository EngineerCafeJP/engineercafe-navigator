"""
SimplifiedMemoryHelper ユニットテスト

backend/utils/memory_helper.py の SimplifiedMemoryHelper クラスを
包括的にテストする。既存の test_memory_helper.py はメモリインターフェース/
ランキングの別モジュールをテストしているため、このファイルは
SimplifiedMemoryHelper 固有のロジックに集中する。

テスト方針:
- supabase.create_client をモックし、外部依存なしでテスト
- シングルトン _memory_helper_instance は各テストでリセット
- 純粋関数（_rank_messages, _topic_overlap, _compute_relevance）はモック不要
"""

import os
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import backend.utils.memory_helper as memory_helper_module
from backend.utils.memory_helper import (
    SimplifiedMemoryHelper,
    get_memory_helper,
    infer_previous_request_type_from_messages,
)

_ACTIVE_SESSION_ID = "11111111-1111-1111-1111-111111111111"
_ENDED_SESSION_ID = "22222222-2222-2222-2222-222222222222"
_MISSING_SESSION_ID = "33333333-3333-3333-3333-333333333333"

# =============================================================================
# フィクスチャ
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """各テストでシングルトンインスタンスをリセット"""
    memory_helper_module._memory_helper_instance = None
    yield
    memory_helper_module._memory_helper_instance = None


@pytest.fixture
def mock_supabase_client():
    """モック Supabase クライアントを返すフィクスチャ"""
    client = Mock()
    return client


@pytest.fixture
def helper_with_client(mock_supabase_client):
    """Supabase クライアントを注入済みの SimplifiedMemoryHelper"""
    with patch("backend.utils.memory_helper.create_client", return_value=mock_supabase_client):
        helper = SimplifiedMemoryHelper()
    return helper, mock_supabase_client


@pytest.fixture
def helper_without_client():
    """Supabase クライアントなしの SimplifiedMemoryHelper"""
    with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
        helper = SimplifiedMemoryHelper()
    assert helper.supabase is None
    return helper


def _build_chain_mock(execute_return):
    """Supabase のメソッドチェーン用モックを構築するヘルパー

    .table().select().eq().like().order().limit().execute() など
    任意の深さのチェーンに対応する MagicMock を返す。
    最終的に .execute() が execute_return を返す。
    """
    chain = MagicMock()
    chain.execute.return_value = execute_return
    # 全チェーンメソッドが自身を返す
    for method_name in (
        "select",
        "eq",
        "neq",
        "like",
        "filter",
        "in_",
        "order",
        "limit",
        "insert",
        "delete",
    ):
        getattr(chain, method_name).return_value = chain
    return chain


def test_infer_previous_request_type_from_messages_prefers_latest_user_intent():
    messages = [
        {
            "role": "user",
            "content": "エンジニアカフェの営業時間を教えて",
            "metadata": {"request_type": "hours"},
        },
        {"role": "assistant", "content": "9時から22時です。", "metadata": {}},
        {"role": "user", "content": "料金はいくら？", "metadata": {}},
    ]

    assert infer_previous_request_type_from_messages(messages) == "price"


def test_infer_previous_request_type_from_messages_ignores_assistant_rows():
    messages = [
        {
            "role": "assistant",
            "content": "営業時間の話です。",
            "metadata": {"request_type": "hours"},
        },
        {"role": "user", "content": "こんにちは", "metadata": {}},
    ]

    assert infer_previous_request_type_from_messages(messages) is None


# =============================================================================
# 初期化テスト
# =============================================================================


class TestInit:
    """__init__ メソッドのテスト"""

    @patch("backend.utils.memory_helper.create_client")
    def test_init_with_valid_env_vars_creates_client(self, mock_create_client):
        """有効な環境変数で初期化すると supabase クライアントが作成される"""
        mock_client = Mock()
        mock_create_client.return_value = mock_client

        with patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "valid-key"},
        ):
            helper = SimplifiedMemoryHelper()

        mock_create_client.assert_called_once_with("https://example.supabase.co", "valid-key")
        assert helper.supabase is mock_client
        assert helper.agent_name == "langgraph_memory"
        assert helper.max_entries == 100

    def test_init_without_env_vars_sets_supabase_none(self):
        """環境変数が未設定の場合 supabase が None になる"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}, clear=False):
            helper = SimplifiedMemoryHelper()

        assert helper.supabase is None

    def test_init_with_partial_env_vars_sets_supabase_none(self):
        """URL のみ設定で KEY が空の場合 supabase が None になる"""
        with patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": ""},
            clear=False,
        ):
            helper = SimplifiedMemoryHelper()

        assert helper.supabase is None


# =============================================================================
# シングルトン get_memory_helper テスト
# =============================================================================


class TestGetMemoryHelper:
    """get_memory_helper シングルトンファクトリのテスト"""

    @patch("backend.utils.memory_helper.create_client")
    def test_returns_singleton_instance(self, mock_create_client):
        """同じインスタンスが返される"""
        mock_create_client.return_value = Mock()

        helper1 = get_memory_helper()
        helper2 = get_memory_helper()

        assert helper1 is helper2

    @patch("backend.utils.memory_helper.create_client")
    def test_creates_instance_on_first_call(self, mock_create_client):
        """初回呼び出しでインスタンスが生成される"""
        mock_create_client.return_value = Mock()

        assert memory_helper_module._memory_helper_instance is None
        helper = get_memory_helper()
        assert memory_helper_module._memory_helper_instance is helper

    @patch("backend.utils.memory_helper.create_client")
    def test_returns_simplifiedmemoryhelper_type(self, mock_create_client):
        """返却型が SimplifiedMemoryHelper である"""
        mock_create_client.return_value = Mock()

        helper = get_memory_helper()
        assert isinstance(helper, SimplifiedMemoryHelper)


# =============================================================================
# _is_session_active テスト
# =============================================================================


class TestIsSessionActive:
    """_is_session_active メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_returns_true_for_active_session(self, helper_with_client):
        """アクティブなセッションに対して True を返す"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": _ACTIVE_SESSION_ID, "status": "active"}]))
        client.table.return_value = chain

        result = await helper._is_session_active(_ACTIVE_SESSION_ID)

        assert result is True
        client.table.assert_called_with("conversation_sessions")

    @pytest.mark.asyncio
    async def test_returns_true_when_uuid_session_row_missing(self, helper_with_client):
        """conversation_sessions 行が未作成の UUID セッションは継続を許可する"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = chain

        result = await helper._is_session_active(_MISSING_SESSION_ID)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_ended_session(self, helper_with_client):
        """ended ステータスのセッションに対して False を返す"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": _ENDED_SESSION_ID, "status": "ended"}]))
        client.table.return_value = chain

        result = await helper._is_session_active(_ENDED_SESSION_ID)

        assert result is False

    @pytest.mark.asyncio
    async def test_non_uuid_session_id_skips_conversation_session_lookup(self, helper_with_client):
        """synthetic session_id は UUID カラムへ問い合わせず active 扱いにする"""
        helper, client = helper_with_client

        result = await helper._is_session_active("alpha-b-20260502-B1-BIZ-002")

        assert result is True
        client.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_true_on_exception_fallback(self, helper_with_client):
        """例外発生時はフォールバックとして True を返す"""
        helper, client = helper_with_client
        client.table.side_effect = Exception("DB connection failed")

        result = await helper._is_session_active("session-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_supabase_is_none(self, helper_without_client):
        """supabase が None の場合 False を返す"""
        result = await helper_without_client._is_session_active("session-1")

        assert result is False


# =============================================================================
# get_previous_request_type テスト
# =============================================================================


class TestGetPreviousRequestType:
    """get_previous_request_type メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_returns_request_type_from_latest_user_message(self, helper_with_client):
        """最新の user メッセージから request_type を返す"""
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "sessionId": "sess-1",
                            "request_type": "hours",
                        }
                    },
                    {
                        "value": {
                            "role": "user",
                            "sessionId": "sess-1",
                            "request_type": "price",
                        }
                    },
                ]
            )
        )
        client.table.return_value = chain

        result = await helper.get_previous_request_type("sess-1")

        assert result == "hours"

    @pytest.mark.asyncio
    async def test_emits_previous_request_type_duration_probe(self, helper_with_client):
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "sessionId": "sess-1",
                            "request_type": "hours",
                        }
                    },
                ]
            )
        )
        client.table.return_value = chain

        with patch("backend.observability.structured_logger.log_memory_event") as mock_log:
            result = await helper.get_previous_request_type("sess-1")

        assert result == "hours"
        payloads = [call.kwargs for call in mock_log.call_args_list]
        probe = next(
            payload
            for payload in payloads
            if payload["event"] == "memory_loader_get_previous_request_type"
        )
        compatibility_probe = next(
            payload
            for payload in payloads
            if payload["event"] == "memory_loader_get_previous_request_type_duration_ms"
        )
        assert probe["success"] is True
        assert probe["row_count"] == 1
        assert probe["request_type"] == "hours"
        assert isinstance(probe["memory_loader_get_previous_request_type_duration_ms"], int)
        assert compatibility_probe["request_type"] == "hours"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_messages(self, helper_with_client):
        """メッセージが存在しない場合 None を返す"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = chain

        result = await helper.get_previous_request_type("sess-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_supabase_is_none(self, helper_without_client):
        """supabase が None の場合 None を返す"""
        result = await helper_without_client.get_previous_request_type("sess-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_matching_session(self, helper_with_client):
        """セッションIDが一致するメッセージがない場合 None を返す"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = chain

        result = await helper.get_previous_request_type("sess-1")

        assert result is None
        chain.filter.assert_any_call("value->>sessionId", "eq", "sess-1")

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, helper_with_client):
        """例外発生時は None を返す"""
        helper, client = helper_with_client
        client.table.side_effect = Exception("Query failed")

        result = await helper.get_previous_request_type("sess-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_assistant_messages(self, helper_with_client):
        """assistant メッセージをSQL filterで除外する"""
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "sessionId": "sess-1",
                            "request_type": "price",
                        }
                    },
                ]
            )
        )
        client.table.return_value = chain

        result = await helper.get_previous_request_type("sess-1")

        assert result == "price"
        chain.filter.assert_any_call("value->>role", "eq", "user")

    @pytest.mark.asyncio
    async def test_skips_user_messages_without_request_type(self, helper_with_client):
        """request_type がない user メッセージをスキップする"""
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "sessionId": "sess-1",
                            # request_type なし
                        }
                    },
                    {
                        "value": {
                            "role": "user",
                            "sessionId": "sess-1",
                            "request_type": "location",
                        }
                    },
                ]
            )
        )
        client.table.return_value = chain

        result = await helper.get_previous_request_type("sess-1")

        assert result == "location"


# =============================================================================
# _get_recent_messages テスト
# =============================================================================


class TestGetRecentMessages:
    """_get_recent_messages メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_returns_filtered_messages_for_session(self, helper_with_client):
        """セッションに属するメッセージのみを返す"""
        helper, client = helper_with_client

        # conversation_sessions (active)
        sessions_chain = _build_chain_mock(Mock(data=[{"id": "sess-1", "status": "active"}]))
        # agent_memory (messages): session_id は SQL filter 済み
        memory_chain = _build_chain_mock(
            Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "content": "Hello",
                            "sessionId": "sess-1",
                            "emotion": "neutral",
                            "confidence": 0.9,
                            "timestamp": 1000,
                            "request_type": None,
                        }
                    },
                ]
            )
        )

        def table_router(name):
            if name == "conversation_sessions":
                return sessions_chain
            return memory_chain

        client.table.side_effect = table_router

        messages = await helper._get_recent_messages("sess-1")

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[0]["metadata"]["emotion"] == "neutral"
        memory_chain.filter.assert_called_once_with("value->>sessionId", "eq", "sess-1")

    @pytest.mark.asyncio
    async def test_emits_recent_messages_duration_probe(self, helper_with_client):
        helper, client = helper_with_client
        memory_chain = _build_chain_mock(
            Mock(
                data=[
                    {
                        "value": {
                            "role": "user",
                            "content": "Hello",
                            "sessionId": "sess-1",
                            "timestamp": 1000,
                        }
                    },
                ]
            )
        )
        client.table.return_value = memory_chain

        with patch("backend.observability.structured_logger.log_memory_event") as mock_log:
            messages = await helper._get_recent_messages("sess-1")

        assert len(messages) == 1
        payloads = [call.kwargs for call in mock_log.call_args_list]
        probe = next(
            payload
            for payload in payloads
            if payload["event"] == "memory_loader_get_recent_messages"
        )
        compatibility_probe = next(
            payload
            for payload in payloads
            if payload["event"] == "memory_loader_get_recent_messages_duration_ms"
        )
        assert probe["success"] is True
        assert probe["row_count"] == 1
        assert probe["message_count"] == 1
        assert isinstance(probe["memory_loader_get_recent_messages_duration_ms"], int)
        assert compatibility_probe["message_count"] == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_session_inactive(self, helper_with_client):
        """非アクティブセッションでは空リストを返す"""
        helper, client = helper_with_client
        sessions_chain = _build_chain_mock(
            Mock(data=[{"id": _ENDED_SESSION_ID, "status": "ended"}])
        )
        client.table.return_value = sessions_chain

        messages = await helper._get_recent_messages(_ENDED_SESSION_ID)

        assert messages == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_supabase_is_none(self, helper_without_client):
        """supabase が None の場合は空リストを返す"""
        with patch("backend.observability.structured_logger.log_memory_event") as mock_log:
            messages = await helper_without_client._get_recent_messages("sess-1")

        assert messages == []
        payloads = [call.kwargs for call in mock_log.call_args_list]
        probe = next(
            payload
            for payload in payloads
            if payload["event"] == "memory_loader_get_recent_messages"
        )
        assert probe["success"] is True
        assert probe["skipped"] is True
        assert probe["reason"] == "supabase_unavailable"
        assert probe["row_count"] == 0

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_data(self, helper_with_client):
        """データが存在しない場合は空リストを返す"""
        helper, client = helper_with_client
        sessions_chain = _build_chain_mock(Mock(data=[{"id": "sess-1", "status": "active"}]))
        memory_chain = _build_chain_mock(Mock(data=[]))

        def table_router(name):
            if name == "conversation_sessions":
                return sessions_chain
            return memory_chain

        client.table.side_effect = table_router

        messages = await helper._get_recent_messages("sess-1")

        assert messages == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_exception(self, helper_with_client):
        """例外発生時は空リストを返す"""
        helper, client = helper_with_client
        # _is_session_active の呼び出しで例外 -> True が返る
        # その後の agent_memory クエリで例外
        call_count = 0

        def table_side_effect(name):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # conversation_sessions -> active
                return _build_chain_mock(
                    Mock(data=[{"id": _ACTIVE_SESSION_ID, "status": "active"}])
                )
            # agent_memory -> 例外
            raise Exception("DB error")

        client.table.side_effect = table_side_effect

        with patch("backend.observability.structured_logger.log_memory_event") as mock_log:
            messages = await helper._get_recent_messages(_ACTIVE_SESSION_ID)

        assert messages == []
        payloads = [call.kwargs for call in mock_log.call_args_list]
        probe = next(
            payload
            for payload in payloads
            if payload["event"] == "memory_loader_get_recent_messages"
        )
        assert probe["success"] is False
        assert probe["error_type"] == "Exception"
        assert isinstance(probe["memory_loader_get_recent_messages_duration_ms"], int)


# =============================================================================
# _rank_messages テスト（純粋関数）
# =============================================================================


class TestRankMessages:
    """_rank_messages メソッドのテスト"""

    def _make_helper(self):
        """supabase=None のヘルパーを作成"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            return SimplifiedMemoryHelper()

    def test_returns_empty_list_for_empty_input(self):
        """空リスト入力で空リストを返す"""
        helper = self._make_helper()

        result = helper._rank_messages([], "test query")

        assert result == []

    def test_adds_rank_score_to_each_message(self):
        """各メッセージに _rank_score が追加される"""
        helper = self._make_helper()
        messages = [
            {"content": "Hello", "metadata": {"timestamp": None}},
            {"content": "World", "metadata": {"timestamp": None}},
        ]

        result = helper._rank_messages(messages, "test")

        for msg in result:
            assert "_rank_score" in msg
            assert isinstance(msg["_rank_score"], float)

    def test_sorts_by_composite_score_descending(self):
        """複合スコアの降順でソートされる"""
        helper = self._make_helper()
        now_ts = int(datetime.now().timestamp() * 1000)
        messages = [
            {"content": "old message", "metadata": {"timestamp": now_ts - 86400000 * 7}},
            {"content": "test query match", "metadata": {"timestamp": now_ts}},
        ]

        result = helper._rank_messages(messages, "test query match")

        # 新しくてクエリと一致するメッセージが先頭
        assert result[0]["content"] == "test query match"
        assert result[0]["_rank_score"] >= result[1]["_rank_score"]

    def test_recency_score_higher_for_newer_messages(self):
        """新しいメッセージほど recency スコアが高い"""
        helper = self._make_helper()
        now_ts = int(datetime.now().timestamp() * 1000)
        messages = [
            {"content": "same", "metadata": {"timestamp": now_ts}},
            {"content": "same", "metadata": {"timestamp": now_ts - 86400000 * 3}},
        ]

        result = helper._rank_messages(messages, "unrelated query xyz")

        # 同じ content, 同じ frequency -> recency の差で決まる
        assert result[0]["metadata"]["timestamp"] == now_ts

    def test_handles_messages_without_timestamp(self):
        """timestamp がない場合もエラーにならない（デフォルト1週間前扱い）"""
        helper = self._make_helper()
        messages = [
            {"content": "no timestamp", "metadata": {}},
            {"content": "also no timestamp", "metadata": {"timestamp": None}},
        ]

        result = helper._rank_messages(messages, "query")

        assert len(result) == 2
        for msg in result:
            assert "_rank_score" in msg


# =============================================================================
# _topic_overlap テスト（純粋関数）
# =============================================================================


class TestTopicOverlap:
    """_topic_overlap メソッドのテスト"""

    def _make_helper(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            return SimplifiedMemoryHelper()

    def test_returns_zero_for_empty_content(self):
        """content が空の場合 0.0 を返す"""
        helper = self._make_helper()

        assert helper._topic_overlap({"content": ""}, {"content": "hello"}) == 0.0
        assert helper._topic_overlap({"content": "hello"}, {"content": ""}) == 0.0
        assert helper._topic_overlap({}, {"content": "hello"}) == 0.0
        assert helper._topic_overlap({"content": "hello"}, {}) == 0.0

    def test_returns_positive_for_similar_content(self):
        """類似コンテンツで正の値を返す"""
        helper = self._make_helper()

        score = helper._topic_overlap(
            {"content": "営業時間は何時ですか"},
            {"content": "営業時間を教えてください"},
        )

        assert score > 0.0

    def test_returns_one_for_identical_content(self):
        """同一コンテンツで 1.0 を返す"""
        helper = self._make_helper()

        score = helper._topic_overlap(
            {"content": "完全一致テスト"},
            {"content": "完全一致テスト"},
        )

        assert score == 1.0

    def test_returns_zero_for_completely_different_content(self):
        """完全に異なるコンテンツで 0.0 を返す"""
        helper = self._make_helper()

        # 単一文字は bigram が生成されないため、十分に長い文字列を使う
        score = helper._topic_overlap(
            {"content": "ab"},
            {"content": "cd"},
        )

        assert score == 0.0

    def test_returns_zero_for_single_character_content(self):
        """1文字のコンテンツ（bigram 生成不可）で 0.0 を返す"""
        helper = self._make_helper()

        score = helper._topic_overlap(
            {"content": "a"},
            {"content": "b"},
        )

        assert score == 0.0


# =============================================================================
# _compute_relevance テスト（純粋関数）
# =============================================================================


class TestComputeRelevance:
    """_compute_relevance メソッドのテスト"""

    def _make_helper(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            return SimplifiedMemoryHelper()

    def test_returns_zero_for_empty_query(self):
        """クエリが空の場合 0.0 を返す"""
        helper = self._make_helper()

        score = helper._compute_relevance({"content": "some content"}, "")

        assert score == 0.0

    def test_returns_zero_for_empty_content(self):
        """content が空の場合 0.0 を返す"""
        helper = self._make_helper()

        score = helper._compute_relevance({"content": ""}, "test query")

        assert score == 0.0

    def test_returns_zero_for_missing_content(self):
        """content キーがない場合 0.0 を返す"""
        helper = self._make_helper()

        score = helper._compute_relevance({}, "test query")

        assert score == 0.0

    def test_returns_positive_for_matching_content(self):
        """マッチするコンテンツで正の値を返す"""
        helper = self._make_helper()

        score = helper._compute_relevance(
            {"content": "営業時間は9時から22時です"},
            "営業時間",
        )

        assert score > 0.0

    def test_returns_one_for_exact_match(self):
        """クエリの全 bigram がコンテンツに含まれる場合 1.0 を返す"""
        helper = self._make_helper()

        # content に query の全 bigram が含まれている場合
        score = helper._compute_relevance(
            {"content": "abcde"},
            "abcde",
        )

        assert score == 1.0

    def test_returns_zero_for_no_match(self):
        """マッチしない場合 0.0 を返す"""
        helper = self._make_helper()

        score = helper._compute_relevance(
            {"content": "XY"},
            "ab",
        )

        assert score == 0.0

    def test_single_character_query_returns_zero(self):
        """1文字クエリ（bigram 生成不可）で 0.0 を返す"""
        helper = self._make_helper()

        score = helper._compute_relevance({"content": "hello world"}, "a")

        assert score == 0.0


# =============================================================================
# _build_comprehensive_context テスト
# =============================================================================


class TestBuildComprehensiveContext:
    """_build_comprehensive_context メソッドのテスト"""

    def _make_helper(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            return SimplifiedMemoryHelper()

    def test_with_messages_and_knowledge_ja(self):
        """日本語でメッセージとナレッジ結果を含むコンテキスト構築"""
        helper = self._make_helper()
        messages = [
            {"role": "user", "content": "営業時間は？", "metadata": {"emotion": "curious"}},
            {"role": "assistant", "content": "9時から22時です。", "metadata": {}},
        ]
        knowledge = [
            {"content": "営業時間は9:00-22:00", "category": "hours"},
        ]

        result = helper._build_comprehensive_context(messages, knowledge, "ja")

        assert "セッション内の会話履歴:" in result
        assert "ユーザー: 営業時間は？ [curious]" in result
        assert "アシスタント: 9時から22時です。" in result
        assert "関連するエンジニアカフェ情報:" in result
        assert "1. 営業時間は9:00-22:00 [hours]" in result

    def test_with_messages_and_knowledge_en(self):
        """英語でメッセージとナレッジ結果を含むコンテキスト構築"""
        helper = self._make_helper()
        messages = [
            {"role": "user", "content": "What are the hours?", "metadata": {"emotion": "curious"}},
            {"role": "assistant", "content": "9am to 10pm.", "metadata": {}},
        ]
        knowledge = [
            {"content": "Open 9:00-22:00", "category": "hours"},
        ]

        result = helper._build_comprehensive_context(messages, knowledge, "en")

        assert "Session conversation history:" in result
        assert "User: What are the hours? [curious]" in result
        assert "Assistant: 9am to 10pm." in result
        assert "Relevant Engineer Cafe information:" in result
        assert "1. Open 9:00-22:00 [hours]" in result

    def test_with_empty_inputs_returns_fallback_ja(self):
        """空入力で日本語フォールバック文字列を返す"""
        helper = self._make_helper()

        result = helper._build_comprehensive_context([], [], "ja")

        assert result == "会話履歴がありません。"

    def test_with_empty_inputs_returns_fallback_en(self):
        """空入力で英語フォールバック文字列を返す"""
        helper = self._make_helper()

        result = helper._build_comprehensive_context([], [], "en")

        assert result == "No conversation context."

    def test_messages_only_without_knowledge(self):
        """メッセージのみ（ナレッジなし）のコンテキスト構築"""
        helper = self._make_helper()
        messages = [
            {"role": "user", "content": "Hello", "metadata": {}},
        ]

        result = helper._build_comprehensive_context(messages, [], "en")

        assert "Session conversation history:" in result
        assert "Relevant Engineer Cafe information:" not in result

    def test_knowledge_only_without_messages(self):
        """ナレッジのみ（メッセージなし）のコンテキスト構築"""
        helper = self._make_helper()
        knowledge = [
            {"content": "Free Wi-Fi available", "category": "facility"},
        ]

        result = helper._build_comprehensive_context([], knowledge, "en")

        assert "Session conversation history:" not in result
        assert "Relevant Engineer Cafe information:" in result
        assert "1. Free Wi-Fi available [facility]" in result

    def test_emotion_not_shown_when_none(self):
        """emotion が None の場合はブラケットが表示されない"""
        helper = self._make_helper()
        messages = [
            {"role": "user", "content": "Hello", "metadata": {"emotion": None}},
            {"role": "user", "content": "World", "metadata": {}},
        ]

        result = helper._build_comprehensive_context(messages, [], "en")

        # [None] や [] が表示されていないことを確認
        assert "[None]" not in result
        assert "User: Hello\n" in result or "User: Hello" in result

    def test_knowledge_without_category(self):
        """category がない場合も正しく構築される"""
        helper = self._make_helper()
        knowledge = [
            {"content": "Some info", "category": ""},
            {"content": "No category"},
        ]

        result = helper._build_comprehensive_context([], knowledge, "ja")

        assert "1. Some info" in result
        assert "2. No category" in result


# =============================================================================
# store_message テスト
# =============================================================================


class TestStoreMessage:
    """store_message メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_inserts_into_agent_memory_table(self, helper_with_client):
        """agent_memory テーブルにメッセージが INSERT される"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": 1}]))
        client.table.return_value = chain

        await helper.store_message(
            role="user",
            content="営業時間は？",
            session_id="sess-1",
            metadata={"emotion": "curious", "request_type": "hours"},
        )

        client.table.assert_called_with("agent_memory")
        chain.insert.assert_called_once()
        call_args = chain.insert.call_args[0][0]
        assert call_args["agent_name"] == "langgraph_memory"
        assert "message_" in call_args["key"]
        assert call_args["value"]["role"] == "user"
        assert call_args["value"]["content"] == "営業時間は？"
        assert call_args["value"]["sessionId"] == "sess-1"
        assert call_args["value"]["emotion"] == "curious"
        assert call_args["value"]["request_type"] == "hours"

    @pytest.mark.asyncio
    async def test_auto_extracts_request_type_for_user_messages(self, helper_with_client):
        """user メッセージで metadata に request_type がない場合は自動抽出する"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": 1}]))
        client.table.return_value = chain

        await helper.store_message(
            role="user",
            content="営業時間は？",
            session_id="sess-1",
            metadata={"emotion": "curious"},
        )

        call_args = chain.insert.call_args[0][0]
        assert call_args["value"]["request_type"] == "hours"

    @pytest.mark.asyncio
    async def test_does_not_auto_extract_for_assistant_messages(self, helper_with_client):
        """assistant メッセージでは request_type の自動抽出をしない"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": 1}]))
        client.table.return_value = chain

        await helper.store_message(
            role="assistant",
            content="営業時間は9時から22時です。",
            session_id="sess-1",
            metadata={},
        )

        call_args = chain.insert.call_args[0][0]
        # assistant の場合は request_type が metadata に入っていない
        assert call_args["value"]["request_type"] is None

    @pytest.mark.asyncio
    async def test_skips_when_supabase_is_none(self, helper_without_client):
        """supabase が None の場合はスキップ（エラーなし）"""
        await helper_without_client.store_message(
            role="user",
            content="test",
            session_id="sess-1",
        )
        # エラーなく完了すれば OK

    @pytest.mark.asyncio
    async def test_skips_agent_memory_write_when_stm_write_flag_disabled(
        self,
        helper_with_client,
        monkeypatch,
    ):
        """本番 cutover では Checkpointer を STM の保存先にして agent_memory insert を止める。"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = chain
        monkeypatch.setenv("ENABLE_AGENT_MEMORY_STM_WRITES", "false")

        await helper.store_message(role="user", content="test", session_id="sess-1")

        chain.insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_on_supabase_error(self, helper_with_client):
        """supabase エラー時は例外が伝播する"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        chain.execute.side_effect = Exception("Insert failed")
        client.table.return_value = chain

        with pytest.raises(Exception, match="Insert failed"):
            await helper.store_message(
                role="user",
                content="test",
                session_id="sess-1",
            )

    @pytest.mark.asyncio
    async def test_preserves_existing_request_type_in_metadata(self, helper_with_client):
        """metadata に既に request_type がある場合は上書きしない"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": 1}]))
        client.table.return_value = chain

        await helper.store_message(
            role="user",
            content="営業時間は？",
            session_id="sess-1",
            metadata={"request_type": "custom_type"},
        )

        call_args = chain.insert.call_args[0][0]
        assert call_args["value"]["request_type"] == "custom_type"

    @pytest.mark.asyncio
    async def test_generates_unique_message_key(self, helper_with_client):
        """メッセージキーが一意に生成される"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": 1}]))
        client.table.return_value = chain

        await helper.store_message("user", "msg1", "sess-1")
        key1 = chain.insert.call_args[0][0]["key"]

        await helper.store_message("user", "msg2", "sess-1")
        key2 = chain.insert.call_args[0][0]["key"]

        assert key1.startswith("message_")
        assert key2.startswith("message_")
        # タイムスタンプ + UUID で一意性を確保
        # 同一ミリ秒でも UUID 部分が異なる可能性が高い
        # （厳密な一意性は UUID に依存）

    @pytest.mark.asyncio
    async def test_default_metadata_is_empty_dict(self, helper_with_client):
        """metadata を省略した場合はデフォルトの空辞書になる"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[{"id": 1}]))
        client.table.return_value = chain

        await helper.store_message("assistant", "reply", "sess-1")

        call_args = chain.insert.call_args[0][0]
        assert call_args["value"]["emotion"] is None
        assert call_args["value"]["confidence"] is None


# =============================================================================
# _extract_request_type テスト
# =============================================================================


class TestExtractRequestType:
    """_extract_request_type メソッドのテスト"""

    def _make_helper(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            return SimplifiedMemoryHelper()

    def test_delegates_to_routing_constants(self):
        """routing_constants.extract_request_type に委譲する"""
        helper = self._make_helper()

        assert helper._extract_request_type("営業時間は？") == "hours"
        assert helper._extract_request_type("料金はいくら？") == "price"
        assert helper._extract_request_type("場所はどこ？") == "location"
        assert helper._extract_request_type("予約したい") == "booking"
        assert helper._extract_request_type("こんにちは") is None


# =============================================================================
# cleanup_session テスト
# =============================================================================


class TestCleanupSession:
    """cleanup_session メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_deletes_matching_session_messages(self, helper_with_client):
        """指定セッションのメッセージのみ削除する"""
        helper, client = helper_with_client
        select_chain = _build_chain_mock(
            Mock(
                data=[
                    {"id": "msg-1", "value": {"sessionId": "sess-1"}},
                    {"id": "msg-2", "value": {"sessionId": "sess-2"}},
                    {"id": "msg-3", "value": {"sessionId": "sess-1"}},
                ]
            )
        )
        delete_chain = _build_chain_mock(Mock(data=[]))

        call_count = {"value": 0}

        def table_side_effect(name):
            call_count["value"] += 1
            # select 呼び出し（最初）と delete 呼び出し（後続）を区別
            # delete は table().delete().eq().execute() のチェーン
            return MagicMock(
                select=select_chain.select,
                delete=Mock(return_value=delete_chain),
            )

        client.table.return_value = MagicMock(
            select=select_chain.select,
            delete=Mock(return_value=delete_chain),
        )

        await helper.cleanup_session("sess-1")

        delete_chain.eq.assert_called_once_with("agent_name", helper.agent_name)
        delete_chain.like.assert_called_once_with("key", "message_%")
        delete_chain.filter.assert_called_once_with("value->>sessionId", "eq", "sess-1")

    @pytest.mark.asyncio
    async def test_does_nothing_when_supabase_is_none(self, helper_without_client):
        """supabase が None の場合は何もしない"""
        await helper_without_client.cleanup_session("sess-1")
        # エラーなく完了すれば OK

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_messages(self, helper_with_client):
        """メッセージがない場合は何もしない"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = chain

        await helper.cleanup_session("sess-1")
        # delete が呼ばれないことを暗黙的に確認（例外なし）

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_matching_session(self, helper_with_client):
        """該当セッションのメッセージがない場合は削除しない"""
        helper, client = helper_with_client
        select_chain = _build_chain_mock(
            Mock(
                data=[
                    {"id": "msg-1", "value": {"sessionId": "other-session"}},
                ]
            )
        )
        delete_chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = MagicMock(
            select=select_chain.select,
            delete=Mock(return_value=delete_chain),
        )

        await helper.cleanup_session("sess-1")

        delete_chain.filter.assert_called_once_with("value->>sessionId", "eq", "sess-1")


# =============================================================================
# cleanup テスト
# =============================================================================


class TestCleanup:
    """cleanup メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_cleans_ended_session_messages(self, helper_with_client):
        """ended セッションのメッセージを削除する"""
        helper, client = helper_with_client

        sessions_chain = _build_chain_mock(Mock(data=[{"id": "ended-1"}, {"id": "ended-2"}]))
        memory_chain = _build_chain_mock(
            Mock(
                data=[
                    {"id": "msg-1"},
                    {"id": "msg-3"},
                ]
            )
        )
        delete_chain = _build_chain_mock(Mock(data=[]))

        def table_router(name):
            if name == "conversation_sessions":
                return MagicMock(
                    select=sessions_chain.select,
                )
            return MagicMock(
                select=memory_chain.select,
                delete=Mock(return_value=delete_chain),
            )

        client.table.side_effect = table_router

        await helper.cleanup()

        # msg-1 と msg-3 が削除される（ended セッション）
        assert delete_chain.eq.call_count == 2
        memory_chain.in_.assert_called_once_with("value->>sessionId", ["ended-1", "ended-2"])

    @pytest.mark.asyncio
    async def test_does_nothing_when_supabase_is_none(self, helper_without_client):
        """supabase が None の場合は何もしない"""
        await helper_without_client.cleanup()

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_ended_sessions(self, helper_with_client):
        """ended セッションがない場合は何もしない"""
        helper, client = helper_with_client
        sessions_chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = MagicMock(
            select=sessions_chain.select,
        )

        await helper.cleanup()
        # エラーなく完了

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, helper_with_client):
        """例外発生時もクラッシュしない"""
        helper, client = helper_with_client
        client.table.side_effect = Exception("Connection lost")

        # 例外がキャッチされてクラッシュしない
        await helper.cleanup()


# =============================================================================
# get_memory_stats テスト
# =============================================================================


class TestGetMemoryStats:
    """get_memory_stats メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_returns_stats_with_valid_data(self, helper_with_client):
        """有効なデータから統計情報を計算する"""
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {"value": {"timestamp": 1000, "emotion": "happy", "sessionId": "s1"}},
                    {"value": {"timestamp": 2000, "emotion": "happy", "sessionId": "s1"}},
                    {"value": {"timestamp": 3000, "emotion": "sad", "sessionId": "s1"}},
                ]
            )
        )
        client.table.return_value = chain

        stats = await helper.get_memory_stats()

        assert stats["active_turns"] == 3
        assert stats["oldest_turn"] == 1000
        assert stats["newest_turn"] == 3000
        assert stats["dominant_emotion"] == "happy"
        assert stats["time_span"] == (3000 - 1000) / (1000 * 60)

    @pytest.mark.asyncio
    async def test_returns_zeros_when_supabase_is_none(self, helper_without_client):
        """supabase が None の場合はゼロ値を返す"""
        stats = await helper_without_client.get_memory_stats()

        assert stats["active_turns"] == 0
        assert stats["oldest_turn"] is None
        assert stats["newest_turn"] is None
        assert stats["dominant_emotion"] is None
        assert stats["time_span"] == 0.0

    @pytest.mark.asyncio
    async def test_filters_by_session_id_when_provided(self, helper_with_client):
        """session_id 指定時はフィルタリングする"""
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {"value": {"timestamp": 1000, "emotion": "happy", "sessionId": "s1"}},
                    {"value": {"timestamp": 3000, "emotion": "sad", "sessionId": "s1"}},
                ]
            )
        )
        client.table.return_value = chain

        stats = await helper.get_memory_stats(session_id="s1")

        assert stats["active_turns"] == 2
        assert stats["oldest_turn"] == 1000
        assert stats["newest_turn"] == 3000
        assert stats["time_span"] == (3000 - 1000) / (1000 * 60)
        chain.filter.assert_called_once_with("value->>sessionId", "eq", "s1")

    @pytest.mark.asyncio
    async def test_returns_zeros_when_no_data(self, helper_with_client):
        """データがない場合はゼロ値を返す"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = chain

        stats = await helper.get_memory_stats()

        assert stats["active_turns"] == 0
        assert stats["oldest_turn"] is None
        assert stats["newest_turn"] is None
        assert stats["dominant_emotion"] is None
        assert stats["time_span"] == 0.0

    @pytest.mark.asyncio
    async def test_returns_zeros_when_session_filter_matches_nothing(self, helper_with_client):
        """session_id フィルタで該当なしの場合はゼロ値を返す"""
        helper, client = helper_with_client
        chain = _build_chain_mock(Mock(data=[]))
        client.table.return_value = chain

        stats = await helper.get_memory_stats(session_id="nonexistent")

        assert stats["active_turns"] == 0
        chain.filter.assert_called_once_with("value->>sessionId", "eq", "nonexistent")

    @pytest.mark.asyncio
    async def test_handles_messages_without_timestamp(self, helper_with_client):
        """timestamp がないメッセージも処理される"""
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {"value": {"emotion": "happy", "sessionId": "s1"}},
                    {"value": {"timestamp": None, "emotion": "neutral", "sessionId": "s1"}},
                ]
            )
        )
        client.table.return_value = chain

        stats = await helper.get_memory_stats()

        assert stats["active_turns"] == 2
        assert stats["oldest_turn"] is None
        assert stats["newest_turn"] is None
        assert stats["time_span"] == 0.0

    @pytest.mark.asyncio
    async def test_handles_messages_without_emotion(self, helper_with_client):
        """emotion がないメッセージも処理される"""
        helper, client = helper_with_client
        chain = _build_chain_mock(
            Mock(
                data=[
                    {"value": {"timestamp": 1000, "sessionId": "s1"}},
                    {"value": {"timestamp": 2000, "emotion": None, "sessionId": "s1"}},
                ]
            )
        )
        client.table.return_value = chain

        stats = await helper.get_memory_stats()

        assert stats["active_turns"] == 2
        assert stats["dominant_emotion"] is None

    @pytest.mark.asyncio
    async def test_returns_zeros_on_exception(self, helper_with_client):
        """例外発生時はゼロ値を返す"""
        helper, client = helper_with_client
        client.table.side_effect = Exception("Query failed")

        stats = await helper.get_memory_stats()

        assert stats["active_turns"] == 0
        assert stats["oldest_turn"] is None


# =============================================================================
# get_context テスト
# =============================================================================


class TestGetContext:
    """get_context メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_orchestrates_all_parts(self):
        """_get_recent_messages, _rank_messages, get_previous_request_type, RAG を統合する"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

        mock_messages = [
            {
                "role": "user",
                "content": "営業時間は？",
                "metadata": {"timestamp": 1000},
            }
        ]
        ranked_messages = [
            {
                "role": "user",
                "content": "営業時間は？",
                "metadata": {"timestamp": 1000},
                "_rank_score": 0.8,
            }
        ]

        with (
            patch.object(
                helper, "_get_recent_messages", new_callable=AsyncMock, return_value=mock_messages
            ),
            patch.object(helper, "_rank_messages", return_value=ranked_messages),
            patch.object(
                helper,
                "get_previous_request_type",
                new_callable=AsyncMock,
                return_value="hours",
            ),
            patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_class,
        ):
            mock_rag = AsyncMock()
            mock_rag.search = AsyncMock(
                return_value={
                    "success": True,
                    "data": {
                        "results": [
                            {"content": "9:00-22:00", "entity": "engineer-cafe"},
                        ]
                    },
                }
            )
            mock_rag_class.return_value = mock_rag

            result = await helper.get_context("営業時間は？", "sess-1", {"language": "ja"})

        assert "recent_messages" in result
        assert "knowledge_results" in result
        assert "context_string" in result
        assert "inherited_request_type" in result
        assert result["inherited_request_type"] == "hours"
        assert len(result["recent_messages"]) == 1
        assert len(result["knowledge_results"]) == 1
        assert result["knowledge_results"][0]["content"] == "9:00-22:00"

    @pytest.mark.asyncio
    async def test_skips_rag_when_knowledge_base_disabled(self):
        """include_knowledge_base=False の場合は RAG 検索をスキップする"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

        with (
            patch.object(helper, "_get_recent_messages", new_callable=AsyncMock, return_value=[]),
            patch.object(
                helper,
                "get_previous_request_type",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_class,
        ):
            result = await helper.get_context("test", "sess-1", {"include_knowledge_base": False})

            mock_rag_class.assert_not_called()
            assert result["knowledge_results"] == []

    @pytest.mark.asyncio
    async def test_get_context_emits_recent_messages_probe_when_stm_writes_disabled(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "",
                "SUPABASE_KEY": "",
                "ENABLE_AGENT_MEMORY_STM_WRITES": "false",
                "ENVIRONMENT": "development",
            },
        ):
            helper = SimplifiedMemoryHelper()
            with (
                patch("backend.observability.structured_logger.log_memory_event") as mock_log,
                patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_class,
            ):
                result = await helper.get_context(
                    "営業時間は？",
                    "sess-1",
                    {"include_knowledge_base": False},
                )

            mock_rag_class.assert_not_called()
            assert result["recent_messages"] == []
            payloads = [call.kwargs for call in mock_log.call_args_list]
            probe = next(
                payload
                for payload in payloads
                if payload["event"] == "memory_loader_get_recent_messages"
            )
            compatibility_probe = next(
                payload
                for payload in payloads
                if payload["event"] == "memory_loader_get_recent_messages_duration_ms"
            )
            assert probe["success"] is True
            assert probe["skipped"] is True
            assert probe["reason"] == "agent_memory_stm_writes_disabled"
            assert probe["row_count"] == 0
            assert probe["memory_loader_get_recent_messages_duration_ms"] == 0
            assert compatibility_probe["reason"] == "agent_memory_stm_writes_disabled"

    @pytest.mark.asyncio
    async def test_handles_rag_failure_gracefully(self):
        """RAG 検索失敗時も正常に返る"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

        with (
            patch.object(helper, "_get_recent_messages", new_callable=AsyncMock, return_value=[]),
            patch.object(
                helper,
                "get_previous_request_type",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_class,
        ):
            mock_rag = AsyncMock()
            mock_rag.search = AsyncMock(side_effect=Exception("RAG error"))
            mock_rag_class.return_value = mock_rag

            result = await helper.get_context("test", "sess-1")

            assert result["knowledge_results"] == []
            assert "context_string" in result

    @pytest.mark.asyncio
    async def test_skips_inherit_context_when_disabled(self):
        """inherit_context=False の場合は get_previous_request_type を呼ばない"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

        with (
            patch.object(helper, "_get_recent_messages", new_callable=AsyncMock, return_value=[]),
            patch.object(
                helper,
                "get_previous_request_type",
                new_callable=AsyncMock,
                return_value="hours",
            ) as mock_get_prev,
        ):
            result = await helper.get_context(
                "test",
                "sess-1",
                {"inherit_context": False, "include_knowledge_base": False},
            )

            mock_get_prev.assert_not_called()
            assert result["inherited_request_type"] is None

    @pytest.mark.asyncio
    async def test_current_query_intent_overrides_stale_inherited_request_type(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

        with (
            patch.object(helper, "_get_recent_messages", new_callable=AsyncMock, return_value=[]),
            patch.object(
                helper,
                "get_previous_request_type",
                new_callable=AsyncMock,
                return_value="basement",
            ),
        ):
            result = await helper.get_context(
                "明日のイベントは？",
                "sess-1",
                {"include_knowledge_base": False, "inherit_context": True},
            )

        assert result["inherited_request_type"] == "event"
        assert result["query_intent_override"] is True

    @pytest.mark.asyncio
    async def test_default_options(self):
        """options が None の場合はデフォルト値が使用される"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

        with (
            patch.object(helper, "_get_recent_messages", new_callable=AsyncMock, return_value=[]),
            patch.object(
                helper,
                "get_previous_request_type",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("backend.tools.enhanced_rag.EnhancedRAGSearch") as mock_rag_class,
        ):
            mock_rag = AsyncMock()
            mock_rag.search = AsyncMock(return_value={"success": False, "data": {"results": []}})
            mock_rag_class.return_value = mock_rag

            result = await helper.get_context("test", "sess-1", None)

            # デフォルトで include_knowledge_base=True, inherit_context=True
            assert "context_string" in result

    @pytest.mark.asyncio
    async def test_does_not_rank_empty_messages(self):
        """メッセージが空の場合 _rank_messages を呼ばない"""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
            helper = SimplifiedMemoryHelper()

        with (
            patch.object(helper, "_get_recent_messages", new_callable=AsyncMock, return_value=[]),
            patch.object(helper, "_rank_messages") as mock_rank,
            patch.object(
                helper,
                "get_previous_request_type",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await helper.get_context("test", "sess-1", {"include_knowledge_base": False})

            mock_rank.assert_not_called()
