"""
Emergency テンプレート - 緊急事態に対する固定応答メッセージ

OrchestratorAgent がインラインで使用する。LLM 呼び出しなし。
緊急サブタイプと言語に基づいてテンプレートメッセージを返す純粋関数。

パターンは clarification_templates.py と同等。
"""

import logging
from typing import Literal, TypedDict

from backend.utils.emotion_tagger import add_emotion_tag
from backend.utils.language_types import SupportedLanguage

logger = logging.getLogger(__name__)

EmergencySubtype = Literal[
    "earthquake",
    "fire",
    "medical_emergency",
    "evacuation_route",
    "general_emergency",
]


class EmergencyResult(TypedDict):
    """Emergency テンプレートの出力結果"""

    response: str  # 感情タグ付きテキスト
    emotion: Literal["serious"]
    metadata: dict  # agent名, subtype, confidence など


# --------------------------------------------------------------------------- #
#  緊急サブタイプ分類キーワード
# --------------------------------------------------------------------------- #

try:
    from backend.config.routing_constants import (
        EARTHQUAKE_KEYWORDS,
        FIRE_KEYWORDS,
        MEDICAL_EMERGENCY_KEYWORDS,
    )
except ImportError:
    # Fallback values if constants are not yet available in routing_constants
    EARTHQUAKE_KEYWORDS = ["地震", "earthquake", "揺れ"]
    FIRE_KEYWORDS = ["火事", "火災", "fire", "煙"]
    MEDICAL_EMERGENCY_KEYWORDS = ["AED", "倒れ", "意識", "ambulance", "怪我"]


# --------------------------------------------------------------------------- #
#  テンプレートメッセージ定数
# --------------------------------------------------------------------------- #

_EARTHQUAKE: dict[str, str] = {
    "ja": (
        "地震です！机の下に身を隠してください。"
        "揺れが収まったら、1階正面玄関から避難してください。"
        "スタッフの指示に従ってください。"
    ),
    "en": (
        "Earthquake! Take cover under a desk. "
        "Once shaking stops, evacuate through the 1F main entrance. "
        "Follow staff instructions."
    ),
}

_FIRE: dict[str, str] = {
    "ja": (
        "火事です！すぐに119番に通報してください。"
        "最寄りの出口から速やかに避難してください。"
        "1階正面玄関または地下1階職員通路から脱出できます。"
    ),
    "en": (
        "Fire! Call 119 immediately. "
        "Evacuate through the nearest exit. "
        "You can exit via 1F main entrance or B1F staff corridor."
    ),
}

_MEDICAL_EMERGENCY: dict[str, str] = {
    "ja": (
        "医療緊急事態です。119番に通報してください。"
        "AEDは1階受付横にあります。"
        "応急処置が必要な方は、スタッフにお声がけください。"
    ),
    "en": (
        "Medical emergency. Call 119. "
        "AED is located next to the 1F reception. "
        "Please alert staff if first aid is needed."
    ),
}

_EVACUATION_ROUTE: dict[str, str] = {
    "ja": (
        "避難経路は1階正面玄関と地下1階職員通路の2箇所です。"
        "火災や地震など緊急時は、近い出口から避難し、スタッフの指示に従ってください。"
        "AEDは1階受付横にあります。"
        "医療機関が必要な場合は、アクロス福岡側のクリニック群が徒歩1〜3分圏内にあります。"
    ),
    "en": (
        "Evacuation routes are the 1F main entrance and the B1F staff corridor. "
        "In an emergency, use the nearest safe exit and follow staff instructions. "
        "The AED is next to the 1F reception."
    ),
}

_GENERAL_EMERGENCY: dict[str, str] = {
    "ja": (
        "緊急事態を確認しました。スタッフに連絡中です。"
        "落ち着いて行動してください。"
        "必要に応じて119番（救急・消防）または110番（警察）に通報してください。"
    ),
    "en": (
        "Emergency acknowledged. Staff is being notified. "
        "Please stay calm. "
        "Call 119 (ambulance/fire) or 110 (police) if needed."
    ),
}


# --------------------------------------------------------------------------- #
#  テンプレートマッピング（サブタイプ → メッセージ辞書, confidence）
# --------------------------------------------------------------------------- #

_TEMPLATES: dict[EmergencySubtype, tuple[dict[str, str], float]] = {
    "earthquake": (_EARTHQUAKE, 0.95),
    "fire": (_FIRE, 0.95),
    "medical_emergency": (_MEDICAL_EMERGENCY, 0.95),
    "evacuation_route": (_EVACUATION_ROUTE, 0.9),
    "general_emergency": (_GENERAL_EMERGENCY, 0.85),
}


# --------------------------------------------------------------------------- #
#  サブタイプ分類
# --------------------------------------------------------------------------- #


def classify_emergency_subtype(query: str) -> EmergencySubtype:
    """
    クエリから緊急サブタイプを分類する。

    キーワードマッチングを使用してサブタイプを判定する。
    複数のキーワードが一致する場合は最初に一致したサブタイプを返す。

    Args:
        query: ユーザーからのクエリ

    Returns:
        EmergencySubtype: 緊急サブタイプ
    """
    lower_query = query.lower()

    for kw in EARTHQUAKE_KEYWORDS:
        if kw.lower() in lower_query:
            return "earthquake"

    for kw in FIRE_KEYWORDS:
        if kw.lower() in lower_query:
            return "fire"

    for kw in MEDICAL_EMERGENCY_KEYWORDS:
        if kw.lower() in lower_query:
            return "medical_emergency"

    if any(
        marker in lower_query for marker in ("避難経路", "evacuation route", "evacuation routes")
    ):
        return "evacuation_route"

    return "general_emergency"


# --------------------------------------------------------------------------- #
#  公開 API
# --------------------------------------------------------------------------- #


def get_emergency_response(
    query: str,
    language: SupportedLanguage = "ja",
) -> EmergencyResult:
    """
    緊急サブタイプと言語に基づいてテンプレート応答を返す。

    LLM 不要の純粋関数。クエリからサブタイプを自動分類する。

    Args:
        query: ユーザーからのクエリ（サブタイプ分類に使用）
        language: 応答言語 ("ja" | "en")

    Returns:
        EmergencyResult: 感情タグ付きの応答とメタデータ
    """
    subtype = classify_emergency_subtype(query)
    messages, confidence = _TEMPLATES.get(
        subtype,
        (_GENERAL_EMERGENCY, 0.85),
    )

    message = messages.get(language, messages["ja"])
    tagged_message = add_emotion_tag(message, "serious")

    logger.info(
        "Emergency template: subtype=%s, language=%s",
        subtype,
        language,
    )

    return {
        "response": tagged_message,
        "emotion": "serious",
        "metadata": {
            "agent": "EmergencyAgent",
            "confidence": confidence,
            "subtype": subtype,
            "sources": ["emergency_system"],
        },
    }
