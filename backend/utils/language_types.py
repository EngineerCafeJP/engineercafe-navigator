"""
Shared language type definitions for multilingual support.

Provides centralized SupportedLanguage type, language-specific LLM instructions,
and default fallback responses for all supported languages (ja, en, zh, ko).
"""

import os
from typing import Literal, Optional

SupportedLanguage = Literal["ja", "en", "zh", "ko"]

LANGUAGE_INSTRUCTION: dict[str, str] = {
    "ja": "",
    "en": "Reply in English.",
    "zh": "请用中文回答。",
    "ko": "한국어로 답변해 주세요.",
}

DEFAULT_ERROR_RESPONSE: dict[str, str] = {
    "ja": (
        "[sad]申し訳ございません。"
        "エラーが発生しました。"
        "しばらくしてからもう一度お試しください。"
    ),
    "en": ("[sad]I'm sorry, something went wrong." " Please try again later."),
    "zh": "[sad]抱歉，出现了错误。请稍后再试。",
    "ko": "[sad]죄송합니다. 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
}

DEFAULT_NOT_FOUND_RESPONSE: dict[str, str] = {
    "ja": (
        "[sad]申し訳ございません。"
        "お探しの情報が見つかりませんでした。"
        "質問を言い換えていただくか、"
        "スタッフにお問い合わせください。"
    ),
    "en": (
        "[sad]I couldn't find a detailed English answer for that question. "
        "Our Japanese knowledge base covers Engineer Cafe topics in detail — "
        "please ask a staff member at the reception, "
        "or try asking in Japanese for a richer answer."
    ),
    "zh": (
        "[sad]抱歉，暂时没有找到该问题的中文详细信息。"
        "工程师咖啡馆以日语为主，请向前台工作人员咨询，"
        "或以日语提问以获取详细答案。"
    ),
    "ko": (
        "[sad]해당 질문에 대한 한국어 상세 정보를 찾지 못했습니다. "
        "프런트 직원에게 문의하시거나 "
        "일본어로 질문해 주시면 자세히 안내해 드릴 수 있습니다."
    ),
}


def _demo_concise_answer_enabled() -> bool:
    """DEMO_CONCISE_ANSWER フラグ（1/true/yes/on のみ有効）を返す。"""
    raw = os.getenv("DEMO_CONCISE_ANSWER", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_language_instruction(language: str) -> str:
    """言語別 LLM 指示文を返す。

    DEMO_CONCISE_ANSWER=true の場合のみ、英語（en）の指示文に
    簡潔回答の 1 文を追記する（デモ専用・env gated）。
    未設定時は従来の LANGUAGE_INSTRUCTION と同一の値を返す。
    """
    instruction = LANGUAGE_INSTRUCTION.get(language, "")
    if language == "en" and _demo_concise_answer_enabled():
        instruction = f"{instruction} Keep your answer to 2-3 short sentences (under 35 words)."
    return instruction


def get_forced_response_language() -> Optional[str]:
    """LANGUAGE_FORCE による応答言語の強制値を返す。

    未設定・空白のみの場合は None（従来の自動検出動作を維持）。
    例: LANGUAGE_FORCE=en で英語固定、LANGUAGE_FORCE=en-US は "en" に正規化。
    """
    raw = os.getenv("LANGUAGE_FORCE", "").strip().lower().split("-", 1)[0]
    return raw or None


def get_calendar_fallback_message() -> Optional[str]:
    """デモモード時のカレンダー失敗メッセージを返す。

    DEMO_CONCISE_ANSWER=true または LANGUAGE_FORCE=en が有効な場合のみ、
    カレンダー取得失敗時に来場者向けの自然な英語メッセージを返す。
    それ以外は None（従来の応答を維持）。
    """
    if not (_demo_concise_answer_enabled() or get_forced_response_language() == "en"):
        return None
    return (
        "I can't reach the event calendar right now, "
        "but our Wi-Fi, meeting rooms, and cafe are open as usual."
    )
