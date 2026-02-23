"""Tests for backend.utils.store — AsyncPostgresStore singleton management."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.utils.store as store_module
from backend.utils.store import (
    close_store,
    create_store,
    get_store,
    reset_store,
)


def _make_mock_cm(store_instance):
    """from_conn_string が返すコンテキストマネージャーのモックを生成"""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=store_instance)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.fixture(autouse=True)
def _reset_singleton():
    """各テスト前後にシングルトンをリセット"""
    store_module._store_instance = None
    store_module._store_cm = None
    yield
    store_module._store_instance = None
    store_module._store_cm = None


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
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test:test@localhost/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                result = await create_store()
                assert result is mock_store
                mock_store.setup.assert_awaited_once()
                mock_cm.__aenter__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_store_connection_error(self):
        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://bad@localhost/bad"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                side_effect=Exception("Connection refused"),
            ):
                with pytest.raises(ConnectionError, match="Failed to connect"):
                    await create_store()


class TestGetStore:
    """get_store() シングルトンパターンのテスト"""

    @pytest.mark.asyncio
    async def test_get_store_creates_instance(self):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test:test@localhost/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ):
                result = await get_store()
                assert result is mock_store

    @pytest.mark.asyncio
    async def test_get_store_returns_same_instance(self):
        mock_store = AsyncMock()
        mock_store.setup = AsyncMock()
        mock_cm = _make_mock_cm(mock_store)

        with patch.dict("os.environ", {"SUPABASE_DB_URI": "postgresql://test:test@localhost/test"}):
            with patch(
                "backend.utils.store.AsyncPostgresStore.from_conn_string",
                return_value=mock_cm,
            ) as mock_from_conn:
                result1 = await get_store()
                result2 = await get_store()
                assert result1 is result2
                # from_conn_string は1回しか呼ばれない（シングルトン）
                mock_from_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_store_existing_instance(self):
        existing = AsyncMock()
        store_module._store_instance = existing
        result = await get_store()
        assert result is existing


class TestCloseStore:
    """close_store() のテスト"""

    @pytest.mark.asyncio
    async def test_close_store_no_instance(self):
        # None の場合は何も起きない
        await close_store()
        assert store_module._store_instance is None

    @pytest.mark.asyncio
    async def test_close_store_with_cm(self):
        """_store_cm がある場合、__aexit__ を呼んでクリーンアップ"""
        mock_store = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        store_module._store_instance = mock_store
        store_module._store_cm = mock_cm

        await close_store()

        mock_cm.__aexit__.assert_awaited_once_with(None, None, None)
        assert store_module._store_instance is None
        assert store_module._store_cm is None

    @pytest.mark.asyncio
    async def test_close_store_without_cm(self):
        """_store_cm が None でもインスタンスはクリーンアップされる"""
        mock_store = AsyncMock()
        store_module._store_instance = mock_store
        store_module._store_cm = None

        await close_store()

        assert store_module._store_instance is None
        assert store_module._store_cm is None

    @pytest.mark.asyncio
    async def test_close_store_error_cleans_up(self):
        """__aexit__ でエラーが発生してもインスタンスは None にリセット"""
        mock_store = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aexit__ = AsyncMock(side_effect=Exception("close error"))
        store_module._store_instance = mock_store
        store_module._store_cm = mock_cm

        await close_store()
        assert store_module._store_instance is None
        assert store_module._store_cm is None

    @pytest.mark.asyncio
    async def test_close_store_instance_only(self):
        """_store_cm なし・_store_instance ありでもエラーにならない"""
        mock_store = MagicMock(spec=[])
        store_module._store_instance = mock_store

        await close_store()
        assert store_module._store_instance is None


class TestResetStore:
    """reset_store() のテスト"""

    @pytest.mark.asyncio
    async def test_reset_store_calls_close(self):
        mock_store = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        store_module._store_instance = mock_store
        store_module._store_cm = mock_cm

        await reset_store()

        mock_cm.__aexit__.assert_awaited_once_with(None, None, None)
        assert store_module._store_instance is None
        assert store_module._store_cm is None

    @pytest.mark.asyncio
    async def test_reset_store_no_instance(self):
        await reset_store()
        assert store_module._store_instance is None
