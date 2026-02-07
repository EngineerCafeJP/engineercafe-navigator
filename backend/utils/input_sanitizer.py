"""
入力サニタイズモジュール

ユーザー入力のサニタイズ処理を一箇所に集約。
プロンプトインジェクション検出、制御文字除去、長さ制限を提供。

Note: このモジュールはリーフ依存（他のエージェントモジュールをimportしない）
"""

import re
from typing import List


MAX_QUERY_LENGTH = 1000
MAX_CONTEXT_LENGTH = 500

# プロンプトインジェクション検出パターン
DANGEROUS_PATTERNS: List[str] = [
    r"(?i)(ignore|forget|disregard)\s*(the\s*)?(above|previous|instructions)",
    r"(?i)system\s*prompt",
    r"(?i)new\s*instructions?",
    r"(?i)you\s*are\s*now",
    r"(?i)act\s*as\s*if",
]


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

    # 長さ制限
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    # プロンプトインジェクションパターンの検出とフィルタリング
    for pattern in DANGEROUS_PATTERNS:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized)

    return sanitized
