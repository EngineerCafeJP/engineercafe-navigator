"""
セッション別タスク管理ユーティリティ

音声割り込み機能（Issue #127）において、進行中のLLM生成・TTS処理を
セッション単位で追跡・管理するためのモジュール。

主要クラス:
  - SessionTaskInfo: セッション内のタスク情報
  - SessionTaskManager: セッション別タスク管理（Singleton）
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from io import BytesIO

logger = logging.getLogger(__name__)


@dataclass
class SessionTaskInfo:
    """セッション内の進行中タスク情報"""

    session_id: str
    llm_task: Optional[asyncio.Task] = None
    """進行中のLLM生成タスク"""

    tts_task: Optional[asyncio.Task] = None
    """進行中のTTS処理タスク"""

    tts_buffer: Optional[BytesIO] = None
    """TTS出力バッファ（音声データ）"""

    created_at: datetime = field(default_factory=datetime.now)
    """セッション作成時刻"""

    last_activity: datetime = field(default_factory=datetime.now)
    """最後の活動時刻（TTL計算用）"""

    def update_activity(self) -> None:
        """最後の活動時刻を更新"""
        self.last_activity = datetime.now()

    def is_active(self) -> bool:
        """タスクが進行中か判定"""
        return (self.llm_task is not None and not self.llm_task.done()) or (
            self.tts_task is not None and not self.tts_task.done()
        )


class SessionTaskManager:
    """
    セッション別タスク管理（Singleton パターン）

    機能:
      - セッション登録/取得/削除
      - LLM/TTSタスク登録
      - タスクキャンセル
      - TTSバッファ管理
      - TTL-based自動クリーンアップ

    スレッド安全性: asyncio.Lock で保護

    使用例:
      ```python
      manager = SessionTaskManager()
      await manager.initialize()  # バックグラウンド クリーンアップ開始

      # セッション登録
      await manager.register_session("session-123")

      # LLMタスク登録
      llm_task = asyncio.create_task(llm_generation())
      await manager.set_llm_task("session-123", llm_task)

      # 割り込み: タスクキャンセル
      await manager.cancel_llm_task("session-123")
      ```
    """

    _instance: Optional["SessionTaskManager"] = None
    CLEANUP_INTERVAL = 60  # クリーンアップ実行間隔（秒）
    SESSION_TTL = 300  # セッション有効期限（秒、5分）

    def __new__(cls) -> "SessionTaskManager":
        """Singleton パターン実装"""
        if cls._instance is None:
            cls._instance = super(SessionTaskManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初期化"""
        if self._initialized:
            return

        self._sessions: Dict[str, SessionTaskInfo] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._initialized = True
        logger.info("SessionTaskManager initialized")

    async def _get_lock(self) -> asyncio.Lock:
        """イベントループ内で Lock を遅延初期化"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def initialize(self) -> None:
        """バックグラウンド クリーンアップタスク開始"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("SessionTaskManager cleanup loop started")

    async def shutdown(self) -> None:
        """クリーンアップタスク停止＆セッション全削除"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with await self._get_lock():
            self._sessions.clear()

        logger.info("SessionTaskManager shutdown complete")

    async def register_session(self, session_id: str) -> SessionTaskInfo:
        """セッションを登録/取得"""
        async with await self._get_lock():
            if session_id not in self._sessions:
                info = SessionTaskInfo(session_id=session_id)
                self._sessions[session_id] = info
                logger.debug("Session registered: %s", session_id)
            else:
                self._sessions[session_id].update_activity()

            return self._sessions[session_id]

    async def get_session(self, session_id: str) -> Optional[SessionTaskInfo]:
        """セッション情報を取得"""
        async with await self._get_lock():
            return self._sessions.get(session_id)

    async def set_llm_task(self, session_id: str, task: asyncio.Task) -> bool:
        """LLM生成タスクを登録"""
        async with await self._get_lock():
            if session_id in self._sessions:
                self._sessions[session_id].llm_task = task
                self._sessions[session_id].update_activity()
                logger.debug("LLM task set for session %s", session_id)
                return True
            return False

    async def set_tts_task(self, session_id: str, task: asyncio.Task) -> bool:
        """TTS処理タスクを登録"""
        async with await self._get_lock():
            if session_id in self._sessions:
                self._sessions[session_id].tts_task = task
                self._sessions[session_id].update_activity()
                logger.debug("TTS task set for session %s", session_id)
                return True
            return False

    async def set_tts_buffer(self, session_id: str, buffer: BytesIO) -> bool:
        """TTSバッファを登録"""
        async with await self._get_lock():
            if session_id in self._sessions:
                self._sessions[session_id].tts_buffer = buffer
                self._sessions[session_id].update_activity()
                logger.debug("TTS buffer set for session %s", session_id)
                return True
            return False

    async def get_tts_buffer(self, session_id: str) -> Optional[BytesIO]:
        """TTSバッファを取得"""
        async with await self._get_lock():
            if session_id in self._sessions:
                return self._sessions[session_id].tts_buffer
            return None

    async def cancel_llm_task(self, session_id: str) -> bool:
        """LLMタスクをキャンセル"""
        async with await self._get_lock():
            if session_id not in self._sessions:
                logger.warning("Session not found for cancel_llm_task: %s", session_id)
                return False

            info = self._sessions[session_id]
            if info.llm_task is None:
                logger.warning("No LLM task for session %s", session_id)
                return False

            if info.llm_task.done():
                logger.debug("LLM task already done for session %s", session_id)
                return False

            info.llm_task.cancel()
            logger.info("LLM task cancelled for session %s", session_id)
            return True

    async def cancel_tts_task(self, session_id: str) -> bool:
        """TTSタスクをキャンセル"""
        async with await self._get_lock():
            if session_id not in self._sessions:
                logger.warning("Session not found for cancel_tts_task: %s", session_id)
                return False

            info = self._sessions[session_id]
            if info.tts_task is None:
                logger.warning("No TTS task for session %s", session_id)
                return False

            if info.tts_task.done():
                logger.debug("TTS task already done for session %s", session_id)
                return False

            info.tts_task.cancel()
            logger.info("TTS task cancelled for session %s", session_id)
            return True

    async def clear_tts_buffer(self, session_id: str) -> bool:
        """TTSバッファをクリア"""
        async with await self._get_lock():
            if session_id in self._sessions:
                self._sessions[session_id].tts_buffer = None
                logger.debug("TTS buffer cleared for session %s", session_id)
                return True
            return False

    async def cancel_all_tasks(self, session_id: str) -> bool:
        """セッションの全タスクをキャンセル"""
        async with await self._get_lock():
            if session_id not in self._sessions:
                logger.warning("Session not found for cancel_all_tasks: %s", session_id)
                return False

            info = self._sessions[session_id]
            any_cancelled = False

            # LLMタスクキャンセル
            if info.llm_task and not info.llm_task.done():
                info.llm_task.cancel()
                any_cancelled = True
                logger.info("LLM task cancelled for session %s", session_id)

            # TTSタスクキャンセル
            if info.tts_task and not info.tts_task.done():
                info.tts_task.cancel()
                any_cancelled = True
                logger.info("TTS task cancelled for session %s", session_id)

            # バッファクリア
            if info.tts_buffer is not None:
                info.tts_buffer = None
                logger.info("TTS buffer cleared for session %s", session_id)

            return any_cancelled

    async def cleanup_session(self, session_id: str) -> bool:
        """セッションを削除"""
        async with await self._get_lock():
            if session_id in self._sessions:
                # タスクのキャンセルを試みる（念のため）
                info = self._sessions[session_id]
                if info.llm_task and not info.llm_task.done():
                    info.llm_task.cancel()
                if info.tts_task and not info.tts_task.done():
                    info.tts_task.cancel()

                del self._sessions[session_id]
                logger.info("Session cleaned up: %s", session_id)
                return True
            return False

    async def get_active_sessions(self) -> list:
        """進行中のセッション一覧を取得"""
        async with await self._get_lock():
            return [info.session_id for info in self._sessions.values() if info.is_active()]

    async def get_session_count(self) -> int:
        """登録されているセッション数"""
        async with await self._get_lock():
            return len(self._sessions)

    async def _cleanup_loop(self) -> None:
        """バックグラウンド クリーンアップループ（TTL-based）"""
        try:
            while True:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self._cleanup_expired_sessions()
        except asyncio.CancelledError:
            logger.info("SessionTaskManager cleanup loop cancelled")

    async def _cleanup_expired_sessions(self) -> None:
        """期限切れセッションを自動削除"""
        async with await self._get_lock():
            now = datetime.now()
            expired_sessions = [
                (sid, info)
                for sid, info in self._sessions.items()
                if (now - info.last_activity).total_seconds() > self.SESSION_TTL
            ]

            for session_id, info in expired_sessions:
                # タスクをキャンセル
                if info.llm_task and not info.llm_task.done():
                    info.llm_task.cancel()
                if info.tts_task and not info.tts_task.done():
                    info.tts_task.cancel()

                # セッション削除
                del self._sessions[session_id]
                logger.info("Expired session cleaned up: %s", session_id)

            if expired_sessions:
                logger.info("Cleaned up %d expired sessions", len(expired_sessions))


# グローバルインスタンス
_session_task_manager: Optional[SessionTaskManager] = None


def get_session_task_manager() -> SessionTaskManager:
    """SessionTaskManager のシングルトン インスタンスを取得"""
    global _session_task_manager
    if _session_task_manager is None:
        _session_task_manager = SessionTaskManager()
    return _session_task_manager


def reset_session_task_manager() -> None:
    """テスト用: SessionTaskManager シングルトンをリセット"""
    global _session_task_manager
    _session_task_manager = None
    SessionTaskManager._instance = None
