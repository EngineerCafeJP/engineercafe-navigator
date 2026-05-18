"""
ナレッジベースシードスクリプト

OpenRouter API経由でembeddingを生成し、Supabaseのknowledge_baseテーブルに
正確な情報をupsertする。

Usage:
    cd backend
    uv run python -m scripts.seed_knowledge

環境変数:
    OPENROUTER_API_KEY: OpenRouter APIキー
    SUPABASE_URL: Supabase URL
    SUPABASE_KEY: Supabase サービスロールキー
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

# .env.local → .env の順で環境変数をロード
_env_local = Path(__file__).resolve().parent.parent / ".env.local"
_env = Path(__file__).resolve().parent.parent / ".env"
if _env_local.exists():
    load_dotenv(_env_local)
elif _env.exists():
    load_dotenv(_env)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

try:
    from backend.scripts.seed_knowledge_data import KNOWLEDGE_BASE_DATA
except ImportError:  # pragma: no cover - supports `python -m scripts...` from backend/
    from scripts.seed_knowledge_data import KNOWLEDGE_BASE_DATA


async def generate_embedding_for_seed(text: str) -> list[float]:
    """embedding生成（共通サービスに委譲）

    Args:
        text: エンベディング対象のテキスト

    Returns:
        1536次元のembeddingベクトル
    """
    from backend.utils.embedding_service import generate_embedding

    result = await generate_embedding(text)
    if not result:
        raise Exception("Embedding generation failed (check OPENROUTER_API_KEY)")
    logger.info("Generated embedding: %d dimensions", len(result))
    return result


async def seed_knowledge_base() -> None:
    """ナレッジベースにデータをシードする"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not api_key:
        logger.error("OPENROUTER_API_KEY is not set")
        sys.exit(1)
    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL or SUPABASE_KEY is not set")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    success_count = 0
    error_count = 0

    for item in KNOWLEDGE_BASE_DATA:
        title = item["title"]
        content = item["content"]
        category = item["category"]
        metadata = item.get("metadata", {})

        try:
            logger.info("Processing: %s", title)

            # Embedding生成
            embedding = await generate_embedding_for_seed(f"{title}\n{content}")

            # Upsert（titleで重複排除）
            upsert_data = {
                "title": title,
                "content": content,
                "category": category,
                "metadata": metadata,
                "content_embedding": embedding,
                "chunk_level": "document",
                "chunk_index": 0,
            }

            supabase.table("knowledge_base").upsert(
                upsert_data,
                on_conflict="title",
            ).execute()

            logger.info("  ✓ Upserted: %s", title)
            success_count += 1

        except Exception as e:
            logger.error("  ✗ Failed: %s - %s", title, e)
            error_count += 1

    logger.info("\nSeed complete: %d success, %d errors", success_count, error_count)


async def seed_from_yaml_files() -> None:
    """YAML ファイルベースのシーディング（新方式）

    backend/knowledge/data/*.yaml を読み込み、Hierarchical チャンキング +
    embedding 生成 → Supabase upsert を行う。
    """
    from backend.knowledge.loader import SeedResult, seed_from_yaml

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

    supabase = create_client(supabase_url, supabase_key)
    data_dir = Path(__file__).resolve().parent.parent / "knowledge" / "data"

    logger.info("Starting YAML-based seed from: %s", data_dir)
    result: SeedResult = await seed_from_yaml(supabase, data_dir)

    logger.info(
        "YAML seed complete: success=%d, errors=%d, total_chunks=%d, skipped=%d",
        result.success_count,
        result.error_count,
        result.total_chunks,
        result.skipped_count,
    )
    if result.error_count > 0:
        raise RuntimeError(f"YAML seed completed with {result.error_count} errors")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed knowledge base")
    parser.add_argument(
        "--yaml",
        action="store_true",
        help="Use YAML-based seeding (new method with hierarchical chunking)",
    )
    args = parser.parse_args()

    if args.yaml:
        asyncio.run(seed_from_yaml_files())
    else:
        asyncio.run(seed_knowledge_base())
