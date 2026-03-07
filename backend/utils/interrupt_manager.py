"""Session-scoped interrupt signal management."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class InterruptState:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    timestamp: float = field(default_factory=time.time)


class InterruptManager:
    """Manage session-scoped interrupt signals outside LangGraph state."""

    def __init__(self):
        self._sessions: dict[str, InterruptState] = {}

    def _get_or_create_state(self, session_id: str) -> InterruptState:
        state = self._sessions.get(session_id)
        if state is None:
            state = InterruptState()
            self._sessions[session_id] = state
        return state

    def request_interrupt(self, session_id: str) -> None:
        """Request interruption for a session."""
        state = self._get_or_create_state(session_id)
        state.timestamp = time.time()
        state.event.set()

    def is_interrupted(self, session_id: str) -> bool:
        """Return whether a session currently has a pending interrupt."""
        state = self._sessions.get(session_id)
        return bool(state and state.event.is_set())

    def clear_interrupt(self, session_id: str) -> None:
        """Clear interrupt state for a session."""
        self._sessions.pop(session_id, None)

    async def wait_for_interrupt(self, session_id: str, timeout: float | None = None) -> bool:
        """Wait asynchronously for an interrupt signal."""
        state = self._get_or_create_state(session_id)
        if state.event.is_set():
            return True

        try:
            await asyncio.wait_for(state.event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def cleanup_stale_sessions(self, max_age_seconds: float) -> None:
        """Remove interrupt state older than the configured age."""
        now = time.time()
        stale_session_ids = [
            session_id
            for session_id, state in self._sessions.items()
            if now - state.timestamp >= max_age_seconds
        ]
        for session_id in stale_session_ids:
            self._sessions.pop(session_id, None)


_manager = InterruptManager()


def get_interrupt_manager() -> InterruptManager:
    return _manager
