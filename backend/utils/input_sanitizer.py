"""
入力サニタイズモジュール

ユーザー入力のサニタイズ処理を一箇所に集約。
プロンプトインジェクション検出、制御文字除去、長さ制限、
過剰繰り返し圧縮を提供。

Note: このモジュールはリーフ依存（他のエージェントモジュールをimportしない）
"""

import re
from typing import List

MAX_QUERY_LENGTH = 1000
MAX_CONTEXT_LENGTH = 500

# プロンプトインジェクション検出パターン (30+)
DANGEROUS_PATTERNS: List[str] = [
    # === 英語: 指示無視系 ===
    r"(?i)(ignore|forget|disregard)\s*(the\s*)?(above|previous|all|prior)\s*(instructions?|prompts?|rules?)?",
    r"(?i)override\s*(the\s*)?(above|previous|all|prior)?\s*(instructions?|prompts?|rules?|settings?)",
    r"(?i)bypass\s*(the\s*)?(above|previous|all|prior)?\s*(instructions?|prompts?|rules?|filters?|safety)",
    # === 英語: プロンプト漏洩系 ===
    r"(?i)system\s*prompt",
    r"(?i)(show|reveal|display|print|output|repeat)\s*(the\s*)?(system|original|initial|full)?\s*prompt",
    r"(?i)(show|reveal|display|print)\s*(the\s*)?(hidden|secret|internal)\s*(instructions?|rules?|config)",
    # === 英語: ロール変更系 ===
    r"(?i)you\s*are\s*now",
    r"(?i)act\s*as\s*if",
    r"(?i)from\s*now\s*on",
    r"(?i)pretend\s*(you\s*are|to\s*be)",
    r"(?i)roleplay\s*as",
    r"(?i)(enter|enable|activate|switch\s*to)\s*(developer|admin|sudo|god|root|debug|DAN)\s*mode",
    r"(?i)jailbreak",
    r"(?i)DAN\s*mode",
    # === 英語: 指示注入系 ===
    r"(?i)new\s*instructions?",
    r"(?i)(here\s*are|follow\s*these)\s*(new|my|the)?\s*instructions?",
    # === 日本語: 指示無視系 ===
    r"上記の指示を無視",
    r"(前の|以前の|すべての)?(指示|命令|ルール|プロンプト)を(無視|忘れ|破棄)",
    r"制限を解除",
    # === 日本語: プロンプト漏洩系 ===
    r"システムプロンプトを(表示|見せて|教えて|出力)",
    r"(隠された|内部の|秘密の)(指示|設定|ルール)を(表示|見せて|教えて)",
    # === 日本語: ロール変更系 ===
    r"今からあなたは",
    r"(管理者|開発者|デバッグ)(モード|権限)",
    r"ロールプレイ",
    r"新しい(指示|命令|ルール)",
    # === エンコーディング・マーカー系 ===
    r"<\|im_start\|>",
    r"\[INST\]",
    r"###\s*(system|assistant|user)",
    r"<\|system\|>",
    r"<\|endoftext\|>",
]

# 過剰繰り返し検出パターン: 同一文字/単語の20回以上の繰り返し
_EXCESSIVE_REPEAT_REGEX = re.compile(r"(.)\1{19,}")
_EXCESSIVE_WORD_REPEAT_REGEX = re.compile(r"(\b\w+\b)(?:\s+\1){9,}", re.IGNORECASE)


def sanitize_input(text: str, max_length: int = MAX_QUERY_LENGTH) -> str:
    """
    ユーザー入力をサニタイズ

    Args:
        text: サニタイズする文字列
        max_length: 最大長

    Returns:
        サニタイズされた文字列
    """
    if not text:
        return ""

    # 制御文字の除去
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

    # 過剰繰り返しの圧縮（同一文字20回以上→3回に）
    sanitized = _EXCESSIVE_REPEAT_REGEX.sub(lambda m: m.group(1) * 3, sanitized)

    # 過剰単語繰り返しの圧縮（同一単語10回以上→3回に）
    sanitized = _EXCESSIVE_WORD_REPEAT_REGEX.sub(lambda m: " ".join([m.group(1)] * 3), sanitized)

    # 長さ制限
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    # プロンプトインジェクションパターンの検出とフィルタリング
    for pattern in DANGEROUS_PATTERNS:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized)

    return sanitized


def contains_prompt_injection(text: str) -> bool:
    """
    Return True when the raw user input matches known prompt-injection patterns.

    This intentionally runs before sanitize_input(), because replacing dangerous
    fragments with [FILTERED] can leave enough surrounding text for a model to
    treat the request as a normal operational question.
    """
    if not text:
        return False

    return any(re.search(pattern, text) for pattern in DANGEROUS_PATTERNS)


def prompt_injection_refusal(language: str | None = None) -> str:
    """Build a concise refusal that avoids echoing attacker-controlled tokens."""
    if language == "en":
        return (
            "I can't enable debug modes, bypass internal routing or safety behavior, "
            "reveal private instructions, or change logging and memory policy. "
            "I can still help with public Engineer Cafe information and normal "
            "navigation questions."
        )

    return (
        "デバッグ権限の有効化、内部ルーティングや安全制御の回避、非公開指示や秘密情報の開示、"
        "ログや記憶ポリシーの変更には対応できません。"
        "エンジニアカフェの公開情報や通常の案内であればお手伝いできます。"
    )
