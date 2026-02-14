"""
ルーティング定数・キーワード・ヘルパー関数の集約モジュール

orchestrator_agent.py, router_agent.py, memory_helper.py で共通使用される
キーワードリスト、マッピング、ヘルパー関数を一箇所に集約。

Note: このモジュールはリーフ依存（他のエージェントモジュールをimportしない）
"""

import re
from typing import Dict, List, Literal, Optional


# =============================================================================
# エージェントノード名の型定義
# =============================================================================

AgentNodeName = Literal[
    "business_info",
    "facility",
    "event",
    "memory_agent",
    "general_knowledge",
    "clarification",
    "slide",
]

RoutingTarget = Literal[
    "business_info",
    "facility",
    "event",
    "memory_agent",
    "general_knowledge",
    "clarification",
    "slide",
    "__end__",
]

AgentName = Literal[
    "BusinessInfoAgent",
    "FacilityAgent",
    "EventAgent",
    "MemoryAgent",
    "GeneralKnowledgeAgent",
    "ClarificationAgent",
    "TimeAgent",
    "SlideAgent",
]


# =============================================================================
# キーワード定数
# =============================================================================

WIFI_KEYWORDS = ["wi-fi", "wifi", "ワイファイ", "インターネット", "internet", "ネット"]

BUSINESS_HOURS_KEYWORDS = [
    "営業時間",
    "何時まで",
    "何時から",
    "開いて",
    "閉まる",
    "いつまで",
    "opening hours",
    "business hours",
    "hours",
    "open",
    "close",
    "what time",
    "when do you",
]

PRICING_KEYWORDS = [
    "料金",
    "いくら",
    "値段",
    "価格",
    "cost",
    "price",
    "fee",
    "how much",
]

BASEMENT_KEYWORDS = [
    "地下",
    "basement",
    "b1",
    "mtgスペース",
    "集中スペース",
    "階下",
    "ちか",
    "チカ",
    "underground",
    "アンダースペース",
    "makersスペース",
    "focus space",
    "meeting space",
    "makers space",
]

BASEMENT_PATTERNS = [
    re.compile(r"地下.*スペース"),
    re.compile(r"地下.*施設"),
    re.compile(r"地下.*会議"),
    re.compile(r"ちか.*ミーティング"),
    re.compile(r"ちか.*スペース"),
]

MEETING_ROOM_KEYWORDS = [
    "会議室",
    "meeting room",
    "ミーティングルーム",
    "会議スペース",
]

EVENT_KEYWORDS = [
    "イベント",
    "勉強会",
    "セミナー",
    "ミートアップ",
    "event",
    "workshop",
    "meetup",
    "seminar",
]

SLIDE_KEYWORDS = [
    "スライド",
    "プレゼン",
    "次のスライド",
    "前のスライド",
    "slide",
    "presentation",
    "説明して",
    "ナレーション",
    "narration",
]

CONSULTATION_KEYWORDS = [
    "相談",
    "アドバイス",
    "カウンセリング",
    "キャリア",
    "スキルチェンジ",
    "転職",
    "コミュニティマネージャー",
    "consultation",
    "advice",
    "career",
    "counseling",
]

ACCESS_DIRECTION_KEYWORDS = [
    # FROM station TO cafe
    "行き方",
    "道順",
    "最寄り駅",
    "最寄り",
    "たどり着",
    "行く方法",
    "来る方法",
    "来方",
    "directions",
    "how to get",
    # FROM cafe TO station (bidirectional - agent is at reception)
    "駅まで",
    "駅への",
    "帰り方",
    "帰り道",
    "帰る方法",
    "出口",
    "最寄り駅まで",
    "駅に行く",
    "how to get to the station",
    "nearest station from here",
    "way to the station",
    "exit",
]

BUILDING_KEYWORDS = [
    "建物",
    "ビル",
    "赤煉瓦",
    "文化館",
    "重要文化財",
    "building",
    "architecture",
    "歴史的",
]

COMMUNITY_KEYWORDS = [
    "engineer cafe lab",
    "エンジニアカフェlab",
    "エンジニアカフェラボ",
    "eic",
    "会員制コミュニティ",
]

MEMORY_KEYWORDS = [
    "さっき",
    "前に",
    "覚えて",
    "記憶",
    "聞いた",
    "話した",
    "何を",
    "言った",
    "会話",
    "履歴",
    "先ほど",
    "remember",
    "earlier",
    "previous",
    "asked",
    "said",
]

# 除外キーワード（メモリ判定で使用）
MEMORY_EXCLUSION_BUSINESS = [
    "メニュー",
    "料金",
    "営業時間",
    "場所",
    "設備",
    "saino",
    "エンジニアカフェ",
]

MEMORY_EXCLUSION_FACILITY = ["地下", "スペース", "会議室", "施設"]

# RouterAgent用の拡張メモリキーワード
MEMORY_KEYWORDS_EXTENDED = [
    *MEMORY_KEYWORDS,
    "質問",
    "どんな",
    "先ほど",
    "recall",
    "before",
    "mentioned",
    "conversation",
    "history",
    "what did i",
]

# RouterAgent用の拡張メモリ除外キーワード
MEMORY_EXCLUSION_BUSINESS_EXTENDED = [
    *MEMORY_EXCLUSION_BUSINESS,
    "menu",
    "price",
    "pricing",
    "hours",
    "location",
    "access",
    "facility",
    "サイノカフェ",
    "engineer",
]

MEMORY_EXCLUSION_FACILITY_EXTENDED = [
    *MEMORY_EXCLUSION_FACILITY,
    "basement",
    "space",
    "mtg",
    "facility",
    "equipment",
    "makers",
]

# "もう一つ" 系パターン（RouterAgentで使用）
OTHER_ONE_PATTERNS = [
    "もう一つ",
    "もうひとつ",
    "もう1つ",
    "もう一方",
    "もう片方",
    "他の方",
    "ほかの方",
    "別の方",
    "そっち",
    "あっち",
    "the other",
    "other one",
    "other option",
    "the alternative",
]

PARKING_KEYWORDS = [
    "駐車場",
    "駐車",
    "パーキング",
    "車を停め",
    "車を止め",
    "parking",
    "park",
    "car park",
]

BICYCLE_KEYWORDS = [
    "駐輪場",
    "駐輪",
    "自転車",
    "バイク置き場",
    "bicycle",
    "bike parking",
    "cycle",
]

SMOKING_KEYWORDS = [
    "喫煙",
    "タバコ",
    "たばこ",
    "煙草",
    "禁煙",
    "smoking",
    "cigarette",
    "smoke",
]

FOOD_DRINK_KEYWORDS = [
    "飲食",
    "食べ物",
    "飲み物",
    "持ち込み",
    "食事",
    "ドリンク",
    "food",
    "drink",
    "beverage",
    "eating",
    "bring food",
]

BOOKING_KEYWORDS = [
    "予約",
    "booking",
    "book",
    "reservation",
    "reserve",
]

FACILITY_EQUIPMENT_KEYWORDS = [
    "設備",
    "電源",
    "プリンター",
    "何がある",
    "何があり",
    "利用できる",
    "equipment",
    "facility",
    "facilities",
    "outlet",
    "printer",
]


# =============================================================================
# エージェント説明・マッピング
# =============================================================================

AGENT_DESCRIPTIONS: Dict[str, str] = {
    "business_info": "営業情報エージェント: 営業時間、料金、場所、相談（キャリア・スキルチェンジ等）、コミュニティ（Engineer Cafe Lab等）など施設の基本情報・サービスを回答",
    "facility": "施設エージェント: Wi-Fi、電源、会議室、地下スペース、建物の歴史・構造、アクセス方法・行き方など設備・物理施設に関する情報を回答",
    "event": "イベントエージェント: イベント情報、勉強会、セミナーなどの予定を回答",
    "memory_agent": "メモリエージェント: 過去の会話履歴に関する質問に回答（「さっき何を聞いた？」など）",
    "general_knowledge": "一般知識エージェント: 上記以外の一般的な質問に回答",
    "clarification": "明確化エージェント: 曖昧な質問に対して詳細を確認",
    "slide": "スライドエージェント: スライドのナレーション、操作、質問応答を処理",
}

CATEGORY_TO_AGENT_MAP: Dict[str, AgentNodeName] = {
    "facility-info": "facility",
    "saino-cafe": "business_info",
    "calendar": "event",
    "events": "event",
    "current-time": "general_knowledge",
    "general": "general_knowledge",
    "memory": "memory_agent",
    "consultation": "business_info",
    "community": "business_info",
    "cafe-clarification-needed": "clarification",
    "meeting-room-clarification-needed": "clarification",
    # query_classifier._detect_specific_category が返すカテゴリ
    "pricing": "business_info",
    "facilities": "facility",
    "access": "facility",
    "hours": "business_info",
    "parking": "facility",
    "bicycle": "facility",
    "smoking": "facility",
    "food_drink": "facility",
}


# =============================================================================
# ヘルパー関数
# =============================================================================


def match_keywords(text: str, keywords: List[str]) -> bool:
    """テキストにキーワードリストのいずれかが含まれているか判定"""
    lower_text = text.lower()
    return any(kw in lower_text for kw in keywords)


LOCATION_KEYWORDS = ["場所", "どこ", "アクセス", "住所", "location", "where", "address"]


def extract_request_type(query: str) -> Optional[str]:
    """
    クエリから具体的なリクエストタイプを抽出

    RouterAgent と memory_helper で共通使用される統合版。
    basement は regex パターンにも対応。

    Args:
        query: ユーザーからのクエリ

    Returns:
        リクエストタイプ（wifi, hours, price等）またはNone
    """
    lower_query = query.lower()

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
    if match_keywords(lower_query, FOOD_DRINK_KEYWORDS):
        return "food_drink"
    if match_keywords(lower_query, LOCATION_KEYWORDS):
        return "location"
    if match_keywords(lower_query, BOOKING_KEYWORDS):
        return "booking"
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

    return None
