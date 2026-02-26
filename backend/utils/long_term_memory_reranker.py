"""Long-term memory reranking utilities (Phase 3)."""

from __future__ import annotations

import re
import time
from typing import Any, Iterable, List


def rerank_store_memory_items(query: str, items: Iterable[Any]) -> List[Any]:
    """
    Store の検索結果をアプリ層で再順位付けする。

    目的:
    - 新規情報が常に最上位になる挙動を緩和
    - 明示記憶や反復された記憶を優先
    """
    scored: list[tuple[float, int, Any]] = []
    now = time.time()
    for idx, item in enumerate(items):
        value = getattr(item, "value", None) or {}
        score = _score_item(query, value, now=now, base_score=getattr(item, "score", None))
        scored.append((score, idx, item))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item for _, _, item in scored]


def _score_item(query: str, value: dict, *, now: float, base_score: float | None = None) -> float:
    score = float(base_score) if isinstance(base_score, (int, float)) else 0.5

    confidence = float(value.get("confidence", 0.5) or 0.5)
    score += confidence * 0.25

    mtype = str(value.get("type", "") or "")
    if mtype == "explicit_remember":
        score += 0.2

    promotion = value.get("promotion", {}) or {}
    repeat_count = int(
        promotion.get("repeat_count_sum", value.get("repeat_count", 1) or 1) or 1
    )
    candidate_count = int(promotion.get("candidate_count", 1) or 1)
    score += min(repeat_count, 5) * 0.03
    score += min(candidate_count, 5) * 0.02

    # lexical signal: simple token overlap (JP/EN mixed heuristics)
    text = str(value.get("data", value.get("content", "")) or "")
    overlap = _token_overlap(query, text)
    score += min(overlap, 4) * 0.04

    ts = float(value.get("timestamp", promotion.get("last_seen_at", 0)) or 0)
    if ts > 0:
        age_sec = max(0.0, now - ts)
        # Small freshness penalty for non-explicit very new memories to avoid overreacting
        if mtype != "explicit_remember":
            if age_sec < 60:
                score -= 0.12
            elif age_sec < 600:
                score -= 0.08
            elif age_sec < 3600:
                score -= 0.03

    # Promoted entries are considered more stable than raw one-shot writes
    if value.get("source") == "promoter":
        score += 0.05

    return score


def _token_overlap(a: str, b: str) -> int:
    a_tokens = set(_simple_tokens(a))
    b_tokens = set(_simple_tokens(b))
    if not a_tokens or not b_tokens:
        return 0
    return len(a_tokens & b_tokens)


def _simple_tokens(text: str) -> list[str]:
    # Latin words + numbers + contiguous Japanese chars (coarse but deterministic)
    if not text:
        return []
    pattern = r"[A-Za-z0-9]+|[\u3040-\u30ff\u4e00-\u9fff]{2,}"
    return [t.lower() for t in re.findall(pattern, text)]

