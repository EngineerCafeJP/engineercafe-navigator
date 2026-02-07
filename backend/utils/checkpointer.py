"""
Checkpointer基盤実装

LangGraphの永続化機能を有効化するための AsyncPostgresSaver 実装。
Supabase PostgreSQL を使用した langgraph-checkpoint-postgres 統合。

参考: https://langchain-ai.github.io/langgraph/concepts/persistence/
"""

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

# 非同期シングルトン用ロック
_checkpointer_lock = asyncio.Lock()


def _mask_connection_string(db_uri: str) -> str:
    """
    接続文字列から認証情報を安全にマスク

    Args:
        db_uri: PostgreSQL接続文字列

    Returns:
        パスワードがマスクされた接続文字列
    """
    # パスワード部分をマスク: postgresql://user:password@host -> postgresql://user:****@host
    masked = re.sub(r"(://[^:]+:)[^@]+(@)", r"\1****\2", db_uri)
    return masked


async def create_checkpointer() -> AsyncPostgresSaver:
    """
    AsyncPostgresSaverを作成（Supabase PostgreSQL使用）

    環境変数 SUPABASE_DB_URI から PostgreSQL 接続文字列を取得し、
    langgraph-checkpoint-postgres の AsyncPostgresSaver を初期化します。

    環境変数:
        SUPABASE_DB_URI: PostgreSQL接続文字列
            例: postgresql://user:password@host:port/database

    Returns:
        AsyncPostgresSaver: LangGraph用のCheckpointerインスタンス

    Raises:
        ValueError: SUPABASE_DB_URI が設定されていない場合
        ConnectionError: データベース接続に失敗した場合

    Example:
        >>> checkpointer = await create_checkpointer()
        >>> # LangGraph workflow で使用
        >>> workflow = StateGraph(WorkflowState).compile(checkpointer=checkpointer)
    """
    db_uri = os.getenv("SUPABASE_DB_URI")

    if not db_uri:
        error_msg = (
            "SUPABASE_DB_URI environment variable is not set. "
            "Please set it to your Supabase PostgreSQL connection string."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 接続文字列をマスクしてログ出力（パスワード漏洩防止）
    masked_uri = _mask_connection_string(db_uri)
    logger.info(f"Creating AsyncPostgresSaver with connection: {masked_uri}")

    try:
        checkpointer = await AsyncPostgresSaver.from_conn_string(db_uri)
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver created and initialized successfully")
        return checkpointer
    except Exception as e:
        logger.error(f"Failed to create AsyncPostgresSaver: {e}")
        raise ConnectionError(f"Failed to connect to Supabase PostgreSQL: {e}") from e


@asynccontextmanager
async def get_checkpointer_context() -> AsyncGenerator[AsyncPostgresSaver, None]:
    """
    Checkpointerのコンテキストマネージャー

    async with文で使用することで、接続の自動クリーンアップを保証します。

    Yields:
        AsyncPostgresSaver: Checkpointerインスタンス

    Example:
        >>> async with get_checkpointer_context() as checkpointer:
        ...     graph = builder.compile(checkpointer=checkpointer)
        ...     result = await graph.ainvoke(input_data)
    """
    db_uri = os.getenv("SUPABASE_DB_URI")

    if not db_uri:
        error_msg = (
            "SUPABASE_DB_URI environment variable is not set. "
            "Please set it to your Supabase PostgreSQL connection string."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver context created successfully")
        yield checkpointer


async def create_memory_checkpointer() -> AsyncPostgresSaver:
    """
    メモリ専用のCheckpointerを作成

    メモリエージェント用に最適化されたCheckpointerインスタンスを作成します。
    現在は通常のCheckpointerと同じ実装ですが、将来的に異なる設定を適用可能。

    Returns:
        AsyncPostgresSaver: メモリエージェント用のCheckpointerインスタンス
    """
    logger.info("Creating memory-specific checkpointer")
    return await create_checkpointer()


# シングルトンインスタンス
_checkpointer_instance: Optional[AsyncPostgresSaver] = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """
    Checkpointerのシングルトンインスタンスを取得（スレッドセーフ）

    アプリケーション全体で単一のCheckpointerインスタンスを共有します。
    複数のワークフローで同じCheckpointerを使用する場合に便利。
    asyncio.Lockを使用してrace conditionを防止。

    Returns:
        AsyncPostgresSaver: Checkpointerのシングルトンインスタンス

    Example:
        >>> checkpointer = await get_checkpointer()
        >>> workflow1 = StateGraph(State1).compile(checkpointer=checkpointer)
        >>> workflow2 = StateGraph(State2).compile(checkpointer=checkpointer)
    """
    global _checkpointer_instance
    if _checkpointer_instance is None:
        async with _checkpointer_lock:
            # Double-check after acquiring lock
            if _checkpointer_instance is None:
                _checkpointer_instance = await create_checkpointer()
                logger.info("Checkpointer singleton instance created")
    return _checkpointer_instance


async def close_checkpointer() -> None:
    """
    シングルトンCheckpointerをクローズ

    アプリケーション終了時に呼び出して、接続をクリーンアップします。
    """
    global _checkpointer_instance
    if _checkpointer_instance is not None:
        try:
            # AsyncPostgresSaverの適切なクローズメソッドを使用
            if hasattr(_checkpointer_instance, "aclose"):
                await _checkpointer_instance.aclose()
            elif hasattr(_checkpointer_instance, "conn") and hasattr(
                _checkpointer_instance.conn, "close"
            ):
                await _checkpointer_instance.conn.close()
            logger.info("Checkpointer singleton instance closed")
        except Exception as e:
            logger.warning(f"Error closing checkpointer: {e}")
        finally:
            _checkpointer_instance = None


async def reset_checkpointer() -> None:
    """
    Checkpointerインスタンスをリセット（テスト用）

    既存の接続を適切にクローズしてからリセットします。
    """
    await close_checkpointer()
