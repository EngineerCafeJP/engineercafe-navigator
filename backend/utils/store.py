"""
LangGraph Store基盤実装

クロスセッションメモリのためのAsyncPostgresStore実装。
Supabase PostgreSQLを使用して訪問者の長期記憶を永続化する。

参考: https://langchain-ai.github.io/langgraph/concepts/persistence/
"""

import asyncio
import logging
import os
from typing import Awaitable, Callable, Optional, TypeVar

from langgraph.store.postgres.aio import AsyncPostgresStore

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


def is_store_connection_error(error: Exception) -> bool:
    """Return True when the exception indicates a dead/closed Store connection."""
    error_message = str(error).lower()
    return any(indicator in error_message for indicator in _CONNECTION_ERROR_INDICATORS)


_T = TypeVar("_T")


async def store_with_retry(
    operation: Callable[[AsyncPostgresStore], Awaitable[_T]],
    *,
    max_retries: int = 1,
    operation_name: str = "store operation",
) -> _T:
    """Execute a store operation with automatic reconnect on connection errors.

    On detected connection error (see is_store_connection_error), reset the
    module-level store singleton via close_store() + get_store() and retry once.
    """
    store = await get_store()
    for attempt in range(max_retries + 1):
        try:
            return await operation(store)
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
            logger.warning(
                "%s hit connection error (attempt %d/%d), resetting store: %s",
                operation_name,
                attempt + 1,
                max_retries + 1,
                e,
            )
            await close_store()
            store = await get_store()
    raise RuntimeError("store_with_retry exited loop unexpectedly")


# 非同期シングルトン用ロック
_store_lock = asyncio.Lock()

# シングルトンインスタンス
_store_instance: Optional[AsyncPostgresStore] = None

# コンテキストマネージャー参照
_store_cm = None


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
    global _store_cm

    db_uri = os.getenv("SUPABASE_DB_URI")
    if not db_uri:
        raise ValueError(
            "SUPABASE_DB_URI environment variable is not set. "
            "Please set it to your Supabase PostgreSQL connection string."
        )

    logger.info("Creating AsyncPostgresStore")
    try:
        # from_conn_string は @asynccontextmanager でラップされているため、
        # 呼び出すとコンテキストマネージャーが返される。
        # シングルトンパターンのため、コンテキストマネージャーを保持し、__aenter__() で取得する。
        _store_cm = AsyncPostgresStore.from_conn_string(db_uri)
        store = await _store_cm.__aenter__()
        await store.setup()
        logger.info("AsyncPostgresStore created and initialized successfully")
        return store
    except Exception as e:
        logger.exception("Failed to create AsyncPostgresStore: %s", e)
        raise ConnectionError(f"Failed to connect to Supabase PostgreSQL for Store: {e}") from e


async def get_store() -> AsyncPostgresStore:
    """
    Storeのシングルトンインスタンスを取得（スレッドセーフ）

    Returns:
        AsyncPostgresStore: Store のシングルトンインスタンス
    """
    global _store_instance
    if _store_instance is None:
        async with _store_lock:
            if _store_instance is None:
                _store_instance = await create_store()
                logger.info("Store singleton instance created")
    return _store_instance


async def close_store() -> None:
    """
    シングルトンStoreをクローズ

    アプリケーション終了時に呼び出して、接続をクリーンアップします。
    """
    global _store_instance, _store_cm
    if _store_instance is not None:
        try:
            # コンテキストマネージャーの __aexit__() を呼び出してクリーンアップ
            if _store_cm is not None:
                await _store_cm.__aexit__(None, None, None)
            logger.info("Store singleton instance closed")
        except Exception as e:
            logger.warning("Error closing store: %s", e, exc_info=True)
        finally:
            _store_instance = None
            _store_cm = None


async def reset_store() -> None:
    """Storeインスタンスをリセット（テスト用）"""
    await close_store()
