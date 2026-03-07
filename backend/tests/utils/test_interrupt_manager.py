import asyncio

import pytest

from backend.utils.interrupt_manager import InterruptManager


class TestInterruptManager:
    def test_request_and_check_interrupt(self):
        mgr = InterruptManager()

        assert not mgr.is_interrupted("s1")

        mgr.request_interrupt("s1")

        assert mgr.is_interrupted("s1")

    def test_clear_interrupt(self):
        mgr = InterruptManager()

        mgr.request_interrupt("s1")
        mgr.clear_interrupt("s1")

        assert not mgr.is_interrupted("s1")

    def test_session_isolation(self):
        mgr = InterruptManager()

        mgr.request_interrupt("s1")

        assert not mgr.is_interrupted("s2")

    @pytest.mark.asyncio
    async def test_wait_for_interrupt_timeout(self):
        mgr = InterruptManager()

        result = await mgr.wait_for_interrupt("s1", timeout=0.1)

        assert not result

    @pytest.mark.asyncio
    async def test_wait_for_interrupt_signaled(self):
        mgr = InterruptManager()

        async def signal_later():
            await asyncio.sleep(0.05)
            mgr.request_interrupt("s1")

        asyncio.create_task(signal_later())
        result = await mgr.wait_for_interrupt("s1", timeout=1.0)

        assert result

    def test_stale_session_cleanup(self):
        mgr = InterruptManager()

        mgr.request_interrupt("old_session")
        mgr.cleanup_stale_sessions(max_age_seconds=0)

        assert not mgr.is_interrupted("old_session")
