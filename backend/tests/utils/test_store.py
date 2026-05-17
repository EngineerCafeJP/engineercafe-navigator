"""Tests for backend.utils.store pooled AsyncPostgresStore management."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.utils.store as store_module
from backend.utils.store import (
    add_tcp_keepalive_params,
    close_store,
    create_store,
    get_store,
    reset_store,
)


class FakePool(store_module.AsyncConnectionPool):
    check_connection = AsyncMock()
    instances: list["FakePool"] = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.open = AsyncMock()
        self.close = AsyncMock()
        self.check = AsyncMock()
        FakePool.instances.append(self)


class FakeStore:
    def __init__(self, conn):
        self.conn = conn
        self.setup = AsyncMock()
        self.__aexit__ = AsyncMock(return_value=None)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """各テスト前後にシングルトンをリセット"""
    store_module._store_instance = None
    store_module._store_loop = None
    FakePool.instances = []
    yield
    store_module._store_instance = None
    store_module._store_loop = None
    FakePool.instances = []


class TestKeepaliveParams:
    def test_adds_keepalive_params_to_empty_query(self):
        result = add_tcp_keepalive_params("postgresql://u:p@localhost:5432/db")

        assert result == (
            "postgresql://u:p@localhost:5432/db?"
            "keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=3"
        )

    def test_preserves_existing_query_params(self):
        result = add_tcp_keepalive_params(
            "postgresql://u:p@localhost/db?sslmode=require&keepalives_idle=90"
        )

        assert "sslmode=require" in result
        assert "keepalives=1" in result
        assert "keepalives_idle=30" in result
        assert "keepalives_interval=10" in result
        assert "keepalives_count=3" in result


class TestCreateStore:
    """create_store() のテスト"""

    @pytest.mark.asyncio
    async def test_create_store_no_env_var_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_DB_URI"):
                await create_store()

    @pytest.mark.asyncio
    async def test_create_store_empty_env_var_raises(self):
        with patch.dict("os.environ", {"SUPABASE_DB_URI": ""}):
            with pytest.raises(ValueError, match="SUPABASE_DB_URI"):
                await create_store()

    @pytest.mark.asyncio
    async def test_create_store_success(self):
        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch("backend.utils.store.AsyncConnectionPool", FakePool):
                with patch("backend.utils.store.AsyncPostgresStore", FakeStore):
                    result = await create_store()

        assert isinstance(result, FakeStore)
        assert result.conn is FakePool.instances[0]
        result.setup.assert_awaited_once()
        pool = FakePool.instances[0]
        pool.open.assert_awaited_once()
        assert pool.kwargs["min_size"] == 1
        assert pool.kwargs["max_size"] == 5
        assert pool.kwargs["max_idle"] == 120
        assert pool.kwargs["timeout"] == 30
        assert pool.kwargs["open"] is False
        assert "keepalives_idle=30" in pool.kwargs["conninfo"]

    @pytest.mark.asyncio
    async def test_create_store_connection_error_closes_pool(self):
        class FailingStore(FakeStore):
            def __init__(self, conn):
                super().__init__(conn)
                self.setup = AsyncMock(side_effect=Exception("Connection refused"))

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://bad@localhost/bad"}):
            with patch("backend.utils.store.AsyncConnectionPool", FakePool):
                with patch("backend.utils.store.AsyncPostgresStore", FailingStore):
                    with pytest.raises(ConnectionError, match="Failed to connect"):
                        await create_store()

        FakePool.instances[0].close.assert_awaited_once()


class TestGetStore:
    """get_store() シングルトンパターンのテスト"""

    @pytest.mark.asyncio
    async def test_get_store_creates_instance(self):
        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch("backend.utils.store.AsyncConnectionPool", FakePool):
                with patch("backend.utils.store.AsyncPostgresStore", FakeStore):
                    result = await get_store()

        assert isinstance(result, FakeStore)

    @pytest.mark.asyncio
    async def test_get_store_returns_same_instance(self):
        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test@test/test"}):
            with patch("backend.utils.store.AsyncConnectionPool", FakePool):
                with patch("backend.utils.store.AsyncPostgresStore", FakeStore):
                    result1 = await get_store()
                    result2 = await get_store()

        assert result1 is result2
        assert len(FakePool.instances) == 1

    @pytest.mark.asyncio
    async def test_get_store_existing_instance(self):
        existing = MagicMock()
        store_module._store_instance = existing
        result = await get_store()
        assert result is existing


class TestCloseStore:
    """close_store() のテスト"""

    @pytest.mark.asyncio
    async def test_close_store_no_instance(self):
        await close_store()
        assert store_module._store_instance is None

    @pytest.mark.asyncio
    async def test_close_store_with_pool(self):
        pool = FakePool()
        mock_store = FakeStore(pool)
        store_module._store_instance = mock_store

        await close_store()

        mock_store.__aexit__.assert_awaited_once_with(None, None, None)
        pool.close.assert_awaited_once()
        assert store_module._store_instance is None

    @pytest.mark.asyncio
    async def test_close_store_without_pool(self):
        mock_store = FakeStore(conn=object())
        store_module._store_instance = mock_store

        await close_store()

        mock_store.__aexit__.assert_awaited_once_with(None, None, None)
        assert store_module._store_instance is None

    @pytest.mark.asyncio
    async def test_close_store_error_cleans_up(self):
        pool = FakePool()
        mock_store = FakeStore(pool)
        mock_store.__aexit__ = AsyncMock(side_effect=Exception("close error"))
        store_module._store_instance = mock_store

        await close_store()

        assert store_module._store_instance is None


class TestResetStore:
    """reset_store() のテスト"""

    @pytest.mark.asyncio
    async def test_reset_store_calls_close(self):
        pool = FakePool()
        mock_store = FakeStore(pool)
        store_module._store_instance = mock_store

        await reset_store()

        mock_store.__aexit__.assert_awaited_once_with(None, None, None)
        pool.close.assert_awaited_once()
        assert store_module._store_instance is None

    @pytest.mark.asyncio
    async def test_reset_store_no_instance(self):
        await reset_store()
        assert store_module._store_instance is None
