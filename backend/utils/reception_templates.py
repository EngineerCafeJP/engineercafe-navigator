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

logger = logging.getLogger(__name__)

SupportedLanguage = Literal["ja", "en"]

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
}

_RETURNING_GREETING: dict[str, str] = {
    "ja": (
        "おかえりなさい！エンジニアカフェへようこそ。\n"
        "またのご利用ありがとうございます。本日のご用件をお聞かせください。"
    ),
    "en": (
        "Welcome back to Engineer Cafe!\nThank you for visiting again. What brings you here today?"
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
    },
    "event_participation": {
        "ja": "イベントへのご参加ですね！本日開催中のイベントを確認いたします。",
        "en": "You're here for an event! Let me check today's events for you.",
    },
    "tour": {
        "ja": "施設の見学ですね！エンジニアカフェについてご案内いたします。",
        "en": "A facility tour! Let me show you around Engineer Cafe.",
    },
    "consultation": {
        "ja": "技術相談ですね！スタッフにおつなぎいたします。少々お待ちください。",
        "en": "A consultation! Let me connect you with our staff. Please wait a moment.",
    },
    "other": {
        "ja": "かしこまりました。何でもお気軽にお尋ねください！",
        "en": "Of course! Feel free to ask me anything!",
    },
}

_DEFAULT_PURPOSE_LABEL: dict[str, str] = {
    "ja": "ご利用",
    "en": "a visit",
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
    if language in ("ja", "en"):
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
    text = _RETURNING_PERSONALIZED[lang].format(
        name=name,
        last_purpose=purpose_label,
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
