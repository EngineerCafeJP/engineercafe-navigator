"""
ローカルpgvectorナレッジシードスクリプト（COSCUPデモ用・完全オフライン）

backend/knowledge/data/*.yaml の公式ナレッジを読み込み、OllamaのOpenAI互換
/v1/embeddings でembeddingを生成し、ローカルPostgreSQL (pgvector) の
knowledge_embeddings テーブルへupsertする。

注意:
    - ローカルのcompose postgres (pgvector/pgvector:pg16) に対して実行すること。
    - 外部APIに一切依存しない（Ollama embeddings + ローカルPostgreSQLのみで動作）。
    - embedding次元数は EMBEDDING_DIMENSIONS（デフォルト1536）と
      scripts/sql/local_rag_schema.sql の vector(1536) が一致している必要がある。

Usage:
    cd backend
    EMBEDDING_API_URL=http://host.docker.internal:11434/v1/embeddings \\
    EMBEDDING_MODEL=nomic-embed-text \\
    EMBEDDING_DIMENSIONS=768 \\
    EMBEDDING_API_KEY=ollama \\
    .venv/bin/python -m scripts.seed_local_knowledge

環境変数:
    SUPABASE_DB_URI: ローカルPostgreSQL接続URI（docker-compose の postgres を指す）
    EMBEDDING_API_URL: Ollama OpenAI互換エンドポイント
    EMBEDDING_MODEL: embeddingモデル名
    EMBEDDING_DIMENSIONS: embedding次元数
    EMBEDDING_API_KEY: Ollama用ダミーキー（未設定時はOPENROUTER_API_KEYへフォールバック）
"""

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from backend.tools.enhanced_rag_fallbacks import RAGFallbackMixin
from backend.utils.embedding_service import (
    EMBEDDING_DIMENSIONS,
    generate_embedding,
)

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "local_rag_schema.sql"
_DATA_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "data"

# 言語ごとのembedding対象: (language, contentキー, titleキー)
_LANGUAGE_KEYS = (
    ("ja", "content", "title"),
    ("en", "content_en", "title_en"),
)

_UPSERT_SQL = """
INSERT INTO knowledge_embeddings
    (id, title, content, category, subcategory, language, metadata, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)
ON CONFLICT (id, language) DO UPDATE SET
    title = EXCLUDED.title,
    content = EXCLUDED.content,
    category = EXCLUDED.category,
    subcategory = EXCLUDED.subcategory,
    metadata = EXCLUDED.metadata,
    embedding = EXCLUDED.embedding
"""


def load_schema_sql(dimensions: int = EMBEDDING_DIMENSIONS) -> str:
    """local_rag_schema.sql を読み込み、embedding次元数を差し替えて返す。

    Args:
        dimensions: シード時のembedding次元数

    Returns:
        実行可能なスキーマSQL文字列
    """
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    if dimensions != EMBEDDING_DIMENSIONS:
        sql = sql.replace(f"vector({EMBEDDING_DIMENSIONS})", f"vector({dimensions})")
    return sql


def load_yaml_entries(path: Path) -> List[Dict[str, Any]]:
    """YAMLファイルから entries リストを読み込む。

    Args:
        path: YAMLファイルパス

    Returns:
        entries リスト（ファイルが空の場合は空リスト）
    """
    with open(path, encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    return payload.get("entries", [])


async def build_rows(
    entries: List[Dict[str, Any]],
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> List[Dict[str, Any]]:
    """YAMLエントリをknowledge_embeddings用の行へ変換する。

    各エントリの content（ja）と content_en（en）をそれぞれembeddingし、
    言語タグ付きの行を生成する。contentが無いエントリはスキップする。

    Args:
        entries: YAMLの entries リスト
        dimensions: embedding次元数（不一致行はスキップ）

    Returns:
        upsert用の行リスト（id, title, content, category, subcategory,
        language, metadata, embedding）
    """
    rows: List[Dict[str, Any]] = []
    for entry in entries:
        entry_id = entry.get("id")
        if not entry.get("content"):
            logger.warning("Skipping entry without content: %s", entry_id)
            continue

        # 公式YAMLフォールバックと同じエンティティ推論を使う
        entity = RAGFallbackMixin._infer_entity_from_yaml_entry(entry)

        for language, content_key, title_key in _LANGUAGE_KEYS:
            content = entry.get(content_key)
            if not content:
                continue
            embedding = await generate_embedding(content)
            if not embedding or len(embedding) != dimensions:
                logger.warning(
                    "Skipping %s/%s: embedding failed or dimension mismatch",
                    entry_id,
                    language,
                )
                continue

            metadata = {
                "entity": entity,
                "tags": entry.get("tags", []),
                "priority": entry.get("priority", 50),
                "verified": entry.get("verified", False),
                "source": entry.get("source") or "official-yaml",
            }
            rows.append(
                {
                    "id": entry_id,
                    "title": entry.get(title_key) or entry.get("title") or "",
                    "content": content,
                    "category": entry.get("category", "general"),
                    "subcategory": entry.get("subcategory"),
                    "language": language,
                    "metadata": metadata,
                    "embedding": embedding,
                }
            )
    return rows


async def apply_schema(db_uri: str, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
    """local_rag_schema.sql を実行してスキーマを作成する。

    Args:
        db_uri: PostgreSQL接続URI
        dimensions: embedding次元数（vector(N)のNを差し替える）
    """
    schema_sql = load_schema_sql(dimensions)
    async with await AsyncConnection.connect(db_uri, autocommit=True) as conn:
        await conn.execute(schema_sql)
    logger.info("Applied local RAG schema (dimensions=%d)", dimensions)


async def upsert_rows(db_uri: str, rows: List[Dict[str, Any]]) -> None:
    """knowledge_embeddings へ行をupsertする。

    Args:
        db_uri: PostgreSQL接続URI
        rows: build_rows() が返した行リスト
    """
    async with await AsyncConnection.connect(db_uri, autocommit=True) as conn:
        async with conn.cursor() as cur:
            for row in rows:
                await cur.execute(
                    _UPSERT_SQL,
                    (
                        row["id"],
                        row["title"],
                        row["content"],
                        row["category"],
                        row["subcategory"],
                        row["language"],
                        Jsonb(row["metadata"]),
                        row["embedding"],
                    ),
                )


async def seed_from_yaml_files(
    data_dir: Path,
    db_uri: str,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> int:
    """YAMLナレッジをシードし、ファイルごとの行数をログ出力する。

    Args:
        data_dir: YAMLファイルが置かれたディレクトリ
        db_uri: PostgreSQL接続URI
        dimensions: embedding次元数

    Returns:
        シードした行数の合計
    """
    await apply_schema(db_uri, dimensions)

    total = 0
    for path in sorted(data_dir.glob("*.yaml")):
        entries = load_yaml_entries(path)
        rows = await build_rows(entries, dimensions)
        if rows:
            await upsert_rows(db_uri, rows)
        logger.info("%s: %d rows", path.name, len(rows))
        total += len(rows)
    logger.info("Seed complete: %d rows total", total)
    return total


async def main(uri: str, dimensions: int) -> int:
    """CLIエントリポイント。

    Args:
        uri: PostgreSQL接続URI
        dimensions: embedding次元数

    Returns:
        シードした行数の合計
    """
    return await seed_from_yaml_files(
        data_dir=_DATA_DIR,
        db_uri=uri,
        dimensions=dimensions,
    )


def _parse_args() -> argparse.Namespace:
    """CLI引数をパースする。"""
    parser = argparse.ArgumentParser(
        description="ローカルpgvectorへ公式YAMLナレッジをシード（COSCUPデモ用・完全オフライン）"
    )
    parser.add_argument(
        "--uri",
        default=os.getenv("SUPABASE_DB_URI", ""),
        help="PostgreSQL接続URI（デフォルト: SUPABASE_DB_URI 環境変数）",
    )
    parser.add_argument(
        "--dims",
        type=int,
        default=None,
        help="embedding次元数（デフォルト: EMBEDDING_DIMENSIONS 環境変数、未設定時は 1536）",
    )
    args = parser.parse_args()
    if not args.uri:
        parser.error("SUPABASE_DB_URI is not set (use --uri to specify it)")
    if args.dims is None:
        args.dims = int(os.getenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS)))
    return args


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parsed = _parse_args()
    asyncio.run(main(uri=parsed.uri, dimensions=parsed.dims))
