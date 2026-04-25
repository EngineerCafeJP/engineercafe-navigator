"""STT warmup orchestration for Qwen-primary voice sessions."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from backend.observability.structured_logger import log_stt_event

logger = logging.getLogger(__name__)

STTWarmupStatus = Literal["started", "warming", "ready", "failed", "skipped"]


@dataclass(frozen=True)
class STTWarmupSnapshot:
    status: STTWarmupStatus
    provider: str
    error: str | None = None
    duration_ms: int | None = None


class STTWarmupService:
    """Start Qwen warmup once and expose non-blocking readiness state."""

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._task: asyncio.Task[STTWarmupSnapshot] | None = None
        self._status: STTWarmupStatus | None = None
        self._provider = "unknown"
        self._error: str | None = None
        self._duration_ms: int | None = None

    async def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def snapshot(self) -> STTWarmupSnapshot:
        return STTWarmupSnapshot(
            status=self._status or "skipped",
            provider=self._provider,
            error=self._error,
            duration_ms=self._duration_ms,
        )

    async def warmup(
        self,
        *,
        provider: str | None,
        warmup_factory: Callable[[], Awaitable[None]],
        session_id: str | None = None,
        wait: bool = False,
        raise_on_failure: bool = False,
    ) -> STTWarmupSnapshot:
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider != "qwen-primary":
            self._status = "skipped"
            self._provider = normalized_provider or "default"
            self._error = None
            self._duration_ms = None
            return self.snapshot()

        async with await self._get_lock():
            self._provider = normalized_provider
            if self._status == "ready":
                snapshot = self.snapshot()
            elif self._status == "failed":
                snapshot = self.snapshot()
            elif self._task is not None and not self._task.done():
                snapshot = STTWarmupSnapshot(status="warming", provider=normalized_provider)
            else:
                self._status = "warming"
                self._error = None
                self._duration_ms = None
                self._task = asyncio.create_task(
                    self._run_warmup(
                        provider=normalized_provider,
                        session_id=session_id,
                        warmup_factory=warmup_factory,
                    )
                )
                snapshot = STTWarmupSnapshot(status="started", provider=normalized_provider)

        if not wait:
            return snapshot

        if self._task is not None:
            snapshot = await self._task
        else:
            snapshot = self.snapshot()
        if raise_on_failure and snapshot.status == "failed":
            raise RuntimeError(snapshot.error or "STT warmup failed")
        return snapshot

    async def _run_warmup(
        self,
        *,
        provider: str,
        session_id: str | None,
        warmup_factory: Callable[[], Awaitable[None]],
    ) -> STTWarmupSnapshot:
        started_at = time.perf_counter()
        log_stt_event(
            event="stt_warmup_start",
            provider=provider,
            session_id=session_id,
        )
        try:
            await warmup_factory()
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            error = f"{type(exc).__name__}: {exc}"
            self._status = "failed"
            self._error = error
            self._duration_ms = duration_ms
            logger.warning("STT warmup failed: %s", error)
            log_stt_event(
                event="stt_warmup_complete",
                provider=provider,
                session_id=session_id,
                success=False,
                error_type=type(exc).__name__,
                stt_warmup_duration_ms=duration_ms,
            )
            return self.snapshot()

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        self._status = "ready"
        self._error = None
        self._duration_ms = duration_ms
        log_stt_event(
            event="stt_warmup_complete",
            provider=provider,
            session_id=session_id,
            success=True,
            stt_warmup_duration_ms=duration_ms,
        )
        return self.snapshot()


_stt_warmup_service: STTWarmupService | None = None


def get_stt_warmup_service() -> STTWarmupService:
    global _stt_warmup_service
    if _stt_warmup_service is None:
        _stt_warmup_service = STTWarmupService()
    return _stt_warmup_service


def reset_stt_warmup_service() -> None:
    global _stt_warmup_service
    _stt_warmup_service = None
