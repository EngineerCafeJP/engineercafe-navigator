"""Facility/policy routing keyword sets and greeting templates."""

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
