"""
SessionTaskManager ユニットテスト

Issue #127: 音声割り込みバックエンド処理

テスト対象:
  - SessionTaskInfo データクラス
  - SessionTaskManager シングルトン
  - タスク登録・キャンセル・自動クリーンアップ
"""

import asyncio
import pytest
from io import BytesIO

from backend.utils.session_task_manager import (
    SessionTaskInfo,
    SessionTaskManager,
    get_session_task_manager,
)


@pytest.fixture
async def manager():
    """SessionTaskManager フィクスチャ"""
    mgr = SessionTaskManager()
    # Singleton を初期化
    mgr._sessions.clear()
    mgr._initialized = True

    yield mgr


@pytest.mark.asyncio
class TestSessionTaskInfo:
    """SessionTaskInfo テスト"""

    async def test_creation(self):
        """SessionTaskInfo の生成"""
        info = SessionTaskInfo(session_id="test-001")
        assert info.session_id == "test-001"
        assert info.llm_task is None
        assert info.tts_task is None
        assert info.tts_buffer is None
        assert info.is_active() is False

    async def test_update_activity(self):
        """activity 時刻更新"""
        info = SessionTaskInfo(session_id="test-001")
        old_time = info.last_activity
        await asyncio.sleep(0.01)  # 時刻差を作る
        info.update_activity()
        assert info.last_activity > old_time

    async def test_is_active_with_no_tasks(self):
        """is_active (no tasks)"""
        info = SessionTaskInfo(session_id="test-001")
        assert info.is_active() is False

    async def test_is_active_with_running_task(self):
        """is_active (running task)"""

        async def dummy_coro():
            await asyncio.sleep(1)

        info = SessionTaskInfo(session_id="test-001")
        task = asyncio.create_task(dummy_coro())
        info.llm_task = task

        assert info.is_active() is True

        # クリーンアップ
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_is_active_with_completed_task(self):
        """is_active (completed task)"""

        async def dummy_coro():
            return "done"

        info = SessionTaskInfo(session_id="test-001")
        task = asyncio.create_task(dummy_coro())
        await task
        info.llm_task = task

        assert info.is_active() is False


@pytest.mark.asyncio
class TestSessionTaskManager:
    """SessionTaskManager テスト"""

    async def test_singleton_pattern(self):
        """Singleton パターン動作"""
        mgr1 = SessionTaskManager()
        mgr2 = SessionTaskManager()
        assert mgr1 is mgr2

    async def test_register_session(self, manager):
        """セッション登録"""
        info = await manager.register_session("session-123")
        assert info.session_id == "session-123"
        assert await manager.get_session("session-123") is not None

    async def test_register_session_twice(self, manager):
        """セッション重複登録"""
        info1 = await manager.register_session("session-123")
        info2 = await manager.register_session("session-123")
        # 同じ SessionTaskInfo が返される
        assert info1 is info2

    async def test_get_nonexistent_session(self, manager):
        """存在しないセッション取得"""
        info = await manager.get_session("nonexistent")
        assert info is None

    async def test_set_llm_task(self, manager):
        """LLMタスク登録"""
        await manager.register_session("session-123")

        async def dummy_llm():
            await asyncio.sleep(1)

        task = asyncio.create_task(dummy_llm())
        result = await manager.set_llm_task("session-123", task)

        assert result is True
        info = await manager.get_session("session-123")
        assert info.llm_task is task

        # クリーンアップ
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_set_llm_task_nonexistent_session(self, manager):
        """存在しないセッションへのLLMタスク登録"""

        async def dummy_llm():
            await asyncio.sleep(1)

        task = asyncio.create_task(dummy_llm())
        result = await manager.set_llm_task("nonexistent", task)

        assert result is False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_set_tts_task(self, manager):
        """TTSタスク登録"""
        await manager.register_session("session-123")

        async def dummy_tts():
            await asyncio.sleep(1)

        task = asyncio.create_task(dummy_tts())
        result = await manager.set_tts_task("session-123", task)

        assert result is True
        info = await manager.get_session("session-123")
        assert info.tts_task is task

        # クリーンアップ
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_set_tts_buffer(self, manager):
        """TTSバッファ登録"""
        await manager.register_session("session-123")

        buffer = BytesIO(b"fake_audio_data")
        result = await manager.set_tts_buffer("session-123", buffer)

        assert result is True
        retrieved_buffer = await manager.get_tts_buffer("session-123")
        assert retrieved_buffer is buffer

    async def test_get_tts_buffer_nonexistent(self, manager):
        """存在しないセッションのバッファ取得"""
        buffer = await manager.get_tts_buffer("nonexistent")
        assert buffer is None

    async def test_cancel_llm_task(self, manager):
        """LLMタスクキャンセル"""
        await manager.register_session("session-123")

        async def dummy_llm():
            await asyncio.sleep(10)

        task = asyncio.create_task(dummy_llm())
        await manager.set_llm_task("session-123", task)

        result = await manager.cancel_llm_task("session-123")

        assert result is True
        await asyncio.sleep(0.01)  # 時間をプロセッサに譲る
        assert task.cancelled()

    async def test_cancel_llm_task_nonexistent_session(self, manager):
        """存在しないセッションのLLMタスクキャンセル"""
        result = await manager.cancel_llm_task("nonexistent")
        assert result is False

    async def test_cancel_llm_task_no_task(self, manager):
        """タスクが未登録のセッションでキャンセル"""
        await manager.register_session("session-123")
        result = await manager.cancel_llm_task("session-123")
        assert result is False

    async def test_cancel_llm_task_already_done(self, manager):
        """既に完了したタスクをキャンセル"""
        await manager.register_session("session-123")

        async def dummy_llm():
            return "done"

        task = asyncio.create_task(dummy_llm())
        await task  # 完了待機

        await manager.set_llm_task("session-123", task)
        result = await manager.cancel_llm_task("session-123")

        assert result is False

    async def test_cancel_tts_task(self, manager):
        """TTSタスクキャンセル"""
        await manager.register_session("session-123")

        async def dummy_tts():
            await asyncio.sleep(10)

        task = asyncio.create_task(dummy_tts())
        await manager.set_tts_task("session-123", task)

        result = await manager.cancel_tts_task("session-123")

        assert result is True
        await asyncio.sleep(0.01)  # 時間をプロセッサに譲る
        assert task.cancelled()

    async def test_clear_tts_buffer(self, manager):
        """TTSバッファクリア"""
        await manager.register_session("session-123")

        buffer = BytesIO(b"fake_audio_data")
        await manager.set_tts_buffer("session-123", buffer)

        result = await manager.clear_tts_buffer("session-123")
        assert result is True

        retrieved_buffer = await manager.get_tts_buffer("session-123")
        assert retrieved_buffer is None

    async def test_cancel_all_tasks(self, manager):
        """全タスクキャンセル"""
        await manager.register_session("session-123")

        async def dummy_coro():
            await asyncio.sleep(10)

        llm_task = asyncio.create_task(dummy_coro())
        tts_task = asyncio.create_task(dummy_coro())
        buffer = BytesIO(b"fake_audio")

        await manager.set_llm_task("session-123", llm_task)
        await manager.set_tts_task("session-123", tts_task)
        await manager.set_tts_buffer("session-123", buffer)

        result = await manager.cancel_all_tasks("session-123")

        assert result is True
        await asyncio.sleep(0.01)  # 時間をプロセッサに譲る
        assert llm_task.cancelled()
        assert tts_task.cancelled()
        assert await manager.get_tts_buffer("session-123") is None

    async def test_cleanup_session(self, manager):
        """セッション削除"""
        await manager.register_session("session-123")

        result = await manager.cleanup_session("session-123")
        assert result is True

        info = await manager.get_session("session-123")
        assert info is None

    async def test_cleanup_session_with_running_tasks(self, manager):
        """実行中タスク付きセッション削除"""
        await manager.register_session("session-123")

        async def dummy_coro():
            await asyncio.sleep(10)

        llm_task = asyncio.create_task(dummy_coro())
        tts_task = asyncio.create_task(dummy_coro())

        await manager.set_llm_task("session-123", llm_task)
        await manager.set_tts_task("session-123", tts_task)

        result = await manager.cleanup_session("session-123")

        assert result is True
        await asyncio.sleep(0.01)  # 時間をプロセッサに譲る
        assert llm_task.cancelled()
        assert tts_task.cancelled()

    async def test_cleanup_nonexistent_session(self, manager):
        """存在しないセッション削除"""
        result = await manager.cleanup_session("nonexistent")
        assert result is False

    async def test_get_active_sessions(self, manager):
        """進行中セッション一覧"""
        await manager.register_session("session-1")
        await manager.register_session("session-2")

        async def dummy_coro():
            await asyncio.sleep(10)

        # session-1 をアクティブに
        task1 = asyncio.create_task(dummy_coro())
        await manager.set_llm_task("session-1", task1)

        active = await manager.get_active_sessions()
        assert len(active) == 1
        assert "session-1" in active

        # クリーンアップ
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass

    async def test_get_session_count(self, manager):
        """セッション数"""
        await manager.register_session("session-1")
        await manager.register_session("session-2")
        await manager.register_session("session-3")

        count = await manager.get_session_count()
        assert count == 3

    async def test_get_session_task_manager_singleton(self):
        """グローバル関数 get_session_task_manager"""
        mgr1 = get_session_task_manager()
        mgr2 = get_session_task_manager()
        assert mgr1 is mgr2
        assert isinstance(mgr1, SessionTaskManager)


@pytest.mark.asyncio
class TestSessionTaskManagerThreadSafety:
    """SessionTaskManager スレッド安全性テスト"""

    async def test_concurrent_register_sessions(self, manager):
        """並行セッション登録"""
        tasks = [manager.register_session(f"session-{i}") for i in range(100)]
        results = await asyncio.gather(*tasks)

        count = await manager.get_session_count()
        assert count == 100
        assert all(r.session_id in [f"session-{i}" for i in range(100)] for r in results)

    async def test_concurrent_cancel_tasks(self, manager):
        """並行タスクキャンセル"""
        # セッション準備
        sessions = []
        tasks_list = []

        for i in range(10):
            await manager.register_session(f"session-{i}")

            async def dummy_coro():
                await asyncio.sleep(10)

            task = asyncio.create_task(dummy_coro())
            await manager.set_llm_task(f"session-{i}", task)
            sessions.append(f"session-{i}")
            tasks_list.append(task)

        # 並行キャンセル
        cancel_tasks = [manager.cancel_llm_task(sid) for sid in sessions]
        results = await asyncio.gather(*cancel_tasks)

        assert all(results)
        await asyncio.sleep(0.01)  # 時間をプロセッサに譲る
        assert all(t.cancelled() for t in tasks_list)
