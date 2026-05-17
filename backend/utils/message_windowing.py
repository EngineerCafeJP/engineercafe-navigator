"""
メッセージウィンドウイング

長いセッションでのコンテキストオーバーフロー防止。
最近のメッセージとシステムメッセージを保持し、古いメッセージを要約で置き換える。
"""

import logging
from typing import List, Optional

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MAX_MESSAGES = 20
DEFAULT_SUMMARY_THRESHOLD = 30

_IMPORTANT_MEMORY_DECLARATION_MARKERS = (
    "覚えてください",
    "覚えておいて",
    "希望席は",
    "好きな席は",
    "利用目的は",
    "目的は",
    "名前は",
    "呼んでください",
    "prefer",
    "remember that",
    "my name is",
    "call me",
)
_IMPORTANT_MEMORY_ENTITY_MARKERS = (
    "希望席",
    "好きな席",
    "利用目的",
    "目的",
    "名前",
    "窓側",
    "集中作業",
    "コワーキング",
    "preferred seat",
    "seat preference",
    "purpose",
)
_IMPORTANT_MEMORY_PREFERENCE_MARKERS = (
    "がいい",
    "を使いたい",
    "したい",
    "希望します",
    "お願いします",
    "prefer",
    "would like",
    "i want",
)
_QUESTION_OR_LOOKUP_MARKERS = (
    "?",
    "？",
    "ですか",
    "ますか",
    "でしょうか",
    "教えて",
    "空いて",
    "空き",
    "available",
    "tell me",
    "what",
    "where",
    "how",
)
_MAX_SUMMARY_FACTS = 5
_MAX_SUMMARY_FACT_CHARS = 160


def _looks_like_declared_user_fact(content: str) -> bool:
    normalized = content.lower()
    if any(marker in normalized for marker in _QUESTION_OR_LOOKUP_MARKERS):
        return False

    has_entity = any(marker.lower() in normalized for marker in _IMPORTANT_MEMORY_ENTITY_MARKERS)
    if not has_entity:
        return False

    if any(marker.lower() in normalized for marker in _IMPORTANT_MEMORY_DECLARATION_MARKERS):
        return True

    return any(marker.lower() in normalized for marker in _IMPORTANT_MEMORY_PREFERENCE_MARKERS)


def _extract_important_user_facts(messages: List[BaseMessage]) -> List[str]:
    facts: List[str] = []
    seen: set[str] = set()
    for msg in messages:
        if not isinstance(msg, HumanMessage):
            continue
        content = str(msg.content or "").strip()
        if not content:
            continue
        if not _looks_like_declared_user_fact(content):
            continue
        compact = " ".join(content.split())
        if len(compact) > _MAX_SUMMARY_FACT_CHARS:
            compact = compact[: _MAX_SUMMARY_FACT_CHARS - 1].rstrip() + "…"
        if compact in seen:
            continue
        seen.add(compact)
        facts.append(compact)
        if len(facts) >= _MAX_SUMMARY_FACTS:
            break
    return facts


def _build_window_summary(dropped_messages: List[BaseMessage], dropped_count: int) -> SystemMessage:
    facts = _extract_important_user_facts(dropped_messages)
    content = (
        f"[Previous {dropped_count} messages summarized: "
        "The conversation covered topics from the user's earlier questions."
    )
    if facts:
        content += " Important earlier user facts: " + " / ".join(facts) + "."
    content += " Refer to the most recent messages for current context.]"
    return SystemMessage(content=content)


class MessageWindow:
    """メッセージウィンドウ管理"""

    def __init__(
        self,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        summary_threshold: int = DEFAULT_SUMMARY_THRESHOLD,
    ):
        self.max_messages = max_messages
        self.summary_threshold = summary_threshold

    def apply_window(
        self,
        messages: List[BaseMessage],
        system_messages: Optional[List[SystemMessage]] = None,
    ) -> List[BaseMessage]:
        """メッセージにウィンドウを適用

        Args:
            messages: 全メッセージリスト
            system_messages: 常に保持するシステムメッセージ

        Returns:
            ウィンドウが適用されたメッセージリスト
        """
        if len(messages) <= self.max_messages:
            return list(messages)

        # Separate system messages from conversation messages
        sys_msgs = []
        conv_msgs = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                sys_msgs.append(msg)
            else:
                conv_msgs.append(msg)

        # Keep only recent conversation messages
        if len(conv_msgs) > self.max_messages:
            dropped_count = len(conv_msgs) - self.max_messages
            dropped_msgs = conv_msgs[:dropped_count]
            recent_msgs = conv_msgs[-self.max_messages :]
            summary = _build_window_summary(dropped_msgs, dropped_count)

            logger.info(
                "Message window applied: %d messages dropped, %d retained",
                dropped_count,
                len(recent_msgs),
            )

            return sys_msgs + [summary] + recent_msgs

        return sys_msgs + conv_msgs

    def should_compact(self, messages: List[BaseMessage]) -> bool:
        """メッセージのコンパクション（要約）が必要か判定"""
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]
        return len(non_system) >= self.summary_threshold

    def estimate_tokens(self, messages: List[BaseMessage]) -> int:
        """メッセージの概算トークン数（簡易版: 文字数/3）"""
        total_chars = sum(len(str(m.content)) for m in messages)
        return total_chars // 3  # Rough estimate for mixed JP/EN


# Module-level singleton
_default_window = MessageWindow()


def apply_message_window(messages: List[BaseMessage]) -> List[BaseMessage]:
    """デフォルトウィンドウを適用する便利関数"""
    return _default_window.apply_window(messages)
