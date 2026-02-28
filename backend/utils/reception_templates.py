"""
Reception テンプレート - 受付案内の固定応答メッセージ

OrchestratorAgent がインラインで使用する。LLM 呼び出しなし。
受付タイプと言語に基づいてテンプレートメッセージを返す純粋関数。

パターンは clarification_templates.py と同等。
"""

import logging
from typing import Literal, TypedDict

from backend.utils.emotion_tagger import add_emotion_tag

logger = logging.getLogger(__name__)

SupportedLanguage = Literal["ja", "en"]

ReceptionType = Literal[
    "first_time",
    "returning",
    "general",
]


class ReceptionResult(TypedDict):
    """Reception テンプレートの出力結果"""

    response: str  # 感情タグ付きテキスト
    emotion: Literal["happy"]
    metadata: dict  # agent名, category, confidence など


# --------------------------------------------------------------------------- #
#  テンプレートメッセージ定数
# --------------------------------------------------------------------------- #

_FIRST_TIME: dict[str, str] = {
    "ja": (
        "ようこそエンジニアカフェへ！初めてのご利用ですね。\n"
        "エンジニアカフェは**無料**でご利用いただけるコワーキングスペースです。\n\n"
        "**ご利用の流れ:**\n"
        "1. 1階受付で利用登録をお願いします\n"
        "2. Wi-Fi・電源は自由にお使いいただけます\n"
        "3. 営業時間: 9:00-22:00（年末年始を除く）\n\n"
        "何かご不明な点があれば、お気軽にお尋ねください！"
    ),
    "en": (
        "Welcome to Engineer Cafe! It looks like this is your first visit.\n"
        "Engineer Cafe is a **free** coworking space.\n\n"
        "**How to get started:**\n"
        "1. Please register at the 1F reception\n"
        "2. Free Wi-Fi and power outlets are available\n"
        "3. Open hours: 9:00-22:00 (except year-end/New Year holidays)\n\n"
        "Feel free to ask if you have any questions!"
    ),
}

_RETURNING: dict[str, str] = {
    "ja": (
        "おかえりなさい！またのご利用ありがとうございます。\n"
        "本日もエンジニアカフェをお楽しみください。\n\n"
        "何かお困りのことがあれば、お気軽にお尋ねください。"
    ),
    "en": (
        "Welcome back! Thank you for visiting again.\n"
        "Enjoy your time at Engineer Cafe today.\n\n"
        "Feel free to ask if you need any help."
    ),
}

_GENERAL: dict[str, str] = {
    "ja": (
        "エンジニアカフェへようこそ！\n"
        "こちらではWi-Fiや電源を無料でご利用いただけます。\n"
        "営業時間は9:00-22:00です。\n\n"
        "施設やイベントについてのご質問がございましたら、"
        "お気軽にお尋ねください。"
    ),
    "en": (
        "Welcome to Engineer Cafe!\n"
        "We offer free Wi-Fi and power outlets.\n"
        "Open hours: 9:00-22:00.\n\n"
        "If you have any questions about our facilities or events, "
        "feel free to ask."
    ),
}


# --------------------------------------------------------------------------- #
#  テンプレートマッピング（受付タイプ → メッセージ辞書, confidence）
# --------------------------------------------------------------------------- #

_TEMPLATES: dict[ReceptionType, tuple[dict[str, str], float]] = {
    "first_time": (_FIRST_TIME, 0.95),
    "returning": (_RETURNING, 0.9),
    "general": (_GENERAL, 0.85),
}


# --------------------------------------------------------------------------- #
#  公開 API
# --------------------------------------------------------------------------- #


def get_reception_response(
    language: SupportedLanguage,
    reception_type: ReceptionType = "general",
) -> ReceptionResult:
    """
    受付タイプと言語に基づいてテンプレート応答を返す。

    LLM 不要の純粋関数。

    Args:
        language: 応答言語 ("ja" | "en")
        reception_type: 受付タイプ ("first_time" | "returning" | "general")

    Returns:
        ReceptionResult: 感情タグ付きの応答とメタデータ
    """
    messages, confidence = _TEMPLATES.get(
        reception_type,
        (_GENERAL, 0.85),
    )

    message = messages.get(language, messages["ja"])
    tagged_message = add_emotion_tag(message, "happy")

    logger.info(
        "Reception template: type=%s, language=%s",
        reception_type,
        language,
    )

    return {
        "response": tagged_message,
        "emotion": "happy",
        "metadata": {
            "agent": "ReceptionAgent",
            "confidence": confidence,
            "category": "reception",
            "reception_type": reception_type,
            "sources": ["reception_system"],
        },
    }
