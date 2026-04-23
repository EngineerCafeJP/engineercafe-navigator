"""Tests for long-term memory retry integration in main_workflow."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

import backend.utils.store as store_module
from backend.utils.store import store_with_retry


@pytest.fixture(autouse=True)
def _reset_store_singleton():
    store_module._store_instance = None
    yield
    store_module._store_instance = None


def _setup_mock_store():
    """Create a mock store and inject it as the singleton."""
    mock_store = AsyncMock()
    mock_store.asearch = AsyncMock(return_value=[])
    mock_store.aput = AsyncMock(return_value=None)
    mock_store.setup = AsyncMock()
    store_module._store_instance = mock_store
    return mock_store


async def _noop_close_store():
    """No-op close that preserves the mock singleton for retry tests."""
    pass


class TestLongTermMemoryLoadRetry:
    """Test load path retry via store_with_retry."""

    @pytest.mark.asyncio
    async def test_load_retries_on_connection_error(self):
        """When asearch raises a connection error, store_with_retry retries."""
        mock_store = _setup_mock_store()
        call_count = 0

        async def _asearch_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("connection is closed")
            return []

        mock_store.asearch.side_effect = _asearch_side_effect

        with patch("backend.utils.store.close_store", side_effect=_noop_close_store):
            result = await store_with_retry(
                lambda s: s.asearch(("visitor_memories", "test-user"), query="test", limit=5),
                operation_name="long-term memory load",
            )
        assert result == []
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_load_succeeds_without_retry(self):
        """Normal load path has no retry overhead."""
        mock_store = _setup_mock_store()
        mock_store.asearch.return_value = []

        result = await store_with_retry(
            lambda s: s.asearch(("visitor_memories", "test-user"), query="test", limit=5),
            operation_name="long-term memory load",
        )
        assert result == []
        assert mock_store.asearch.call_count == 1

    @pytest.mark.asyncio
    async def test_runtime_store_is_used_when_provided(self):
        """runtime.store が渡された場合は singleton get_store を使わない。"""
        runtime_store = AsyncMock()
        runtime_store.asearch = AsyncMock(return_value=["runtime"])

        with patch("backend.utils.store.get_store") as mock_get_store:
            result = await store_with_retry(
                lambda s: s.asearch(("visitor_memories", "test-user"), query="test", limit=5),
                store=runtime_store,
                operation_name="long-term memory load",
            )

        assert result == ["runtime"]
        runtime_store.asearch.assert_called_once()
        mock_get_store.assert_not_called()


class TestLongTermMemoryStoreRetry:
    """Test store path retry via store_with_retry."""

    @pytest.mark.asyncio
    async def test_store_retries_on_connection_error(self):
        """When aput raises a connection error, store_with_retry retries."""
        mock_store = _setup_mock_store()
        call_count = 0

        async def _aput_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("connection is closed")
            return None

        mock_store.aput.side_effect = _aput_side_effect

        with patch("backend.utils.store.close_store", side_effect=_noop_close_store):
            await store_with_retry(
                lambda s: s.aput(("visitor_memories", "test-user"), "key", {"data": "test"}),
                operation_name="long-term memory store",
            )
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_store_succeeds_without_retry(self):
        """Normal store path has no retry overhead."""
        mock_store = _setup_mock_store()

        await store_with_retry(
            lambda s: s.aput(("visitor_memories", "test-user"), "key", {"data": "test"}),
            operation_name="long-term memory store",
        )
        assert mock_store.aput.call_count == 1

    @pytest.mark.asyncio
    async def test_store_failed_log_only_on_final_failure(self, caplog):
        """The 'long-term memory store' log only appears after all retries exhausted."""
        _setup_mock_store()  # side-effect only: registers mock store singleton

        async def _always_fail(store):
            raise RuntimeError("connection is closed")

        with patch("backend.utils.store.close_store", side_effect=_noop_close_store):
            with pytest.raises(RuntimeError, match="connection is closed"):
                await store_with_retry(
                    _always_fail,
                    max_retries=1,
                    operation_name="long-term memory store",
                )

        error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("long-term memory store" in r.message for r in error_logs)
