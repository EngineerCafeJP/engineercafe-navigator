"""
ルーティング定数・キーワード・ヘルパー関数の集約モジュール

orchestrator_agent.py, memory_helper.py で共通使用される
キーワードリスト、マッピング、ヘルパー関数を一箇所に集約。

Note: このモジュールはリーフ依存（他のエージェントモジュールをimportしない）
"""

import re
from typing import Dict, List, Literal, Optional, TypeAlias, cast

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

WIFI_KEYWORDS = [
    "wi-fi",
    "wifi",
    "ワイファイ",
    "インターネット",
    "internet",
    "ネット",
    "无线网",
    "無線網",
    "wifi密码",
    "wifi密碼",
    "와이파이",
    "무선인터넷",
    "비밀번호",
]

BUSINESS_HOURS_KEYWORDS = [
    "営業時間",
    "最終受付",
    "受付時間",
    "土日",
    "土日祝",
    "土日祝日",
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
    "last reception",
    "reception hours",
    "hours",
    "open",
    "close",
    "closed",
    "holiday",
    "what time",
    "when do you",
    "营业时间",
    "營業時間",
    "几点",
    "幾點",
    "开放时间",
    "운영 시간",
    "운영시간",
    "이용 시간",
    "이용시간",
    "영업시간",
    "몇 시",
    "몇시",
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
    "收费",
    "费用",
    "多少錢",
    "多少钱",
    "요금",
    "비용",
    "얼마",
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
    "maker'sスペース",
    "makersスペース",
    "メーカースペース",
    "maker's space",
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
    "飲みたい",
    "食べたい",
    "休憩したい",
    "休みたい",
    "一息つきたい",
    "注文",
    "注文したい",
    "オーダー",
    "飲みは可能",
    "飲んでいい",
    "飲めます",
    "飲み物を飲む",
    "休憩できますか",
    "休めますか",
    "want to drink",
    "want to eat",
    "want coffee",
    "grab a coffee",
    "take a break",
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
    "connpass",
    "活动",
    "活動",
    "이벤트",
    "행사",
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
    "how do i get",
    "在哪里",
    "在哪裡",
    "位置",
    "어디",
    "위치",
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
    "空港",
    "福岡空港",
    "博多駅",
    "airport",
    "fukuoka airport",
    "hakata station",
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
    "engineer ignition camp",
    "eic",
    "engineer friendly city",
    "エンジニアフレンドリーシティ",
    "devday",
    "会員制コミュニティ",
]

RECEPTION_KEYWORDS = [
    "membership",
    "member benefits",
    "member number",
    "member card",
    "member registration",
    "become a member",
    "register",
    "sign up",
    "registration",
    "reception",
    "初回利用",
    "利用方法",
    "受付手続き",
    "受付で何を",
    "受け付けで何を",
    "受け付け",
    "入館できますか",
    "入館",
    "手続きは完了",
    "これで完了",
    "社会利用",
    "再受付",
    "会員番号",
    "会員カード",
    "受付カード",
    "予約なし",
    "予約不要",
    "check-in",
    "check in",
    "チェックイン",
    "first-time",
    "first time",
    "初めて",
    "はじめて",
    "また来ました",
    "前にも来た",
    "前にも来たこと",
    "returning visitor",
    "registered before",
    "without a reservation",
    "no reservation",
    "第一次",
    "会员登记",
    "會員登記",
    "처음 방문",
    "회원 등록",
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
    "left my",
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

ENGLISH_FAREWELL_KEYWORDS = [
    "goodbye",
    "bye",
    "leaving",
    "going home",
    "see you",
    "heading out",
    "gotta go",
]

JAPANESE_FAREWELL_KEYWORDS = [
    keyword for keyword in FAREWELL_KEYWORDS if keyword not in ENGLISH_FAREWELL_KEYWORDS
]


def _compile_english_farewell_pattern(keyword: str) -> re.Pattern:
    escaped_keyword = re.escape(keyword).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped_keyword}(?![a-z0-9])")


ENGLISH_FAREWELL_PATTERNS = [
    _compile_english_farewell_pattern(keyword) for keyword in ENGLISH_FAREWELL_KEYWORDS
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
    "前にも来た",
    "また来ました",
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
    "흡연",
    "금연",
    "담배",
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
    "コーヒー",
    "珈琲",
    "カフェラテ",
    "カフェモカ",
    "エスプレッソ",
    "ランチ",
    "軽食",
    "ワッフル",
    "food",
    "drink",
    "beverage",
    "eating",
    "bring food",
    "menu",
    "saino",
    "coffee",
    "latte",
    "espresso",
    "lunch",
    "snack",
    "食物",
    "自带食物",
    "带食物",
    "带吃的",
    "外带食物",
    "饮料",
    "餐饮",
    "음식",
    "음료",
    "외부 음식",
    "가져와",
    "반입",
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
    "充電器",
    "充電ケーブル",
    "USB-C",
    "usb-c",
    "Lightning",
    "プリンター",
    "コンセント",
    "モニター",
    "maker'sスペース",
    "makersスペース",
    "メーカースペース",
    "maker's space",
    "makers space",
    "3Dプリンター",
    "印刷",
    "コピー",
    "vrゴーグル",
    "VRゴーグル",
    "テラス席",
    "メインホール",
    "メインホール使いたい",
    "main hall",
    "レーザーカッター",
    "レーザー加工機",
    "プロジェクター",
    "スクリーン",
    "マイク",
    "ウォーターサーバー",
    "自動販売機",
    "何がある",
    "何があり",
    "利用できる",
    "スペースを使いたい",
    "利用可能スペース",
    "どんなスペース",
    "equipment",
    "facility",
    "facilities",
    "available spaces",
    "what spaces",
    "outlet",
    "printer",
    "monitor",
    "projector",
    "screen",
    "microphone",
    "water server",
    "water dispenser",
    "vending machine",
    "オンライン会議",
    "オンラインミーティング",
    "web会議",
    "通話",
    "電話できる場所",
    "電話したい",
    "防音室",
    "phone booth",
    "online meeting",
    "video call",
    "take a call",
]

CONTACT_KEYWORDS = [
    "連絡先",
    "問い合わせ",
    "問合せ",
    "お問い合わせ",
    "問い合わせフォーム",
    "電話番号",
    "公式sns",
    "snsアカウント",
    "英語対応",
    "英語版",
    "contact",
    "contact form",
    "phone number",
    "official sns",
    "social media",
    "sns account",
    "english support",
    "english website",
    "联系",
    "联系电话",
    "연락",
    "전화번호",
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
    "勧誘",
    "名刺交換",
    "セールス",
    "仮眠",
    "昼寝",
    "children",
    "kids",
    "stroller",
    "noise",
    "solicitation",
    "sales",
    "nap",
]

TEMPORARY_EXIT_KEYWORDS = [
    "一時外出",
    "途中外出",
    "外出のルール",
    "出入り",
    "再入館",
    "再入場",
    "離席",
    "15分以内",
    "15分以上",
]

PET_POLICY_KEYWORDS = [
    "ペット",
    "動物",
    "補助犬",
    "盲導犬",
    "聴導犬",
    "介助犬",
    "pet",
    "pets",
    "animal",
    "service animal",
    "service dog",
    "guide dog",
]

PET_POLICY_EXCLUSION_KEYWORDS = [
    "ペットボトル",
    "petボトル",
    "pet bottle",
    "plastic bottle",
]

POLICY_KEYWORDS = [
    *ACCESSIBILITY_KEYWORDS,
    *PHOTOGRAPHY_KEYWORDS,
    *CHILDREN_NOISE_KEYWORDS,
    *TEMPORARY_EXIT_KEYWORDS,
    *PET_POLICY_KEYWORDS,
]


# =============================================================================
# 挨拶キーワード・テンプレート（時間帯別挨拶・閉館警告機能で使用）
# =============================================================================

# 挨拶キーワード（ルーターで挨拶意図を検出するために使用）
GREETING_KEYWORDS: list[str] = [
    "おはようございます",
    "おはよう",
    "こんにちは",
    "こんばんは",
    "hello",
    "good morning",
    "good afternoon",
    "good evening",
    "你好",
    "早上好",
    "下午好",
    "晚上好",
    "안녕하세요",
    "안녕",
    "좋은 아침",
]

# 時間帯別挨拶テンプレート
TIME_GREETING_TEMPLATES: dict[str, dict[str, str]] = {
    "morning": {
        "ja": "おはようございます！エンジニアカフェへようこそ。",
        "en": "Good morning! Welcome to Engineer Cafe.",
        "zh": "早上好！欢迎来到工程师咖啡馆。",
        "ko": "좋은 아침입니다! 엔지니어 카페에 오신 것을 환영합니다.",
    },
    "afternoon": {
        "ja": "こんにちは！エンジニアカフェへようこそ。",
        "en": "Good afternoon! Welcome to Engineer Cafe.",
        "zh": "你好！欢迎来到工程师咖啡馆。",
        "ko": "안녕하세요! 엔지니어 카페에 오신 것을 환영합니다.",
    },
    "evening": {
        "ja": "こんばんは！エンジニアカフェへようこそ。",
        "en": "Good evening! Welcome to Engineer Cafe.",
        "zh": "晚上好！欢迎来到工程师咖啡馆。",
        "ko": "안녕하세요! 엔지니어 카페에 오신 것을 환영합니다.",
    },
    "night": {
        "ja": "こんばんは！エンジニアカフェへようこそ。",
        "en": "Good evening! Welcome to Engineer Cafe.",
        "zh": "晚上好！欢迎来到工程师咖啡馆。",
        "ko": "안녕하세요! 엔지니어 카페에 오신 것을 환영합니다.",
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
