"""Tests for store retry utilities: is_store_connection_error and store_with_retry."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.utils.store as store_module
from backend.utils.store import (
    _CONNECTION_ERROR_INDICATORS,
    close_store,
    is_store_connection_error,
    store_with_retry,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    store_module._store_instance = None
    store_module._store_cm = None
    yield
    store_module._store_instance = None
    store_module._store_cm = None


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


def _make_mock_cm(store_instance):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=store_instance)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


class TestStoreWithRetry:
    """Tests for store_with_retry()."""

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                result = await store_with_retry(
                    _async_return("ok"),
                    operation_name="test op",
                )
                assert result == "ok"

    @pytest.mark.asyncio
    async def test_retries_on_connection_error_and_succeeds(self):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        op, calls = _async_call_counter()

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                result = await store_with_retry(op, operation_name="memory load")
                assert result == "recovered"
                assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        async def _always_fail(store):
            raise RuntimeError("connection is closed")

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                with pytest.raises(RuntimeError, match="connection is closed"):
                    await store_with_retry(
                        _always_fail,
                        max_retries=1,
                        operation_name="memory load",
                    )

    @pytest.mark.asyncio
    async def test_does_not_retry_non_connection_error(self):
        async def _value_error(store):
            raise ValueError("not a connection error")

        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                with pytest.raises(ValueError, match="not a connection error"):
                    await store_with_retry(_value_error, operation_name="test")

    @pytest.mark.asyncio
    async def test_calls_close_store_on_connection_error(self):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        op, calls = _async_call_counter()

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                with patch("backend.utils.store.close_store", wraps=close_store) as mock_close:
                    result = await store_with_retry(op, operation_name="memory load")
                    assert result == "recovered"
                    mock_close.assert_awaited()

    @pytest.mark.asyncio
    async def test_operation_name_in_retry_log(self, caplog):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        op, calls = _async_call_counter()

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                with caplog.at_level(logging.WARNING, logger="backend.utils.store"):
                    result = await store_with_retry(op, operation_name="long-term memory load")
                    assert result == "recovered"
                    assert any("long-term memory load" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_zero_max_retries_raises_immediately(self):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        async def _conn_err(store):
            raise RuntimeError("connection is closed")

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                with pytest.raises(RuntimeError, match="connection is closed"):
                    await store_with_retry(
                        _conn_err,
                        max_retries=0,
                        operation_name="test",
                    )
