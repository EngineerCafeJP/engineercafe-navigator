"""
Emotion tag utility functions

感情タグの除去と抽出を行うユーティリティ。
VoiceAgent の parse_emotion_tags() と同じ正規表現を共有し、
テキスト応答から感情タグを一括除去する。

Note: VoiceAgentは感情タグを *解析* して音声合成に使うが、
      ここではテキスト応答用にタグを *除去* する目的で使用。
"""

import re
from typing import Optional

EMOTION_TAG_REGEX = re.compile(r"\[/?([a-zA-Z_]+)(?::(\d*\.?\d+))?\]")


def strip_emotion_tags(text: str) -> str:
    """
    テキストから感情タグを除去し、空白を正規化する

    Examples:
        >>> strip_emotion_tags("[happy]Hello!")
        'Hello!'
        >>> strip_emotion_tags("[happy:0.8]こんにちは[/happy]")
        'こんにちは'

    Args:
        text: 感情タグを含むテキスト

    Returns:
        タグが除去され空白が正規化されたテキスト
    """
    if not text:
        return ""
    cleaned = EMOTION_TAG_REGEX.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_primary_emotion(text: str) -> Optional[str]:
    """
    テキストから最初の感情タグの名前を抽出する

    Args:
        text: 感情タグを含むテキスト

    Returns:
        最初の感情タグ名（小文字）、またはタグがない場合はNone
    """
    if not text:
        return None
    match = EMOTION_TAG_REGEX.search(text)
    return match.group(1).lower() if match else None
