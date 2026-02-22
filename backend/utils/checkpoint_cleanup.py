"""
チェックポイント/セッションクリーンアップユーティリティ

TTLベースの古いチェックポイント削除とセッションメッセージ数制限。
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_TTL_HOURS = 24
DEFAULT_MAX_MESSAGES_PER_SESSION = 50
CLEANUP_INTERVAL_SECONDS = 3600  # 1時間ごとにクリーンアップ


class CheckpointCleanup:
    """TTLベースのチェックポイントクリーンアップ"""

    def __init__(
        self,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        max_messages: int = DEFAULT_MAX_MESSAGES_PER_SESSION,
    ):
        """
        Args:
            ttl_hours: チェックポイントのTTL（時間）
            max_messages: セッションあたりの最大メッセージ数
        """
        self.ttl_hours = ttl_hours
        self.max_messages = max_messages
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def cleanup_old_checkpoints(self, checkpointer) -> int:
        """TTLを超えた古いチェックポイントを削除

        Args:
            checkpointer: LangGraphチェックポインターインスタンス

        Returns:
            削除されたチェックポイント数
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)
        cutoff_ts = cutoff.isoformat()
        deleted_count = 0

        try:
            if hasattr(checkpointer, "conn"):
                async with checkpointer.conn.cursor() as cur:
                    # LangGraph stores timestamps in metadata JSONB
                    await cur.execute(
                        """
                        DELETE FROM checkpoints
                        WHERE metadata->>'source' = 'loop'
                          AND metadata->>'step' IS NOT NULL
                          AND checkpoint_id < %s
                        """,
                        (cutoff_ts,),
                    )
                    deleted_count = cur.rowcount
                    await checkpointer.conn.commit()

            logger.info(
                "Cleaned up %d checkpoints older than %d hours",
                deleted_count,
                self.ttl_hours,
            )
        except Exception as e:
            logger.warning("Checkpoint cleanup failed: %s", e)

        return deleted_count

    async def trim_session_messages(
        self,
        checkpointer,
        session_id: str,
    ) -> int:
        """セッションのチェックポイント数を制限（古いものから削除）

        Args:
            checkpointer: チェックポインターインスタンス
            session_id: セッションID

        Returns:
            削除されたチェックポイント数
        """
        deleted_count = 0

        try:
            if hasattr(checkpointer, "conn"):
                async with checkpointer.conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT COUNT(*) FROM checkpoints
                        WHERE thread_id = %s
                        """,
                        (session_id,),
                    )
                    row = await cur.fetchone()
                    count = row[0] if row else 0

                    if count > self.max_messages:
                        excess = count - self.max_messages
                        await cur.execute(
                            """
                            DELETE FROM checkpoints
                            WHERE (thread_id, checkpoint_ns, checkpoint_id) IN (
                                SELECT thread_id, checkpoint_ns, checkpoint_id
                                FROM checkpoints
                                WHERE thread_id = %s
                                ORDER BY checkpoint_id ASC
                                LIMIT %s
                            )
                            """,
                            (session_id, excess),
                        )
                        deleted_count = cur.rowcount
                        await checkpointer.conn.commit()

            if deleted_count > 0:
                logger.info(
                    "Trimmed %d old checkpoints from session %s",
                    deleted_count,
                    session_id,
                )
        except Exception as e:
            logger.warning("Session trim failed for %s: %s", session_id, e)

        return deleted_count

    async def _periodic_cleanup_loop(self, checkpointer):
        """定期クリーンアップループ"""
        await asyncio.sleep(60)  # Initial delay to let DB stabilize
        while self._running:
            try:
                await self.cleanup_old_checkpoints(checkpointer)
            except Exception as e:
                logger.error("Periodic cleanup error: %s", e)

            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

    def start_periodic_cleanup(self, checkpointer) -> None:
        """定期クリーンアップを開始"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._periodic_cleanup_loop(checkpointer))
        logger.info(
            "Periodic checkpoint cleanup started (TTL: %dh, interval: %ds)",
            self.ttl_hours,
            CLEANUP_INTERVAL_SECONDS,
        )

    async def stop(self) -> None:
        """定期クリーンアップを停止"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Periodic checkpoint cleanup stopped")
