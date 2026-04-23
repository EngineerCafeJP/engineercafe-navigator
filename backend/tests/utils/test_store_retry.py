"""Tests for store retry utilities: is_store_connection_error and store_with_retry."""

import asyncio
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

import backend.utils.store as store_module
from backend.utils.store import (
    _CONNECTION_ERROR_INDICATORS,
    is_store_connection_error,
    store_with_retry,
)


class FakePool(store_module.AsyncConnectionPool):
    def __init__(self, max_size: int = 5):
        self.check = AsyncMock()
        self._semaphore = asyncio.Semaphore(max_size)
        self.active = 0
        self.max_active = 0

    @asynccontextmanager
    async def connection(self):
        async with self._semaphore:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                yield object()
            finally:
                self.active -= 1


class FakeStore:
    def __init__(self, pool: FakePool | None = None):
        self.conn = pool or FakePool()
        self.calls = 0

    async def asearch(self, namespace, *, query="", limit=5):
        async with self.conn.connection():
            await asyncio.sleep(0.001)
            return [namespace, query, limit]

    async def aput(self, namespace, key, value):
        async with self.conn.connection():
            await asyncio.sleep(0.001)
            return {"namespace": namespace, "key": key, "value": value}


@pytest.fixture(autouse=True)
def _reset_singleton():
    store_module._store_instance = None
    yield
    store_module._store_instance = None


class TestIsStoreConnectionError:
    """Tests for is_store_connection_error()."""

    @pytest.mark.parametrize(
        "error_message",
        list(_CONNECTION_ERROR_INDICATORS),
        ids=[repr(m) for m in _CONNECTION_ERROR_INDICATORS],
    )
    def test_detects_known_connection_errors(self, error_message: str):
        assert is_store_connection_error(RuntimeError(error_message)) is True

    @pytest.mark.parametrize(
        "error_message",
        [
            "something went wrong",
            "timeout",
            "permission denied",
            "table not found",
        ],
    )
    def test_rejects_unrelated_errors(self, error_message: str):
        assert is_store_connection_error(RuntimeError(error_message)) is False

    def test_detects_value_error_with_connection_closed(self):
        assert is_store_connection_error(ValueError("connection is closed")) is True

    def test_case_insensitive(self):
        assert is_store_connection_error(RuntimeError("Connection Is Closed")) is True

    def test_detects_generic_exception(self):
        assert is_store_connection_error(Exception("broken pipe")) is True

    def test_rejects_key_error(self):
        assert is_store_connection_error(KeyError("missing key")) is False

    def test_rejects_value_error_unrelated(self):
        assert is_store_connection_error(ValueError("invalid argument")) is False


def _async_return(value):
    async def _f(*args, **kwargs):
        return value

    return _f


def _async_call_counter():
    calls = []

    async def _f(store):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("connection is closed")
        return "recovered"

    return _f, calls


class TestStoreWithRetry:
    """Tests for store_with_retry()."""

    @pytest.mark.asyncio
    async def test_returns_result_on_success_with_runtime_store(self):
        runtime_store = FakeStore()

        result = await store_with_retry(
            _async_return("ok"),
            store=runtime_store,
            operation_name="test op",
        )

        assert result == "ok"
        runtime_store.conn.check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retries_on_connection_error_checks_pool_and_succeeds(self):
        runtime_store = FakeStore()
        op, calls = _async_call_counter()

        result = await store_with_retry(
            op,
            store=runtime_store,
            operation_name="memory load",
        )

        assert result == "recovered"
        assert len(calls) == 2
        runtime_store.conn.check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        runtime_store = FakeStore()

        async def _always_fail(store):
            raise RuntimeError("connection is closed")

        with pytest.raises(RuntimeError, match="connection is closed"):
            await store_with_retry(
                _always_fail,
                store=runtime_store,
                max_retries=1,
                operation_name="memory load",
            )

        runtime_store.conn.check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_retry_non_connection_error(self):
        runtime_store = FakeStore()

        async def _value_error(store):
            raise ValueError("not a connection error")

        with pytest.raises(ValueError, match="not a connection error"):
            await store_with_retry(_value_error, store=runtime_store, operation_name="test")

        runtime_store.conn.check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_singleton_store_resets_when_pool_check_fails(self):
        first_store = FakeStore()
        first_store.conn.check.side_effect = RuntimeError("pool is closed")
        second_store = FakeStore()
        op_calls = []

        async def _op(store):
            op_calls.append(store)
            if store is first_store:
                raise RuntimeError("connection is closed")
            return "reconnected"

        with patch(
            "backend.utils.store.get_store", new=AsyncMock(side_effect=[first_store, second_store])
        ):
            with patch("backend.utils.store.close_store", new=AsyncMock()) as close_mock:
                result = await store_with_retry(_op, operation_name="memory load")

        assert result == "reconnected"
        assert op_calls == [first_store, second_store]
        close_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_operation_name_in_retry_log(self, caplog):
        runtime_store = FakeStore()
        op, _calls = _async_call_counter()

        with caplog.at_level(logging.WARNING, logger="backend.utils.store"):
            result = await store_with_retry(
                op,
                store=runtime_store,
                operation_name="long-term memory load",
            )

        assert result == "recovered"
        assert any("long-term memory load" in r.message for r in caplog.records)
        assert any("checking runtime store pool" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_zero_max_retries_raises_immediately(self):
        runtime_store = FakeStore()

        async def _conn_err(store):
            raise RuntimeError("connection is closed")

        with pytest.raises(RuntimeError, match="connection is closed"):
            await store_with_retry(
                _conn_err,
                store=runtime_store,
                max_retries=0,
                operation_name="test",
            )

        runtime_store.conn.check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pool_size_limit_blocks_and_releases(self):
        pool = FakePool(max_size=2)
        runtime_store = FakeStore(pool)

        async def _op(store):
            return await store.asearch(("visitor_memories", "pool-user"), query="test", limit=1)

        results = await asyncio.gather(
            *(
                store_with_retry(_op, store=runtime_store, operation_name="memory load")
                for _ in range(5)
            )
        )

        assert len(results) == 5
        assert pool.max_active == 2
        assert pool.active == 0

    @pytest.mark.asyncio
    async def test_ten_parallel_requests_succeed(self):
        runtime_store = FakeStore(FakePool(max_size=5))

        async def _op(store):
            return await store.aput(("visitor_memories", "parallel-user"), "key", {"data": "ok"})

        results = await asyncio.gather(
            *(
                store_with_retry(
                    _op,
                    store=runtime_store,
                    operation_name="long-term memory store",
                )
                for _ in range(10)
            )
        )

        assert len(results) == 10
        assert all(result["value"] == {"data": "ok"} for result in results)
