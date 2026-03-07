"""Tests for backend.utils.checkpointer — AsyncPostgresSaver checkpointer utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.utils import checkpointer


class TestMaskConnectionString:
    """_mask_connection_string 関数のテスト"""

    def test_masks_password_in_connection_string(self):
        """パスワードが含まれる接続文字列をマスク"""
        db_uri = "postgresql://user:secret_password@host:5432/database"
        result = checkpointer._mask_connection_string(db_uri)
        assert result == "postgresql://user:****@host:5432/database"
        assert "secret_password" not in result

    def test_url_without_password_unchanged(self):
        """パスワードが含まれない接続文字列はそのまま"""
        db_uri = "postgresql://host:5432/database"
        result = checkpointer._mask_connection_string(db_uri)
        assert result == db_uri

    def test_empty_string_returns_empty(self):
        """空文字列は空文字列を返す"""
        result = checkpointer._mask_connection_string("")
        assert result == ""


def _make_mock_context_manager(mock_saver):
    """from_conn_string の戻り値をコンテキストマネージャーとしてモック化"""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_saver)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


class TestCreateCheckpointer:
    """create_checkpointer 関数のテスト"""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """各テスト後にシングルトンをリセット"""
        yield
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None

    async def test_raises_error_without_supabase_db_uri(self, monkeypatch):
        """SUPABASE_DB_URI が設定されていない場合は ValueError"""
        monkeypatch.delenv("SUPABASE_DB_URI", raising=False)

        with pytest.raises(ValueError) as exc_info:
            await checkpointer.create_checkpointer()

        assert "SUPABASE_DB_URI environment variable is not set" in str(exc_info.value)

    async def test_calls_async_postgres_saver_from_conn_string(self, monkeypatch):
        """SUPABASE_DB_URI が設定されている場合は AsyncPostgresSaver.from_conn_string を呼ぶ"""
        test_uri = "postgresql://user:pass@localhost:5432/test_db"
        monkeypatch.setenv("SUPABASE_DB_URI", test_uri)

        mock_saver = AsyncMock()
        mock_saver.setup = AsyncMock()

        mock_cm = _make_mock_context_manager(mock_saver)

        with patch(
            "backend.utils.checkpointer.AsyncPostgresSaver.from_conn_string",
            return_value=mock_cm,
        ):
            result = await checkpointer.create_checkpointer()

            mock_cm.__aenter__.assert_called_once()
            mock_saver.setup.assert_called_once()
            assert result == mock_saver

    async def test_raises_connection_error_on_failure(self, monkeypatch):
        """データベース接続に失敗した場合は ConnectionError"""
        monkeypatch.setenv("SUPABASE_DB_URI", "postgresql://invalid")

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "backend.utils.checkpointer.AsyncPostgresSaver.from_conn_string",
            return_value=mock_cm,
        ):
            with pytest.raises(ConnectionError) as exc_info:
                await checkpointer.create_checkpointer()

            assert "Failed to connect to Supabase PostgreSQL" in str(exc_info.value)


class TestGetCheckpointer:
    """get_checkpointer 関数のテスト（シングルトン）"""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """各テスト後にシングルトンをリセット"""
        yield
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None

    async def test_returns_same_instance_on_double_call(self, monkeypatch):
        """複数回呼び出しても同じインスタンスを返す（シングルトン）"""
        monkeypatch.setenv("SUPABASE_DB_URI", "postgresql://user:pass@localhost:5432/db")

        mock_saver = AsyncMock()
        mock_saver.setup = AsyncMock()

        mock_cm = _make_mock_context_manager(mock_saver)

        with patch(
            "backend.utils.checkpointer.AsyncPostgresSaver.from_conn_string",
            return_value=mock_cm,
        ):
            instance1 = await checkpointer.get_checkpointer()
            instance2 = await checkpointer.get_checkpointer()

            assert instance1 is instance2

    async def test_reset_clears_singleton(self, monkeypatch):
        """reset_checkpointer でシングルトンがクリアされる"""
        monkeypatch.setenv("SUPABASE_DB_URI", "postgresql://user:pass@localhost:5432/db")

        mock_saver1 = AsyncMock()
        mock_saver1.setup = AsyncMock()

        mock_saver2 = AsyncMock()
        mock_saver2.setup = AsyncMock()

        mock_cm1 = _make_mock_context_manager(mock_saver1)
        mock_cm2 = _make_mock_context_manager(mock_saver2)

        with patch(
            "backend.utils.checkpointer.AsyncPostgresSaver.from_conn_string",
            side_effect=[mock_cm1, mock_cm2],
        ):
            instance1 = await checkpointer.get_checkpointer()
            await checkpointer.reset_checkpointer()
            instance2 = await checkpointer.get_checkpointer()

            assert instance1 is not instance2
            mock_cm1.__aexit__.assert_called_once()


class TestCloseCheckpointer:
    """close_checkpointer 関数のテスト"""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """各テスト後にシングルトンをリセット"""
        yield
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None

    async def test_close_with_no_instance_no_error(self):
        """インスタンスが存在しない場合もエラーなし"""
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None
        await checkpointer.close_checkpointer()  # Should not raise

    async def test_close_calls_aexit_on_context_manager(self):
        """インスタンスが存在する場合は __aexit__ を呼ぶ"""
        mock_saver = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        checkpointer._checkpointer_instance = mock_saver
        checkpointer._checkpointer_cm = mock_cm

        await checkpointer.close_checkpointer()

        mock_cm.__aexit__.assert_called_once_with(None, None, None)
        assert checkpointer._checkpointer_instance is None
        assert checkpointer._checkpointer_cm is None


class TestCreateMemoryCheckpointer:
    """create_memory_checkpointer 関数のテスト"""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """各テスト後にシングルトンをリセット"""
        yield
        checkpointer._checkpointer_instance = None
        checkpointer._checkpointer_cm = None

    async def test_delegates_to_create_checkpointer(self, monkeypatch):
        """create_checkpointer に委譲する"""
        monkeypatch.setenv("SUPABASE_DB_URI", "postgresql://user:pass@localhost:5432/db")

        mock_saver = AsyncMock()
        mock_saver.setup = AsyncMock()

        mock_cm = _make_mock_context_manager(mock_saver)

        with patch(
            "backend.utils.checkpointer.AsyncPostgresSaver.from_conn_string",
            return_value=mock_cm,
        ):
            result = await checkpointer.create_memory_checkpointer()
            assert result == mock_saver


class TestGetCheckpointerContext:
    """get_checkpointer_context コンテキストマネージャーのテスト"""

    async def test_raises_error_without_supabase_db_uri(self, monkeypatch):
        """SUPABASE_DB_URI が設定されていない場合は ValueError"""
        monkeypatch.delenv("SUPABASE_DB_URI", raising=False)

        with pytest.raises(ValueError) as exc_info:
            async with checkpointer.get_checkpointer_context():
                pass

        assert "SUPABASE_DB_URI environment variable is not set" in str(exc_info.value)

    async def test_yields_checkpointer_instance(self, monkeypatch):
        """正常なコンテキストマネージャーとして動作"""
        monkeypatch.setenv("SUPABASE_DB_URI", "postgresql://user:pass@localhost:5432/db")

        mock_saver = AsyncMock()
        mock_saver.setup = AsyncMock()

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_saver
        mock_context_manager.__aexit__.return_value = None

        with patch(
            "backend.utils.checkpointer.AsyncPostgresSaver.from_conn_string",
            return_value=mock_context_manager,
        ):
            async with checkpointer.get_checkpointer_context() as cp:
                assert cp == mock_saver
