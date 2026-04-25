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
import time
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

    # 5. エピソード記憶（来訪目的・活動内容）
    episode = _extract_episode_incident(query, language)
    if episode:
        memories.append(
            {
                "type": "episode_incident",
                "content": episode,
                "confidence": 0.75,
            }
        )

    # 6. 場所嗜好（席・エリアの好み）
    location = _extract_location_preference(query, language)
    if location:
        memories.append(
            {
                "type": "location_preference",
                "content": location,
                "confidence": 0.70,
            }
        )

    return memories


def extract_memory_candidates(
    query: str,
    answer: str,
    language: str = "ja",
    *,
    window_seconds: int = 180,
    extracted_at: float | None = None,
) -> List[Dict[str, Any]]:
    """
    会話から候補メモリ（昇格前のステージング用）を抽出

    既存 extract_memories() の互換性を保ちながら、段階昇格に必要なメタデータを付与する。
    """
    base_memories = extract_memories(query=query, answer=answer, language=language)
    if not base_memories:
        return []

    ts = extracted_at if extracted_at is not None else time.time()
    candidates: List[Dict[str, Any]] = []
    for memory in base_memories:
        mtype = memory.get("type", "unknown")
        policy = _candidate_policy_for_type(mtype)
        candidates.append(
            {
                "status": "candidate",
                "candidate_type": mtype,
                "content": memory.get("content", ""),
                "confidence": memory.get("confidence", 0.5),
                "source": "conversation_turn",
                "language": language,
                "extracted_at": ts,
                "window_seconds": window_seconds,
                "volatility": policy["volatility"],
                "sensitivity": policy["sensitivity"],
                "repeat_count": 1,
                "evidence": {
                    "query": query,
                    # 全文保存を避ける（長文応答の肥大化対策）
                    "answer_excerpt": answer[:240],
                },
            }
        )
    return candidates


def _candidate_policy_for_type(memory_type: str) -> Dict[str, str]:
    """メモリ種別ごとの揮発性・感度ポリシー"""
    if memory_type in {"visitor_name", "visitor_affiliation"}:
        return {"volatility": "low", "sensitivity": "pii"}
    if memory_type == "explicit_remember":
        return {"volatility": "medium", "sensitivity": "user_declared"}
    if memory_type in {"language_preference", "episode_incident", "location_preference"}:
        return {"volatility": "medium", "sensitivity": "non_pii"}
    return {"volatility": "high", "sensitivity": "unknown"}


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
            name = _clean_name_candidate(match.group(1))
            if not _looks_like_person_name(name, language):
                continue
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


def _clean_name_candidate(name: str) -> str:
    candidate = name.strip()
    candidate = re.sub(
        r"(?:です|だよ|と申します|といいます|です。|です\.|です！|です!)+$",
        "",
        candidate,
    )
    return candidate.strip()


def _looks_like_person_name(name: str, language: str) -> bool:
    """Reject factual clauses that the loose Japanese `です` pattern can capture."""
    normalized = name.strip()
    if not normalized:
        return False

    lower = normalized.lower()
    non_name_fragments = (
        "wi-fi",
        "wifi",
        "ssid",
        "パスワード",
        "password",
        "http",
        "://",
        "@",
        "=",
    )
    if any(fragment in lower for fragment in non_name_fragments):
        return False

    if language == "ja":
        if any(particle in normalized for particle in ("は", "が", "を", "に", "で", "の")):
            return False
        return len(normalized) <= 12

    if len(normalized.split()) > 3:
        return False
    return True


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


def _extract_episode_incident(query: str, language: str) -> str | None:
    """来訪目的・活動内容を抽出"""
    if language == "ja":
        patterns = [
            r"(?:今日は|本日は)\s*(.+?)(?:で来ました|で参りました|のために来ました)",
            r"(.+?)(?:をしに来ました|しに来ました)",
            r"(?:もくもく会|ハッカソン|勉強会|ミートアップ|イベント)(?:で|に)(.+)",
        ]
    else:
        patterns = [
            r"(?:i'm here to|i came to|i'm here for)\s+(.+?)(?:\.|,|$)",
            r"(?:i'm attending|i'm joining|i'm participating in)\s+(.+?)(?:\.|,|$)",
            r"(?:here for the|here for a)\s+(.+?)(?:\.|,|$)",
        ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            content = match.group(1).strip().rstrip("。.!！")
            if len(content) > 2:
                return content
    return None


def _extract_location_preference(query: str, language: str) -> str | None:
    """場所・席の好みを抽出"""
    if language == "ja":
        patterns = [
            r"(?:いつも|普段|よく)\s*(.+?)(?:を使って|に座って|を利用して|にいます)",
            r"(?:窓際|奥|手前|入口|メインエリア|個室|ブース)(?:席|の席|エリア|スペース)",
        ]
    else:
        patterns = [
            r"(?:i usually use|i prefer|i always sit)\s+(?:the\s+|at\s+)?(.+?)(?:\.|,|$)",
            r"(?:my usual spot is|i like)\s+(?:the\s+)?(.+?)(?:\.|,|$)",
        ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            if match.lastindex:
                content = match.group(1).strip().rstrip("。.!！")
            else:
                content = match.group(0).strip()
            if len(content) > 1:
                return content
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
