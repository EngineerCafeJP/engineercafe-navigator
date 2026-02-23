"""
Memory Extraction Utility

会話からクロスセッション長期記憶として保存すべき重要な事実を抽出する。

抽出対象:
1. 訪問者の自己紹介（名前、所属）
2. 言語設定
3. 明示的な「覚えて」リクエスト
4. 頻繁に聞かれるトピック
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def extract_memories(
    query: str,
    answer: str,
    language: str = "ja",
) -> List[Dict[str, Any]]:
    """
    会話から長期記憶として保存すべき事実を抽出

    Args:
        query: ユーザーの入力
        answer: エージェントの応答
        language: 現在の言語設定

    Returns:
        抽出されたメモリのリスト。各メモリは以下の形式:
        {"type": str, "content": str, "confidence": float}
    """
    memories: List[Dict[str, Any]] = []

    # 1. 名前の抽出
    name = _extract_name(query, language)
    if name:
        memories.append(
            {
                "type": "visitor_name",
                "content": name,
                "confidence": 0.9,
            }
        )

    # 2. 所属の抽出
    affiliation = _extract_affiliation(query, language)
    if affiliation:
        memories.append(
            {
                "type": "visitor_affiliation",
                "content": affiliation,
                "confidence": 0.8,
            }
        )

    # 3. 明示的な「覚えて」リクエスト
    remember_content = _extract_remember_request(query, language)
    if remember_content:
        memories.append(
            {
                "type": "explicit_remember",
                "content": remember_content,
                "confidence": 1.0,
            }
        )

    # 4. 言語設定（英語で話しかけてきた場合）
    if language == "en":
        memories.append(
            {
                "type": "language_preference",
                "content": "en",
                "confidence": 0.7,
            }
        )

    return memories


def _extract_name(query: str, language: str) -> str | None:
    """名前を抽出"""
    if language == "ja":
        patterns = [
            r"(?:私は|僕は|わたしは|ぼくは|俺は|おれは|名前は)\s*([^\s、。,\.]+)",
            r"([^\s、。,\.]+)\s*(?:です|だよ|と申します|といいます)",
        ]
    else:
        patterns = [
            r"(?:my name is|i'm|i am|call me)\s+([A-Za-z]+(?:\s[A-Za-z]+)?)",
        ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Filter out common non-name words
            non_names = {
                "エンジニア",
                "学生",
                "会社員",
                "here",
                "there",
                "fine",
                "good",
                "happy",
                "new",
                "looking",
                "engineer",
                "student",
            }
            if name.lower() not in {n.lower() for n in non_names} and len(name) > 0:
                return name
    return None


def _extract_affiliation(query: str, language: str) -> str | None:
    """所属を抽出"""
    if language == "ja":
        patterns = [
            r"([^\s、。,\.]+)\s*(?:の者|から来ました|に勤めて|に所属|で働いて|の社員)",
            r"(?:所属は|会社は|勤務先は)\s*([^\s、。,\.]+)",
        ]
    else:
        patterns = [
            r"(?:i work at|i'm from|i work for|i'm with)\s+([A-Za-z\s]+?)(?:\.|,|$)",
            r"(?:from|at)\s+([A-Za-z]+(?:\s[A-Za-z]+)?)\s*(?:company|corp|inc|ltd)?",
        ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            affiliation = match.group(1).strip()
            if len(affiliation) > 1:
                return affiliation
    return None


def _extract_remember_request(query: str, language: str) -> str | None:
    """明示的な「覚えて」リクエストを抽出"""
    if language == "ja":
        patterns = [
            r"(?:覚えて|記憶して|忘れないで)[：:、,]?\s*(.+)",
            r"(.+)(?:を覚えて|を記憶して|を忘れないで)",
        ]
    else:
        patterns = [
            r"(?:remember|don't forget|keep in mind)[：:,]?\s*(.+)",
            r"(?:please\s+)?(?:remember|note)\s+(?:that\s+)?(.+)",
        ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            content = match.group(1).strip().rstrip("。.!！")
            if len(content) > 2:
                return content
    return None
