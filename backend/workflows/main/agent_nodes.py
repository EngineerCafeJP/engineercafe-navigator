"""Agent execution nodes for MainWorkflow."""

from __future__ import annotations

import logging

from backend.workflows.main.evidence import _truthy_context_flag
from backend.workflows.main.types import WorkflowStateDict

logger = logging.getLogger(__name__)


class AgentNodesWorkflowMixin:
    async def _business_info_node(self, state: WorkflowStateDict) -> dict:
        """営業情報ノード: 営業情報を処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        request_type = state.get("routing", {}).get("request_type")

        # Get cached knowledge results from state
        state_context = state.get("context", {}).get("knowledge_results")
        priority_signals = state.get("context", {}).get("priority_signals")
        long_term_memory = state.get("context", {}).get("long_term_memory", [])
        if long_term_memory:
            state_context = {**(state_context or {}), "long_term_memory": long_term_memory}

        result = await self._business_info_agent.answer_business_query(
            query,
            request_type,
            language,
            session_id,
            state_context=state_context,
            context_signals=priority_signals,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _farewell_node(self, state: WorkflowStateDict) -> dict:
        """退館ノード: 退館フローを処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")

        result = await self._farewell_agent.handle_farewell(
            query=query,
            language=language,
            session_id=session_id,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "happy"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _facility_node(self, state: WorkflowStateDict) -> dict:
        """施設ノード: 施設情報を処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        request_type = state.get("routing", {}).get("request_type")

        # Get cached knowledge results from state
        state_context = state.get("context", {}).get("knowledge_results")
        priority_signals = state.get("context", {}).get("priority_signals")
        long_term_memory = state.get("context", {}).get("long_term_memory", [])
        if long_term_memory:
            state_context = {**(state_context or {}), "long_term_memory": long_term_memory}

        result = await self._facility_agent.answer_facility_query(
            query,
            request_type,
            language,
            session_id,
            state_context=state_context,
            context_signals=priority_signals,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _event_node(self, state: WorkflowStateDict) -> dict:
        """イベントノード: イベント情報を処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        include_evidence = _truthy_context_flag(
            state.get("context", {}).get("include_rag_evidence")
        )
        result = await self._event_agent.answer_event_query(
            query,
            language,
            session_id,
            include_evidence=include_evidence,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _slide_node(self, state: WorkflowStateDict) -> dict:
        """スライドノード: スライドナレーションと質問応答を処理"""
        from backend.agents.slide_agent import SlideAction

        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "default")
        request_type = state.get("routing", {}).get("request_type", "narrate")

        # アクションマッピング
        action_map: dict[str, SlideAction] = {
            "narrate": "narrate",
            "next": "next",
            "previous": "previous",
            "goto": "goto",
            "question": "question",
        }

        slide_action: SlideAction = action_map.get(request_type, "narrate")

        result = await self._slide_agent.handle_slide_action(
            action=slide_action,
            query=query if slide_action == "question" else None,
            language=language,
            session_id=session_id,
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _general_knowledge_node(self, state: WorkflowStateDict) -> dict:
        """一般知識ノード: 一般的な知識およびメモリクエリを処理"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        session_id = state.get("session_id", "")
        query_type = state.get("routing", {}).get("request_type", "general")
        memory_context = state.get("context", {}).get("memory")
        state_context = (
            memory_context
            if query_type == "memory"
            else state.get("context", {}).get("knowledge_results")
        )
        priority_signals = state.get("context", {}).get("priority_signals")
        long_term_memory = state.get("context", {}).get("long_term_memory", [])

        result = await self._general_knowledge_agent.answer_query(
            query=query,
            language=language,
            session_id=session_id,
            query_type=query_type,
            state_context=state_context,
            context_signals=priority_signals,
            long_term_memory=long_term_memory,  # NEW
        )

        return {
            "answer": result.get("answer", ""),
            "emotion": result.get("emotion", "neutral"),
            "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
        }

    async def _notify_discord_emergency(self, query: str, result: dict) -> None:
        """Discord Webhook に緊急通知を送信（fire-and-forget）"""
        try:
            from backend.services.discord_notification_service import (
                get_discord_notification_service,
            )

            svc = get_discord_notification_service()
            await svc.send_notification(
                title="緊急通報",
                message=f"来館者からの緊急メッセージ: {query}",
                severity="critical",
                metadata=result.get("metadata", {}),
            )
        except Exception:
            logger.warning("Discord emergency notification failed", exc_info=True)
