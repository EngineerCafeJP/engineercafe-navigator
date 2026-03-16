"""
Checkpointer utilities for LangGraph persistence.

Uses a small psycopg async pool so Cloud Run cold starts do not keep serving
through stale PostgreSQL connections after idle scale-to-zero periods.
"""

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional, TypeVar, cast

from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    RunnableConfig,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, InterfaceError, OperationalError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolClosed

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

_POOL_MIN_SIZE = 0
_POOL_MAX_SIZE = 5
_POOL_MAX_IDLE_SECONDS = 300
_CONNECT_TIMEOUT_SECONDS = 10
_KEEPALIVES_IDLE_SECONDS = 30

_CONNECTION_ERROR_MESSAGES = (
    "connection is closed",
    "connection closed",
    "pool is closed",
    "server closed the connection unexpectedly",
    "terminating connection",
    "broken pipe",
    "ssl connection has been closed unexpectedly",
    "consuming input failed",
)

# Non-async types in tests still expect these module globals to exist.
_checkpointer_lock = asyncio.Lock()
_checkpointer_cm = None
_checkpointer_instance: Optional[AsyncPostgresSaver] = None


def _mask_connection_string(db_uri: str) -> str:
    """Mask credentials in a PostgreSQL connection string for logs."""
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1****\2", db_uri)


def is_checkpointer_connection_error(error: Exception) -> bool:
    """Return True when the exception indicates a dead/closed DB connection."""
    if isinstance(error, (OperationalError, InterfaceError, PoolClosed)):
        return True

    error_message = str(error).lower()
    return any(message in error_message for message in _CONNECTION_ERROR_MESSAGES)


async def _health_check_connection(conn: AsyncConnection[Any]) -> None:
    """Fallback pool health check for psycopg versions without check_connection."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT 1")


def _pool_check_callback() -> Callable[[AsyncConnection[Any]], Awaitable[None]]:
    callback = getattr(AsyncConnectionPool, "check_connection", None)
    if callable(callback):
        return cast(Callable[[AsyncConnection[Any]], Awaitable[None]], callback)
    return _health_check_connection


@dataclass(frozen=True)
class _CheckpointerFactory:
    """Factory for creating and re-creating resilient checkpointers."""

    db_uri: str

    @classmethod
    def from_env(cls) -> "_CheckpointerFactory":
        db_uri = os.getenv("SUPABASE_DB_URI")
        if not db_uri:
            error_msg = (
                "SUPABASE_DB_URI environment variable is not set. "
                "Please set it to your Supabase PostgreSQL connection string."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        return cls(db_uri=db_uri)

    async def create_pool(self) -> AsyncConnectionPool:
        pool = AsyncConnectionPool(
            conninfo=self.db_uri,
            open=False,
            min_size=_POOL_MIN_SIZE,
            max_size=_POOL_MAX_SIZE,
            max_idle=_POOL_MAX_IDLE_SECONDS,
            check=_pool_check_callback(),
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
                "connect_timeout": _CONNECT_TIMEOUT_SECONDS,
                "keepalives": 1,
                "keepalives_idle": _KEEPALIVES_IDLE_SECONDS,
            },
        )
        await pool.open()
        return pool

    async def create_checkpointer(self) -> "ResilientAsyncPostgresSaver":
        pool = await self.create_pool()
        saver = ResilientAsyncPostgresSaver(factory=self, pool=pool)
        await saver.setup()
        return saver

    async def prewarm_pool(self, pool: AsyncConnectionPool) -> None:
        async with pool.connection() as conn:
            await _pool_check_callback()(conn)


class ResilientAsyncPostgresSaver(AsyncPostgresSaver):
    """AsyncPostgresSaver that can replace its own pool after connection loss."""

    def __init__(self, factory: _CheckpointerFactory, pool: AsyncConnectionPool) -> None:
        super().__init__(conn=pool)
        self._factory = factory
        self._pool_refresh_lock = asyncio.Lock()

    @property
    def pool(self) -> AsyncConnectionPool:
        return cast(AsyncConnectionPool, self.conn)

    async def prewarm(self) -> None:
        await self._factory.prewarm_pool(self.pool)

    async def recreate(self, reason: Exception | None = None) -> None:
        async with self._pool_refresh_lock:
            previous_pool = self.pool
            new_pool = await self._factory.create_pool()
            try:
                await self._factory.prewarm_pool(new_pool)
            except Exception:
                await new_pool.close()
                raise

            async with self.lock:
                self.conn = new_pool

            try:
                await previous_pool.close()
            except Exception as close_error:
                logger.warning(
                    "Error closing previous checkpointer pool: %s",
                    close_error,
                    exc_info=True,
                )

            if reason is None:
                logger.info("Recreated checkpointer connection pool")
            else:
                logger.warning(
                    "Recreated checkpointer connection pool after failure: %s",
                    reason,
                )

    async def aclose(self) -> None:
        await self.pool.close()

    async def _run_with_connection_retry(
        self,
        operation_name: str,
        operation: Callable[..., Awaitable[_T]],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        try:
            return await operation(*args, **kwargs)
        except Exception as error:
            if not is_checkpointer_connection_error(error):
                raise

            logger.warning(
                "Checkpointer %s failed because the PostgreSQL connection is stale. "
                "Recreating the pool and retrying once.",
                operation_name,
                exc_info=True,
            )
            await self.recreate(reason=error)
            return await operation(*args, **kwargs)

    async def aget_tuple(self, config: RunnableConfig) -> Any:
        return await self._run_with_connection_retry("aget_tuple", super().aget_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Any:
        return await self._run_with_connection_retry(
            "alist",
            super().alist,
            config,
            filter=filter,
            before=before,
            limit=limit,
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await self._run_with_connection_retry(
            "aput",
            super().aput,
            config,
            checkpoint,
            metadata,
            new_versions,
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self._run_with_connection_retry(
            "aput_writes",
            super().aput_writes,
            config,
            writes,
            task_id,
            task_path,
        )

    async def adelete_thread(self, thread_id: str) -> None:
        await self._run_with_connection_retry("adelete_thread", super().adelete_thread, thread_id)


async def create_checkpointer() -> AsyncPostgresSaver:
    """
    Create an AsyncPostgresSaver backed by a resilient AsyncConnectionPool.

    Returns:
        AsyncPostgresSaver: LangGraph checkpointer instance
    """
    factory = _CheckpointerFactory.from_env()
    logger.info(
        "Creating AsyncPostgresSaver with pooled connection: %s",
        _mask_connection_string(factory.db_uri),
    )

    try:
        checkpointer = await factory.create_checkpointer()
        logger.info("AsyncPostgresSaver created and initialized successfully")
        return checkpointer
    except Exception as error:
        logger.exception("Failed to create AsyncPostgresSaver: %s", error)
        raise ConnectionError(f"Failed to connect to Supabase PostgreSQL: {error}") from error


@asynccontextmanager
async def get_checkpointer_context() -> AsyncGenerator[AsyncPostgresSaver, None]:
    """Yield a one-off resilient checkpointer and close its pool afterwards."""
    checkpointer = await create_checkpointer()
    try:
        logger.info("AsyncPostgresSaver context created successfully")
        yield checkpointer
    finally:
        aclose = getattr(checkpointer, "aclose", None)
        if callable(aclose):
            await aclose()


async def create_memory_checkpointer() -> AsyncPostgresSaver:
    """Create the memory-specific checkpointer instance."""
    logger.info("Creating memory-specific checkpointer")
    return await create_checkpointer()


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return the process-wide resilient checkpointer singleton."""
    global _checkpointer_instance

    if _checkpointer_instance is None:
        async with _checkpointer_lock:
            if _checkpointer_instance is None:
                _checkpointer_instance = await create_checkpointer()
                logger.info("Checkpointer singleton instance created")

    return _checkpointer_instance


async def prewarm_checkpointer() -> AsyncPostgresSaver:
    """Open and validate a pooled connection during application startup."""
    checkpointer = await get_checkpointer()
    prewarm = getattr(checkpointer, "prewarm", None)
    if callable(prewarm):
        await prewarm()
        logger.info("Checkpointer connection pool pre-warmed")
    return checkpointer


async def close_checkpointer() -> None:
    """Close the singleton checkpointer and drop the cached instance."""
    global _checkpointer_instance, _checkpointer_cm

    if _checkpointer_instance is None:
        return

    try:
        aclose = getattr(_checkpointer_instance, "aclose", None)
        if callable(aclose):
            await aclose()
        logger.info("Checkpointer singleton instance closed")
    except Exception as error:
        logger.warning("Error closing checkpointer: %s", error, exc_info=True)
    finally:
        _checkpointer_instance = None
        _checkpointer_cm = None


async def reset_checkpointer() -> None:
    """Reset the singleton checkpointer instance for tests."""
    await close_checkpointer()
