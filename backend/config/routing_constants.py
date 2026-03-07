"""
ルーティング定数・キーワード・ヘルパー関数の集約モジュール

orchestrator_agent.py, memory_helper.py で共通使用される
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
    "general_knowledge",
    "slide",
    "farewell",
]

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

WIFI_KEYWORDS = ["wi-fi", "wifi", "ワイファイ", "インターネット", "internet", "ネット"]

BUSINESS_HOURS_KEYWORDS = [
    "営業時間",
    "何時まで",
    "何時から",
    "開いて",
    "閉まる",
    "いつまで",
    "休館日",
    "定休日",
    "お休み",
    "開館",
    "閉館",
    "opening hours",
    "business hours",
    "hours",
    "open",
    "close",
    "closed",
    "holiday",
    "what time",
    "when do you",
]

PRICING_KEYWORDS = [
    "料金",
    "いくら",
    "値段",
    "価格",
    "利用料",
    "cost",
    "price",
    "fee",
    "how much",
    "free",
    "フリー",
    "タダ",
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

FLOOR_KEYWORDS = [
    "2階",
    "二階",
    "2F",
    "2f",
    "3階",
    "三階",
    "3F",
    "3f",
    "地下",
    "B1",
    "b1",
    "地下1階",
]

FOOD_DRINK_VERBS = [
    "飲めますか",
    "食べられますか",
    "飲める",
    "食べられる",
    "注文",
    "オーダー",
]

EVENT_KEYWORDS = [
    "イベント",
    "勉強会",
    "セミナー",
    "ミートアップ",
    "ハッカソン",
    "LT会",
    "もくもく会",
    "交流会",
    "ブロックチェーン",
    "Web3",
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
    "歴史",
    "明治",
    "1909",
    "building",
    "architecture",
    "歴史的",
    "historic",
    "brick",
]

COMMUNITY_KEYWORDS = [
    "engineer cafe lab",
    "エンジニアカフェlab",
    "エンジニアカフェラボ",
    "eic",
    "会員制コミュニティ",
]

RECEPTION_KEYWORDS = [
    "registration",
    "初回利用",
    "利用方法",
    "check-in",
    "チェックイン",
    "初めて",
    "はじめて",
]

EMERGENCY_KEYWORDS = [
    "緊急",
    "地震",
    "火事",
    "火災",
    "避難",
    "AED",
    "救急",
    "警察",
    "救命",
    "emergency",
    "earthquake",
    "fire",
    "evacuate",
    "evacuation",
    "ambulance",
    "police",
    "first aid",
    "defibrillator",
]

LOST_FOUND_KEYWORDS = [
    "忘れ物",
    "落とし物",
    "なくした",
    "なくし",
    "失くした",
    "見つからない",
    "落とした",
    "紛失",
    "置き忘れ",
    "忘れた",
    "lost",
    "found",
    "missing",
    "left behind",
    "forgot",
    "lost and found",
    "misplaced",
]

FAREWELL_KEYWORDS = [
    "さようなら",
    "帰ります",
    "帰る",
    "退館",
    "お先に",
    "失礼します",
    "またね",
    "バイバイ",
    "おつかれ",
    "goodbye",
    "bye",
    "leaving",
    "going home",
    "see you",
    "heading out",
    "gotta go",
]

EARTHQUAKE_KEYWORDS = [
    "地震",
    "earthquake",
    "揺れ",
    "揺れて",
    "震度",
    "seismic",
]

FIRE_KEYWORDS = [
    "火事",
    "火災",
    "fire",
    "煙",
    "smoke",
    "燃えて",
    "burning",
]

MEDICAL_EMERGENCY_KEYWORDS = [
    "AED",
    "倒れ",
    "意識",
    "ambulance",
    "怪我",
    "けが",
    "出血",
    "bleeding",
    "心臓",
    "呼吸",
    "息ができない",
]

FLOOR_LAYOUT_KEYWORDS = [
    "フロア構成",
    "フロアマップ",
    "館内案内",
    "floor map",
    "floor plan",
    "フロアガイド",
    "館内図",
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

NEARBY_FACILITY_KEYWORDS = [
    "コンビニ",
    "ATM",
    "薬局",
    "病院",
    "ドラッグストア",
    "タクシー",
    "バス",
    "バス停",
    "タクシー乗り場",
    "近く",
    "近所",
    "周辺",
    "近隣",
    "そば",
    "convenience store",
    "pharmacy",
    "hospital",
    "clinic",
    "taxi",
    "bus",
    "bus stop",
    "taxi stand",
    "nearby",
    "around here",
    "close by",
    "neighborhood",
    "ホテル",
    "宿泊",
    "hotel",
    "accommodation",
    "ランチ",
    "レストラン",
    "lunch",
    "restaurant",
    "食事",
    "カフェ",
    "喫茶店",
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
    "メニュー",
    "サイノ",
    "food",
    "drink",
    "beverage",
    "eating",
    "bring food",
    "menu",
    "saino",
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
    "コンセント",
    "モニター",
    "3Dプリンター",
    "レーザーカッター",
    "何がある",
    "何があり",
    "利用できる",
    "equipment",
    "facility",
    "facilities",
    "outlet",
    "printer",
    "monitor",
]

EXCLUSIVE_RENTAL_KEYWORDS = [
    "貸切",
    "貸し切り",
    "企業研修",
    "exclusive",
    "rental",
    "研修",
]

TOILET_KEYWORDS = [
    "トイレ",
    "お手洗い",
    "おてあらい",
    "化粧室",
    "洗面所",
    "toilet",
    "restroom",
    "bathroom",
    "lavatory",
]

ACCESSIBILITY_KEYWORDS = [
    "車椅子",
    "バリアフリー",
    "エレベーター",
    "段差",
    "スロープ",
    "wheelchair",
    "accessible",
    "accessibility",
    "barrier-free",
    "elevator",
]

PHOTOGRAPHY_KEYWORDS = [
    "撮影",
    "写真",
    "カメラ",
    "photo",
    "photography",
    "camera",
]

CHILDREN_NOISE_KEYWORDS = [
    "子連れ",
    "子供",
    "ベビーカー",
    "騒音",
    "マナー",
    "children",
    "kids",
    "stroller",
    "noise",
]

POLICY_KEYWORDS = [
    *ACCESSIBILITY_KEYWORDS,
    *PHOTOGRAPHY_KEYWORDS,
    *CHILDREN_NOISE_KEYWORDS,
]


# =============================================================================
# 挨拶キーワード・テンプレート（時間帯別挨拶・閉館警告機能で使用）
# =============================================================================

# 挨拶キーワード（ルーターで挨拶意図を検出するために使用）
GREETING_KEYWORDS: list[str] = [
    "おはよう",
    "こんにちは",
    "こんばんは",
    "hello",
    "good morning",
    "good afternoon",
    "good evening",
    "hi",
    "hey",
]

# 時間帯別挨拶テンプレート
TIME_GREETING_TEMPLATES: dict[str, dict[str, str]] = {
    "morning": {
        "ja": "おはようございます！エンジニアカフェへようこそ。",
        "en": "Good morning! Welcome to Engineer Cafe.",
    },
    "afternoon": {
        "ja": "こんにちは！エンジニアカフェへようこそ。",
        "en": "Good afternoon! Welcome to Engineer Cafe.",
    },
    "evening": {
        "ja": "こんばんは！エンジニアカフェへようこそ。",
        "en": "Good evening! Welcome to Engineer Cafe.",
    },
    "night": {
        "ja": "こんばんは！エンジニアカフェへようこそ。",
        "en": "Good evening! Welcome to Engineer Cafe.",
    },
}

# 閉館警告テンプレート
CLOSING_WARNING_TEMPLATES: dict[str, str] = {
    "ja": "なお、閉館まであと約{minutes}分です。お忘れ物のないようご注意ください。",
    "en": "Please note that we will be closing in about {minutes} minutes. "
    "Please make sure you have all your belongings.",
}

# 休館日メッセージテンプレート
CLOSED_DAY_TEMPLATES: dict[str, str] = {
    "ja": "本日は休館日です。次の営業日にお越しください。",
    "en": "We are closed today. Please visit us on the next business day.",
}


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
    "event": ("イベントエージェント: " "イベント情報、勉強会、セミナーなどの予定を回答"),
    "general_knowledge": (
        "一般知識エージェント: " "上記以外の一般的な質問、" "および過去の会話履歴に関する質問に回答"
    ),
    "slide": ("スライドエージェント: " "スライドのナレーション、操作、質問応答を処理"),
    "farewell": (
        "退館エージェント: さようなら、帰ります等の退館メッセージに対して"
        "温かい退館メッセージ、受付カード返却案内、荷物確認リマインダーを応答"
    ),
}

CATEGORY_TO_AGENT_MAP: Dict[str, AgentNodeName] = {
    "facility-info": "facility",
    "saino-cafe": "business_info",
    "calendar": "event",
    "events": "event",
    "current-time": "general_knowledge",
    "general": "general_knowledge",
    "memory": "general_knowledge",
    "consultation": "business_info",
    "community": "business_info",
    "cafe-clarification-needed": "general_knowledge",
    "meeting-room-clarification-needed": "general_knowledge",
    "event-clarification-needed": "general_knowledge",
    "space-clarification-needed": "general_knowledge",
    # query_classifier._detect_specific_category が返すカテゴリ
    "pricing": "business_info",
    "facilities": "facility",
    "access": "facility",
    "hours": "business_info",
    "parking": "facility",
    "bicycle": "facility",
    "smoking": "facility",
    "food_drink": "facility",
    "policy": "facility",
    "emergency": "facility",
    "reception": "business_info",
    "floor_layout": "facility",
    "nearby": "facility",
    "lost_found": "facility",
    "farewell": "farewell",
}


# =============================================================================
# ヘルパー関数
# =============================================================================


def match_keywords(text: str, keywords: List[str]) -> bool:
    """テキストにキーワードリストのいずれかが含まれているか判定"""
    lower_text = text.lower()
    return any(kw.lower() in lower_text for kw in keywords)


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
    if match_keywords(lower_query, FAREWELL_KEYWORDS):
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
    if match_keywords(lower_query, FOOD_DRINK_KEYWORDS):
        return "food_drink"
    if match_keywords(lower_query, TOILET_KEYWORDS):
        return "toilet"
    if match_keywords(lower_query, ACCESSIBILITY_KEYWORDS):
        return "accessibility"
    if match_keywords(lower_query, PHOTOGRAPHY_KEYWORDS):
        return "photography"
    if match_keywords(lower_query, CHILDREN_NOISE_KEYWORDS):
        return "children_noise"
    if match_keywords(lower_query, LOCATION_KEYWORDS):
        return "location"
    if match_keywords(lower_query, BOOKING_KEYWORDS):
        return "booking"
    if match_keywords(lower_query, RECEPTION_KEYWORDS):
        return "reception"
    if match_keywords(lower_query, FLOOR_LAYOUT_KEYWORDS):
        return "floor_layout"
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
