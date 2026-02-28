"""
Supabase DB結合テスト - SimplifiedMemoryHelper

ローカルSupabase（agent_memoryテーブル）に対する実際のCRUD操作を検証。
テストデータは各テスト終了時にクリーンアップされる。

実行要件:
  - supabase start でローカルSupabaseが起動していること
  - .env.local に SUPABASE_URL, SUPABASE_KEY が設定されていること

実行方法:
  cd backend
  export $(grep -v '^#' .env.local | xargs)
  python -m pytest tests/integration/test_supabase_memory_integration.py -v
"""

import os
import uuid
import pytest
import asyncio

# ローカルSupabase接続チェック
_supabase_url = os.getenv("SUPABASE_URL", "")
_is_local_supabase = any(marker in _supabase_url for marker in ["localhost", "127.0.0.1", "kong"])
_supabase_available = bool(
    os.getenv("SUPABASE_URL")
    and os.getenv("SUPABASE_KEY")
    and os.getenv("SUPABASE_KEY") != "test-key"
    and _is_local_supabase
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _supabase_available,
        reason=(
            "SUPABASE_URL/SUPABASE_KEY が未設定、test-key、"
            "またはローカルSupabase以外"
            "（localhost/127.0.0.1/kong が必要）"
        ),
    ),
]


def _ensure_active_session(helper, session_id: str) -> None:
    helper.supabase.table("conversation_sessions").upsert(
        {"id": session_id, "status": "active"},
        on_conflict="id",
    ).execute()


@pytest.fixture
def unique_session_id():
    """テストごとにユニークなセッションIDを生成"""
    return str(uuid.uuid4())


@pytest.fixture
async def memory_helper(unique_session_id):
    """
    SimplifiedMemoryHelperの実インスタンスを提供し、
    テスト後にテストデータをクリーンアップする。
    """
    # シングルトンを使わず新規インスタンスを作成
    from backend.utils.memory_helper import SimplifiedMemoryHelper

    helper = SimplifiedMemoryHelper()
    tracked_session_ids = {unique_session_id}
    original_store_message = helper.store_message

    async def _tracking_store_message(*args, **kwargs):
        session_id = kwargs.get("session_id")
        if session_id:
            tracked_session_ids.add(session_id)
            _ensure_active_session(helper, session_id)
        return await original_store_message(*args, **kwargs)

    helper.store_message = _tracking_store_message  # type: ignore[method-assign]

    # Supabase接続確認
    assert helper.supabase is not None, "Supabase client の初期化に失敗"

    yield helper

    # テスト後: このテストセッションで作成されたエントリのみを削除
    try:
        # すべてのmessage_%エントリを取得してセッションIDでフィルタ
        response = (
            helper.supabase.table("agent_memory")
            .select("id,value")
            .eq("agent_name", helper.agent_name)
            .like("key", "message_%")
            .execute()
        )

        # このテストセッションで作成されたエントリのIDを収集
        ids_to_delete = [
            row["id"]
            for row in response.data
            if row.get("value", {}).get("sessionId") in tracked_session_ids
        ]

        # 該当するIDのみ削除
        if ids_to_delete:
            helper.supabase.table("agent_memory").delete().in_("id", ids_to_delete).execute()
    except Exception:
        pass


# ==============================================================================
# 接続テスト
# ==============================================================================


class TestSupabaseConnection:
    """Supabase接続の基本テスト"""

    async def test_supabase_client_initialized(self, memory_helper):
        """Supabaseクライアントが正常に初期化されていることを確認"""
        assert memory_helper.supabase is not None

    async def test_agent_memory_table_accessible(self, memory_helper):
        """agent_memoryテーブルにアクセスできることを確認"""
        response = memory_helper.supabase.table("agent_memory").select("id").limit(1).execute()
        # エラーなくレスポンスが返ることを確認（データの有無は問わない）
        assert response is not None
        assert hasattr(response, "data")


# ==============================================================================
# メッセージ保存テスト
# ==============================================================================


class TestStoreMessage:
    """store_message のDB結合テスト"""

    async def test_store_user_message(self, memory_helper, unique_session_id):
        """ユーザーメッセージがagent_memoryに保存される"""
        await memory_helper.store_message(
            role="user",
            content="営業時間を教えてください",
            session_id=unique_session_id,
            metadata={"emotion": "neutral", "confidence": 0.9},
        )

        # DB直接確認
        response = (
            memory_helper.supabase.table("agent_memory")
            .select("*")
            .eq("agent_name", memory_helper.agent_name)
            .like("key", "message_%")
            .execute()
        )

        # セッションIDでフィルタ
        matching = [r for r in response.data if r["value"].get("sessionId") == unique_session_id]
        assert len(matching) == 1

        stored = matching[0]["value"]
        assert stored["role"] == "user"
        assert stored["content"] == "営業時間を教えてください"
        assert stored["sessionId"] == unique_session_id
        assert stored["emotion"] == "neutral"
        assert stored["confidence"] == 0.9

    async def test_store_assistant_message(self, memory_helper, unique_session_id):
        """アシスタントメッセージがagent_memoryに保存される"""
        await memory_helper.store_message(
            role="assistant",
            content="営業時間は9時から22時です。",
            session_id=unique_session_id,
            metadata={"emotion": "helpful"},
        )

        response = (
            memory_helper.supabase.table("agent_memory")
            .select("*")
            .eq("agent_name", memory_helper.agent_name)
            .like("key", "message_%")
            .execute()
        )

        matching = [r for r in response.data if r["value"].get("sessionId") == unique_session_id]
        assert len(matching) == 1
        assert matching[0]["value"]["role"] == "assistant"
        assert matching[0]["value"]["content"] == "営業時間は9時から22時です。"

    async def test_store_message_no_expires_at(self, memory_helper, unique_session_id):
        """セッションベース: メッセージにexpires_atが設定されない"""
        await memory_helper.store_message(
            role="user",
            content="テストセッション",
            session_id=unique_session_id,
        )

        response = (
            memory_helper.supabase.table("agent_memory")
            .select("*")
            .eq("agent_name", memory_helper.agent_name)
            .like("key", "message_%")
            .execute()
        )

        matching = [r for r in response.data if r["value"].get("sessionId") == unique_session_id]
        assert len(matching) == 1

        # セッションベースではexpires_atが設定されない
        expires_at = matching[0].get("expires_at")
        assert expires_at is None

    async def test_store_multiple_messages(self, memory_helper, unique_session_id):
        """複数メッセージが正しく保存される"""
        await memory_helper.store_message(
            role="user",
            content="WiFiのパスワードを教えてください",
            session_id=unique_session_id,
        )
        # タイムスタンプの衝突を避ける
        await asyncio.sleep(0.01)
        await memory_helper.store_message(
            role="assistant",
            content="WiFiのSSIDは「engnrcf-guest-5GHz」です。パスワードは受付でお渡しする名札の裏に記載しています。",
            session_id=unique_session_id,
        )
        await asyncio.sleep(0.01)
        await memory_helper.store_message(
            role="user",
            content="今週のイベントはありますか？",
            session_id=unique_session_id,
        )

        response = (
            memory_helper.supabase.table("agent_memory")
            .select("*")
            .eq("agent_name", memory_helper.agent_name)
            .like("key", "message_%")
            .execute()
        )

        matching = [r for r in response.data if r["value"].get("sessionId") == unique_session_id]
        assert len(matching) == 3

    async def test_store_message_auto_extracts_request_type(self, memory_helper, unique_session_id):
        """ユーザーメッセージでrequest_typeが自動抽出される"""
        await memory_helper.store_message(
            role="user",
            content="営業時間を教えてください",
            session_id=unique_session_id,
        )

        response = (
            memory_helper.supabase.table("agent_memory")
            .select("*")
            .eq("agent_name", memory_helper.agent_name)
            .like("key", "message_%")
            .execute()
        )

        matching = [r for r in response.data if r["value"].get("sessionId") == unique_session_id]
        assert len(matching) == 1
        # request_typeが何かしら設定されていることを確認
        # （具体的な値はextract_request_typeの実装に依存）
        assert matching[0]["value"].get("request_type") is not None


# ==============================================================================
# メッセージ取得テスト
# ==============================================================================


class TestGetRecentMessages:
    """_get_recent_messages のDB結合テスト"""

    async def test_get_messages_returns_stored_data(self, memory_helper, unique_session_id):
        """保存したメッセージが取得できる"""
        _ensure_active_session(memory_helper, unique_session_id)
        await memory_helper.store_message(
            role="user",
            content="Wi-Fiはありますか？",
            session_id=unique_session_id,
            metadata={"emotion": "neutral"},
        )

        messages = await memory_helper._get_recent_messages(unique_session_id)

        assert len(messages) >= 1
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) >= 1
        assert user_msgs[0]["content"] == "Wi-Fiはありますか？"

    async def test_get_messages_filters_by_session(self, memory_helper):
        """セッションIDでフィルタリングされる"""
        session_a = str(uuid.uuid4())
        session_b = str(uuid.uuid4())
        _ensure_active_session(memory_helper, session_a)
        _ensure_active_session(memory_helper, session_b)

        await memory_helper.store_message(
            role="user", content="セッションAの質問", session_id=session_a
        )
        await asyncio.sleep(0.01)
        await memory_helper.store_message(
            role="user", content="セッションBの質問", session_id=session_b
        )

        messages_a = await memory_helper._get_recent_messages(session_a)
        messages_b = await memory_helper._get_recent_messages(session_b)

        assert any(m["content"] == "セッションAの質問" for m in messages_a)
        assert not any(m["content"] == "セッションBの質問" for m in messages_a)

        assert any(m["content"] == "セッションBの質問" for m in messages_b)
        assert not any(m["content"] == "セッションAの質問" for m in messages_b)

    async def test_get_messages_empty_session(self, memory_helper):
        """存在しないセッションIDでは空リストが返る"""
        messages = await memory_helper._get_recent_messages("nonexistent_session_xyz")
        assert messages == []

    async def test_get_messages_ordered_chronologically(self, memory_helper, unique_session_id):
        """メッセージが時系列順で返される"""
        _ensure_active_session(memory_helper, unique_session_id)
        await memory_helper.store_message(
            role="user",
            content="初めて来ました。利用方法を教えてください",
            session_id=unique_session_id,
        )
        await asyncio.sleep(0.02)
        await memory_helper.store_message(
            role="assistant",
            content="ようこそ！1階は自由にご利用いただけます。WiFiと電源も完備しています。",
            session_id=unique_session_id,
        )
        await asyncio.sleep(0.02)
        await memory_helper.store_message(
            role="user", content="3Dプリンターも使えますか？", session_id=unique_session_id
        )

        messages = await memory_helper._get_recent_messages(unique_session_id)

        assert len(messages) == 3
        assert messages[0]["content"] == "初めて来ました。利用方法を教えてください"
        assert (
            messages[1]["content"]
            == "ようこそ！1階は自由にご利用いただけます。WiFiと電源も完備しています。"
        )
        assert messages[2]["content"] == "3Dプリンターも使えますか？"


# ==============================================================================
# コンテキスト取得テスト
# ==============================================================================


class TestGetContext:
    """get_context のDB結合テスト"""

    async def test_get_context_with_messages(self, memory_helper, unique_session_id):
        """会話コンテキストが正しく構築される"""
        _ensure_active_session(memory_helper, unique_session_id)
        await memory_helper.store_message(
            role="user",
            content="営業時間は？",
            session_id=unique_session_id,
            metadata={"request_type": "hours"},
        )
        await asyncio.sleep(0.01)
        await memory_helper.store_message(
            role="assistant",
            content="9時から22時です。",
            session_id=unique_session_id,
            metadata={"emotion": "helpful"},
        )

        context = await memory_helper.get_context(
            query="アクセス方法は？",
            session_id=unique_session_id,
        )

        assert "recent_messages" in context
        assert "context_string" in context
        assert "inherited_request_type" in context
        assert len(context["recent_messages"]) >= 2
        assert "営業時間" in context["context_string"]

    async def test_get_context_empty_session(self, memory_helper):
        """空のセッションではデフォルトコンテキストが返る"""
        context = await memory_helper.get_context(query="テスト", session_id=str(uuid.uuid4()))

        assert context["recent_messages"] == []
        assert "会話履歴がありません" in context["context_string"]

    async def test_get_context_inherits_request_type(self, memory_helper, unique_session_id):
        """前回のrequest_typeが継承される"""
        await memory_helper.store_message(
            role="user",
            content="営業時間を教えてください",
            session_id=unique_session_id,
            metadata={"request_type": "hours"},
        )

        context = await memory_helper.get_context(
            query="続きを教えて",
            session_id=unique_session_id,
        )

        assert context["inherited_request_type"] == "hours"


# ==============================================================================
# request_type取得テスト
# ==============================================================================


class TestGetPreviousRequestType:
    """get_previous_request_type のDB結合テスト"""

    async def test_returns_latest_request_type(self, memory_helper, unique_session_id):
        """最新のrequest_typeが返される"""
        await memory_helper.store_message(
            role="user",
            content="営業時間は？",
            session_id=unique_session_id,
            metadata={"request_type": "hours"},
        )
        await asyncio.sleep(0.01)
        await memory_helper.store_message(
            role="user",
            content="場所はどこ？",
            session_id=unique_session_id,
            metadata={"request_type": "location"},
        )

        result = await memory_helper.get_previous_request_type(unique_session_id)
        # 最新のメッセージ（desc=True）のrequest_typeが返される
        assert result == "location"

    async def test_returns_none_for_empty_session(self, memory_helper):
        """メッセージがない場合はNoneが返る"""
        result = await memory_helper.get_previous_request_type("no_such_session")
        assert result is None


# ==============================================================================
# メモリ統計テスト
# ==============================================================================


class TestGetMemoryStats:
    """get_memory_stats のDB結合テスト"""

    async def test_stats_with_messages(self, memory_helper, unique_session_id):
        """メッセージがある場合の統計情報"""
        await memory_helper.store_message(
            role="user",
            content="テスト1",
            session_id=unique_session_id,
            metadata={"emotion": "neutral"},
        )
        await asyncio.sleep(0.01)
        await memory_helper.store_message(
            role="assistant",
            content="回答1",
            session_id=unique_session_id,
            metadata={"emotion": "helpful"},
        )

        stats = await memory_helper.get_memory_stats()

        assert stats["active_turns"] >= 2
        assert stats["oldest_turn"] is not None
        assert stats["newest_turn"] is not None
        assert stats["oldest_turn"] <= stats["newest_turn"]

    async def test_stats_empty(self, memory_helper):
        """メッセージがない場合の統計情報"""
        # cleanup()は期限切れのみ削除するため、テスト用に全エントリを強制削除
        memory_helper.supabase.table("agent_memory").delete().eq(
            "agent_name", memory_helper.agent_name
        ).like("key", "message_%").execute()

        stats = await memory_helper.get_memory_stats()

        assert stats["active_turns"] == 0
        assert stats["oldest_turn"] is None
        assert stats["newest_turn"] is None


# ==============================================================================
# クリーンアップテスト
# ==============================================================================


class TestCleanup:
    """cleanup のDB結合テスト"""

    async def test_cleanup_session_removes_messages(self, memory_helper):
        """セッション単位のクリーンアップでメッセージが削除される"""
        session = f"cleanup_test_{uuid.uuid4().hex[:8]}"

        # テストメッセージを挿入
        memory_helper.supabase.table("agent_memory").insert(
            {
                "agent_name": memory_helper.agent_name,
                "key": f"message_cleanup_{uuid.uuid4().hex[:8]}",
                "value": {
                    "role": "user",
                    "content": "cleanup target message",
                    "sessionId": session,
                    "timestamp": 1000000,
                },
            }
        ).execute()

        # セッション単位のクリーンアップ実行
        await memory_helper.cleanup_session(session)

        # メッセージが削除されたことを確認
        response = (
            memory_helper.supabase.table("agent_memory")
            .select("*")
            .eq("agent_name", memory_helper.agent_name)
            .like("key", "message_%")
            .execute()
        )
        remaining = [r for r in response.data if r["value"].get("sessionId") == session]
        assert len(remaining) == 0


# ==============================================================================
# DBテーブル存在確認テスト
# ==============================================================================


class TestDatabaseSchema:
    """DBスキーマの結合テスト"""

    async def test_agent_memory_table_exists(self, memory_helper):
        """agent_memoryテーブルが存在する"""
        response = memory_helper.supabase.table("agent_memory").select("id").limit(0).execute()
        assert response is not None

    async def test_conversation_sessions_table_exists(self, memory_helper):
        """conversation_sessionsテーブルが存在する"""
        response = (
            memory_helper.supabase.table("conversation_sessions").select("id").limit(0).execute()
        )
        assert response is not None

    async def test_knowledge_base_table_exists(self, memory_helper):
        """knowledge_baseテーブルが存在する"""
        response = memory_helper.supabase.table("knowledge_base").select("id").limit(0).execute()
        assert response is not None

    async def test_conversation_history_table_exists(self, memory_helper):
        """conversation_historyテーブルが存在する"""
        response = (
            memory_helper.supabase.table("conversation_history").select("id").limit(0).execute()
        )
        assert response is not None
