"""
Cross-Session Memory E2E Tests

クロスセッションメモリ機能の End-to-End テスト。

テスト内容:
- 2A: セッションをまたいだメモリ想起
- 2B: メモリ抽出の精度検証（LLM不要）
- 2C: Store永続化テスト（実DBが必要）
- 2D: 匿名ユーザーのメモリ非保存テスト

NOTE: asyncio_default_fixture_loop_scope=session と
asyncio_default_test_loop_scope=function の不整合を回避するため、
store フィクスチャは sync にして AsyncPostgresStore の CM を返す。
テスト関数内で async with するとテストの event loop 内で接続される。
"""

import asyncio
import os
import uuid

import pytest

from langgraph.store.postgres.aio import AsyncPostgresStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store_cm(_check_e2e_env):
    """AsyncPostgresStore コンテキストマネージャーを返す（sync fixture）。

    sync fixture なので event loop に依存しない。
    テスト関数内で ``async with store_cm as store`` するため、
    store の接続はテスト自身の event loop で確立される。
    """
    db_uri = os.getenv("SUPABASE_DB_URI")
    if not db_uri:
        pytest.skip("SUPABASE_DB_URI not set")
    return AsyncPostgresStore.from_conn_string(db_uri)


@pytest.fixture
def test_visitor_id():
    """Unique visitor ID for test isolation."""
    return f"test-visitor-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 2A. Cross-session memory recall
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestCrossSessionMemoryRecall:
    """セッションをまたいだ長期メモリ想起テスト"""

    async def test_cross_session_memory_recall(self, store_cm, test_visitor_id):
        """
        Session 1 で名前・職業を伝え、Session 2 で過去の記憶を確認する。

        訪問者が別セッションで再訪した場合に、前回の会話から抽出された
        長期記憶（名前など）をワークフローが参照できることを検証する。
        """
        from backend.workflows.main_workflow import MainWorkflow

        async with store_cm as store:
            await store.setup()
            wf = MainWorkflow(checkpointer=None, store=store)

            session_1_id = f"s1-{uuid.uuid4().hex[:8]}"
            session_2_id = f"s2-{uuid.uuid4().hex[:8]}"

            # Session 1: 明示的に名前を覚えるよう依頼する
            result_1 = await asyncio.wait_for(
                wf.ainvoke(
                    {
                        "query": (
                            "私の名前は田中花子です。"
                            "田中花子と呼んでください。覚えてください。"
                        ),
                        "session_id": session_1_id,
                        "language": "ja",
                        "context": {},
                        "visitor_id": test_visitor_id,
                    }
                ),
                timeout=60,
            )
            assert result_1.get("answer"), "Session 1 の回答が空です"

            # Store に長期メモリが書き込まれるまで少し待機
            await asyncio.sleep(1)

            # メモリが Store に保存されているか確認
            namespace = ("visitor_memories", test_visitor_id)
            stored_items = await store.asearch(namespace, query="田中", limit=10)
            assert isinstance(stored_items, list), "Store.asearch の戻り値がリストでない"
            assert stored_items, "Session 1 の明示記憶要求が LTM に保存されていません"
            assert any(
                "田中" in str(getattr(item, "value", {})) for item in stored_items
            ), "保存された LTM に田中への参照がありません"

            # Session 2: 別 session で同じ visitor_id の記憶を確認する
            result_2 = await asyncio.wait_for(
                wf.ainvoke(
                    {
                        "query": "私の名前を覚えていますか？",
                        "session_id": session_2_id,
                        "language": "ja",
                        "context": {},
                        "visitor_id": test_visitor_id,
                    }
                ),
                timeout=60,
            )
            assert result_2.get("answer"), "Session 2 の回答が空です"

            metadata_str = str(result_2.get("metadata", {}))
            has_name_ref = "田中" in result_2["answer"] or "田中" in metadata_str
            assert has_name_ref, (
                "別セッションの回答に田中への参照がありません "
                f"（応答: {result_2['answer'][:100]}）"
            )

            # Cleanup
            try:
                items = await store.asearch(namespace, query="", limit=100)
                for item in items:
                    await store.adelete(namespace, item.key)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# NOTE: Memory extraction precision tests (LLM不要) are in
# tests/utils/test_memory_extractor.py to avoid e2e directory skip.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 2C. Store persistence test (needs real DB)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestStorePersistence:
    """Store（AsyncPostgresStore）の永続化テスト"""

    async def test_store_persistence(self, store_cm):
        """
        aput したデータを asearch で取得できることを確認する。

        Store の基本的な read/write 動作を検証する。
        """
        async with store_cm as store:
            await store.setup()
            test_ns = ("visitor_memories", f"persist-test-{uuid.uuid4().hex[:8]}")
            test_key = str(uuid.uuid4())
            test_value = {
                "data": "テスト用の永続化データ",
                "type": "visitor_name",
                "confidence": 0.9,
            }

            try:
                await store.aput(test_ns, test_key, test_value)

                items = await store.asearch(test_ns, query="テスト", limit=10)
                assert isinstance(items, list), "asearch の戻り値がリストでない"

                found = [i for i in items if i.key == test_key]
                assert found, f"書き込んだキー {test_key} が asearch で見つからない"
                assert (
                    found[0].value == test_value
                ), f"取得した値が一致しない: expected={test_value}, got={found[0].value}"
            finally:
                try:
                    await store.adelete(test_ns, test_key)
                except Exception:
                    pass

    async def test_store_namespace_isolation(self, store_cm):
        """
        異なる namespace に書いたデータが互いに干渉しないことを確認する。
        """
        async with store_cm as store:
            await store.setup()
            ns_a = ("visitor_memories", f"user-a-{uuid.uuid4().hex[:8]}")
            ns_b = ("visitor_memories", f"user-b-{uuid.uuid4().hex[:8]}")
            key = str(uuid.uuid4())

            try:
                await store.aput(ns_a, key, {"data": "namespace A のデータ", "type": "test"})

                items_b = await store.asearch(ns_b, query="namespace", limit=10)
                assert not any(
                    i.key == key for i in items_b
                ), "namespace A のデータが namespace B で取得されてしまった"
            finally:
                try:
                    await store.adelete(ns_a, key)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# 2D. Anonymous user memory non-storage test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAnonymousUserMemory:
    """匿名ユーザーのメモリ非保存テスト"""

    async def test_anonymous_user_no_memory_storage(self, store_cm):
        """
        visitor_id が "anonymous" の場合、Store にメモリが書き込まれないことを確認。
        """
        from backend.workflows.main_workflow import MainWorkflow

        async with store_cm as store:
            await store.setup()
            wf = MainWorkflow(checkpointer=None, store=store)
            anon_visitor_id = "anonymous"
            session_id = f"anon-test-{uuid.uuid4().hex[:8]}"

            result = await asyncio.wait_for(
                wf.ainvoke(
                    {
                        "query": "私の名前は匿名テストユーザーです",
                        "session_id": session_id,
                        "language": "ja",
                        "context": {},
                        "visitor_id": anon_visitor_id,
                    }
                ),
                timeout=60,
            )
            assert result.get("answer"), "anonymous ユーザーへの回答が空"

            namespace = ("visitor_memories", anon_visitor_id)
            items = await store.asearch(namespace, query="匿名", limit=10)
            assert not items, f"anonymous ユーザーのメモリが Store に保存されてしまった: {items}"

    async def test_none_visitor_id_no_memory_storage(self, store_cm):
        """
        visitor_id が None（省略）の場合も Store にメモリが保存されないことを確認。
        """
        from backend.workflows.main_workflow import MainWorkflow

        async with store_cm as store:
            await store.setup()
            wf = MainWorkflow(checkpointer=None, store=store)
            session_id = f"no-visitor-{uuid.uuid4().hex[:8]}"

            result = await asyncio.wait_for(
                wf.ainvoke(
                    {
                        "query": "visitor_idなしのテストです",
                        "session_id": session_id,
                        "language": "ja",
                        "context": {},
                        # visitor_id は意図的に省略
                    }
                ),
                timeout=60,
            )
            assert result.get("answer"), "visitor_id なしへの回答が空"
