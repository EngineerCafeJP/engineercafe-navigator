"""Shared keyword intent classification for routing and filler audio."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from backend.config.routing_constants import (
    ACCESSIBILITY_KEYWORDS,
    ACCESS_DIRECTION_KEYWORDS,
    BASEMENT_KEYWORDS,
    BICYCLE_KEYWORDS,
    BUILDING_KEYWORDS,
    BUSINESS_HOURS_KEYWORDS,
    CHILDREN_NOISE_KEYWORDS,
    COMMUNITY_KEYWORDS,
    CONSULTATION_KEYWORDS,
    CONTACT_KEYWORDS,
    EMERGENCY_KEYWORDS,
    EXCLUSIVE_RENTAL_KEYWORDS,
    EVENT_KEYWORDS,
    FACILITY_EQUIPMENT_KEYWORDS,
    FLOOR_KEYWORDS,
    FLOOR_LAYOUT_KEYWORDS,
    FOOD_DRINK_KEYWORDS,
    FOOD_DRINK_VERBS,
    GREETING_KEYWORDS,
    LOST_FOUND_KEYWORDS,
    MEETING_ROOM_KEYWORDS,
    PARKING_KEYWORDS,
    PHOTOGRAPHY_KEYWORDS,
    PRICING_KEYWORDS,
    RECEPTION_KEYWORDS,
    SLIDE_KEYWORDS,
    SMOKING_KEYWORDS,
    TEMPORARY_EXIT_KEYWORDS,
    TOILET_KEYWORDS,
    WIFI_KEYWORDS,
    extract_request_type,
    match_farewell_keywords,
    match_keywords,
    match_pet_policy_keywords,
)
from backend.utils.cafe_entity import (
    is_ambiguous_cafe_hours_query,
    is_saino_reference,
    resolve_cafe_entity,
)
from backend.utils.intent_profile import is_assistant_profile_question
from backend.utils.query_classifier import QueryClassifier

_MATA_KIMASU_FAREWELL_RE = re.compile(r"また\s*来(ます|る|るね|ますね)\s*[。!！?？\.]?\s*$")
_SERVICE_INTENT_RE = re.compile(r"(受付|予約|会員|問合せ|問い合わせ)")
_RECEPTION_SOCIAL_NICETY_MARKERS = (
    "お元気ですか",
    "元気ですか",
    "調子はいかが",
    "調子はどう",
    "how are you",
)
_RECEPTION_CONTINUATION_STRIP_CHARS = "!！?？。、., \t\n\r"

FILLER_INTENTS = frozenset(
    {
        "greeting",
        "business_info",
        "facility",
        "event",
        "wifi",
        "general",
        "thinking",
        "fallback",
        "emergency",
        "slide",
    }
)


def _matches_any_lower(lower_query: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword.lower() in lower_query for keyword in keywords)


def _matches_pricing_intent(lower_query: str) -> bool:
    """Match pricing intent without treating the "fee" inside "coffee" as a hit."""
    english_terms = ("cost", "price", "fee", "free")
    if any(re.search(rf"\b{re.escape(term)}\b", lower_query) for term in english_terms):
        return True
    if "how much" in lower_query:
        return True

    guarded_terms = set(english_terms) | {"how much"}
    return any(
        keyword.lower() in lower_query
        for keyword in PRICING_KEYWORDS
        if keyword.lower() not in guarded_terms
    )


@dataclass(frozen=True)
class FastIntent:
    agent: str
    category: str
    request_type: str
    reasoning: str

    def as_route(self) -> dict[str, str]:
        return {
            "agent": self.agent,
            "category": self.category,
            "request_type": self.request_type,
            "reasoning": self.reasoning,
        }


def is_daily_conversation_request(lower_query: str) -> bool:
    """Detect lightweight small-talk requests that should not invoke search."""
    markers = (
        "雑談",
        "おしゃべり",
        "少し話",
        "ちょっと話",
        "話し相手",
        "元気",
        "疲れた",
        "お疲れ様",
        "ひま",
        "暇",
        "退屈",
        "さみしい",
        "ありがとう",
        "サンキュー",
        "軽く話",
        "ちょっと話して",
        "相手して",
        "small talk",
        "chat with me",
        "talk with me",
        "talk to me",
        "how are you",
        "i am tired",
        "i'm tired",
        "thanks",
        "thank you",
    )
    return any(marker in lower_query for marker in markers)


def is_reception_continuation_utterance(query: str) -> bool:
    """Detect greetings/social niceties that should keep active reception open.

    This is intentionally narrower than daily_conversation. Explicit requests
    like "少し雑談して" should still route to the normal daily conversation path,
    while "こんにちは" and "こんにちは、お元気ですか" should behave like a
    receptionist acknowledging the visitor and asking for their purpose.
    """
    lower_query = query.lower().strip()
    if not lower_query:
        return False

    has_greeting = match_keywords(lower_query, GREETING_KEYWORDS)
    has_social_nicety = any(marker in lower_query for marker in _RECEPTION_SOCIAL_NICETY_MARKERS)
    if not has_greeting and not has_social_nicety:
        return False

    remaining = lower_query
    for keyword in sorted(GREETING_KEYWORDS, key=len, reverse=True):
        remaining = remaining.replace(keyword.lower(), " ")
    for marker in _RECEPTION_SOCIAL_NICETY_MARKERS:
        remaining = remaining.replace(marker, " ")
    remaining = remaining.strip(_RECEPTION_CONTINUATION_STRIP_CHARS)

    return not remaining


def is_current_info_request(lower_query: str) -> bool:
    """Detect daily receptionist questions that need current external facts."""
    if QueryClassifier._is_date_only_query(lower_query):
        return True

    current_markers = (
        "今日",
        "明日",
        "今朝",
        "今夜",
        "今週",
        "最新",
        "現在",
        "ニュース",
        "天気",
        "気温",
        "雨",
        "today",
        "tomorrow",
        "this week",
        "latest",
        "current",
        "news",
        "weather",
        "temperature",
        "rain",
    )
    return any(marker in lower_query for marker in current_markers)


def is_current_time_request(lower_query: str) -> bool:
    """Detect exact current-time questions that should use the system clock."""
    classifier = QueryClassifier()
    normalized = classifier._normalize_query(lower_query)
    if QueryClassifier._is_date_only_query(normalized):
        return False
    return classifier._is_current_time_query(normalized)


def classify_fast_intent(query: str) -> Optional[FastIntent]:
    """Return the same fast keyword route used by the orchestrator."""
    lower_query = query.lower()

    if is_assistant_profile_question(lower_query):
        return FastIntent(
            agent="general_knowledge",
            category="assistant_profile",
            request_type="assistant_profile",
            reasoning="Assistant profile/capability question detected",
        )

    farewell_substring_hit = match_farewell_keywords(lower_query)
    farewell_anchored_hit = bool(_MATA_KIMASU_FAREWELL_RE.search(query))
    has_service_intent = bool(_SERVICE_INTENT_RE.search(query))
    has_emergency = match_keywords(lower_query, EMERGENCY_KEYWORDS)

    # Farewell before daily_conversation so thanks + また来ます routes out (Q-FAREWELL-JA-001).
    # Emergency and service-intent tokens must keep their more specific routing flows.
    if (
        (farewell_substring_hit or farewell_anchored_hit)
        and not has_emergency
        and not has_service_intent
    ):
        return FastIntent(
            "farewell",
            "farewell",
            "farewell",
            "Farewell keyword detected",
        )

    has_explicit_service_intent = any(
        match_keywords(lower_query, keywords)
        for keywords in (
            WIFI_KEYWORDS,
            BUSINESS_HOURS_KEYWORDS,
            PRICING_KEYWORDS,
            EVENT_KEYWORDS,
            COMMUNITY_KEYWORDS,
            CONSULTATION_KEYWORDS,
            ACCESS_DIRECTION_KEYWORDS,
            FACILITY_EQUIPMENT_KEYWORDS,
            CONTACT_KEYWORDS,
            FLOOR_LAYOUT_KEYWORDS,
            RECEPTION_KEYWORDS,
        )
    )

    if is_daily_conversation_request(lower_query) and not has_explicit_service_intent:
        return FastIntent(
            agent="general_knowledge",
            category="daily_conversation",
            request_type="daily_conversation",
            reasoning="Daily conversation request detected",
        )

    if has_emergency:
        return FastIntent("facility", "emergency", "emergency", "Emergency keyword detected")

    if _is_rain_route_query(lower_query):
        return FastIntent("facility", "facility-info", "access", "Rain route query detected")

    if match_keywords(lower_query, LOST_FOUND_KEYWORDS):
        return FastIntent(
            "facility", "facility-info", "lost_found", "Lost-and-found keyword detected"
        )

    if match_keywords(lower_query, GREETING_KEYWORDS):
        stripped = lower_query.strip()
        remaining = stripped
        for kw in sorted(GREETING_KEYWORDS, key=len, reverse=True):
            remaining = remaining.replace(kw.lower(), "").strip()
        remaining = remaining.strip("!！?？。、.,  ")
        if len(remaining) <= 3:
            return FastIntent(
                "business_info",
                "greeting",
                "greeting",
                f"Greeting keyword detected: {stripped[:30]}",
            )

    if is_current_time_request(lower_query):
        return FastIntent(
            "general_knowledge",
            "current-time",
            "current-time",
            "Current time request detected",
        )

    cafe_entity = resolve_cafe_entity(query)
    if cafe_entity == "saino":
        request_type = "general"
        if match_keywords(lower_query, BUSINESS_HOURS_KEYWORDS):
            request_type = "hours"
        elif _matches_pricing_intent(lower_query):
            request_type = "price"
        elif match_keywords(lower_query, FOOD_DRINK_KEYWORDS) or match_keywords(
            lower_query, FOOD_DRINK_VERBS
        ):
            request_type = "food_drink"
        else:
            request_type = extract_request_type(lower_query) or request_type
        return FastIntent(
            "business_info",
            "saino-cafe",
            request_type,
            "Saino cafe reference detected",
        )

    if cafe_entity == "ambiguous-cafe" and (
        any(kw in lower_query for kw in ["どっち", "どちら", "which"])
        or match_keywords(lower_query, BUSINESS_HOURS_KEYWORDS)
        or match_keywords(lower_query, PRICING_KEYWORDS)
        or match_keywords(lower_query, ACCESS_DIRECTION_KEYWORDS)
    ):
        return FastIntent(
            "general_knowledge",
            "cafe-clarification-needed",
            "clarification",
            "Ambiguous cafe reference detected",
        )

    if is_ambiguous_cafe_hours_query(lower_query):
        return FastIntent(
            "general_knowledge",
            "cafe-clarification-needed",
            "clarification",
            "Ambiguous cafe entity for hours query",
        )

    if _is_engineer_cafe_overview_query(lower_query):
        return FastIntent(
            "business_info",
            "general",
            "general",
            "Engineer Cafe overview query detected",
        )

    if is_saino_reference(lower_query) and match_keywords(lower_query, BUSINESS_HOURS_KEYWORDS):
        return FastIntent(
            "business_info",
            "saino-cafe",
            "hours",
            "Saino cafe hours query detected",
        )

    if match_keywords(lower_query, WIFI_KEYWORDS):
        return FastIntent("facility", "facility-info", "wifi", "Wi-Fi keyword detected")
    if match_keywords(lower_query, BUSINESS_HOURS_KEYWORDS):
        return FastIntent(
            "business_info", "business-hours", "hours", "Business hours keyword detected"
        )
    if self_or_static_community := _static_community_program_route(lower_query):
        return self_or_static_community
    if any(kw in lower_query for kw in MEETING_ROOM_KEYWORDS) and match_keywords(
        lower_query, PRICING_KEYWORDS
    ):
        return FastIntent(
            "facility",
            "facility-info",
            "meeting_room",
            "Meeting room pricing query detected",
        )
    if _is_3d_printer_price_query(lower_query):
        return FastIntent(
            "facility",
            "facility-info",
            "facility",
            "3D printer filament pricing query detected",
        )
    if match_keywords(lower_query, PRICING_KEYWORDS):
        return FastIntent("business_info", "pricing", "price", "Pricing keyword detected")
    if _is_maker_space_equipment_query(lower_query):
        return FastIntent(
            "facility",
            "facility-info",
            "facility",
            "Maker space equipment query detected",
        )
    if match_keywords(lower_query, BASEMENT_KEYWORDS):
        return FastIntent(
            "facility", "basement-facility", "basement", "Basement facility keyword detected"
        )
    if match_keywords(lower_query, EVENT_KEYWORDS):
        return FastIntent("event", "events", "event", "Event keyword detected")
    if match_keywords(lower_query, SLIDE_KEYWORDS):
        return FastIntent("slide", "slide", "slide", "Slide keyword detected")
    if match_keywords(lower_query, COMMUNITY_KEYWORDS):
        return FastIntent(
            "business_info", "community", "community", "Community/program keyword detected"
        )
    if match_keywords(lower_query, CONSULTATION_KEYWORDS):
        return FastIntent(
            "business_info", "consultation", "consultation", "Consultation keyword detected"
        )
    if match_keywords(lower_query, ACCESS_DIRECTION_KEYWORDS):
        return FastIntent(
            "facility", "facility-info", "access", "Access/direction keyword detected"
        )
    if match_keywords(lower_query, EXCLUSIVE_RENTAL_KEYWORDS):
        return FastIntent(
            "facility",
            "facility-info",
            "exclusive_rental",
            "Exclusive rental keyword detected",
        )
    if match_keywords(lower_query, FACILITY_EQUIPMENT_KEYWORDS):
        return FastIntent(
            "facility", "facility-info", "facility", "Facility equipment keyword detected"
        )
    if _is_nearby_facility_query(lower_query):
        return FastIntent("facility", "facility-info", "nearby", "Nearby facility keyword detected")
    if match_keywords(lower_query, BUILDING_KEYWORDS):
        return FastIntent("facility", "facility-info", "building", "Building keyword detected")
    if match_keywords(lower_query, PARKING_KEYWORDS):
        return FastIntent("facility", "facility-info", "parking", "Parking keyword detected")
    if match_keywords(lower_query, BICYCLE_KEYWORDS):
        return FastIntent(
            "facility", "facility-info", "bicycle", "Bicycle parking keyword detected"
        )
    if match_keywords(lower_query, SMOKING_KEYWORDS):
        return FastIntent("facility", "facility-info", "smoking", "Smoking policy keyword detected")
    if match_keywords(lower_query, TOILET_KEYWORDS):
        return FastIntent("facility", "facility-info", "toilet", "Toilet/restroom keyword detected")
    if match_keywords(lower_query, ACCESSIBILITY_KEYWORDS):
        return FastIntent(
            "facility",
            "facility-info",
            "accessibility",
            "Accessibility/wheelchair keyword detected",
        )
    if match_keywords(lower_query, PHOTOGRAPHY_KEYWORDS):
        return FastIntent(
            "facility", "facility-info", "photography", "Photography policy keyword detected"
        )
    if match_keywords(lower_query, CHILDREN_NOISE_KEYWORDS):
        return FastIntent(
            "facility",
            "facility-info",
            "children_noise",
            "Children/noise policy keyword detected",
        )
    if match_keywords(lower_query, TEMPORARY_EXIT_KEYWORDS):
        return FastIntent(
            "facility",
            "facility-info",
            "temporary_exit",
            "Temporary exit policy keyword detected",
        )
    if match_pet_policy_keywords(lower_query):
        return FastIntent(
            "facility",
            "facility-info",
            "pets",
            "Pet policy keyword detected",
        )
    if match_keywords(lower_query, CONTACT_KEYWORDS):
        return FastIntent(
            "business_info",
            "contact",
            "contact",
            "Contact keyword detected",
        )
    if match_keywords(lower_query, FLOOR_LAYOUT_KEYWORDS):
        return FastIntent(
            "facility", "facility-info", "floor_layout", "Floor layout/map keyword detected"
        )
    if any(kw in lower_query for kw in MEETING_ROOM_KEYWORDS) and any(
        kw in lower_query for kw in FLOOR_KEYWORDS
    ):
        return FastIntent(
            "facility",
            "facility-info",
            "meeting_room",
            "Meeting room with floor info detected",
        )
    if any(kw in lower_query for kw in FOOD_DRINK_VERBS):
        return FastIntent("facility", "facility-info", "food_drink", "Food/drink verb detected")
    if match_keywords(lower_query, FOOD_DRINK_KEYWORDS):
        return FastIntent(
            "facility", "facility-info", "food_drink", "Food/drink policy keyword detected"
        )
    # Reception stays before current_info so 今日 + 再受付 is not misclassified (Q-RECV-JA-002),
    # but after specific facility/event/business intents so broad 初めて does not preempt them.
    if match_keywords(lower_query, RECEPTION_KEYWORDS):
        return FastIntent(
            "business_info", "reception", "reception", "Reception/check-in keyword detected"
        )
    if is_current_info_request(lower_query):
        return FastIntent(
            "general_knowledge",
            "current_info",
            "current_info",
            "Current-information small-talk request detected",
        )

    return None


def _static_community_program_route(lower_query: str) -> Optional[FastIntent]:
    """Keep EIC/DevDay ground-truth questions on static community knowledge."""
    program_markers = ("engineer ignition camp", "eic", "devday")
    if not any(marker in lower_query for marker in program_markers):
        return None

    static_question_markers = (
        "とは",
        "何",
        "なに",
        "いつ",
        "when",
        "what",
        "修了",
        "条件",
        "開催",
        "about",
    )
    if any(marker in lower_query for marker in static_question_markers):
        return FastIntent(
            "business_info",
            "community",
            "community",
            "Static community/program keyword detected",
        )
    return None


def _is_nearby_facility_query(lower_query: str) -> bool:
    proximity_markers = (
        "周辺",
        "近く",
        "近所",
        "近隣",
        "そば",
        "nearby",
        "around here",
        "close by",
    )
    target_markers = (
        "ランチ",
        "レストラン",
        "食事",
        "コンビニ",
        "病院",
        "クリニック",
        "ホテル",
        "宿泊",
        "lunch",
        "restaurant",
        "convenience store",
        "clinic",
        "hospital",
        "hotel",
        "accommodation",
    )
    return any(marker in lower_query for marker in proximity_markers) and any(
        marker in lower_query for marker in target_markers
    )


def _is_rain_route_query(lower_query: str) -> bool:
    rain_markers = ("雨の日", "雨天", "rainy", "rain route")
    route_markers = ("ルート", "行き方", "行く", "最短", "route", "access")
    return any(marker in lower_query for marker in rain_markers) and any(
        marker in lower_query for marker in route_markers
    )


def _is_engineer_cafe_overview_query(lower_query: str) -> bool:
    if any(
        match_keywords(lower_query, keywords)
        for keywords in (
            BUSINESS_HOURS_KEYWORDS,
            PRICING_KEYWORDS,
            ACCESS_DIRECTION_KEYWORDS,
            CONTACT_KEYWORDS,
            WIFI_KEYWORDS,
            EVENT_KEYWORDS,
            FACILITY_EQUIPMENT_KEYWORDS,
        )
    ):
        return False

    cafe_markers = (
        "エンジニアカフェ",
        "engineer cafe",
        "工程师咖啡",
        "工程師咖啡",
        "엔지니어 카페",
        "엔지니어카페",
    )
    overview_markers = (
        "って何",
        "とは",
        "何ですか",
        "なにですか",
        "どんなところ",
        "どんな場所",
        "紹介",
        "tell me about",
        "what is",
        "what's",
        "about engineer cafe",
        "是什么",
        "是什麼",
        "뭐",
        "무엇",
        "어떤 곳",
        "소개",
    )
    return any(marker in lower_query for marker in cafe_markers) and any(
        marker in lower_query for marker in overview_markers
    )


def _is_maker_space_equipment_query(lower_query: str) -> bool:
    maker_markers = (
        "maker'sスペース",
        "makersスペース",
        "メーカースペース",
        "maker's space",
        "makers space",
    )
    equipment_markers = (
        "機材",
        "設備",
        "使え",
        "利用",
        "何が",
        "どんな",
        "equipment",
        "facilities",
        "available",
    )
    return any(marker in lower_query for marker in maker_markers) and any(
        marker in lower_query for marker in equipment_markers
    )


def _is_3d_printer_price_query(lower_query: str) -> bool:
    printer_markers = ("3dプリンター", "3d printer", "3d打印", "3d 프린터")
    material_markers = ("フィラメント", "filament", "材料", "素材", "耗材")
    price_markers = (
        "料金",
        "価格",
        "費用",
        "値段",
        "いくら",
        "price",
        "fee",
        "cost",
        "收费",
        "费用",
    )
    has_printer_or_material = any(marker in lower_query for marker in printer_markers) or any(
        marker in lower_query for marker in material_markers
    )
    return has_printer_or_material and any(marker in lower_query for marker in price_markers)


def filler_intent_for_query(query: str) -> str:
    """Map a user query to the static filler catalog."""
    lower_query = query.lower()

    if _matches_any_lower(lower_query, WIFI_KEYWORDS):
        return "wifi"
    if _matches_any_lower(lower_query, EMERGENCY_KEYWORDS):
        return "emergency"
    if _matches_any_lower(lower_query, EVENT_KEYWORDS):
        return "event"
    if _matches_any_lower(lower_query, SLIDE_KEYWORDS):
        return "slide"
    if _matches_any_lower(lower_query, GREETING_KEYWORDS):
        stripped = lower_query.strip()
        remaining = stripped
        for keyword in sorted(GREETING_KEYWORDS, key=len, reverse=True):
            remaining = remaining.replace(keyword.lower(), "").strip()
        if len(remaining.strip("!！?？。、.,  ")) <= 3:
            return "greeting"

    if _matches_any_lower(
        lower_query,
        BUSINESS_HOURS_KEYWORDS
        + PRICING_KEYWORDS
        + COMMUNITY_KEYWORDS
        + CONSULTATION_KEYWORDS
        + CONTACT_KEYWORDS
        + RECEPTION_KEYWORDS,
    ):
        return "business_info"

    if (
        _matches_any_lower(
            lower_query,
            ACCESS_DIRECTION_KEYWORDS
            + FACILITY_EQUIPMENT_KEYWORDS
            + BASEMENT_KEYWORDS
            + BUILDING_KEYWORDS
            + PARKING_KEYWORDS
            + BICYCLE_KEYWORDS
            + SMOKING_KEYWORDS
            + EXCLUSIVE_RENTAL_KEYWORDS
            + TOILET_KEYWORDS
            + ACCESSIBILITY_KEYWORDS
            + PHOTOGRAPHY_KEYWORDS
            + CHILDREN_NOISE_KEYWORDS
            + TEMPORARY_EXIT_KEYWORDS
            + FLOOR_LAYOUT_KEYWORDS
            + FLOOR_KEYWORDS
            + FOOD_DRINK_KEYWORDS
            + FOOD_DRINK_VERBS,
        )
        or match_pet_policy_keywords(lower_query)
        or _is_nearby_facility_query(lower_query)
        or _is_rain_route_query(lower_query)
    ):
        return "facility"

    if is_assistant_profile_question(lower_query) or is_current_info_request(lower_query):
        return "general"

    return "thinking"
