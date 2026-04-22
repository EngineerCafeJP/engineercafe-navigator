"""
Shared language type definitions for multilingual support.

Provides centralized SupportedLanguage type, language-specific LLM instructions,
and default fallback responses for all supported languages (ja, en, zh, ko).
"""

from typing import Literal

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
