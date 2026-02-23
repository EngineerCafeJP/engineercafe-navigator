"""
メッセージウィンドウイング

長いセッションでのコンテキストオーバーフロー防止。
最近のメッセージとシステムメッセージを保持し、古いメッセージを要約で置き換える。
"""

import logging
from typing import List, Optional

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MAX_MESSAGES = 20
DEFAULT_SUMMARY_THRESHOLD = 30


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
            recent_msgs = conv_msgs[-self.max_messages :]

            # Create summary placeholder for dropped messages
            summary = SystemMessage(
                content=f"[Previous {dropped_count} messages summarized: "
                f"The conversation covered topics from the user's earlier questions. "
                f"Refer to the most recent messages for current context.]"
            )

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
