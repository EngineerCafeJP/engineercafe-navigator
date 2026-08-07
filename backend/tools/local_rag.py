"""
ローカルpgvectorベクトル検索ヘルパー

RAG_VECTOR_BACKEND=local-pgvector のとき、Supabase RPCの代わりに
ローカルPostgreSQL (pgvector) に対してコサイン類似度検索を実行する。

COSCUPデモ用途: docker-compose の postgres (pgvector/pgvector:pg16) と
ホスト上のOllama embeddings のみで完全オフライン動作する。
エラー時は空リストを返し、呼び出し側（EnhancedRAGSearch.search）の
既存フォールバック（_fallback_search_response）へ委ねる。
"""

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

# プール設定（遅延オープン + 上限2接続 + 5秒タイムアウト）
_POOL_MIN_SIZE = 0
_POOL_MAX_SIZE = 2
_CONNECT_TIMEOUT_SECONDS = 5
_QUERY_TIMEOUT_SECONDS = 5

_LOCAL_SEARCH_FUNCTION = "search_knowledge_base_local"


def _pool_check_callback() -> Callable[[Any], Awaitable[None]]:
    """psycopg_poolの接続ヘルスチェックコールバックを取得する。

    psycopg_pool 3.2+ では組み込みの check_connection を使い、
    それ以前のバージョンでは SELECT 1 によるヘルスチェックへフォールバックする。
    """
    check_connection = getattr(AsyncConnectionPool, "check_connection", None)
    if callable(check_connection):
        return check_connection

    async def _health_check(conn: Any) -> None:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")

    return _health_check


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """DB行をフォールバック行と同じ行コントラクトへ正規化する。

    Supabase RPC / YAMLフォールバックと同一のキー
    (id, title, content, category, subcategory, language, source, metadata, similarity)
    を返す。metadata には entity/tags/priority/verified/local_fallback を補完する。
    """
    metadata = dict(row.get("metadata") or {})
    source = metadata.pop("source", None) or "official-yaml"
    metadata.setdefault("entity", "general")
    metadata.setdefault("tags", [])
    metadata.setdefault("priority", 50)
    metadata.setdefault("verified", False)
    metadata.setdefault("local_fallback", True)
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "content": row.get("content"),
        "category": row.get("category"),
        "subcategory": row.get("subcategory"),
        "language": row.get("language"),
        "source": source,
        "metadata": metadata,
        "similarity": float(row.get("similarity") or 0.0),
    }


async def local_pgvector_search(
    embedding: List[float],
    similarity_threshold: float,
    match_count: int,
    db_uri: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """ローカルpgvectorに対してコサイン類似度ベクトル検索を実行する。

    Args:
        embedding: クエリのembeddingベクトル
        similarity_threshold: 類似度閾値
        match_count: 最大取得件数
        db_uri: PostgreSQL接続URI（未指定時は SUPABASE_DB_URI 環境変数を使用。
            demo compose ではローカルpostgresを指す）

    Returns:
        正規化された検索結果のリスト。
        接続エラー・テーブル未存在・検索結果ゼロの場合は空リスト。
    """
    db_uri = db_uri or os.getenv("SUPABASE_DB_URI", "")
    if not db_uri:
        logger.warning("SUPABASE_DB_URI not set, skipping local pgvector search")
        return []

    pool = AsyncConnectionPool(
        conninfo=db_uri,
        open=False,
        min_size=_POOL_MIN_SIZE,
        max_size=_POOL_MAX_SIZE,
        check=_pool_check_callback(),
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "connect_timeout": _CONNECT_TIMEOUT_SECONDS,
        },
    )
    try:
        await asyncio.wait_for(pool.open(), timeout=_QUERY_TIMEOUT_SECONDS)
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await asyncio.wait_for(
                    cur.execute(
                        "SELECT * FROM search_knowledge_base_local(%s::vector, %s, %s)",
                        (embedding, similarity_threshold, match_count),
                    ),
                    timeout=_QUERY_TIMEOUT_SECONDS,
                )
                rows = await cur.fetchall()
        logger.info("Local pgvector search returned %d rows", len(rows))
        return [_normalize_row(row) for row in rows]
    except Exception as e:
        logger.error("Local pgvector search failed: %s", e)
        return []
    finally:
        try:
            await pool.close()
        except Exception as close_error:
            logger.warning("Error closing local pgvector pool: %s", close_error)
