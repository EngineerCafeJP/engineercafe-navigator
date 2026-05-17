"""
LangGraph Store基盤実装

クロスセッションメモリのためのAsyncPostgresStore実装。
Supabase PostgreSQLを使用して訪問者の長期記憶を永続化する。

参考: https://langchain-ai.github.io/langgraph/concepts/persistence/
"""

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Optional, TypeVar, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_CONNECTION_ERROR_INDICATORS = (
    "connection is closed",
    "connection closed",
    "pool is closed",
    "server closed the connection unexpectedly",
    "terminating connection",
    "broken pipe",
    "ssl connection has been closed unexpectedly",
    "consuming input failed",
)

_KEEPALIVE_PARAMS = {
    "keepalives": "1",
    "keepalives_idle": "30",
    "keepalives_interval": "10",
    "keepalives_count": "3",
}

_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 5
_POOL_MAX_IDLE_SECONDS = 120
_POOL_TIMEOUT_SECONDS = 30


def is_store_connection_error(error: Exception) -> bool:
    """Return True when the exception indicates a dead/closed Store connection."""
    error_message = str(error).lower()
    return any(indicator in error_message for indicator in _CONNECTION_ERROR_INDICATORS)


_T = TypeVar("_T")


def add_tcp_keepalive_params(db_uri: str) -> str:
    """Return ``db_uri`` with TCP keepalive parameters required by Supabase direct DB."""
    if "://" not in db_uri:
        separator = " " if db_uri and not db_uri.endswith(" ") else ""
        keepalive_conninfo = " ".join(f"{k}={v}" for k, v in _KEEPALIVE_PARAMS.items())
        return f"{db_uri}{separator}{keepalive_conninfo}"

    parsed = urlsplit(db_uri)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params.update(_KEEPALIVE_PARAMS)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query_params),
            parsed.fragment,
        )
    )


async def _check_store_pool(store: Any) -> bool:
    """Ask psycopg_pool to discard broken idle connections if this Store is pooled."""
    pool = getattr(store, "conn", None)
    if not isinstance(pool, AsyncConnectionPool):
        return False

    await pool.check()
    return True


async def store_with_retry(
    operation: Callable[[Any], Awaitable[_T]],
    *,
    store: Any = None,
    max_retries: int = 1,
    operation_name: str = "store operation",
) -> _T:
    """Execute a store operation with automatic pooled reconnect on connection errors.

    On detected connection error (see is_store_connection_error), ask
    psycopg_pool to discard broken connections before retrying. If ``store`` is
    provided, use it as the runtime-injected Store instead of the module-level
    singleton.
    """
    active_store = store if store is not None else await get_store()
    for attempt in range(max_retries + 1):
        try:
            return await operation(active_store)
        except Exception as e:
            if not is_store_connection_error(e):
                raise
            if attempt >= max_retries:
                logger.error(
                    "%s failed after %d retries: %s",
                    operation_name,
                    max_retries,
                    e,
                )
                raise
            retry_action = (
                "checking singleton store pool" if store is None else "checking runtime store pool"
            )
            try:
                checked_pool = await _check_store_pool(active_store)
            except Exception as pool_error:
                checked_pool = False
                if store is None:
                    await close_store()
                    active_store = await get_store()
                    checked_pool = True
                    retry_action = (
                        f"singleton store pool check failed ({pool_error!s}); "
                        "resetting singleton store"
                    )
                else:
                    retry_action = (
                        f"runtime store pool check failed ({pool_error!s}); retrying same store"
                    )
            if not checked_pool and store is None:
                await close_store()
                active_store = await get_store()
                retry_action = "resetting singleton store"
            logger.warning(
                "%s hit connection error (attempt %d/%d), %s: %s",
                operation_name,
                attempt + 1,
                max_retries + 1,
                retry_action,
                e,
            )
    raise RuntimeError("store_with_retry exited loop unexpectedly")


# 非同期シングルトン用ロック
_store_lock = asyncio.Lock()
_store_lock_loop: asyncio.AbstractEventLoop | None = None

# シングルトンインスタンス
_store_instance: Optional[AsyncPostgresStore] = None
_store_loop: asyncio.AbstractEventLoop | None = None


def _get_store_lock() -> asyncio.Lock:
    """Return a lock bound to the current event loop."""
    global _store_lock, _store_lock_loop

    loop = asyncio.get_running_loop()
    if _store_lock_loop is not loop:
        _store_lock = asyncio.Lock()
        _store_lock_loop = loop
    return _store_lock


async def create_store() -> AsyncPostgresStore:
    """
    AsyncPostgresStoreを作成（Supabase PostgreSQL使用）

    環境変数 SUPABASE_DB_URI から PostgreSQL 接続文字列を取得し、
    LangGraph の AsyncPostgresStore を初期化します。

    Returns:
        AsyncPostgresStore: LangGraph Store インスタンス

    Raises:
        ValueError: SUPABASE_DB_URI が設定されていない場合
        ConnectionError: データベース接続に失敗した場合
    """
    db_uri = os.getenv("SUPABASE_DB_URI")
    if not db_uri:
        raise ValueError(
            "SUPABASE_DB_URI environment variable is not set. "
            "Please set it to your Supabase PostgreSQL connection string."
        )

    db_uri_with_keepalive = add_tcp_keepalive_params(db_uri)

    logger.info("Creating pooled AsyncPostgresStore")
    pool = AsyncConnectionPool(
        conninfo=db_uri_with_keepalive,
        min_size=_POOL_MIN_SIZE,
        max_size=_POOL_MAX_SIZE,
        max_idle=_POOL_MAX_IDLE_SECONDS,
        timeout=_POOL_TIMEOUT_SECONDS,
        check=AsyncConnectionPool.check_connection,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=False,
    )
    try:
        await pool.open()
        store = AsyncPostgresStore(conn=cast(Any, pool))
        await store.setup()
        logger.info("Pooled AsyncPostgresStore created and initialized successfully")
        return store
    except Exception as e:
        await pool.close()
        logger.exception("Failed to create pooled AsyncPostgresStore: %s", e)
        raise ConnectionError(f"Failed to connect to Supabase PostgreSQL for Store: {e}") from e


async def get_store() -> AsyncPostgresStore:
    """
    Storeのシングルトンインスタンスを取得（スレッドセーフ）

    Returns:
        AsyncPostgresStore: Store のシングルトンインスタンス
    """
    global _store_instance, _store_loop
    loop = asyncio.get_running_loop()
    if _store_instance is not None and _store_loop is not loop:
        logger.warning("Store event loop changed; recreating singleton instance")
        _store_instance = None
        _store_loop = None

    if _store_instance is None:
        async with _get_store_lock():
            loop = asyncio.get_running_loop()
            if _store_instance is not None and _store_loop is not loop:
                logger.warning("Store event loop changed while waiting; recreating")
                _store_instance = None
                _store_loop = None
            if _store_instance is None:
                _store_instance = await create_store()
                _store_loop = loop
                logger.info("Store singleton instance created")
    return _store_instance


async def close_store() -> None:
    """
    シングルトンStoreをクローズ

    アプリケーション終了時に呼び出して、接続をクリーンアップします。
    """
    global _store_instance, _store_loop
    if _store_instance is not None:
        try:
            await _store_instance.__aexit__(None, None, None)
            pool = getattr(_store_instance, "conn", None)
            if isinstance(pool, AsyncConnectionPool):
                await pool.close()
            logger.info("Store singleton pool closed")
        except asyncio.CancelledError as e:
            logger.warning(
                "Store singleton close was cancelled; dropping cached instance: %s",
                e,
            )
        except Exception as e:
            logger.warning("Error closing store: %s", e, exc_info=True)
        finally:
            _store_instance = None
            _store_loop = None


async def reset_store() -> None:
    """Storeインスタンスをリセット（テスト用）"""
    await close_store()
