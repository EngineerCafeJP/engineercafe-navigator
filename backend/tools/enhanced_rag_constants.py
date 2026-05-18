"""Constants and keyword tables for enhanced RAG search."""

from typing import Dict, List

# Embedding model configuration
# text-embedding-3-small: 1536 dims (OpenAI)
# text-embedding-3-large: 3072 dims (OpenAI)
# The DB column dimension must match the model output dimension.
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536

# RPC similarity thresholds per category
# Lower threshold = broader recall; higher = stricter precision
RPC_SIMILARITY_THRESHOLDS: Dict[str, float] = {
    "hours": 0.25,
    "pricing": 0.25,
    "location": 0.25,
    "facility-info": 0.30,
    "event": 0.35,
    "general": 0.30,
    "consultation": 0.30,
    "community": 0.30,
    "smoking": 0.30,
    "food_drink": 0.30,
    "parking": 0.30,
    "bicycle": 0.30,
    "policy": 0.30,
}
DEFAULT_RPC_SIMILARITY_THRESHOLD = 0.30
RPC_TIMEOUT_SECONDS = 10.0

# カテゴリ別品質グレーディング閾値
CATEGORY_THRESHOLDS = {
    "hours": {"high": 0.75, "medium": 0.50, "term_match": 0.25},
    "pricing": {"high": 0.75, "medium": 0.50, "term_match": 0.25},
    "facility-info": {"high": 0.78, "medium": 0.58, "term_match": 0.25},
    "location": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
    "event": {"high": 0.80, "medium": 0.60, "term_match": 0.30},
    "general": {"high": 0.72, "medium": 0.52, "term_match": 0.20},
    "consultation": {"high": 0.65, "medium": 0.45, "term_match": 0.18},
    "community": {"high": 0.73, "medium": 0.53, "term_match": 0.20},
    "smoking": {"high": 0.65, "medium": 0.45, "term_match": 0.18},
    "food_drink": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
    "parking": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
    "bicycle": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
    "policy": {"high": 0.70, "medium": 0.50, "term_match": 0.20},
}
DEFAULT_THRESHOLDS = {"high": 0.78, "medium": 0.58, "term_match": 0.25}


# Query expansion mappings for Japanese/English synonyms
QUERY_EXPANSION_MAP: Dict[str, List[str]] = {
    "営業時間": ["opening hours", "business hours", "営業", "時間", "何時から", "何時まで", "開館"],
    "料金": ["pricing", "price", "cost", "fee", "料金", "値段", "いくら", "無料"],
    "アクセス": ["access", "location", "directions", "場所", "行き方", "住所", "最寄り駅"],
    "wifi": ["Wi-Fi", "WiFi", "wireless", "ネットワーク", "インターネット"],
    "会議室": ["meeting room", "conference room", "部屋", "予約"],
    "予約なし": ["予約不要", "予約なし", "no reservation", "受付", "利用登録", "初回"],
    "予約不要": ["予約不要", "予約なし", "no reservation", "受付", "利用登録", "初回"],
    "再受付": ["再受付", "会員番号", "受付カード", "2回目以降", "returning visitor"],
    "受付": ["受付", "利用登録", "初回", "会員番号", "受付カード"],
    "設備": ["facility", "facilities", "equipment", "機材", "備品"],
    "イベント": ["event", "events", "セミナー", "勉強会", "ワークショップ"],
    "opening hours": ["営業時間", "business hours", "operating hours"],
    "price": ["料金", "pricing", "cost", "fee"],
    "location": ["アクセス", "場所", "address", "directions"],
    "いくら": ["料金", "pricing", "price", "cost", "fee", "値段", "無料", "有料"],
    "何時": ["営業時間", "opening hours", "business hours", "開館", "閉館"],
    "どこ": ["場所", "アクセス", "location", "access", "住所", "所在地"],
    # Korean → Japanese keyword expansion (tRAG Phase 2)
    "이용 시간": ["営業時間", "開館時間", "利用時間"],
    "운영 시간": ["営業時間", "開館時間"],
    "어디": ["場所", "アクセス", "住所", "所在地"],
    "위치": ["場所", "アクセス", "住所", "所在地"],
    "시설": ["設備", "施設", "facility"],
    "요금": ["料金", "値段", "無料"],
    "무료": ["無料", "料金", "pricing"],
    "회원": ["会員", "利用登録", "会員番号", "受付", "無料"],
    "회원 등록": ["利用登録", "会員", "受付", "会員番号", "無料"],
    "회원가입": ["利用登録", "会員", "受付", "会員番号"],
    "멤버십": ["会員", "会員制度", "利用登録", "無料"],
    "가입": ["利用登録", "会員", "受付"],
    "등록": ["利用方法", "登録", "初回", "初めて"],
    "방문": ["来訪", "初めて", "利用方法"],
    "와이파이": ["Wi-Fi", "WiFi", "ネットワーク"],
    "이벤트": ["イベント", "セミナー", "勉強会"],
    "회의실": ["会議室", "meeting room", "予約"],
    # English → Japanese keyword expansion (registration / membership)
    "register": ["利用登録", "登録", "会員", "初回", "受付"],
    "registration": ["利用登録", "登録", "会員", "初回", "受付"],
    "membership": ["会員", "利用登録", "無料", "受付", "会員番号"],
    "membership system": ["会員制度", "会員", "利用登録", "無料", "会員番号"],
    "about membership": ["会員制度", "会員", "利用登録", "無料", "受付"],
    "membership like": ["会員制度", "会員", "利用登録", "無料", "受付"],
    "member benefits": ["無料", "利用料", "会員", "利用登録", "受付"],
    "sign up": ["利用登録", "登録", "初回", "会員"],
    "signing up": ["利用登録", "登録", "初回"],
    "become a member": ["会員", "利用登録", "登録", "初回"],
    "how to join": ["利用方法", "利用登録", "参加", "登録"],
    "first time": ["初回", "初めて", "利用登録"],
    "first-time": ["初回", "初めて", "利用登録", "受付"],
    "first-time visitor": ["初回", "初めて", "利用登録", "受付"],
    "first time visitor": ["初回", "初めて", "利用登録", "受付"],
    "first time here": ["初回", "初めて", "利用登録", "受付"],
    "what should i do": ["利用方法", "受付", "利用登録", "初回"],
    "member": ["会員", "利用登録", "会員番号", "受付", "無料"],
    "member number": ["会員番号", "受付", "受付カード"],
    "returning visitor": ["2回目以降", "会員番号", "受付カード", "再受付"],
    "registered before": ["2回目以降", "会員番号", "受付カード", "再受付"],
    "without a reservation": ["予約不要", "予約なし", "受付", "利用登録"],
    "no reservation": ["予約不要", "予約なし", "受付", "利用登録"],
    # Chinese → Japanese keyword expansion
    "营业时间": ["営業時間", "開館時間"],
    "费用": ["料金", "値段", "無料"],
    "位置": ["場所", "アクセス", "住所"],
    "设施": ["設備", "施設", "facility"],
    "会员": ["会員", "利用登録", "会員番号", "受付", "無料"],
    "會員": ["会員", "利用登録", "会員番号", "受付", "無料"],
    "会员制度": ["会員制度", "会員", "利用登録", "無料"],
    "加入会员": ["利用登録", "会員", "受付", "会員番号"],
    "登记": ["利用方法", "登録", "初回"],
    # Policy / space queries
    "spaces": ["スペース", "施設", "設備", "メインホール", "集中スペース"],
    "available spaces": ["スペース", "施設", "設備", "メインホール", "集中スペース"],
    "what spaces": ["スペース", "施設", "設備", "メインホール", "集中スペース"],
    "smoking": ["喫煙", "禁煙", "喫煙所"],
    "흡연": ["喫煙", "禁煙", "喫煙所"],
    "금연": ["禁煙", "喫煙"],
    "담배": ["喫煙", "禁煙", "喫煙所"],
}

RAG_CATEGORY_ALIASES: Dict[str, set[str]] = {
    "access": {"access", "location"},
    "location": {"access", "location"},
    "facilities": {"facility-info"},
    "facility": {"facility-info"},
    "business-hours": {"hours"},
    "saino-cafe": {"hours", "facility-info", "food_drink", "pricing", "general"},
}

SAINO_QUERY_TERMS = (
    "saino",
    "サイノ",
    "サイノカフェ",
    "cafe&bar",
    "cafe and bar",
    "say no cafe",
    "coffee say no",
    "併設カフェ",
)

MEMBERSHIP_QUERY_TERMS = (
    "membership",
    "member",
    "registration",
    "register",
    "sign up",
    "signup",
    "join",
    "会員",
    "会員制度",
    "会員登録",
    "利用登録",
    "登録",
    "受付",
    "会员",
    "會員",
    "登记",
    "登記",
    "회원",
    "회원가입",
    "멤버십",
    "가입",
    "등록",
)

MEMBERSHIP_RESULT_TERMS = (
    "membership",
    "member number",
    "registration",
    "register",
    "reception",
    "会員",
    "会員制度",
    "会員番号",
    "利用登録",
    "登録",
    "受付",
    "初回",
    "無料",
)
