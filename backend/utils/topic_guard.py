"""
トピック遵守ガードレール

エンジニアカフェの業務範囲内のクエリかを軽量判定する。
LLM呼び出しなしでキーワード + カテゴリベースで判定。
"""

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

# エンジニアカフェの業務範囲内カテゴリ
ON_TOPIC_CATEGORIES: set[str] = {
    "business_info",
    "facility",
    "event",
    "slide",
    "general_knowledge",
    "assistant_profile",
    "daily_conversation",
    "general_light",
    "current_info",
    "consultation",
    "community",
    "career",
    "pricing",
    "hours",
    "access",
    "location",
    "cafe-clarification-needed",
    "meeting-room-clarification-needed",
    "general-clarification-needed",
}

# 明確にドメイン外のキーワード（日本語 + 英語）
OFF_TOPIC_KEYWORDS: list[str] = [
    "政治",
    "選挙",
    "政党",
    "天気",
    "天候",
    "気温",
    "レシピ",
    "料理",
    "作り方",
    "スポーツ",
    "サッカー",
    "野球",
    "バスケ",
    "株価",
    "仮想通貨",
    "ビットコイン",
    "FX",
    "ギャンブル",
    "賭け",
    "パチンコ",
    "宗教",
    "占い",
    "星座",
    "芸能",
    "ゴシップ",
    "恋愛相談",
    "ダイエット",
    "politics",
    "election",
    "weather",
    "forecast",
    "recipe",
    "cooking",
    "sports",
    "football",
    "baseball",
    "basketball",
    "stock market",
    "cryptocurrency",
    "bitcoin",
    "gambling",
    "religion",
    "horoscope",
    "gossip",
    "dating advice",
    "diet",
]

# off-topicキーワードを正規表現にコンパイル（高速マッチング）
_OFF_TOPIC_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in OFF_TOPIC_KEYWORDS),
    re.IGNORECASE,
)


def is_on_topic(query: str, routing_category: str = "") -> bool:
    """
    クエリがエンジニアカフェの業務範囲内かを判定する。

    判定ロジック:
    1. ルーティングカテゴリがon-topicリストに含まれていればTrue
    2. off-topicキーワードが含まれていて、かつカテゴリが空またはgeneral_knowledgeならFalse
    3. それ以外はTrue（false positive回避のためon-topic寄りに判定）

    Args:
        query: ユーザーのクエリ文字列
        routing_category: オーケストレーターが判定したカテゴリ

    Returns:
        業務範囲内ならTrue
    """
    if not query:
        return True

    # カテゴリが明確にon-topicなら即True
    # ただし general_knowledge は汎用カテゴリのため、off-topicキーワードチェックを通す
    if (
        routing_category
        and routing_category in ON_TOPIC_CATEGORIES
        and routing_category != "general_knowledge"
    ):
        return True

    # off-topicキーワードチェック
    if _OFF_TOPIC_PATTERN.search(query):
        # カテゴリが明示的に設定されていて、かつ具体的なon-topicカテゴリならキーワードを無視
        # （例: 「エンジニアカフェの天気対策は？」→ facility カテゴリ）
        # general_knowledge は汎用カテゴリのため除外
        if (
            routing_category
            and routing_category in ON_TOPIC_CATEGORIES
            and routing_category != "general_knowledge"
        ):
            return True
        # カテゴリ未設定 or general_knowledge → off-topic判定
        if not routing_category or routing_category == "general_knowledge":
            logger.info(
                "Off-topic query detected: category=%s, query=%.50s",
                routing_category,
                query,
            )
            return False

    return True


def get_off_topic_response(language: str = "ja") -> str:
    """
    off-topicクエリに対する定型応答を返す。

    Args:
        language: 応答言語 (ja/en/zh/ko)

    Returns:
        定型応答文字列
    """
    responses = {
        "ja": (
            "申し訳ございませんが、そのご質問はエンジニアカフェの業務範囲外となります。"
            "エンジニアカフェの施設情報、イベント、キャリア相談などについてお気軽にお尋ねください。"
        ),
        "en": (
            "I'm sorry, but that question is outside the scope of Engineer Cafe services. "
            "Please feel free to ask about our facilities, events, career consultations, and more."
        ),
        "zh": (
            "很抱歉，该问题超出了Engineer Cafe的服务范围。"
            "欢迎咨询我们的设施信息、活动、职业咨询等。"
        ),
        "ko": (
            "죄송합니다만, 해당 질문은 엔지니어 카페의 서비스 범위 밖입니다. "
            "시설 정보, 이벤트, 커리어 상담 등에 대해 편하게 물어봐 주세요."
        ),
    }
    return responses.get(language, responses["en"])


def check_topic_adherence(
    query: str, routing_category: str = "", language: str = "ja"
) -> Tuple[bool, str]:
    """
    トピック遵守チェックの統合関数。

    Args:
        query: ユーザーのクエリ
        routing_category: ルーティングカテゴリ
        language: 応答言語

    Returns:
        (is_on_topic, response_if_off_topic)
        on-topicの場合: (True, "")
        off-topicの場合: (False, 定型応答)
    """
    if is_on_topic(query, routing_category):
        return (True, "")
    return (False, get_off_topic_response(language))
