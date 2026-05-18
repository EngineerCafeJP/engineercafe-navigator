from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.agents.llm_metadata import merge_llm_metadata
from backend.config.prompts.memory_prompts import build_memory_prompt

logger = logging.getLogger(__name__)


class GeneralKnowledgeMemoryMixin:
    async def _handle_memory_query(
        self,
        query: str,
        session_id: str,
        language: str = "ja",
        state_context: Optional[Dict[str, Any]] = None,
        long_term_memory: Optional[list] = None,
    ) -> Dict[str, Any]:
        """メモリ関連クエリを処理"""
        has_state_memory_context = self._has_state_memory_context(state_context)
        if not self.memory_system and not has_state_memory_context:
            return self._handle_no_memory_system(language)

        try:
            query_type = self._detect_memory_query_type(query)
            if has_state_memory_context:
                context = dict(state_context)
            elif self.memory_system:
                context = await self.memory_system.get_context(
                    query, session_id, {"language": language, "inherit_context": True}
                )
            else:
                return self._no_history_response(language)
            context = self._merge_long_term_memory_context(
                context,
                long_term_memory,
                language,
            )

            if not context.get("recent_messages") and not context.get("long_term_memory"):
                if self._is_memory_write_query(query):
                    return self._memory_write_ack_response(language)
                return self._no_history_response(language)

            preference_response = self._session_preference_recall_response(
                query,
                context,
                query_type,
                language,
            )
            if preference_response is not None:
                return preference_response

            prompt = self._build_memory_prompt(query, context, query_type, language)

            from langchain_core.messages import HumanMessage

            messages = [HumanMessage(content=prompt)]
            answer = await self.provider.generate(messages=messages, config=self.model_config)

            emotion = self._determine_memory_emotion(context, query_type)

            metadata = merge_llm_metadata(
                {
                    "agent": self.name,
                    "status": "success",
                    "category": "general_knowledge",
                    "request_type": query_type,
                    "route": "general_knowledge",
                    "query_type": query_type,
                    "message_count": len(context.get("recent_messages", [])),
                    "inherited_request_type": context.get("inherited_request_type"),
                    "long_term_memory_count": len(context.get("long_term_memory", [])),
                },
                answer,
            )

            return {
                "answer": str(answer),
                "emotion": emotion,
                "metadata": metadata,
            }
        except Exception as e:
            logger.exception("Memory query error: %s", e)
            return {
                "answer": (
                    "メモリの処理中にエラーが発生しました。"
                    if language == "ja"
                    else "An error occurred while processing memory."
                ),
                "emotion": "surprised",
                "metadata": {"agent": self.name, "status": "error", "error": str(e)},
            }

    @staticmethod
    def _has_state_memory_context(state_context: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(state_context, dict):
            return False
        return bool(
            state_context.get("recent_messages")
            or state_context.get("context_string")
            or state_context.get("long_term_memory")
        )

    def _session_preference_recall_response(
        self,
        query: str,
        context: Dict[str, Any],
        query_type: str,
        language: str,
    ) -> Optional[Dict[str, Any]]:
        """Answer practical same-session seat/purpose recalls deterministically."""
        normalized = query.lower()
        asks_seat_or_purpose = any(
            marker in normalized
            for marker in (
                "希望席",
                "好きな席",
                "利用目的",
                "目的",
                "preferred seat",
                "seat preference",
                "purpose",
            )
        )
        if not asks_seat_or_purpose:
            return None

        seat: Optional[str] = None
        purpose: Optional[str] = None
        contents = self._trusted_session_memory_contents(context)

        for content in contents:
            lower_content = content.lower()
            if seat is None:
                if "窓側" in content or ("窓" in content and "席" in content):
                    seat = "窓側"
                elif "電源" in content and "席" in content:
                    seat = "電源に近い席"
                elif "集中スペース" in content:
                    seat = "集中スペース"
            if purpose is None:
                if "集中作業" in content:
                    purpose = "集中作業"
                elif "コワーキングスペース" in content or "コワーキング" in content:
                    purpose = "コワーキング"
                elif "開発作業" in content or "作業" in content:
                    purpose = "作業"
                elif "coworking" in lower_content:
                    purpose = "coworking"
                elif "focus work" in lower_content:
                    purpose = "focus work"

        if seat is None and purpose is None:
            return None

        if language == "en":
            parts = []
            if seat:
                parts.append(f"your preferred seat is {seat}")
            if purpose:
                parts.append(f"your purpose is {purpose}")
            answer = "[relaxed]In this session, " + " and ".join(parts) + "."
        else:
            if seat and purpose:
                answer = f"[relaxed]この会話では、希望席は{seat}、利用目的は{purpose}です。"
            elif seat:
                answer = f"[relaxed]この会話では、希望席は{seat}です。"
            else:
                answer = f"[relaxed]この会話では、利用目的は{purpose}です。"

        metadata = {
            "agent": self.name,
            "status": "success",
            "category": "general_knowledge",
            "request_type": query_type,
            "route": "general_knowledge",
            "query_type": query_type,
            "message_count": len(context.get("recent_messages", [])),
            "inherited_request_type": context.get("inherited_request_type"),
            "long_term_memory_count": len(context.get("long_term_memory", [])),
            "provider_called": False,
            "sources": ["session_memory"],
        }
        return {
            "answer": answer,
            "emotion": "relaxed",
            "metadata": metadata,
        }

    @staticmethod
    def _trusted_session_memory_contents(context: Dict[str, Any]) -> list[str]:
        """Return user-authored or workflow-summarized facts for deterministic recall."""
        contents: list[str] = []
        for message in context.get("recent_messages", []):
            if not isinstance(message, dict):
                continue
            content = str(message.get("content") or "")
            if not content:
                continue
            role = str(message.get("role") or "").lower()
            if role == "user" or "Important earlier user facts:" in content:
                contents.append(content)

        context_string = str(context.get("context_string") or "").strip()
        if context_string:
            for line in context_string.splitlines():
                stripped = line.strip()
                if stripped.startswith(("ユーザー:", "User:")):
                    contents.append(stripped.split(":", 1)[1].strip())
                elif "Important earlier user facts:" in stripped:
                    contents.append(stripped)
        return contents

    def _detect_memory_query_type(self, query: str) -> str:
        """メモリ質問タイプの判定"""
        lower_query = query.lower()

        question_keywords = [
            "何を聞いた",
            "何聞いた",
            "質問した",
            "さっき聞いた",
            "前に聞いた",
            "what did i ask",
            "what i asked",
            "my question",
            "previous question",
        ]
        if any(kw in lower_query for kw in question_keywords):
            return "question_history"

        answer_keywords = [
            "答え",
            "回答",
            "何て言った",
            "何と言った",
            "教えてくれた",
            "answer",
            "response",
            "what did you say",
            "you told me",
            "your answer",
        ]
        if any(kw in lower_query for kw in answer_keywords):
            return "answer_history"

        other_keywords = [
            "もう一つの方",
            "もう一つ",
            "もうひとつ",
            "他の方",
            "別の方",
            "the other one",
            "the other",
            "another one",
            "alternative",
        ]
        if any(kw in lower_query for kw in other_keywords):
            return "other_option"

        return "general_memory"

    @staticmethod
    def _is_memory_write_query(query: str) -> bool:
        """初回の記憶登録依頼を、履歴参照質問と区別する。"""
        lower_query = query.lower()
        remember_keywords = [
            "覚えて",
            "憶えて",
            "覚えといて",
            "覚えておいて",
            "記憶して",
            "忘れないで",
            "remember",
            "memorize",
            "keep in mind",
        ]
        self_disclosure_keywords = [
            "私の名前",
            "僕の名前",
            "俺の名前",
            "名前は",
            "わたしは",
            "私は",
            "ぼくは",
            "僕は",
            "my name is",
            "i am ",
            "i'm ",
            "call me",
        ]
        if any(kw in lower_query for kw in remember_keywords):
            try:
                from backend.utils.memory_extractor import _extract_remember_request

                if _extract_remember_request(query, "ja") or _extract_remember_request(
                    query,
                    "en",
                ):
                    return True
            except Exception:
                pass

        return any(kw in lower_query for kw in remember_keywords) and any(
            kw in lower_query for kw in self_disclosure_keywords
        )

    def _build_memory_prompt(
        self, query: str, context: Dict, query_type: str, language: str
    ) -> str:
        """メモリプロンプト構築（memory_prompts.pyに委譲）"""
        return build_memory_prompt(query, context, query_type, language)

    def _merge_long_term_memory_context(
        self,
        context: Dict[str, Any],
        long_term_memory: Optional[list],
        language: str,
    ) -> Dict[str, Any]:
        """セッション履歴コンテキストへ長期メモリを追記する。"""
        if not long_term_memory:
            return context

        merged = dict(context or {})
        long_term_text = self._format_long_term_memory_context(long_term_memory, language)
        if not long_term_text:
            return merged

        existing_context = str(merged.get("context_string") or "").strip()
        merged["context_string"] = f"{existing_context}\n\n{long_term_text}".strip()
        merged["long_term_memory"] = long_term_memory
        return merged

    @staticmethod
    def _format_long_term_memory_context(
        long_term_memory: Optional[list],
        language: str,
    ) -> str:
        """長期メモリをプロンプトへ渡せる短い箇条書きに整形する。"""
        if not long_term_memory:
            return ""

        lines: list[str] = []
        for memory in long_term_memory:
            if isinstance(memory, dict):
                content = str(
                    memory.get("data")
                    or memory.get("content")
                    or memory.get("summary")
                    or memory.get("text")
                    or ""
                ).strip()
                memory_type = str(memory.get("type") or memory.get("candidate_type") or "").strip()
                if content and memory_type:
                    lines.append(f"- [{memory_type}] {content}")
                elif content:
                    lines.append(f"- {content}")
            else:
                content = str(memory).strip()
                if content:
                    lines.append(f"- {content}")

        if not lines:
            return ""

        title = (
            "長期メモリ（過去セッションから保持された利用者情報）"
            if language == "ja"
            else ("Long-term memory (visitor facts retained across sessions)")
        )
        return f"{title}:\n" + "\n".join(lines)

    def _determine_memory_emotion(self, context: Dict, query_type: str) -> str:
        """メモリクエリの感情タグ決定"""
        if not context.get("recent_messages"):
            return "sad"
        if query_type == "other_option":
            return "happy"
        if query_type in ["question_history", "answer_history"]:
            return "relaxed"
        return "neutral"

    def _handle_no_memory_system(self, language: str) -> Dict[str, Any]:
        """メモリシステム利用不可時の応答"""
        message = (
            "メモリシステムが利用できません。しばらくしてからもう一度お試しください。"
            if language == "ja"
            else "Memory system is not available at the moment. Please try again later."
        )
        return {
            "answer": message,
            "emotion": "sad",
            "metadata": {
                "agent": self.name,
                "status": "memory_unavailable",
                "error": "no_memory_system",
            },
        }

    def _no_history_response(self, language: str) -> Dict[str, Any]:
        """会話履歴なし時の応答"""
        message = (
            "まだ会話履歴がありません。何か質問してみてください！"
            if language == "ja"
            else "I don't have any conversation history yet. Let's start chatting!"
        )
        return {
            "answer": message,
            "emotion": "sad",
            "metadata": {"agent": self.name, "status": "no_history", "query_type": "memory"},
        }

    def _memory_write_ack_response(self, language: str) -> Dict[str, Any]:
        """初回の記憶登録依頼に対する応答。"""
        message = (
            "承知しました。今後の会話で参照できるように覚えておきます。"
            if language == "ja"
            else "Got it. I'll remember that so I can refer to it in future conversations."
        )
        return {
            "answer": message,
            "emotion": "helpful",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "query_type": "memory_write",
            },
        }

    # =========================================================================
    # 一般クエリ ヘルパーメソッド
    # =========================================================================
