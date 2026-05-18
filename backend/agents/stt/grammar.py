from __future__ import annotations

from typing import Dict, List

ENGINEER_CAFE_GRAMMAR: Dict[str, List[str]] = {
    "ja": [
        "エンジニアカフェ",
        "エンジニアカフェラボ",
        "営業時間",
        "会議室",
        "ミーティング",
        "ミートアップ",
        "集中スペース",
        "メーカーズスペース",
        "地下",
        "赤煉瓦",
        "天神",
        "博多",
        "ハカタ",
        "福岡",
        "ワイファイ",
        "Wi-Fi",
        "イベント",
        "コワーキング",
        "コワーキングスペース",
        "予約",
        "受付",
        "料金",
        "無料",
        "駐車場",
        "駐輪場",
        "サイノ",
    ],
    "en": [
        "engineer cafe",
        "engineer cafe lab",
        "business hours",
        "meeting room",
        "focus space",
        "makers space",
        "basement",
        "red brick",
        "tenjin",
        "hakata",
        "fukuoka",
        "wifi",
        "event",
        "meetup",
        "coworking",
        "coworking space",
        "reservation",
        "reception",
        "price",
        "free",
        "parking",
        "saino",
    ],
}


# -----------------------------------------------------------------------------
# Stage-specific grammars (greeting -> service_selection -> confirmation)
# -----------------------------------------------------------------------------

STAGE_GRAMMARS: Dict[str, Dict[str, List[str]]] = {
    "greeting": {
        "ja": [
            "こんにちは",
            "おはようございます",
            "こんばんは",
            "すみません",
            "はじめまして",
            "エンジニアカフェ",
            "受付",
            "サイノ",
        ],
        "en": [
            "hello",
            "hi",
            "good morning",
            "good afternoon",
            "excuse me",
            "engineer cafe",
            "reception",
            "saino",
        ],
    },
    "service_selection": {
        "ja": [
            "会議室",
            "コワーキングスペース",
            "コワーキング",
            "集中スペース",
            "メーカーズスペース",
            "Wi-Fi",
            "ワイファイ",
            "イベント",
            "ミートアップ",
            "ミーティング",
            "予約",
            "料金",
            "営業時間",
            "駐車場",
            "駐輪場",
            "エンジニアカフェラボ",
            "サイノ",
        ],
        "en": [
            "meeting room",
            "coworking space",
            "coworking",
            "focus space",
            "makers space",
            "wifi",
            "event",
            "meetup",
            "reservation",
            "price",
            "business hours",
            "parking",
            "engineer cafe lab",
            "saino",
        ],
    },
    "confirmation": {
        "ja": [
            "はい",
            "いいえ",
            "そうです",
            "違います",
            "お願いします",
            "キャンセル",
            "ありがとう",
            "ありがとうございます",
            "了解",
            "わかりました",
        ],
        "en": [
            "yes",
            "no",
            "correct",
            "that's right",
            "cancel",
            "please",
            "thank you",
            "thanks",
            "okay",
            "understood",
        ],
    },
}

VALID_STAGES = tuple(STAGE_GRAMMARS.keys())


# -----------------------------------------------------------------------------
# Default model paths
# -----------------------------------------------------------------------------

DEFAULT_MODEL_PATHS: Dict[str, str] = {
    "ja": "models/vosk-model-ja",
    "en": "models/vosk-model-en-us",
}

SUPPORTED_LANGUAGES = ("ja", "en")
