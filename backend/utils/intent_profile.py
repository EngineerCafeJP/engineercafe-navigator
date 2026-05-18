"""Assistant identity/profile intent detection helpers."""

from __future__ import annotations

import re

from backend.config.routing_constants import (
    ACCESSIBILITY_KEYWORDS,
    BASEMENT_KEYWORDS,
    CHILDREN_NOISE_KEYWORDS,
    CONTACT_KEYWORDS,
    EVENT_KEYWORDS,
    FACILITY_EQUIPMENT_KEYWORDS,
    FLOOR_LAYOUT_KEYWORDS,
    FOOD_DRINK_KEYWORDS,
    FOOD_DRINK_VERBS,
    MEETING_ROOM_KEYWORDS,
    PHOTOGRAPHY_KEYWORDS,
    SLIDE_KEYWORDS,
    TEMPORARY_EXIT_KEYWORDS,
    TOILET_KEYWORDS,
    WIFI_KEYWORDS,
    match_keywords,
)

# --- Identity-intent regex patterns (see is_assistant_profile_question) ---
#
# These patterns require co-occurrence of an identity-asking signal with the
# matched token, so that bare second-person pronouns ("貴方"), bare model/AI
# tokens ("which AI events..."), or bare Chinese capability markers ("能帮我
# 连接 Wi-Fi") do NOT false-route to the assistant_profile fast-path.
#
# Per Codex CLI 経路A review on PR #648 (#615 follow-up).

# Japanese: 貴方 used as identity subject — "貴方の名前", "貴方は誰", etc.
# Excludes "貴方にWi-Fi..." (used as 2nd-person pronoun, not asking-about-bot).
_JA_ANATA_IDENTITY = re.compile(
    r"貴方(の|は|って|わ)[^。！？!?]*?(名前|誰|何者|モデル|ai|ボット|自己紹介)",
    re.IGNORECASE,
)
# English: "model" / "AI" only when in identity-asking context (possessive or
# explicit asking pattern). Excludes "which AI events are held here?".
_EN_MODEL_AI_IDENTITY = re.compile(
    r"\b("
    r"(what|which)\s+(model|ai|assistant|bot)\s+(are|is)\s+(you|this)"  # what model are you
    r"|your\s+(model|ai|assistant|bot)\b"  # your model
    r"|(am|are)\s+i\s+talking\s+to\s+(an?\s+)?(model|ai|assistant|bot)"
    r")",
    re.IGNORECASE,
)
# Chinese: capability marker 能 only counts as identity when paired with a
# self-referential identity token ("你是谁", "你叫什么", "什么模型"). Plain
# "能帮我连接Wi-Fi" should NOT route to identity.
_ZH_CAPABILITY_IDENTITY = re.compile(
    r"(你|您)[^。！？!?]*?(是谁|是誰|叫什么|叫什麼|什么模型|什麼模型|什么ai|什麼ai|什么助手|什麼助手|哪个模型|哪個模型)",
    re.IGNORECASE,
)


def is_assistant_profile_question(lower_query: str) -> bool:
    """Detect questions about this kiosk assistant, not the visitor's name.

    Covers ja/en/ko/zh identity and capability queries. Used as a fast-path
    route to short-circuit LLM/web_search and force a hardcoded
    "Engineer Cafe Navigator" self-introduction. See issue #615.

    Tightened per Codex CLI 経路A review on PR #648:
    - 貴方 requires identity-asking co-occurrence (not bare 2nd-person)
    - bare model/AI requires possessive or asking pattern
    - Chinese 能帮我 requires self-referential identity token co-occurrence
    """
    visitor_name_markers = (
        "私の名前",
        "僕の名前",
        "俺の名前",
        "わたしの名前",
        "my name",
        "call me",
        "내 이름",
        "제 이름",
        "我的名字",
        "我叫",
    )
    if any(marker in lower_query for marker in visitor_name_markers):
        return False

    domain_service_markers = (
        "コミュニティマネージャー",
        "community manager",
        "キャリア相談",
        "技術相談",
        "スキルチェンジ",
        "転職",
    )
    if any(marker in lower_query for marker in domain_service_markers):
        return False

    domain_object_keyword_groups = (
        WIFI_KEYWORDS,
        EVENT_KEYWORDS,
        FACILITY_EQUIPMENT_KEYWORDS,
        CONTACT_KEYWORDS,
        FLOOR_LAYOUT_KEYWORDS,
        BASEMENT_KEYWORDS,
        MEETING_ROOM_KEYWORDS,
        FOOD_DRINK_KEYWORDS,
        FOOD_DRINK_VERBS,
        TOILET_KEYWORDS,
        ACCESSIBILITY_KEYWORDS,
        PHOTOGRAPHY_KEYWORDS,
        CHILDREN_NOISE_KEYWORDS,
        TEMPORARY_EXIT_KEYWORDS,
        SLIDE_KEYWORDS,
    )
    if any(match_keywords(lower_query, keywords) for keywords in domain_object_keyword_groups):
        return False

    # Substring identity markers that are unambiguous on their own.
    identity_markers = (
        # Japanese
        "あなたの名前",
        "君の名前",
        "きみの名前",
        "お名前は",
        "名前は何",
        "名前を教えて",
        "あなたは誰",
        "君は誰",
        "何者",
        "自己紹介",
        "どんなボット",
        "どんなモデル",
        "どのモデル",
        # English
        "what is your name",
        "what's your name",
        "what are you called",
        "who are you",
        "are you trained",
        "are you made",
        "introduce yourself",
        # Korean
        "너의 이름",
        "너 이름",
        "당신의 이름",
        "당신 이름",
        "이름이 뭐",
        "이름이 무엇",
        "누구세요",
        "누구야",
        "누구신가요",
        "자기소개",
        # Chinese (Simplified + Traditional) — these are unambiguous identity
        # questions. Bare 能 / 能帮我 is excluded; see _ZH_CAPABILITY_IDENTITY.
        "你叫什么",
        "你叫什麼",
        "你是谁",
        "你是誰",
        "你的名字",
        "您的名字",
        "您是谁",
        "您是誰",
        "自我介绍",
        "自我介紹",
    )
    if any(marker in lower_query for marker in identity_markers):
        return True

    capability_markers = (
        # Japanese
        "何ができます",
        "なにができます",
        "できること",
        "何を手伝",
        "ヘルプ",
        "使い方を教えて",
        "どんな案内",
        "どんなai",
        "どのai",
        # English
        "what can you do",
        "how can you help",
        "help me with",
        # Korean
        "무엇을 할 수 있",
        "뭘 할 수 있",
        "어떻게 도와",
        # Chinese
        "你能做什么",
        "你能做什麼",
    )
    if any(marker in lower_query for marker in capability_markers):
        return True

    # Tightened regex checks — require co-occurrence of identity-asking context
    # with otherwise-ambiguous tokens.
    if _JA_ANATA_IDENTITY.search(lower_query):
        return True
    if _EN_MODEL_AI_IDENTITY.search(lower_query):
        return True
    if _ZH_CAPABILITY_IDENTITY.search(lower_query):
        return True

    return False
