"""
FacilityAgent用プロンプトテンプレート

施設情報クエリに対するプロンプト構築ロジックとキーワード辞書を集約。
"""

from typing import Dict, Optional

# クエリ拡張キーワード（requestType別）
FACILITY_ENHANCEMENT_KEYWORDS: Dict[str, Dict[str, str]] = {
    "wifi": {
        "ja": "無料Wi-Fi インターネット 接続方法 パスワード",
        "en": "free Wi-Fi internet connection method password",
    },
    "facility": {
        "ja": "設備 電源 コンセント プリンター 利用方法",
        "en": "facilities power outlet printer usage",
    },
    "basement": {
        "ja": "地下 B1 MTGスペース 集中スペース アンダースペース Makersスペース 予約 利用方法",
        "en": "basement B1 MTG space focus space under space makers space reservation",
    },
    "access": {
        "ja": "アクセス 行き方 最寄り駅 天神駅 徒歩 道順 出口 帰り方",
        "en": "access directions nearest station Tenjin walking route exit",
    },
    "building": {
        "ja": "建物 赤煉瓦文化館 重要文化財 辰野金吾 歴史 明治",
        "en": "building red brick cultural hall important cultural property history Meiji",
    },
    "parking": {
        "ja": "駐車場 パーキング 車 近隣 コインパーキング",
        "en": "parking car park nearby coin parking",
    },
    "bicycle": {
        "ja": "駐輪場 自転車 バイク置き場 公共駐輪場",
        "en": "bicycle parking bike cycle public",
    },
    "smoking": {
        "ja": "喫煙 タバコ 禁煙 喫煙所 全館禁煙",
        "en": "smoking cigarette no smoking smoke area",
    },
    "food_drink": {
        "ja": "飲食 食べ物 飲み物 メニュー ランチ 料金 カフェ saino 持ち込み 軽食",
        "en": "food drink beverage menu lunch price cafe saino bring eat snack",
    },
    "accessibility": {
        "ja": "車椅子 バリアフリー エレベーター 段差 スロープ 対応",
        "en": "wheelchair accessible elevator ramp barrier-free support",
    },
    "photography": {
        "ja": "撮影 写真 カメラ SNS 撮影ポリシー 許可",
        "en": "photography photo camera SNS photo policy permission",
    },
    "children_noise": {
        "ja": "子連れ 子供 ベビーカー 騒音 マナー 利用ルール",
        "en": "children kids stroller noise policy rules",
    },
    "meeting_room": {
        "ja": "会議室 貸会議室 貸切 予約 コミネット 2階",
        "en": "meeting room conference booking reservation 2nd floor",
    },
    "toilet": {
        "ja": "トイレ お手洗い 化粧室 テラス 場所 行き方",
        "en": "toilet restroom bathroom location terrace directions",
    },
}

# requestTypeに応じたプロンプト文言
FACILITY_REQUEST_TYPE_PROMPTS: Dict[str, Dict[str, str]] = {
    "wifi": {"en": "Wi-Fi information", "ja": "Wi-Fi情報"},
    "facility": {"en": "facility information", "ja": "設備情報"},
    "basement": {"en": "basement facility information", "ja": "地下施設情報"},
    "access": {"en": "access information", "ja": "アクセス情報"},
    "building": {"en": "building information", "ja": "建物情報"},
    "parking": {"en": "parking information", "ja": "駐車場情報"},
    "bicycle": {"en": "bicycle parking information", "ja": "駐輪場情報"},
    "smoking": {"en": "smoking policy", "ja": "喫煙ポリシー"},
    "food_drink": {"en": "food and drink menu/policy information", "ja": "飲食・メニュー情報"},
    "accessibility": {
        "en": "accessibility and wheelchair information",
        "ja": "バリアフリー・車椅子対応情報",
    },
    "photography": {"en": "photography and filming policy", "ja": "撮影ポリシー"},
    "children_noise": {"en": "children and noise policy", "ja": "子連れ利用・騒音ポリシー"},
    "meeting_room": {"en": "meeting room information", "ja": "会議室情報"},
    "toilet": {
        "en": "toilet and restroom location information",
        "ja": "トイレ・お手洗いの場所情報",
    },
}


def build_facility_prompt(
    query: str, context: str, request_type: Optional[str], language: str
) -> str:
    """LLMプロンプトを構築

    Args:
        query: ユーザークエリ
        context: RAG検索で取得したコンテキスト
        request_type: リクエストタイプ
        language: 言語（ja or en）

    Returns:
        構築されたプロンプト
    """
    if request_type:
        prompt_info = FACILITY_REQUEST_TYPE_PROMPTS.get(
            request_type, {"en": "requested information", "ja": "要求された情報"}
        )
        request_type_prompt = prompt_info.get(language, prompt_info.get("ja", ""))

        if language == "en":
            return f"""Answer the question directly using the {request_type_prompt} from the following information.
Focus on what the user is specifically asking about. Include concrete details (prices, times, names) when available.

Question: {query}
Information: {context}

Answer in 2-3 sentences with specific, relevant details. Do not include unrelated information.
IMPORTANT: Start your response with [relaxed] for information or [happy] for positive news."""
        else:
            return f"""質問に対して、以下の情報から{request_type_prompt}を使って直接回答してください。
ユーザーが具体的に聞いていることに焦点を当て、具体的な情報（価格、時間、名前等）を含めてください。

質問: {query}
情報: {context}

具体的で関連性の高い情報を2-3文で答えてください。質問と無関係な情報は含めないでください。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。"""
    else:
        if language == "en":
            return f"""Answer the question using the provided information. Be concise and direct.

Question: {query}
Information: {context}

Answer briefly (2-3 sentences) with only the relevant information.
IMPORTANT: Start your response with an emotion tag: [relaxed] for information, [happy] for positive news, [sad] for unavailable services."""
        else:
            return f"""提供された情報を使って質問に答えてください。簡潔で直接的に答えてください。

質問: {query}
情報: {context}

関連する情報のみを簡潔に（2-3文）答えてください。
重要: 感情タグで回答を始めてください: 情報提供は[relaxed]、良いニュースは[happy]、利用できないサービスは[sad]。"""
