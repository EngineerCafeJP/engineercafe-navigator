"""Core routing keyword sets shared by routing_constants."""

import re

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
