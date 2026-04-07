"""Reception templates for the Engineer Cafe Navigator.

Provides multilingual greeting, purpose-hearing, and follow-up
templates used by the autonomous reception flow.

Also maintains backward-compatible get_reception_response for
existing MainWorkflow inline usage.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional, TypedDict

from backend.utils.emotion_tagger import add_emotion_tag
from backend.utils.language_types import SupportedLanguage

logger = logging.getLogger(__name__)

ReceptionType = Literal[
    "first_time",
    "returning",
    "general",
]


# ---------------------------------------------------------------------------
# Legacy result type (dict-based, used by MainWorkflow)
# ---------------------------------------------------------------------------


class LegacyReceptionResult(TypedDict):
    """Reception テンプレートの出力結果（レガシー互換）"""

    response: str
    emotion: Literal["happy"]
    metadata: dict


# ---------------------------------------------------------------------------
# New result type (dataclass, used by ReceptionWorkflow)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReceptionResult:
    """Immutable result from a reception template lookup.

    Attributes:
        text: The formatted template text.
        language: The language code used.
        template_type: Identifier for the template category.
    """

    text: str
    language: SupportedLanguage
    template_type: str


# ---------------------------------------------------------------------------
# Legacy templates (used by MainWorkflow inline reception)
# ---------------------------------------------------------------------------

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
    "zh": (
        "欢迎来到 Engineer Cafe！看起来这是您第一次来访。\n"
        "Engineer Cafe 是可**免费**使用的联合办公空间。\n\n"
        "**使用流程：**\n"
        "1. 请先在 1 楼前台办理登记\n"
        "2. Wi-Fi 和电源插座可自由使用\n"
        "3. 营业时间：9:00-22:00（年末年初除外）\n\n"
        "如果有任何疑问，欢迎随时咨询。"
    ),
    "ko": (
        "Engineer Cafe에 오신 것을 환영합니다! 처음 방문하셨군요.\n"
        "Engineer Cafe는 **무료**로 이용할 수 있는 코워킹 공간입니다.\n\n"
        "**이용 방법:**\n"
        "1. 1층 안내 데스크에서 이용 등록을 해주세요\n"
        "2. Wi-Fi와 전원은 자유롭게 사용할 수 있습니다\n"
        "3. 운영 시간: 9:00-22:00 (연말연시 제외)\n\n"
        "궁금한 점이 있으면 언제든지 말씀해 주세요!"
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
    "zh": (
        "欢迎回来！感谢您再次来到 Engineer Cafe。\n"
        "祝您今天也能在这里度过高效而愉快的时间。\n\n"
        "如果需要帮助，请随时告诉我。"
    ),
    "ko": (
        "다시 오신 것을 환영합니다! Engineer Cafe를 또 찾아주셔서 감사합니다.\n"
        "오늘도 편안하게 이용해 주세요.\n\n"
        "도움이 필요하시면 언제든지 말씀해 주세요."
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
    "zh": (
        "欢迎来到 Engineer Cafe！\n"
        "这里提供免费的 Wi-Fi 和电源插座。\n"
        "营业时间为 9:00-22:00。\n\n"
        "如果您想了解设施或活动信息，请随时提问。"
    ),
    "ko": (
        "Engineer Cafe에 오신 것을 환영합니다!\n"
        "이곳에서는 무료 Wi-Fi와 전원을 이용하실 수 있습니다.\n"
        "운영 시간은 9:00-22:00입니다.\n\n"
        "시설이나 이벤트에 대해 궁금한 점이 있으면 편하게 물어보세요."
    ),
}

_LEGACY_TEMPLATES: dict[ReceptionType, tuple[dict[str, str], float]] = {
    "first_time": (_FIRST_TIME, 0.95),
    "returning": (_RETURNING, 0.9),
    "general": (_GENERAL, 0.85),
}


# ---------------------------------------------------------------------------
# New enhanced templates (used by ReceptionWorkflow)
# ---------------------------------------------------------------------------

_FIRST_VISIT_GREETING: dict[str, str] = {
    "ja": (
        "こんにちは！エンジニアカフェへようこそ。\n"
        "初めてのご来館ですね。本日のご用件をお聞かせください。"
    ),
    "en": (
        "Hello! Welcome to Engineer Cafe.\n"
        "It looks like this is your first visit. What brings you here today?"
    ),
    "zh": ("您好，欢迎来到 Engineer Cafe。\n看起来这是您第一次来访，请问今天想办理什么事项？"),
    "ko": (
        "안녕하세요, Engineer Cafe에 오신 것을 환영합니다.\n"
        "처음 방문하신 것 같은데 오늘 어떤 용무로 오셨나요?"
    ),
}

_RETURNING_GREETING: dict[str, str] = {
    "ja": (
        "おかえりなさい！エンジニアカフェへようこそ。\n"
        "またのご利用ありがとうございます。本日のご用件をお聞かせください。"
    ),
    "en": (
        "Welcome back to Engineer Cafe!\nThank you for visiting again. What brings you here today?"
    ),
    "zh": ("欢迎再次来到 Engineer Cafe！\n感谢您的再次光临，请问今天想办理什么事项？"),
    "ko": (
        "Engineer Cafe에 다시 오신 것을 환영합니다!\n"
        "또 방문해 주셔서 감사합니다. 오늘 어떤 용무로 오셨나요?"
    ),
}

_RETURNING_PERSONALIZED: dict[str, str] = {
    "ja": (
        "おかえりなさい、{name}さん！またのご利用ありがとうございます。\n"
        "前回は{last_purpose}でご利用いただきましたね。\n"
        "本日のご用件をお聞かせください。"
    ),
    "en": (
        "Welcome back, {name}! Thank you for visiting again.\n"
        "Last time you were here for {last_purpose}.\n"
        "What brings you here today?"
    ),
    "zh": (
        "欢迎回来，{name}！感谢您再次来到 Engineer Cafe。\n"
        "您上次来访的目的为：{last_purpose}。\n"
        "请问今天想办理什么事项？"
    ),
    "ko": (
        "{name}님, 다시 오신 것을 환영합니다! 또 방문해 주셔서 감사합니다.\n"
        "지난 방문 목적은 {last_purpose}였네요.\n"
        "오늘은 어떤 용무로 오셨나요?"
    ),
}

_PURPOSE_HEARING: dict[str, str] = {
    "ja": (
        "ご用件をお聞かせください。\n\n"
        "例えば...\n"
        "* コワーキングスペースの利用\n"
        "* イベント参加\n"
        "* 施設見学\n"
        "* 技術相談\n\n"
        "など、お気軽にどうぞ！"
    ),
    "en": (
        "What brings you here today?\n\n"
        "For example:\n"
        "* Using the coworking space\n"
        "* Attending an event\n"
        "* Taking a facility tour\n"
        "* Technical consultation\n\n"
        "Feel free to ask!"
    ),
    "zh": (
        "请告诉我您的来访目的。\n\n"
        "例如：\n"
        "* 使用联合办公空间\n"
        "* 参加活动\n"
        "* 参观设施\n"
        "* 技术咨询\n\n"
        "请随时告诉我！"
    ),
    "ko": (
        "방문 목적을 알려주세요.\n\n"
        "예를 들면:\n"
        "* 코워킹 공간 이용\n"
        "* 이벤트 참가\n"
        "* 시설 투어\n"
        "* 기술 상담\n\n"
        "편하게 말씀해 주세요!"
    ),
}

_PURPOSE_FOLLOWUP: dict[str, dict[str, str]] = {
    "facility_use": {
        "ja": (
            "承知しました！エンジニアカフェのご利用ですね。\n"
            "1階受付で利用登録をお願いします。"
            "Wi-Fiと電源は自由にお使いいただけます。"
        ),
        "en": (
            "Got it! You'd like to use our coworking space.\n"
            "Please register at the 1F reception. "
            "Free Wi-Fi and power outlets are available."
        ),
        "zh": (
            "好的！您是来使用 Engineer Cafe 的联合办公空间。\n"
            "请先在 1 楼前台办理登记，Wi-Fi 和电源插座都可以自由使用。"
        ),
        "ko": (
            "알겠습니다! Engineer Cafe 코워킹 공간을 이용하시는군요.\n"
            "1층 안내 데스크에서 등록해 주시면 Wi-Fi와 전원을 자유롭게 이용하실 수 있습니다."
        ),
    },
    "event_participation": {
        "ja": "イベントへのご参加ですね！本日開催中のイベントを確認いたします。",
        "en": "You're here for an event! Let me check today's events for you.",
        "zh": "您是来参加活动的！我来帮您确认今天正在举行的活动。",
        "ko": "이벤트에 참가하시는군요! 오늘 진행 중인 이벤트를 확인해 드리겠습니다.",
    },
    "tour": {
        "ja": "施設の見学ですね！エンジニアカフェについてご案内いたします。",
        "en": "A facility tour! Let me show you around Engineer Cafe.",
        "zh": "您想参观设施！我来为您介绍 Engineer Cafe。",
        "ko": "시설 투어를 원하시는군요! Engineer Cafe를 안내해 드리겠습니다.",
    },
    "consultation": {
        "ja": "技術相談ですね！スタッフにおつなぎいたします。少々お待ちください。",
        "en": "A consultation! Let me connect you with our staff. Please wait a moment.",
        "zh": "您需要技术咨询！我将为您联系工作人员，请稍候。",
        "ko": "기술 상담이시군요! 담당 스태프에게 연결해 드리겠습니다. 잠시만 기다려 주세요.",
    },
    "other": {
        "ja": "かしこまりました。何でもお気軽にお尋ねください！",
        "en": "Of course! Feel free to ask me anything!",
        "zh": "好的，如有任何问题都可以随时告诉我！",
        "ko": "알겠습니다. 궁금한 점이 있으면 무엇이든 편하게 물어보세요!",
    },
}

_DEFAULT_PURPOSE_LABEL: dict[str, str] = {
    "ja": "ご利用",
    "en": "a visit",
    "zh": "来访",
    "ko": "방문",
}


# ===================================================================
# Public API — Legacy (backward-compatible with MainWorkflow)
# ===================================================================


def get_reception_response(
    language: SupportedLanguage,
    reception_type: ReceptionType = "general",
    *,
    is_returning: bool | None = None,
) -> LegacyReceptionResult | ReceptionResult:
    """Get a reception greeting.

    Supports two calling conventions:
    - Legacy: get_reception_response("ja", "first_time") → dict
    - New: get_reception_response("ja", is_returning=True) → ReceptionResult

    Args:
        language: Language code ("ja" or "en").
        reception_type: Legacy reception type.
        is_returning: If provided, uses new-style API.

    Returns:
        LegacyReceptionResult or ReceptionResult depending on calling convention.
    """
    if is_returning is not None:
        lang = _resolve_language(language)
        if is_returning:
            return ReceptionResult(
                text=_RETURNING_GREETING[lang],
                language=lang,
                template_type="returning_greeting",
            )
        return ReceptionResult(
            text=_FIRST_VISIT_GREETING[lang],
            language=lang,
            template_type="first_visit_greeting",
        )

    messages, confidence = _LEGACY_TEMPLATES.get(
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


# ===================================================================
# Public API — New (for ReceptionWorkflow)
# ===================================================================


def _resolve_language(language: SupportedLanguage) -> SupportedLanguage:
    """Normalize language code, defaulting to 'ja' for unsupported values."""
    if language in ("ja", "en", "zh", "ko"):
        return language
    return "ja"


def get_personalized_greeting(
    language: SupportedLanguage,
    name: str,
    last_purpose: Optional[str] = None,
) -> ReceptionResult:
    """Personalized greeting for returning visitors with name.

    Args:
        language: Language code ("ja" or "en").
        name: The visitor's name.
        last_purpose: Description of their last visit purpose.

    Returns:
        ReceptionResult with a personalized greeting.
    """
    lang = _resolve_language(language)
    purpose_label = last_purpose or _DEFAULT_PURPOSE_LABEL[lang]
    safe_name = str(name).replace("{", "").replace("}", "")
    safe_purpose = str(purpose_label).replace("{", "").replace("}", "")
    text = _RETURNING_PERSONALIZED[lang].format(
        name=safe_name,
        last_purpose=safe_purpose,
    )
    return ReceptionResult(
        text=text,
        language=lang,
        template_type="returning_personalized",
    )


def get_purpose_hearing_prompt(
    language: SupportedLanguage,
) -> ReceptionResult:
    """Ask the visitor about their purpose.

    Args:
        language: Language code ("ja" or "en").

    Returns:
        ReceptionResult with a purpose-hearing prompt.
    """
    lang = _resolve_language(language)
    return ReceptionResult(
        text=_PURPOSE_HEARING[lang],
        language=lang,
        template_type="purpose_hearing",
    )


def get_purpose_followup(
    language: SupportedLanguage,
    purpose: str,
) -> ReceptionResult:
    """Follow-up message after purpose is identified.

    Args:
        language: Language code ("ja" or "en").
        purpose: The classified purpose category.

    Returns:
        ReceptionResult with an appropriate follow-up message.
    """
    lang = _resolve_language(language)
    templates = _PURPOSE_FOLLOWUP.get(purpose, _PURPOSE_FOLLOWUP["other"])
    return ReceptionResult(
        text=templates[lang],
        language=lang,
        template_type=f"purpose_followup_{purpose}",
    )
