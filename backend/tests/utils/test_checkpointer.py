"""Tests for backend.utils.checkpointer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from psycopg import OperationalError
from psycopg_pool import PoolClosed

from backend.utils import checkpointer


class TestMaskConnectionString:
    def test_masks_password_in_connection_string(self):
        db_uri = "postgresql://user:secret_password@host:5432/database"
        result = checkpointer._mask_connection_string(db_uri)
        assert result == "postgresql://user:****@host:5432/database"
        assert "secret_password" not in result

    def test_url_without_password_unchanged(self):
        db_uri = "postgresql://host:5432/database"
        assert checkpointer._mask_connection_string(db_uri) == db_uri

    def test_empty_string_returns_empty(self):
        assert checkpointer._mask_connection_string("") == ""


class TestConnectionErrorDetection:
    def test_detects_driver_level_connection_errors(self):
        assert checkpointer.is_checkpointer_connection_error(
            OperationalError("connection is closed")
        )
        assert checkpointer.is_checkpointer_connection_error(PoolClosed("pool is closed"))

    def test_detects_message_only_connection_errors(self):
        error = RuntimeError("server closed the connection unexpectedly")
        assert checkpointer.is_checkpointer_connection_error(error)

    def test_ignores_unrelated_errors(self):
        assert not checkpointer.is_checkpointer_connection_error(ValueError("bad config"))


class TestCheckpointerFactory:
    @pytest.mark.asyncio
    async def test_create_pool_uses_resilient_cloud_run_settings(self):
        mock_pool = AsyncMock()
        mock_pool.open = AsyncMock()

        with patch(
            "backend.utils.checkpointer.AsyncConnectionPool",
            return_value=mock_pool,
        ) as pool_cls:
            factory = checkpointer._CheckpointerFactory("postgresql://user:pass@localhost:5432/db")
            result = await factory.create_pool()

        assert result is mock_pool
        mock_pool.open.assert_awaited_once()

        call_kwargs = pool_cls.call_args.kwargs
        assert call_kwargs["min_size"] == 0
        assert call_kwargs["max_size"] == 5
        assert call_kwargs["max_idle"] == 300
        assert call_kwargs["open"] is False
        assert callable(call_kwargs["check"])
        assert call_kwargs["kwargs"]["connect_timeout"] == 10
        assert call_kwargs["kwargs"]["keepalives"] == 1
        assert call_kwargs["kwargs"]["keepalives_idle"] == 30

    @pytest.mark.asyncio
    async def test_create_checkpointer_sets_up_saver(self):
        mock_factory = MagicMock()
        mock_factory.db_uri = "postgresql://user:pass@localhost:5432/db"
        mock_factory.create_checkpointer = AsyncMock(return_value=AsyncMock())

        with patch.object(checkpointer._CheckpointerFactory, "from_env", return_value=mock_factory):
            result = await checkpointer.create_checkpointer()

        assert result is mock_factory.create_checkpointer.return_value
        mock_factory.create_checkpointer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_checkpointer_wraps_factory_errors(self):
        mock_factory = MagicMock()
        mock_factory.db_uri = "postgresql://user:pass@localhost:5432/db"
        mock_factory.create_checkpointer = AsyncMock(side_effect=Exception("Connection failed"))

        with patch.object(checkpointer._CheckpointerFactory, "from_env", return_value=mock_factory):
            with pytest.raises(ConnectionError) as exc_info:
                await checkpointer.create_checkpointer()

        assert "Failed to connect to Supabase PostgreSQL" in str(exc_info.value)


class TestResilientAsyncPostgresSaver:
    @pytest.mark.asyncio
    async def test_alist_retries_after_stale_connection(self):
        initial_pool = MagicMock()
        initial_pool.close = AsyncMock()
        recovered_pool = MagicMock()
        recovered_pool.close = AsyncMock()

        factory = MagicMock()
        factory.create_pool = AsyncMock(return_value=recovered_pool)
        factory.prewarm_pool = AsyncMock()

        saver = checkpointer.ResilientAsyncPostgresSaver(factory=factory, pool=initial_pool)

        attempts = 0

        async def mock_alist(_self, config, *, filter=None, before=None, limit=None):
            nonlocal attempts
            attempts += 1
            assert config == {"configurable": {"thread_id": "session-1"}}
            assert filter == {"topic": "test"}
            assert before is None
            assert limit == 2
            if attempts == 1:
                raise RuntimeError("connection is closed")
            yield {"checkpoint_id": "one"}
            yield {"checkpoint_id": "two"}

        with patch.object(checkpointer.AsyncPostgresSaver, "alist", mock_alist):
            result = [
                item
                async for item in saver.alist(
                    {"configurable": {"thread_id": "session-1"}},
                    filter={"topic": "test"},
                    limit=2,
                )
            ]

        assert result == [{"checkpoint_id": "one"}, {"checkpoint_id": "two"}]
        assert attempts == 2
        factory.create_pool.assert_awaited_once()
        factory.prewarm_pool.assert_awaited_once_with(recovered_pool)
        initial_pool.close.assert_awaited_once()
        assert saver.pool is recovered_pool

    @pytest.mark.asyncio
    async def test_recreate_returns_when_pool_already_refreshed(self):
        initial_pool = MagicMock()
        initial_pool.close = AsyncMock()
        refreshed_pool = MagicMock()
        refreshed_pool.close = AsyncMock()

        factory = MagicMock()
        factory.create_pool = AsyncMock()
        factory.prewarm_pool = AsyncMock()

        saver = checkpointer.ResilientAsyncPostgresSaver(factory=factory, pool=initial_pool)
        saver.conn = refreshed_pool

        await saver.recreate(
            reason=RuntimeError("connection is closed"),
            stale_pool=initial_pool,
        )

        factory.create_pool.assert_not_awaited()
        factory.prewarm_pool.assert_not_awaited()
        initial_pool.close.assert_not_awaited()
        assert saver.pool is refreshed_pool


class TestGetCheckpointer:
    @pytest.fixture(autouse=True)
    async def cleanup(self):
        yield
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None

    @pytest.mark.asyncio
    async def test_returns_same_instance_on_double_call(self):
        mock_saver = AsyncMock()

        with patch(
            "backend.utils.checkpointer.create_checkpointer",
            AsyncMock(return_value=mock_saver),
        ):
            instance1 = await checkpointer.get_checkpointer()
            instance2 = await checkpointer.get_checkpointer()

        assert instance1 is instance2

    @pytest.mark.asyncio
    async def test_reset_clears_singleton(self):
        saver1 = AsyncMock()
        saver1.aclose = AsyncMock()
        saver2 = AsyncMock()
        saver2.aclose = AsyncMock()

        with patch(
            "backend.utils.checkpointer.create_checkpointer",
            AsyncMock(side_effect=[saver1, saver2]),
        ):
            instance1 = await checkpointer.get_checkpointer()
            await checkpointer.reset_checkpointer()
            instance2 = await checkpointer.get_checkpointer()

        assert instance1 is not instance2
        saver1.aclose.assert_awaited_once()


class TestCloseCheckpointer:
    @pytest.fixture(autouse=True)
    async def cleanup(self):
        yield
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None

    @pytest.mark.asyncio
    async def test_close_with_no_instance_no_error(self):
        await checkpointer.close_checkpointer()

    @pytest.mark.asyncio
    async def test_close_calls_aclose_on_instance(self):
        mock_saver = AsyncMock()
        mock_saver.aclose = AsyncMock()
        checkpointer._checkpointer_instance = mock_saver

        await checkpointer.close_checkpointer()

        mock_saver.aclose.assert_awaited_once()
        assert checkpointer._checkpointer_instance is None
        assert checkpointer._checkpointer_cm is None


class TestCreateMemoryCheckpointer:
    @pytest.mark.asyncio
    async def test_delegates_to_create_checkpointer(self):
        mock_saver = AsyncMock()

        with patch(
            "backend.utils.checkpointer.create_checkpointer",
            AsyncMock(return_value=mock_saver),
        ):
            result = await checkpointer.create_memory_checkpointer()

        assert result is mock_saver


class TestGetCheckpointerContext:
    @pytest.mark.asyncio
    async def test_raises_error_without_supabase_db_uri(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_DB_URI", raising=False)

        with pytest.raises(ValueError) as exc_info:
            async with checkpointer.get_checkpointer_context():
                pass

        assert "SUPABASE_DB_URI environment variable is not set" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_yields_checkpointer_instance_and_closes_it(self):
        mock_saver = AsyncMock()
        mock_saver.aclose = AsyncMock()

        with patch(
            "backend.utils.checkpointer.create_checkpointer",
            AsyncMock(return_value=mock_saver),
        ):
            async with checkpointer.get_checkpointer_context() as cp:
                assert cp is mock_saver

        mock_saver.aclose.assert_awaited_once()


class TestPrewarmCheckpointer:
    @pytest.fixture(autouse=True)
    async def cleanup(self):
        yield
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None

    @pytest.mark.asyncio
    async def test_prewarm_gets_singleton_and_calls_prewarm(self):
        mock_saver = AsyncMock()
        mock_saver.prewarm = AsyncMock()

        with patch(
            "backend.utils.checkpointer.get_checkpointer",
            AsyncMock(return_value=mock_saver),
        ):
            result = await checkpointer.prewarm_checkpointer()

        assert result is mock_saver
        mock_saver.prewarm.assert_awaited_once()
