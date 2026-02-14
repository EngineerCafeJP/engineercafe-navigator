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
from typing import Any

from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# ナレッジベースデータ定義
# =============================================================================

KNOWLEDGE_BASE_DATA: list[dict[str, Any]] = [
    # --- 基本情報（誤情報修正） ---
    {
        "title": "エンジニアカフェ 料金情報",
        "content": "エンジニアカフェの利用は完全無料です。登録も不要で、どなたでもご利用いただけます。Wi-Fi、電源、作業スペースなど、すべて無料でご利用いただけます。",
        "category": "pricing",
        "metadata": {"entity": "engineer-cafe", "priority": "high"},
    },
    {
        "title": "エンジニアカフェ 営業時間",
        "content": "エンジニアカフェの営業時間は、火曜日から土曜日の9:00〜22:00です。日曜日は9:00〜20:00です。月曜日は定休日です（祝日の場合は翌平日が休み）。",
        "category": "hours",
        "metadata": {"entity": "engineer-cafe", "priority": "high"},
    },
    {
        "title": "エンジニアカフェ アクセス情報",
        "content": "エンジニアカフェは福岡市中央区天神1-15-30（福岡市赤煉瓦文化館内）にあります。地下鉄天神駅から徒歩5分、西鉄福岡（天神）駅から徒歩7分、天神南駅から徒歩10分です。",
        "category": "access",
        "metadata": {"entity": "engineer-cafe", "priority": "high"},
    },
    {
        "title": "エンジニアカフェ 電話番号",
        "content": "エンジニアカフェの電話番号は 092-986-8026 です。お問い合わせはお気軽にどうぞ。",
        "category": "contact",
        "metadata": {"entity": "engineer-cafe", "priority": "medium"},
    },
    # --- sainoカフェ（誤情報修正） ---
    {
        "title": "sainoカフェ 営業情報",
        "content": "sainoカフェ（サイノカフェ）はエンジニアカフェの1階にあるカフェです。営業時間は11:00〜18:00です。定休日は月曜日と水曜日です。コーヒーや軽食を提供しています。",
        "category": "hours",
        "metadata": {"entity": "saino", "priority": "high"},
    },
    # --- 駐車場・駐輪場（新規） ---
    {
        "title": "エンジニアカフェ 駐車場情報",
        "content": "エンジニアカフェには専用駐車場はありません。近隣のコインパーキングをご利用ください。天神地下街の駐車場や、周辺の有料パーキングが便利です。",
        "category": "parking",
        "metadata": {"entity": "engineer-cafe", "priority": "medium"},
    },
    {
        "title": "エンジニアカフェ 駐輪場情報",
        "content": "エンジニアカフェには専用の駐輪場はありません。周辺の公共駐輪場をご利用ください。天神中央公園の地下駐輪場などが近くにあります。",
        "category": "bicycle",
        "metadata": {"entity": "engineer-cafe", "priority": "medium"},
    },
    # --- 喫煙ポリシー（新規） ---
    {
        "title": "エンジニアカフェ 喫煙ポリシー",
        "content": "エンジニアカフェは全館禁煙です。施設内での喫煙はできません。喫煙される方は、近隣の喫煙所をご利用ください。",
        "category": "smoking",
        "metadata": {"entity": "engineer-cafe", "priority": "medium"},
    },
    # --- 飲食ポリシー（新規） ---
    {
        "title": "エンジニアカフェ 飲食ポリシー",
        "content": "エンジニアカフェでは飲み物の持ち込みは可能です。食べ物については、匂いの強くない軽食であれば持ち込みできます。1階のsainoカフェでドリンクや軽食を購入することもできます。ゴミは各自お持ち帰りください。",
        "category": "food_drink",
        "metadata": {"entity": "engineer-cafe", "priority": "medium"},
    },
    # --- Engineer Cafe Lab / EIC（新規） ---
    {
        "title": "Engineer Cafe Lab（エンジニアカフェラボ）",
        "content": "Engineer Cafe Lab（エンジニアカフェラボ）は、エンジニアカフェの会員制コミュニティプログラムです。月額会員として、専用のワークスペースやイベント優先参加権、コミュニティネットワーキングなどの特典を受けられます。詳細はスタッフにお問い合わせください。",
        "category": "community",
        "metadata": {"entity": "engineer-cafe", "priority": "medium"},
    },
    {
        "title": "EIC（Engineer in Cafe）",
        "content": "EIC（Engineer in Cafe）は、エンジニアカフェの常駐エンジニアプログラムです。経験豊富なエンジニアがカフェに常駐し、技術的な相談やキャリア相談、スキルチェンジの支援を無料で行っています。相談は予約不要で、気軽に話しかけてください。",
        "category": "consultation",
        "metadata": {"entity": "engineer-cafe", "priority": "medium"},
    },
    # --- 地下施設情報 ---
    {
        "title": "エンジニアカフェ 地下スペース",
        "content": "エンジニアカフェの地下（B1）には、MTGスペース（会議用）、集中スペース（静かな作業用）、Makersスペース（ものづくり用）があります。利用は無料ですが、一部スペースは予約が必要な場合があります。",
        "category": "facility-info",
        "metadata": {"entity": "engineer-cafe", "priority": "high"},
    },
]


async def generate_embedding_for_seed(text: str) -> list[float]:
    """embedding生成（共通サービスに委譲）

    Args:
        text: エンベディング対象のテキスト

    Returns:
        1536次元のembeddingベクトル
    """
    from utils.embedding_service import generate_embedding

    result = await generate_embedding(text)
    if not result:
        raise Exception("Embedding generation failed (check OPENROUTER_API_KEY)")
    logger.info(f"Generated embedding: {len(result)} dimensions")
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
            logger.info(f"Processing: {title}")

            # Embedding生成
            embedding = await generate_embedding_for_seed(f"{title}\n{content}")

            # Upsert（titleで重複排除）
            upsert_data = {
                "title": title,
                "content": content,
                "category": category,
                "metadata": metadata,
                "content_embedding": embedding,
            }

            supabase.table("knowledge_base").upsert(
                upsert_data,
                on_conflict="title",
            ).execute()

            logger.info(f"  ✓ Upserted: {title}")
            success_count += 1

        except Exception as e:
            logger.error(f"  ✗ Failed: {title} - {e}")
            error_count += 1

    logger.info(f"\nSeed complete: {success_count} success, {error_count} errors")


if __name__ == "__main__":
    asyncio.run(seed_knowledge_base())
