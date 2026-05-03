"""
PII (個人情報) スキャナーモジュール

AIレセプションエージェントの出力レスポンスから
個人情報 (PII) を検出・マスキングする。

検出対象:
- メールアドレス
- 電話番号 (日本国内・国際形式)
- クレジットカード番号
- マイナンバー (個人番号)
- IPアドレス (IPv4)
- 認証情報を含むURL

Note: このモジュールはリーフ依存（他のエージェントモジュールをimportしない）
"""

import re
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# PII検出パターン定義
# ---------------------------------------------------------------------------

# 各パターンは (pattern_name, compiled_regex) のタプル
# pattern_name はマスキング時の置換ラベルに使用される

_PUBLIC_CONTACT_ALLOWLIST = {
    "080-6742-7231",
    "080 6742 7231",
    "08067427231",
}


def _normalize_public_contact_candidate(value: str) -> str:
    return re.sub(r"[\s\-]", "", value)


_PUBLIC_CONTACT_ALLOWLIST_NORMALIZED = {
    _normalize_public_contact_candidate(value) for value in _PUBLIC_CONTACT_ALLOWLIST
}


_PII_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    # --- メールアドレス ---
    (
        "EMAIL",
        re.compile(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        ),
    ),
    # --- クレジットカード番号 (検出優先度を電話番号より上に) ---
    # 半角: 16桁連続 (日本語文字隣接でも検出するため lookaround 使用)
    (
        "CREDIT_CARD",
        re.compile(
            r"(?<!\d)\d{16}(?!\d)",
        ),
    ),
    # 半角: 4桁-4桁-4桁-4桁 (区切りあり)
    (
        "CREDIT_CARD",
        re.compile(
            r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b",
        ),
    ),
    # 全角数字のクレジットカード番号
    (
        "CREDIT_CARD",
        re.compile(
            r"[０-９]{4}[\s\-ー]?[０-９]{4}[\s\-ー]?[０-９]{4}[\s\-ー]?[０-９]{4}",
        ),
    ),
    # --- マイナンバー (12桁の個人番号) ---
    # 半角: 12桁連続 or 4-4-4 ハイフン区切り
    (
        "MY_NUMBER",
        re.compile(
            r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b",
        ),
    ),
    (
        "MY_NUMBER",
        re.compile(
            r"(?<!\d)\d{12}(?!\d)",
        ),
    ),
    # 全角数字のマイナンバー
    (
        "MY_NUMBER",
        re.compile(
            r"[０-９]{4}[\s\-ー][０-９]{4}[\s\-ー][０-９]{4}",
        ),
    ),
    (
        "MY_NUMBER",
        re.compile(
            r"[０-９]{12}",
        ),
    ),
    # --- 電話番号 (日本形式) ---
    # 固定電話: 0X-XXXX-XXXX, 0XX-XXX-XXXX 等
    (
        "PHONE",
        re.compile(
            r"\b0\d{1,4}[\s\-]\d{1,4}[\s\-]\d{3,4}\b",
        ),
    ),
    # 携帯電話: 090/080/070-XXXX-XXXX
    (
        "PHONE",
        re.compile(
            r"\b0[789]0[\s\-]?\d{4}[\s\-]?\d{4}\b",
        ),
    ),
    # ハイフンなし11桁 (携帯)
    (
        "PHONE",
        re.compile(
            r"\b0[789]0\d{8}\b",
        ),
    ),
    # ハイフンなし10桁 (固定電話)
    (
        "PHONE",
        re.compile(
            r"\b0\d{9}\b",
        ),
    ),
    # 全角数字の電話番号
    (
        "PHONE",
        re.compile(
            r"０[０-９]{1,4}[ー\-][０-９]{1,4}[ー\-][０-９]{3,4}",
        ),
    ),
    # 国際形式: +81-XX-XXXX-XXXX or +1-XXX-XXX-XXXX 等
    (
        "PHONE",
        re.compile(
            r"\+\d{1,3}[\s\-]?\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{2,4}",
        ),
    ),
    # --- IPアドレス (IPv4) ---
    (
        "IP_ADDRESS",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        ),
    ),
    # --- 認証情報を含むURL ---
    # user:password@host 形式
    (
        "URL_WITH_CREDENTIALS",
        re.compile(
            r"https?://[^\s:]+:[^\s@]+@[^\s]+",
        ),
    ),
    # URLにapi_key/token等のクエリパラメータが含まれる場合
    (
        "URL_WITH_CREDENTIALS",
        re.compile(
            r"https?://[^\s]*[?&](?:api[_\-]?key|token|secret|password|auth)=[^\s&]+",
            re.IGNORECASE,
        ),
    ),
]


def scan_and_mask(text: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    テキストからPIIを検出し、マスキングした結果を返す。

    Args:
        text: スキャン対象のテキスト

    Returns:
        タプル (masked_text, detected_items)
        - masked_text: PIIが [REDACTED_TYPE] に置換されたテキスト
        - detected_items: 検出されたPII情報のリスト
          各要素は {"type": str, "original": str, "position": int} の辞書
    """
    if not text:
        return ("", [])

    detected_items: List[Dict[str, str]] = []

    # 全パターンのマッチを収集し、位置でソート（重複除去のため）
    all_matches: List[Tuple[int, int, str, str]] = []  # (start, end, type, original)

    for pattern_name, pattern in _PII_PATTERNS:
        for match in pattern.finditer(text):
            if (
                pattern_name == "PHONE"
                and _normalize_public_contact_candidate(match.group())
                in _PUBLIC_CONTACT_ALLOWLIST_NORMALIZED
            ):
                continue
            all_matches.append((match.start(), match.end(), pattern_name, match.group()))

    if not all_matches:
        return (text, [])

    # 開始位置でソートし、重複する範囲を除去（先にマッチしたものを優先）
    all_matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))

    # 重複除去: 既にカバーされた範囲のマッチをスキップ
    filtered_matches: List[Tuple[int, int, str, str]] = []
    last_end = -1
    for start, end, ptype, original in all_matches:
        if start >= last_end:
            filtered_matches.append((start, end, ptype, original))
            last_end = end

    # マスキング適用（後ろから置換してインデックスがずれないようにする）
    masked_text = text
    for start, end, ptype, original in reversed(filtered_matches):
        replacement = f"[REDACTED_{ptype}]"
        masked_text = masked_text[:start] + replacement + masked_text[end:]
        detected_items.append(
            {
                "type": ptype,
                "original": original,
                "position": start,
            }
        )

    # detected_items を位置順に並べ直す（reversed で追加したため逆順になっている）
    detected_items.reverse()

    return (masked_text, detected_items)


def contains_pii(text: str) -> bool:
    """
    テキストにPIIが含まれるかを判定する。

    scan_and_mask のラッパーで、PIIの有無だけを素早く確認したい場合に使用。

    Args:
        text: チェック対象のテキスト

    Returns:
        PIIが検出された場合 True、そうでなければ False
    """
    if not text:
        return False

    for pattern_name, pattern in _PII_PATTERNS:
        for match in pattern.finditer(text):
            if (
                pattern_name == "PHONE"
                and _normalize_public_contact_candidate(match.group())
                in _PUBLIC_CONTACT_ALLOWLIST_NORMALIZED
            ):
                continue
            return True

    return False
