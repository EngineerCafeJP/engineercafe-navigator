"""
ルーティング定数・キーワード・ヘルパー関数の集約モジュール

orchestrator_agent.py, memory_helper.py で共通使用される
キーワードリスト、マッピング、ヘルパー関数を一箇所に集約。

Note: このモジュールはリーフ依存（他のエージェントモジュールをimportしない）
"""

import re
from typing import Dict, List, Literal, Optional, TypeAlias, cast

from backend.config.routing_core_keywords import (
    ACCESS_DIRECTION_KEYWORDS,
    BASEMENT_KEYWORDS,
    BASEMENT_PATTERNS,
    BUILDING_KEYWORDS,
    BUSINESS_HOURS_KEYWORDS,
    COMMUNITY_KEYWORDS,
    CONSULTATION_KEYWORDS,
    EARTHQUAKE_KEYWORDS as EARTHQUAKE_KEYWORDS,
    EMERGENCY_KEYWORDS,
    ENGLISH_FAREWELL_KEYWORDS as ENGLISH_FAREWELL_KEYWORDS,
    ENGLISH_FAREWELL_PATTERNS,
    EVENT_KEYWORDS,
    FAREWELL_KEYWORDS as FAREWELL_KEYWORDS,
    FIRE_KEYWORDS as FIRE_KEYWORDS,
    FLOOR_KEYWORDS as FLOOR_KEYWORDS,
    FLOOR_LAYOUT_KEYWORDS,
    FOOD_DRINK_VERBS,
    JAPANESE_FAREWELL_KEYWORDS,
    LOST_FOUND_KEYWORDS,
    MEDICAL_EMERGENCY_KEYWORDS as MEDICAL_EMERGENCY_KEYWORDS,
    MEETING_ROOM_KEYWORDS,
    MEMORY_EXCLUSION_BUSINESS as MEMORY_EXCLUSION_BUSINESS,
    MEMORY_EXCLUSION_FACILITY as MEMORY_EXCLUSION_FACILITY,
    MEMORY_KEYWORDS as MEMORY_KEYWORDS,
    PRICING_KEYWORDS,
    RECEPTION_KEYWORDS,
    SLIDE_KEYWORDS,
    WIFI_KEYWORDS,
)
from backend.config.routing_facility_keywords import (
    ACCESSIBILITY_KEYWORDS,
    BICYCLE_KEYWORDS,
    BOOKING_KEYWORDS,
    CHILDREN_NOISE_KEYWORDS,
    CLOSED_DAY_TEMPLATES as CLOSED_DAY_TEMPLATES,
    CLOSING_WARNING_TEMPLATES as CLOSING_WARNING_TEMPLATES,
    CONTACT_KEYWORDS,
    EXCLUSIVE_RENTAL_KEYWORDS,
    FACILITY_EQUIPMENT_KEYWORDS,
    FOOD_DRINK_KEYWORDS,
    GREETING_KEYWORDS as GREETING_KEYWORDS,
    NEARBY_FACILITY_KEYWORDS,
    PARKING_KEYWORDS,
    PET_POLICY_EXCLUSION_KEYWORDS,
    PET_POLICY_KEYWORDS as PET_POLICY_KEYWORDS,
    PHOTOGRAPHY_KEYWORDS,
    POLICY_KEYWORDS as POLICY_KEYWORDS,
    SMOKING_KEYWORDS,
    TEMPORARY_EXIT_KEYWORDS,
    TIME_GREETING_TEMPLATES as TIME_GREETING_TEMPLATES,
    TOILET_KEYWORDS,
)

# =============================================================================
# エージェントノード名の型定義
# =============================================================================

AgentNodeName = Literal[
    "business_info",
    "facility",
    "event",
    "general_knowledge",
    "slide",
    "farewell",
]

EXECUTABLE_AGENT_NODES: frozenset[AgentNodeName] = frozenset(
    (
        "business_info",
        "facility",
        "event",
        "general_knowledge",
        "slide",
        "farewell",
    )
)

RoutingTarget = Literal[
    "business_info",
    "facility",
    "event",
    "general_knowledge",
    "slide",
    "farewell",
    "__end__",
]

AgentName = Literal[
    "BusinessInfoAgent",
    "FacilityAgent",
    "EventAgent",
    "GeneralKnowledgeAgent",
    "TimeAgent",
    "SlideAgent",
    "FarewellAgent",
]


# =============================================================================
# キーワード定数
# =============================================================================


# =============================================================================
# エージェント説明・マッピング
# =============================================================================

AGENT_DESCRIPTIONS: Dict[str, str] = {
    "business_info": (
        "営業情報エージェント: 営業時間、料金、場所、"
        "相談（キャリア・スキルチェンジ等）、"
        "コミュニティ（Engineer Cafe Lab等）"
        "など施設の基本情報・サービスを回答"
    ),
    "facility": (
        "施設エージェント: Wi-Fi、電源、会議室、地下スペース、"
        "建物の歴史・構造、アクセス方法・行き方"
        "など設備・物理施設に関する情報を回答"
    ),
    "event": ("イベントエージェント: イベント情報、勉強会、セミナーなどの予定を回答"),
    "general_knowledge": (
        "一般知識エージェント: 上記以外の一般的な質問、および過去の会話履歴に関する質問に回答"
    ),
    "slide": ("スライドエージェント: スライドのナレーション、操作、質問応答を処理"),
    "greeting": (
        "挨拶処理（インライン）: こんにちは、おはよう等の挨拶に対して"
        "エンジニアカフェの温かい歓迎メッセージを応答。"
        "オーケストレーターがインラインで処理する。"
    ),
    "farewell": (
        "退館エージェント: さようなら、帰ります等の退館メッセージに対して"
        "温かい退館メッセージ、受付カード返却案内、荷物確認リマインダーを応答"
    ),
}

CATEGORY_TO_AGENT_MAP: Dict[str, AgentNodeName] = {
    "business-hours": "business_info",
    "facility-info": "facility",
    "basement-facility": "facility",
    "saino-cafe": "business_info",
    "calendar": "event",
    "events": "event",
    "current-time": "general_knowledge",
    "current_info": "general_knowledge",
    "assistant_profile": "general_knowledge",
    "daily_conversation": "general_knowledge",
    "general": "general_knowledge",
    "memory": "general_knowledge",
    "consultation": "business_info",
    "community": "business_info",
    "cafe-clarification-needed": "general_knowledge",
    "meeting-room-clarification-needed": "general_knowledge",
    "event-clarification-needed": "general_knowledge",
    "space-clarification-needed": "general_knowledge",
    "general-clarification-needed": "general_knowledge",
    # query_classifier._detect_specific_category が返すカテゴリ
    "pricing": "business_info",
    "facilities": "facility",
    "access": "facility",
    "hours": "business_info",
    "parking": "facility",
    "bicycle": "facility",
    "smoking": "facility",
    "food_drink": "facility",
    "contact": "business_info",
    "policy": "facility",
    "emergency": "facility",
    "reception": "business_info",
    "floor_layout": "facility",
    "nearby": "facility",
    "lost_found": "facility",
    "greeting": "business_info",
    "farewell": "farewell",
    "slide": "slide",
}

_BROAD_ROUTING_CATEGORIES = frozenset(
    (
        "general",
        "general-clarification-needed",
        "cafe-clarification-needed",
        "meeting-room-clarification-needed",
        "event-clarification-needed",
        "space-clarification-needed",
    )
)

_AGENT_NODE_ALIASES: dict[str, AgentNodeName] = {
    "businessinfoagent": "business_info",
    "business_info_agent": "business_info",
    "business-info": "business_info",
    "business info": "business_info",
    "facilityagent": "facility",
    "facility_agent": "facility",
    "eventagent": "event",
    "event_agent": "event",
    "generalknowledgeagent": "general_knowledge",
    "general_knowledge_agent": "general_knowledge",
    "general-knowledge": "general_knowledge",
    "general knowledge": "general_knowledge",
    "gka": "general_knowledge",
    "timeagent": "general_knowledge",
    "time_agent": "general_knowledge",
    "slideagent": "slide",
    "slide_agent": "slide",
    "farewellagent": "farewell",
    "farewell_agent": "farewell",
}

REQUEST_TYPE_TO_AGENT_MAP: dict[str, AgentNodeName] = {
    "hours": "business_info",
    "price": "business_info",
    "pricing": "business_info",
    "contact": "business_info",
    "reception": "business_info",
    "consultation": "business_info",
    "community": "business_info",
    "wifi": "facility",
    "lost_found": "facility",
    "basement": "facility",
    "facility": "facility",
    "meeting_room": "facility",
    "meeting-room": "facility",
    "access": "facility",
    "location": "facility",
    "building": "facility",
    "parking": "facility",
    "bicycle": "facility",
    "smoking": "facility",
    "food_drink": "facility",
    "floor_layout": "facility",
    "nearby": "facility",
    "exclusive_rental": "facility",
    "toilet": "facility",
    "accessibility": "facility",
    "photography": "facility",
    "children_noise": "facility",
    "temporary_exit": "facility",
    "pets": "facility",
    "emergency": "facility",
    "event": "event",
    "slide": "slide",
    "farewell": "farewell",
    "memory": "general_knowledge",
    "assistant_profile": "general_knowledge",
    "daily_conversation": "general_knowledge",
    "current_info": "general_knowledge",
}

AgentResolutionSource: TypeAlias = Literal["request_type", "category", "agent", "alias", "fallback"]


def normalize_agent_node(
    raw_agent: object,
    *,
    category: Optional[str] = None,
    request_type: Optional[str] = None,
    fallback: AgentNodeName = "general_knowledge",
    prefer_category: bool = False,
) -> tuple[AgentNodeName, AgentResolutionSource]:
    """Resolve routing output to an executable LangGraph agent node.

    LLMs and integration layers can return display class names
    (``BusinessInfoAgent``), inline pseudo-targets (``greeting``), or stale
    defaults. LangGraph ``Command.goto`` must receive one of the concrete node
    names, so this helper is the single normalization point for routing and
    state-transition code.
    """
    request_type_agent = REQUEST_TYPE_TO_AGENT_MAP.get(request_type or "")
    if prefer_category and request_type_agent:
        return request_type_agent, "request_type"

    category_agent = CATEGORY_TO_AGENT_MAP.get(category or "")
    if prefer_category and category_agent and category not in _BROAD_ROUTING_CATEGORIES:
        return category_agent, "category"

    if isinstance(raw_agent, str):
        normalized = raw_agent.strip()
        if normalized in EXECUTABLE_AGENT_NODES:
            return cast(AgentNodeName, normalized), "agent"

        alias = _AGENT_NODE_ALIASES.get(normalized.lower())
        if alias:
            return alias, "alias"

    if category_agent:
        return category_agent, "category"

    return fallback, "fallback"


# =============================================================================
# ヘルパー関数
# =============================================================================


def match_keywords(text: str, keywords: List[str]) -> bool:
    """テキストにキーワードリストのいずれかが含まれているか判定"""
    lower_text = text.lower()
    return any(kw.lower() in lower_text for kw in keywords)


def match_farewell_keywords(text: str) -> bool:
    """退館フレーズを判定する。英語は語境界つきで substring 誤爆を避ける。"""
    lower_text = text.lower()
    return any(kw in lower_text for kw in JAPANESE_FAREWELL_KEYWORDS) or any(
        pattern.search(lower_text) for pattern in ENGLISH_FAREWELL_PATTERNS
    )


def match_pet_policy_keywords(text: str) -> bool:
    """Pet policy keywords with bottle/whole-word guards."""
    lower_text = text.lower()
    if any(kw.lower() in lower_text for kw in PET_POLICY_EXCLUSION_KEYWORDS):
        return False

    japanese_keywords = [
        "ペット",
        "動物",
        "補助犬",
        "盲導犬",
        "聴導犬",
        "介助犬",
    ]
    if any(kw in lower_text for kw in japanese_keywords):
        return True

    english_keywords = [
        "pet",
        "pets",
        "animal",
        "service animal",
        "service dog",
        "guide dog",
        "assistance dog",
    ]
    return any(re.search(rf"\b{re.escape(kw)}\b", lower_text) for kw in english_keywords)


LOCATION_KEYWORDS = ["場所", "どこ", "アクセス", "住所", "location", "where", "address"]


def extract_request_type(query: str) -> Optional[str]:
    """
    クエリから具体的なリクエストタイプを抽出

    orchestrator_agent と memory_helper で共通使用される統合版。
    basement は regex パターンにも対応。

    Args:
        query: ユーザーからのクエリ

    Returns:
        リクエストタイプ（wifi, hours, price等）またはNone
    """
    lower_query = query.lower()

    if match_keywords(lower_query, EMERGENCY_KEYWORDS):
        return "emergency"
    if match_farewell_keywords(lower_query):
        return "farewell"
    if match_keywords(lower_query, LOST_FOUND_KEYWORDS):
        return "lost_found"
    if match_keywords(lower_query, WIFI_KEYWORDS):
        return "wifi"
    if match_keywords(lower_query, BUSINESS_HOURS_KEYWORDS):
        return "hours"
    if match_keywords(lower_query, PRICING_KEYWORDS):
        return "price"
    if match_keywords(lower_query, CONSULTATION_KEYWORDS):
        return "consultation"
    if match_keywords(lower_query, COMMUNITY_KEYWORDS):
        return "community"
    if match_keywords(lower_query, ACCESS_DIRECTION_KEYWORDS):
        return "access"
    if match_keywords(lower_query, CONTACT_KEYWORDS):
        return "contact"
    if match_keywords(lower_query, NEARBY_FACILITY_KEYWORDS):
        return "nearby"
    if match_keywords(lower_query, BUILDING_KEYWORDS):
        return "building"
    # 新しいキーワード（bicycle, parking, smoking, food_drink）を LOCATION_KEYWORDS より優先
    # Note: "bicycle parking" のような複合語では bicycle を優先するため、bicycleを先にチェック
    if match_keywords(lower_query, BICYCLE_KEYWORDS):
        return "bicycle"
    if match_keywords(lower_query, PARKING_KEYWORDS):
        return "parking"
    if match_keywords(lower_query, SMOKING_KEYWORDS):
        return "smoking"
    if match_keywords(lower_query, FOOD_DRINK_KEYWORDS) or match_keywords(
        lower_query, FOOD_DRINK_VERBS
    ):
        return "food_drink"
    if match_keywords(lower_query, TOILET_KEYWORDS):
        return "toilet"
    if match_keywords(lower_query, ACCESSIBILITY_KEYWORDS):
        return "accessibility"
    if match_keywords(lower_query, PHOTOGRAPHY_KEYWORDS):
        return "photography"
    if match_keywords(lower_query, CHILDREN_NOISE_KEYWORDS):
        return "children_noise"
    if match_keywords(lower_query, TEMPORARY_EXIT_KEYWORDS):
        return "temporary_exit"
    if match_pet_policy_keywords(lower_query):
        return "pets"
    if match_keywords(lower_query, FLOOR_LAYOUT_KEYWORDS):
        return "floor_layout"
    if match_keywords(lower_query, EXCLUSIVE_RENTAL_KEYWORDS):
        return "exclusive_rental"
    if match_keywords(lower_query, FACILITY_EQUIPMENT_KEYWORDS):
        return "facility"
    # basement: キーワード + regex パターン
    if match_keywords(lower_query, BASEMENT_KEYWORDS) or any(
        p.search(lower_query) for p in BASEMENT_PATTERNS
    ):
        return "basement"
    # meeting-room (basement に該当しなかった場合のみ)
    if match_keywords(lower_query, MEETING_ROOM_KEYWORDS):
        return "meeting-room"
    if match_keywords(lower_query, EVENT_KEYWORDS):
        return "event"
    if match_keywords(lower_query, SLIDE_KEYWORDS):
        return "slide"
    if match_keywords(lower_query, LOCATION_KEYWORDS):
        return "location"
    if match_keywords(lower_query, BOOKING_KEYWORDS):
        return "booking"
    if match_keywords(lower_query, RECEPTION_KEYWORDS):
        return "reception"

    return None
