"""Orchestrator command helpers for MainWorkflow."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, cast

from langgraph.types import Command

from backend.agents.orchestrator_agent import OrchestratorDecision, RoutingTarget
from backend.config.routing_constants import extract_request_type, normalize_agent_node
from backend.utils.cafe_entity import cafe_entity_metadata
from backend.workflows.main.types import WorkflowStateDict

logger = logging.getLogger(__name__)


class OrchestrationWorkflowMixin:
    @staticmethod
    def _build_routing_payload(
        decision: OrchestratorDecision,
        *,
        agent: str,
        category: Optional[str] = None,
        request_type: Optional[str] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "agent": agent,
            "category": category or decision.category,
            "request_type": request_type or decision.request_type,
            "confidence": confidence if confidence is not None else decision.confidence,
            "reasoning": reasoning or decision.reasoning,
            "debug_info": decision.debug_info,
        }

    async def _handle_emergency(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
    ) -> Optional[Command[RoutingTarget]]:
        if decision.category != "emergency":
            return None

        from backend.utils.emergency_templates import get_emergency_response

        query = state.get("query", "")
        logger.info(
            "Inline emergency: lang=%s, query=%s",
            decision.language,
            query[:80],
        )
        result = get_emergency_response(query, decision.language)
        asyncio.create_task(self._notify_discord_emergency(query, result))
        return Command(
            goto="format_response",
            update={
                "language": decision.language,
                "routing": self._build_routing_payload(
                    decision,
                    agent="orchestrator_inline",
                    category="emergency",
                ),
                "answer": result["response"],
                "emotion": result["emotion"],
                "metadata": {
                    **state.get("metadata", {}),
                    "emergency": result["metadata"],
                },
            },
        )

    async def _handle_greeting(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
        session_id: str,
    ) -> Optional[Command[RoutingTarget]]:
        if decision.category != "greeting":
            return None

        from backend.config.routing_constants import TIME_GREETING_TEMPLATES
        from backend.utils.time_utils import get_current_time_period, get_now_jst

        query = state.get("query", "")
        lang = decision.language or "ja"
        if lang not in ("ja", "en", "zh", "ko"):
            logger.warning("Greeting: unsupported language '%s', falling back to 'ja'", lang)
            lang = "ja"
        now = get_now_jst()
        period = get_current_time_period(now.hour)
        templates = TIME_GREETING_TEMPLATES.get(period, TIME_GREETING_TEMPLATES["afternoon"])
        base_greeting = templates.get(lang, templates["ja"])

        greeting_bodies = {
            "ja": (
                "ここはエンジニアのための無料コワーキングスペースです。"
                "お気軽にご利用ください。何かお手伝いできることはありますか？"
            ),
            "en": (
                "This is a free coworking space for engineers. "
                "Feel free to make yourself at home. "
                "How can I help you?"
            ),
            "zh": ("这里是面向工程师的免费共享工作空间。请随意使用。有什么可以帮助您的吗？"),
            "ko": (
                "이곳은 엔지니어를 위한 무료 코워킹 스페이스입니다. "
                "편하게 이용해 주세요. 무엇을 도와드릴까요?"
            ),
        }
        body = greeting_bodies.get(lang, greeting_bodies["ja"])
        sep = " " if lang == "en" else ""
        greeting_msg = f"{base_greeting}{sep}{body}"

        logger.info(
            "Inline greeting: lang=%s, period=%s, query=%s",
            lang,
            period,
            query[:80],
        )
        await self._store_reception_session(
            session_id=session_id,
            stage="greeting",
            language=lang,
            metadata={"reception_action": "start_reception"},
        )

        return Command(
            goto="format_response",
            update={
                "language": lang,
                "routing": self._build_routing_payload(
                    decision,
                    agent="orchestrator_inline",
                    category="greeting",
                ),
                "answer": greeting_msg,
                "emotion": "happy",
                "metadata": {
                    **state.get("metadata", {}),
                    "agent": "reception",
                    "reception_stage": "greeting",
                    "reception_action": "start_reception",
                },
            },
        )

    async def _handle_clarification(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
    ) -> Optional[Command[RoutingTarget]]:
        if decision.category not in self._CLARIFICATION_CATEGORIES:
            return None

        from backend.utils.clarification_templates import get_clarification_response

        query = state.get("query", "")
        logger.info(
            "Inline clarification: category=%s, lang=%s, query=%s",
            decision.category,
            decision.language,
            query[:80],
        )
        result = get_clarification_response(
            category=decision.category,
            language=decision.language,
        )
        metadata = {
            **state.get("metadata", {}),
            "clarification": {
                **result["metadata"],
                "clarification_type": decision.category,
            },
            "requires_followup": True,
        }
        if decision.category == "cafe-clarification-needed":
            metadata["cafe_entity_resolution"] = cafe_entity_metadata(
                entity="ambiguous",
                status="needs_clarification",
                source="workflow_clarification",
                request_type=decision.request_type,
            )
        return Command(
            goto="format_response",
            update={
                "language": decision.language,
                "routing": self._build_routing_payload(
                    decision,
                    agent="orchestrator_inline",
                ),
                "answer": result["response"],
                "emotion": result["emotion"],
                "metadata": metadata,
            },
        )

    async def _handle_topic_guard(
        self,
        state: WorkflowStateDict,
        decision: OrchestratorDecision,
    ) -> Optional[Command[RoutingTarget]]:
        query = state.get("query", "")
        try:
            from backend.utils.topic_guard import check_topic_adherence

            on_topic, off_topic_response = check_topic_adherence(
                query=query,
                routing_category=decision.category,
                language=decision.language,
            )
        except Exception as guard_err:
            logger.debug("Topic guard skipped: %s", guard_err)
            return None

        if on_topic:
            return None

        logger.info("Off-topic query filtered: %.50s", query)
        return Command(
            goto="format_response",
            update={
                "language": decision.language,
                "routing": self._build_routing_payload(
                    decision,
                    agent="topic_guard",
                    category="off_topic",
                    request_type="redirect",
                    confidence=1.0,
                    reasoning="Query is outside Engineer Cafe scope",
                ),
                "answer": off_topic_response,
                "emotion": "neutral",
            },
        )

    async def _orchestrator_node(self, state: WorkflowStateDict) -> Command[RoutingTarget]:
        """
        オーケストレーターノード（Supervisor）

        OrchestratorAgentを使用してクエリを分析し、
        適切なエージェントにCommand patternでルーティング。
        clarification カテゴリはインラインでテンプレート応答を生成し、
        format_response に直接ルーティングする。

        Reception integration: before the LLM routing call, check if the
        session has an active (incomplete) reception flow. If so, short-circuit
        with the appropriate reception stage response.
        """
        from backend.workflows.reception_workflow import invoke_reception_subgraph
        from backend.utils.reception_status import check_reception_status

        query = state.get("query", "")
        session_id = state.get("session_id", "")

        # --- Reception status gate (before LLM call) ---
        reception_status = state.get("reception_status")
        if reception_status is None or not reception_status:
            reception_status = await check_reception_status(session_id)

        if self._reception_is_active(reception_status):
            assistant_profile_response = self._active_reception_assistant_profile_response(
                query,
                state.get("language", "ja"),
            )
            if assistant_profile_response is not None:
                return Command(
                    goto="format_response",
                    update=assistant_profile_response,
                )

            if await self._should_bypass_active_reception_async(query, reception_status):
                await self._store_reception_session(
                    session_id=session_id,
                    stage="completed",
                    language=state.get("language", "ja"),
                    trigger_type=reception_status.get("trigger_type", "voice"),
                    status="completed",
                    metadata={"reception_action": "bypass_for_information_query"},
                    purpose=reception_status.get("purpose"),
                    visitor_identity=reception_status.get("visitor_identity"),
                )
            else:
                reception_result = await invoke_reception_subgraph(
                    state,
                    reception_status,
                    self._store_reception_session,
                )
                if reception_result.get("target_agent"):
                    routing = reception_result.get("routing") or {}
                    target_agent, resolution_source = normalize_agent_node(
                        reception_result["target_agent"],
                        category=routing.get("category"),
                        request_type=routing.get("request_type"),
                    )
                    return Command(
                        goto=cast(RoutingTarget, target_agent),
                        update={
                            "language": state.get("language", "ja"),
                            "routing": {
                                **routing,
                                "agent": target_agent,
                                "debug_info": {
                                    **routing.get("debug_info", {}),
                                    "raw_target_agent": reception_result["target_agent"],
                                    "agent_resolution_source": resolution_source,
                                },
                            },
                            "metadata": {
                                **reception_result["metadata"],
                                "reception_target_agent": target_agent,
                            },
                        },
                    )

                return Command(
                    goto="format_response",
                    update={
                        "answer": reception_result["answer"],
                        "emotion": reception_result["emotion"],
                        "metadata": reception_result["metadata"],
                    },
                )

        # --- Normal orchestrator LLM routing ---
        memory_context = state.get("context", {}).get("memory")
        cafe_resolution = self._resolve_cafe_entity_for_turn(query, memory_context)
        if cafe_resolution and cafe_resolution.get("entity") == "saino_cafe":
            request_type = cafe_resolution.get("request_type") or extract_request_type(query)
            if request_type == "nearby":
                request_type = None
            return Command(
                goto="business_info",
                update={
                    "language": self._get_response_language(
                        query,
                        state.get("language", "ja"),
                    ),
                    "routing": {
                        "agent": "business_info",
                        "category": "saino-cafe",
                        "request_type": request_type,
                        "confidence": cafe_resolution.get("confidence", 0.95),
                        "reasoning": "Cafe entity resolved to cafe&bar saino",
                        "debug_info": {
                            "fast_path": True,
                            "cafe_entity_resolution": cafe_resolution,
                        },
                    },
                    "metadata": {
                        **state.get("metadata", {}),
                        "cafe_entity_resolution": cafe_resolution,
                    },
                },
            )

        decision = await self.orchestrator.decide_next_agent(
            query=query,
            session_id=session_id,
            memory_context=memory_context,
        )
        next_agent, resolution_source = normalize_agent_node(
            decision.next_agent,
            category=decision.category,
            request_type=decision.request_type,
            prefer_category=True,
        )
        debug_info = {
            **decision.debug_info,
            "raw_next_agent": decision.next_agent,
            "agent_resolution_source": resolution_source,
        }

        for handler in (
            lambda current_state, current_decision: self._handle_emergency(
                current_state,
                current_decision,
            ),
            lambda current_state, current_decision: self._handle_greeting(
                current_state,
                current_decision,
                session_id,
            ),
            lambda current_state, current_decision: self._handle_clarification(
                current_state,
                current_decision,
            ),
            lambda current_state, current_decision: self._handle_topic_guard(
                current_state,
                current_decision,
            ),
        ):
            cmd = await handler(state, decision)
            if cmd is not None:
                return cmd

        return Command(
            goto=next_agent,
            update={
                "language": decision.language,
                "routing": {
                    **self._build_routing_payload(
                        decision,
                        agent=next_agent,
                    ),
                    "debug_info": debug_info,
                },
            },
        )
