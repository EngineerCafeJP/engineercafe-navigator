"""
Memory promotion service.

候補メモリを集約し、昇格ルールに基づいて長期メモリへ昇格させる。
Phase 2 では既存の直書き保存と併用可能なように、重複回避を優先する。
"""

from __future__ import annotations

import time
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable

from backend.utils.cafe_entity import canonicalize_facility_memory_key_text


@dataclass
class PromotionDecision:
    promote: bool
    reason: str


class MemoryPromoter:
    def __init__(
        self,
        *,
        candidate_namespace_root: str = "visitor_memory_candidates",
        long_term_namespace_root: str = "visitor_memories",
    ):
        self.candidate_namespace_root = candidate_namespace_root
        self.long_term_namespace_root = long_term_namespace_root

    async def promote_for_user(
        self,
        store: Any,
        user_id: str,
        *,
        max_candidates: int = 200,
        max_existing: int = 200,
        delete_promoted_candidates: bool = False,
    ) -> Dict[str, int]:
        """
        ユーザー単位で候補メモリを昇格する。

        Returns:
            集計統計 {"candidates", "aggregated", "promoted", "duplicates_skipped", ...}
        """
        candidate_ns = (self.candidate_namespace_root, user_id)
        long_term_ns = (self.long_term_namespace_root, user_id)

        candidate_items = await store.asearch(candidate_ns, query="", limit=max_candidates)
        if not candidate_items:
            return {
                "candidates": 0,
                "aggregated": 0,
                "promoted": 0,
                "duplicates_skipped": 0,
                "rule_rejected": 0,
            }

        aggregated = self.aggregate_candidates(candidate_items)
        existing_items = await store.asearch(long_term_ns, query="", limit=max_existing)
        existing_keys = self.build_existing_index(existing_items)

        promoted = 0
        duplicates_skipped = 0
        rule_rejected = 0
        promoted_candidate_keys: list[str] = []

        for agg_key, aggregate in aggregated.items():
            decision = self.should_promote(aggregate)
            if not decision.promote:
                rule_rejected += 1
                continue

            if agg_key in existing_keys:
                duplicates_skipped += 1
                continue

            payload = self.to_long_term_record(aggregate)
            await store.aput(long_term_ns, str(uuid.uuid4()), payload)
            promoted += 1
            promoted_candidate_keys.extend(aggregate["candidate_keys"])

        if delete_promoted_candidates and hasattr(store, "adelete"):
            for key in promoted_candidate_keys:
                try:
                    await store.adelete(candidate_ns, key)
                except Exception:
                    # cleanup failure is non-fatal
                    pass

        return {
            "candidates": len(candidate_items),
            "aggregated": len(aggregated),
            "promoted": promoted,
            "duplicates_skipped": duplicates_skipped,
            "rule_rejected": rule_rejected,
        }

    @staticmethod
    def aggregate_candidates(items: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
        """候補メモリを type+content 単位で集約する。"""
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in items:
            value = getattr(item, "value", None) or {}
            ctype = value.get("candidate_type") or value.get("type") or "unknown"
            content = str(value.get("content", "")).strip()
            if not content:
                continue

            agg_key = MemoryPromoter._aggregate_key(ctype, content)
            extracted_at = float(value.get("extracted_at", 0) or 0)
            confidence = float(value.get("confidence", 0.5) or 0.5)
            repeat_count = int(value.get("repeat_count", 1) or 1)
            evidence = value.get("evidence") or {}
            evidence_query = evidence.get("query", "") if isinstance(evidence, dict) else ""

            if agg_key not in grouped:
                grouped[agg_key] = {
                    "agg_key": agg_key,
                    "candidate_type": ctype,
                    "content": content,
                    "confidence_max": confidence,
                    "confidence_sum": confidence,
                    "candidate_count": 1,
                    "repeat_count_sum": repeat_count,
                    "first_seen_at": extracted_at or time.time(),
                    "last_seen_at": extracted_at or time.time(),
                    "sensitivity": value.get("sensitivity", "unknown"),
                    "volatility": value.get("volatility", "high"),
                    "languages": {value.get("language", "ja")},
                    "candidate_keys": [getattr(item, "key", "")],
                    "sources": {value.get("source", "conversation_turn")},
                    "evidence_queries": {str(evidence_query)} if evidence_query else set(),
                }
                continue

            g = grouped[agg_key]
            g["candidate_count"] += 1
            g["repeat_count_sum"] += repeat_count
            g["confidence_sum"] += confidence
            g["confidence_max"] = max(g["confidence_max"], confidence)
            g["first_seen_at"] = min(g["first_seen_at"], extracted_at or g["first_seen_at"])
            g["last_seen_at"] = max(g["last_seen_at"], extracted_at or g["last_seen_at"])
            if getattr(item, "key", ""):
                g["candidate_keys"].append(getattr(item, "key", ""))
            g["languages"].add(value.get("language", "ja"))
            g["sources"].add(value.get("source", "conversation_turn"))
            if evidence_query:
                g["evidence_queries"].add(str(evidence_query))

        for g in grouped.values():
            g["confidence_avg"] = g["confidence_sum"] / max(g["candidate_count"], 1)
            g["languages"] = sorted(g["languages"])
            g["sources"] = sorted(g["sources"])
            g["evidence_queries"] = sorted(g["evidence_queries"])
        return grouped

    @staticmethod
    def should_promote(aggregate: Dict[str, Any]) -> PromotionDecision:
        """簡易昇格ルール。明示要求は優先、その他は複数回出現ベース。"""
        ctype = aggregate.get("candidate_type", "unknown")
        count = int(aggregate.get("candidate_count", 0))
        repeat_sum = int(aggregate.get("repeat_count_sum", 0))
        conf_max = float(aggregate.get("confidence_max", 0.0))
        if MemoryPromoter._is_explicit_remember(aggregate):
            if conf_max >= 0.5 and MemoryPromoter._has_actionable_content(aggregate):
                return PromotionDecision(True, "explicit_remember")
            return PromotionDecision(False, "explicit_low_confidence")

        if ctype == "visitor_name" and conf_max >= 0.9:
            return PromotionDecision(True, "visitor_name_high_confidence")

        thresholds = {
            "visitor_name": 0.85,
            "visitor_affiliation": 0.8,
            "language_preference": 0.65,
            "episode_incident": 0.7,
            "location_preference": 0.65,
        }
        min_conf = thresholds.get(ctype, 0.8)
        if conf_max < min_conf:
            return PromotionDecision(False, "confidence_below_threshold")

        if count >= 2 or repeat_sum >= 2:
            return PromotionDecision(True, "repeated_candidate")
        return PromotionDecision(False, "insufficient_repetition")

    @staticmethod
    def build_existing_index(items: Iterable[Any]) -> set[str]:
        """既存長期メモリの重複判定インデックスを作成。"""
        keys: set[str] = set()
        for item in items:
            value = getattr(item, "value", None) or {}
            mtype = value.get("type") or value.get("candidate_type") or "unknown"
            content = str(value.get("data", value.get("content", ""))).strip()
            if content:
                keys.add(MemoryPromoter._aggregate_key(mtype, content))
        return keys

    @staticmethod
    def to_long_term_record(aggregate: Dict[str, Any]) -> Dict[str, Any]:
        """集約候補から長期メモリレコードを生成。"""
        return {
            "data": aggregate["content"],
            "type": aggregate["candidate_type"],
            "confidence": aggregate.get("confidence_max", 0.5),
            "timestamp": aggregate.get("last_seen_at", time.time()),
            "source": "promoter",
            "promotion": {
                "candidate_count": aggregate.get("candidate_count", 1),
                "repeat_count_sum": aggregate.get("repeat_count_sum", 1),
                "confidence_avg": aggregate.get(
                    "confidence_avg",
                    aggregate.get("confidence_max", 0.5),
                ),
                "first_seen_at": aggregate.get("first_seen_at"),
                "last_seen_at": aggregate.get("last_seen_at"),
                "sensitivity": aggregate.get("sensitivity", "unknown"),
                "volatility": aggregate.get("volatility", "high"),
            },
        }

    @staticmethod
    def _aggregate_key(memory_type: str, content: str) -> str:
        normalized = canonicalize_facility_memory_key_text(content)
        normalized = unicodedata.normalize("NFKC", normalized)
        normalized = " ".join(normalized.strip().lower().split())
        return f"{memory_type}:{normalized}"

    @staticmethod
    def _is_explicit_remember(aggregate: Dict[str, Any]) -> bool:
        ctype = str(aggregate.get("candidate_type", "unknown"))
        if ctype == "explicit_remember":
            return True

        text_parts = [str(aggregate.get("content", ""))]
        evidence_queries = aggregate.get("evidence_queries", [])
        if isinstance(evidence_queries, list):
            text_parts.extend(str(q) for q in evidence_queries)
        text = " ".join(text_parts).lower()
        return any(
            keyword in text
            for keyword in (
                "覚えて",
                "記憶して",
                "忘れないで",
                "remember",
                "don't forget",
                "keep in mind",
            )
        )

    @staticmethod
    def _has_actionable_content(aggregate: Dict[str, Any]) -> bool:
        content = str(aggregate.get("content", "")).strip()
        return content not in {"ください", "お願いします", "please"} and len(content) > 1


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_memory_promoter_instance: MemoryPromoter | None = None


def get_memory_promoter() -> MemoryPromoter:
    """Return a module-level singleton MemoryPromoter instance."""
    global _memory_promoter_instance
    if _memory_promoter_instance is None:
        _memory_promoter_instance = MemoryPromoter()
    return _memory_promoter_instance


def reset_memory_promoter() -> None:
    """Reset the singleton (for tests)."""
    global _memory_promoter_instance
    _memory_promoter_instance = None
