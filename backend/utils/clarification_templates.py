"""
Clarification テンプレート - 曖昧なクエリに対する固定応答メッセージ

OrchestratorAgent がインラインで使用する。LLM 呼び出しなし。
カテゴリと言語に基づいてテンプレートメッセージを返す純粋関数。

元: backend/agents/clarification_agent.py の handle_clarification()
"""

import logging
from typing import Literal, TypedDict

from backend.utils.emotion_tagger import add_emotion_tag

logger = logging.getLogger(__name__)

SupportedLanguage = Literal["ja", "en"]

ClarificationCategory = Literal[
    "cafe-clarification-needed",
    "meeting-room-clarification-needed",
    "event-clarification-needed",
    "space-clarification-needed",
    "general-clarification-needed",
]


class ClarificationResult(TypedDict):
    """Clarification テンプレートの出力結果"""

    response: str  # 感情タグ付きテキスト
    emotion: Literal["surprised"]
    metadata: dict  # agent名, category, confidence など


# --------------------------------------------------------------------------- #
#  テンプレートメッセージ定数
# --------------------------------------------------------------------------- #

_CAFE_CLARIFICATION: dict[str, str] = {
    "en": (
        "I'd be happy to help! Are you asking about:\n"
        "1. **Engineer Cafe** (coworking space) - Open 9:00-22:00, free WiFi & power outlets\n"
        "2. **Saino Cafe** (attached cafe & bar) - Weekdays 12:00-20:00, lunch & drink menu\n\n"
        "Please let me know which one you're interested in!"
    ),
    "ja": (
        "お手伝いさせていただきます！どちらについてお聞きでしょうか：\n"
        "1. **エンジニアカフェ**（コワーキングスペース）- 9:00-22:00、WiFi・電源完備、無料利用可\n"
        "2. **サイノカフェ**（併設のカフェ＆バー）"
        "- 平日12:00-20:00、ランチ・ドリンクメニューあり\n\n"
        "お聞かせください！"
    ),
}

_MEETING_ROOM_CLARIFICATION: dict[str, str] = {
    "en": (
        "I'd be happy to help! We have two types of meeting spaces:\n"
        "1. **Paid Meeting Rooms (2F)** - Managed by Fukuoka City "
        "(Red Brick Cultural Hall reception, right side of 1F). "
        "Advance booking required\n"
        "2. **Basement Meeting Spaces (B1)** - Free, reservation "
        "priority (2h blocks). Book by the day before; "
        "walk-in OK if available\n\n"
        "Which one would you like to know about?"
    ),
    "ja": (
        "お手伝いさせていただきます！会議スペースは2種類ございます：\n"
        "1. **有料会議室（2階）** - 福岡市の施設です。"
        "1F右手奥の赤煉瓦文化館受付でお手続きください"
        "（エンジニアカフェとは別管理）\n"
        "2. **地下MTGスペース（地下1階）** - 無料・予約優先"
        "（2時間区切り）。前日までに予約可、"
        "空いていれば予約なしでも利用OK\n\n"
        "どちらについてお知りになりたいですか？"
    ),
}

_EVENT_CLARIFICATION: dict[str, str] = {
    "en": (
        "I'd be happy to help with event information! "
        "Could you tell me more about what you're looking for?\n"
        "1. **Attend an event** - Browse upcoming events at Engineer Cafe\n"
        "2. **Host an event** - Information about hosting your own event\n"
        "3. **Today's schedule** - Check what's happening today\n\n"
        "Which one interests you?"
    ),
    "ja": (
        "イベントについてお手伝いします！"
        "どのような情報をお探しでしょうか？\n"
        "1. **イベントに参加したい** - エンジニアカフェの今後のイベント一覧\n"
        "2. **イベントを開催したい** - イベント開催に関する情報\n"
        "3. **本日のスケジュール** - 今日開催されるイベントの確認\n\n"
        "どちらについてお知りになりたいですか？"
    ),
}

_SPACE_CLARIFICATION: dict[str, str] = {
    "en": (
        "We have several spaces available! "
        "Which one are you interested in?\n"
        "1. **Main Hall (1F)** - Open coworking area, free to use\n"
        "2. **Focus Space (B1)** - Quiet area for concentrated work\n"
        "3. **MTG Space (B1)** - Free meeting space (2h blocks, reservation priority)\n"
        "4. **MAKER's Space (B1)** - 3D printer, laser cutter available\n"
        "5. **Under Space (B1)** - Event & presentation space\n\n"
        "Which space would you like to know about?"
    ),
    "ja": (
        "いくつかのスペースがございます！"
        "どちらにご興味がありますか？\n"
        "1. **メインホール（1階）** - オープンコワーキングエリア、無料利用可\n"
        "2. **集中スペース（地下1階）** - 静かな作業環境\n"
        "3. **MTGスペース（地下1階）** - 無料会議スペース（2時間区切り、予約優先）\n"
        "4. **MAKER'sスペース（地下1階）** - 3Dプリンター・レーザーカッター利用可\n"
        "5. **アンダースペース（地下1階）** - イベント・プレゼンテーション用スペース\n\n"
        "どのスペースについてお知りになりたいですか？"
    ),
}

_GENERAL_CLARIFICATION: dict[str, str] = {
    "en": (
        "I'd be happy to help! Could you please provide "
        "more details about what you'd like to know?"
    ),
    "ja": "お手伝いさせていただきます！もう少し詳しくお聞かせいただけますか？",
}


# --------------------------------------------------------------------------- #
#  テンプレートマッピング（カテゴリ → メッセージ辞書, confidence）
# --------------------------------------------------------------------------- #

_TEMPLATES: dict[ClarificationCategory, tuple[dict[str, str], float]] = {
    "cafe-clarification-needed": (_CAFE_CLARIFICATION, 0.9),
    "meeting-room-clarification-needed": (_MEETING_ROOM_CLARIFICATION, 0.9),
    "event-clarification-needed": (_EVENT_CLARIFICATION, 0.9),
    "space-clarification-needed": (_SPACE_CLARIFICATION, 0.9),
    "general-clarification-needed": (_GENERAL_CLARIFICATION, 0.7),
}


# --------------------------------------------------------------------------- #
#  公開 API
# --------------------------------------------------------------------------- #


def get_clarification_response(
    category: ClarificationCategory,
    language: SupportedLanguage,
) -> ClarificationResult:
    """
    カテゴリと言語に基づいてテンプレート応答を返す。

    LLM 不要の純粋関数。元 ClarificationAgent.handle_clarification() と同等。

    Args:
        category: 曖昧性の種類
        language: 応答言語 ("ja" | "en")

    Returns:
        ClarificationResult: 感情タグ付きの応答とメタデータ
    """
    messages, confidence = _TEMPLATES.get(
        category,
        (_GENERAL_CLARIFICATION, 0.7),
    )

    message = messages.get(language, messages["ja"])
    tagged_message = add_emotion_tag(message, "surprised")

    logger.info(
        "Clarification template: category=%s, language=%s",
        category,
        language,
    )

    return {
        "response": tagged_message,
        "emotion": "surprised",
        "metadata": {
            "agent": "ClarificationAgent",
            "confidence": confidence,
            "category": category,
            "sources": ["clarification_system"],
        },
    }
