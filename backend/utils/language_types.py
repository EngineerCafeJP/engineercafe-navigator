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
        "[sad]I'm sorry, I couldn't find the"
        " information you're looking for."
        " Please try rephrasing your question"
        " or ask a staff member for help."
    ),
    "zh": ("[sad]抱歉，我未能找到您所需的信息。请尝试换一种方式提问，或联系工作人员寻求帮助。"),
    "ko": (
        "[sad]죄송합니다. "
        "찾으시는 정보를 찾지 못했습니다. "
        "질문을 바꾸어 보시거나 "
        "직원에게 문의해 주세요."
    ),
}
