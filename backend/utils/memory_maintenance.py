"""Cleanup and statistics mixin for SimplifiedMemoryHelper."""

import logging
import time
from typing import Any, Dict, Optional

from backend.utils.memory_observability import (
    _AGENT_MEMORY_SESSION_COLUMN,
    _duration_ms,
    _log_memory_event_safely,
)
from backend.utils.postgres_sanitizer import sanitize_for_postgres

logger = logging.getLogger(__name__)


class MemoryMaintenanceMixin:
    async def cleanup_session(self, session_id: str) -> None:
        """
        セッション終了時のメッセージアーカイブ

        セッションに紐づくメッセージを削除（またはアーカイブ）する。
        conversation_sessionsのstatus更新と連動して呼ぶことを想定。

        Args:
            session_id: セッションID
        """
        logger.info("Cleaning up messages for session: %s", session_id)
        started_at = time.perf_counter()

        if not self.supabase:
            _log_memory_event_safely(
                "memory_cleanup_session_duration_ms",
                session_id=session_id,
                success=True,
                skipped=True,
                reason="supabase_unavailable",
                duration_ms=_duration_ms(started_at),
                deleted_count=0,
            )
            return

        try:
            response = (
                self.supabase.table("agent_memory")
                .delete()
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
                .filter(_AGENT_MEMORY_SESSION_COLUMN, "eq", sanitize_for_postgres(session_id))
                .execute()
            )

            deleted_count = len(response.data or [])
            logger.info("Cleaned up %d messages for session: %s", deleted_count, session_id)
            duration_ms = _duration_ms(started_at)
            _log_memory_event_safely(
                "memory_cleanup_session_duration_ms",
                session_id=session_id,
                success=True,
                duration_ms=duration_ms,
                deleted_count=deleted_count,
            )
            _log_memory_event_safely(
                "memory_cleanup_session",
                session_id=session_id,
                success=True,
                duration_ms=duration_ms,
                deleted_count=deleted_count,
            )

        except Exception as e:
            logger.error("Error during session cleanup: %s", e)
            duration_ms = _duration_ms(started_at)
            _log_memory_event_safely(
                "memory_cleanup_session_duration_ms",
                session_id=session_id,
                success=False,
                duration_ms=duration_ms,
                deleted_count=0,
                error_type=type(e).__name__,
            )
            _log_memory_event_safely(
                "memory_cleanup_session",
                session_id=session_id,
                success=False,
                duration_ms=duration_ms,
                error_type=type(e).__name__,
            )

    async def cleanup(self) -> None:
        """
        非アクティブセッションのメッセージクリーンアップ

        conversation_sessionsテーブルでステータスが'ended'のセッションに
        紐づくメッセージを削除する。
        """
        logger.info("Running cleanup for ended session messages")

        if not self.supabase:
            return

        try:
            # 終了済みセッションのIDを取得
            sessions_response = (
                self.supabase.table("conversation_sessions")
                .select("id")
                .neq("status", "active")
                .execute()
            )

            if not sessions_response.data:
                logger.info("No ended sessions to clean up")
                return

            ended_session_ids = {s["id"] for s in sessions_response.data}

            messages_query = (
                self.supabase.table("agent_memory")
                .select("id")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
            )
            messages_response = messages_query.in_(
                _AGENT_MEMORY_SESSION_COLUMN,
                sorted(sanitize_for_postgres(session_id) for session_id in ended_session_ids),
            ).execute()

            if not messages_response.data:
                return

            ids_to_delete = [item["id"] for item in messages_response.data]

            if ids_to_delete:
                for record_id in ids_to_delete:
                    self.supabase.table("agent_memory").delete().eq("id", record_id).execute()

                logger.info("Cleaned up %d messages from ended sessions", len(ids_to_delete))

        except Exception as e:
            logger.error("Error during cleanup: %s", e)

    async def get_memory_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        メモリ統計を取得

        Args:
            session_id: 特定セッションの統計を取得（Noneなら全体）

        Returns:
            {
                "active_turns": int,  # アクティブな会話ターン数
                "oldest_turn": Optional[int],  # 最古のタイムスタンプ
                "newest_turn": Optional[int],  # 最新のタイムスタンプ
                "dominant_emotion": Optional[str],  # 主な感情
                "time_span": float  # 会話の時間範囲（分）
            }
        """
        logger.info("Getting memory statistics")

        if not self.supabase:
            return {
                "active_turns": 0,
                "oldest_turn": None,
                "newest_turn": None,
                "dominant_emotion": None,
                "time_span": 0.0,
            }

        try:
            query = (
                self.supabase.table("agent_memory")
                .select("value")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
            )
            if session_id:
                query = query.filter(
                    _AGENT_MEMORY_SESSION_COLUMN,
                    "eq",
                    sanitize_for_postgres(session_id),
                )
            response = query.execute()

            if not response.data:
                return {
                    "active_turns": 0,
                    "oldest_turn": None,
                    "newest_turn": None,
                    "dominant_emotion": None,
                    "time_span": 0.0,
                }

            items = response.data

            if not items:
                return {
                    "active_turns": 0,
                    "oldest_turn": None,
                    "newest_turn": None,
                    "dominant_emotion": None,
                    "time_span": 0.0,
                }

            # 統計情報を計算
            timestamps = []
            emotions = []

            for item in items:
                value = item.get("value", {})
                ts = value.get("timestamp")
                if ts:
                    timestamps.append(ts)
                emotion = value.get("emotion")
                if emotion:
                    emotions.append(emotion)

            oldest_turn = min(timestamps) if timestamps else None
            newest_turn = max(timestamps) if timestamps else None
            time_span = (
                (newest_turn - oldest_turn) / (1000 * 60) if oldest_turn and newest_turn else 0.0
            )

            # 最も多い感情を取得
            dominant_emotion = None
            if emotions:
                emotion_counts: Dict[str, int] = {}
                for e in emotions:
                    emotion_counts[e] = emotion_counts.get(e, 0) + 1
                dominant_emotion = max(emotion_counts, key=lambda k: emotion_counts[k])

            return {
                "active_turns": len(items),
                "oldest_turn": oldest_turn,
                "newest_turn": newest_turn,
                "dominant_emotion": dominant_emotion,
                "time_span": time_span,
            }

        except Exception as e:
            logger.error("Error getting memory stats: %s", e)
            return {
                "active_turns": 0,
                "oldest_turn": None,
                "newest_turn": None,
                "dominant_emotion": None,
                "time_span": 0.0,
            }
