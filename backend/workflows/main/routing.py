"""Routing and reception guard helpers for MainWorkflow."""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from backend.agents.orchestrator_agent import OrchestratorAgent as RoutingLogicAgent
from backend.config.routing_constants import (
    GREETING_KEYWORDS,
    extract_request_type,
    match_keywords,
    normalize_agent_node,
)
from backend.utils.cafe_entity import (
    cafe_entity_metadata,
    canonicalize_facility_memory_key_text,
    context_mentions_engineer_cafe_hours,
    inherited_request_type,
    is_ambiguous_cafe_hours_query,
    is_colocated_or_adjacent_saino_reference,
    is_saino_reference,
)
from backend.observability.structured_logger import log_reception_bypass_decision
from backend.utils.intent_classifier import is_reception_continuation_utterance
from backend.workflows.main.types import WorkflowStateDict

logger = logging.getLogger(__name__)


class RoutingWorkflowMixin:
    def _input_type_decision(self, state: WorkflowStateDict) -> str:
        """入力タイプに基づいてルーティング（テキスト or 画像）"""
        if state.get("image_data") is not None:
            return "image"
        return "text"

    @staticmethod
    def _reception_is_active(reception_status: Optional[dict[str, Any]]) -> bool:
        if not reception_status:
            return False
        return not reception_status.get("completed") and reception_status.get("stage") not in (
            "none",
            "error",
        )

    def _has_mixed_intent_greeting(self, query: str) -> bool:
        lower_query = query.lower().strip()
        if not match_keywords(lower_query, GREETING_KEYWORDS):
            return False

        remaining = lower_query
        for keyword in sorted(GREETING_KEYWORDS, key=len, reverse=True):
            remaining = remaining.replace(keyword.lower(), " ").strip()

        remaining = remaining.strip("!！?？。、.,  ")
        return len(remaining) > 3

    def _requires_memory_loader_before_fast_path(self, query: str) -> bool:
        stripped_query = query.strip()
        lower_query = stripped_query.lower()

        if len(stripped_query) < 5:
            return True

        if any(marker in lower_query for marker in self._ANAPHORA_MARKERS):
            return True

        if any(marker in lower_query for marker in self._MEMORY_CONTEXT_QUERY_MARKERS):
            return True

        if self._has_mixed_intent_greeting(stripped_query):
            return True

        memory_checker = getattr(self, "orchestrator", None)
        if memory_checker and hasattr(memory_checker, "_is_memory_related_question"):
            try:
                return bool(memory_checker._is_memory_related_question(stripped_query))
            except AttributeError:
                logger.debug(
                    "Memory fast-path checker is incomplete; falling back to routing logic"
                )

        return RoutingLogicAgent()._is_memory_related_question(stripped_query)

    def _resolve_cafe_entity_for_turn(
        self,
        query: str,
        memory_context: Optional[dict[str, Any]],
    ) -> dict[str, Any] | None:
        current_request_type = extract_request_type(query)
        if current_request_type == "nearby" and is_saino_reference(query):
            current_request_type = None

        if is_ambiguous_cafe_hours_query(query):
            return cafe_entity_metadata(
                entity="ambiguous",
                status="needs_clarification",
                source="workflow_turn",
                request_type=current_request_type,
            )

        if not is_saino_reference(query):
            return None

        resolved_request_type = current_request_type or inherited_request_type(memory_context)
        context_used = False
        source = "workflow_explicit_saino"

        if not current_request_type and resolved_request_type:
            context_used = True
            source = "workflow_short_term_request_type"

        if (
            not resolved_request_type
            and is_colocated_or_adjacent_saino_reference(query)
            and context_mentions_engineer_cafe_hours(memory_context)
        ):
            resolved_request_type = "hours"
            context_used = True
            source = "workflow_short_term_engineer_cafe_hours"

        return cafe_entity_metadata(
            entity="saino_cafe",
            status="resolved",
            source=source,
            request_type=resolved_request_type,
            context_used=context_used,
        )

    @staticmethod
    def _looks_like_information_query(query: str) -> bool:
        """Return true when an active reception turn is actually a normal QA request."""
        normalized = query.strip().lower()
        if not normalized:
            return False

        question_markers = (
            "?",
            "？",
            "教えて",
            "知りたい",
            "方法",
            "どこ",
            "いつ",
            "何時",
            "いくら",
            "ありますか",
            "できますか",
            "していますか",
            "対応",
            "英語対応",
            "違い",
            "営業時間",
            "予約",
            "受付手続き",
            "受付で何を",
            "受け付けで何を",
            "入館",
            "完了",
            "社会利用",
            "料金",
            "飲みたい",
            "食べたい",
            "飲みは可能",
            "飲んでいい",
            "飲めます",
            "飲み物を飲む",
            "注文したい",
            "休憩",
            "休憩できますか",
            "休みたい",
            "休めますか",
            "一息",
            "座りたい",
            "使いたい",
            "見たい",
            "maker'sスペース",
            "makersスペース",
            "メーカースペース",
            "maker's space",
            "makers space",
            "コーヒー",
            "珈琲",
            "カフェラテ",
            "ドリンク",
            "ランチ",
            "サイノ",
            "雑談",
            "おしゃべり",
            "話し相手",
            "元気",
            "疲れた",
            "ありがとう",
            "how",
            "what",
            "where",
            "when",
            "which",
            "tell me",
            "small talk",
            "chat with me",
            "talk with me",
            "how are you",
            "i am tired",
            "i'm tired",
            "thanks",
            "thank you",
            "want to drink",
            "want coffee",
            "grab a coffee",
            "want to eat",
            "take a break",
            # 2026-07-29 (#928) 実地検証で取りこぼしていた疑問形。
            # 受付発話 16 件（挨拶・用件表明）に対して誤爆 0 件であることを確認済み。
            # backend/tests/workflows/test_reception_bypass.py で回帰を担保する。
            "ますか",
            "調べて",
            "使える",
            "って何",
            "ってなに",
            "とは",
            "何が",
            "何か",
        )
        return any(marker in normalized for marker in question_markers)

    def _should_bypass_active_reception(self, query: str, reception_status: dict[str, Any]) -> bool:
        """Do not let stale reception state hijack ordinary information questions."""
        if is_reception_continuation_utterance(query):
            return False

        if not self._looks_like_information_query(query):
            return False

        stage = reception_status.get("stage")
        if stage not in {"greeting", "purpose_hearing", "routing"}:
            return False

        lower_query = query.strip().lower()
        fast_route = RoutingLogicAgent._try_fast_routing(self, lower_query)
        if fast_route is not None and fast_route.get("request_type") != "greeting":
            return True

        return False

    # 受付中でもバイパスしないカテゴリ。
    # "general" は含めない (#928)。QueryClassifier は施設固有語を含まない質問
    # （「赤レンガ文化会館について教えて」「駐車場はありますか」等）を general に
    # 落とすため、除外すると正当な質問まで受付フローに飲まれる。
    # 挨拶・用件表明は手前の _looks_like_information_query で False になるため、
    # general を通しても受付フローは壊れない（受付発話 16 件で誤爆 0 件を確認）。
    _RECEPTION_BYPASS_EXCLUDED_CATEGORIES = frozenset({"daily_conversation", "assistant_profile"})

    _RECEPTION_BYPASS_ELIGIBLE_STAGES = frozenset({"greeting", "purpose_hearing", "routing"})

    async def _should_bypass_active_reception_async(
        self,
        query: str,
        reception_status: dict[str, Any],
    ) -> bool:
        """受付フロー中の情報質問を受付から抜いて通常ルーティングへ回すか判定する。

        判定は必ず ``reception_bypass_decision`` として構造化ログに残す。
        本 issue (#928) の切り分けでは、どの条件で落ちたかがログに残らず
        DB 実査が必要になったため、決定経路を可視化する。
        """
        stage = reception_status.get("stage")

        def _decide(bypass: bool, reason: str, **extra: Any) -> bool:
            log_reception_bypass_decision(
                bypass=bypass,
                reason=reason,
                stage=stage,
                query_chars=len(query),
                **extra,
            )
            return bypass

        if is_reception_continuation_utterance(query):
            return _decide(False, "reception_continuation_utterance")

        if self._should_bypass_active_reception(query, reception_status):
            return _decide(True, "fast_route_or_static_bypass")

        if not self._looks_like_information_query(query):
            return _decide(False, "not_information_query")

        if stage not in self._RECEPTION_BYPASS_ELIGIBLE_STAGES:
            return _decide(False, "stage_not_eligible")

        try:
            from backend.utils.query_classifier import QueryClassifier

            classification = await QueryClassifier().classify_with_details(query)
        except Exception as exc:
            logger.warning(
                "QueryClassifier failed during reception bypass check; "
                "falling back to reception flow",
                exc_info=True,
            )
            return _decide(False, "classifier_error", error_type=type(exc).__name__)

        category = classification.category
        excluded = category in self._RECEPTION_BYPASS_EXCLUDED_CATEGORIES
        return _decide(
            not excluded,
            "category_excluded" if excluded else "information_query",
            category=category,
        )

    def _active_reception_assistant_profile_response(
        self,
        query: str,
        language: str,
    ) -> dict[str, Any] | None:
        """Answer assistant identity/capability questions without advancing reception."""
        from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
        from backend.utils.intent_classifier import is_assistant_profile_question

        if not is_assistant_profile_question(query.lower()):
            return None

        response_language = self._get_response_language(query, language)
        return {
            "answer": GeneralKnowledgeAgent.assistant_profile_message(response_language),
            "emotion": "helpful",
            "language": response_language,
            "routing": {
                "agent": "general_knowledge",
                "category": "assistant_profile",
                "request_type": "assistant_profile",
                "confidence": 1.0,
                "reasoning": "Assistant profile question during active reception",
                "debug_info": {},
            },
            "metadata": {
                "agent": "GeneralKnowledgeAgent",
                "status": "success",
                "category": "general_knowledge",
                "query_type": "assistant_profile",
                "reception_action": "answer_assistant_profile",
                "web_search_used": False,
                "rag_used": False,
                "provider_called": False,
            },
        }

    def _get_response_language(self, query: str, fallback_language: str) -> str:
        # デモ用: LANGUAGE_FORCE が設定されていれば、言語検出より先に強制返却する
        from backend.utils.language_types import get_forced_response_language

        forced_language = get_forced_response_language()
        if forced_language:
            return forced_language

        from backend.utils.language_processor import LanguageProcessor

        language_processor = LanguageProcessor()
        language_result = language_processor.detect_language(query)
        response_language = language_processor.determine_response_language(language_result)
        return response_language or fallback_language

    async def _store_fast_path_user_message(self, session_id: str, query: str) -> None:
        if not session_id or not query:
            return

        try:
            from backend.utils.memory_helper import get_memory_helper

            memory_helper = get_memory_helper()
            await memory_helper.store_message(
                session_id=session_id,
                role="user",
                content=query,
            )
        except Exception as exc:
            logger.warning("Failed to store fast-path user message: %s", exc)

    @staticmethod
    def _checkpoint_messages_to_recent_memory(messages: list[BaseMessage]) -> list[dict[str, Any]]:
        """Convert persisted LangGraph messages into memory-context rows."""
        recent: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            elif isinstance(message, SystemMessage) and "Important earlier user facts:" in str(
                message.content
            ):
                role = "assistant"
            else:
                continue
            content = message.content
            if isinstance(content, list):
                content = " ".join(str(part) for part in content)
            content = str(content or "").strip()
            if not content:
                continue
            metadata = {"canonical_content_key": canonicalize_facility_memory_key_text(content)}
            if role == "user":
                request_type = extract_request_type(content)
                if request_type:
                    metadata["request_type"] = request_type
            recent.append(
                {
                    "role": role,
                    "content": content,
                    "metadata": metadata,
                }
            )
        # A 20-turn live STM gate needs the initial preference/purpose turn to
        # remain visible. Keep a broader bounded window here; message_windowing
        # already summarizes older facts before this converter runs.
        return recent[-100:]

    async def _reception_check_node(self, state: WorkflowStateDict) -> dict[str, Any]:
        from backend.utils.reception_status import check_reception_status

        session_id = state.get("session_id", "")
        reception_status = await check_reception_status(session_id)
        return {"reception_status": reception_status}

    def _reception_check_decision(self, state: WorkflowStateDict) -> str:
        if self._reception_is_active(state.get("reception_status")):
            return "active_reception"
        return "no_reception"

    async def _keyword_router_node(self, state: WorkflowStateDict) -> dict[str, Any]:
        query = state.get("query", "")
        fallback_language = state.get("language", "ja")

        if self._requires_memory_loader_before_fast_path(query):
            return {"routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None}}

        response_language = self._get_response_language(query, fallback_language)
        fast_route = RoutingLogicAgent._try_fast_routing(self, query)
        if fast_route is None:
            return {
                "language": response_language,
                "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
            }

        if fast_route["category"] in self._PRE_MEMORY_INLINE_CATEGORIES:
            return {
                "language": response_language,
                "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
            }

        try:
            from backend.utils.topic_guard import check_topic_adherence

            on_topic, _ = check_topic_adherence(
                query=query,
                routing_category=fast_route["category"],
                language=response_language,
            )
            if not on_topic:
                return {
                    "language": response_language,
                    "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
                }
        except Exception as guard_err:
            logger.debug("Pre-memory topic guard skipped: %s", guard_err)

        fast_path_agent, resolution_source = normalize_agent_node(
            fast_route.get("agent"),
            category=fast_route.get("category"),
            request_type=fast_route.get("request_type"),
        )
        if fast_path_agent not in self._PRE_MEMORY_DIRECT_AGENTS:
            return {
                "language": response_language,
                "routing": {**state.get("routing", {}), "pre_memory_fast_path_agent": None},
            }

        await self._store_fast_path_user_message(state.get("session_id", ""), query)

        return {
            "language": response_language,
            "routing": {
                **state.get("routing", {}),
                **fast_route,
                "agent": fast_path_agent,
                "pre_memory_fast_path_agent": fast_path_agent,
                "confidence": 0.9,
                "debug_info": {
                    "fast_path": True,
                    "path": "keyword_router",
                    "agent_resolution_source": resolution_source,
                },
            },
        }

    def _keyword_router_decision(self, state: WorkflowStateDict) -> str:
        routing = state.get("routing", {})
        fast_path_agent = routing.get("pre_memory_fast_path_agent")
        if fast_path_agent in self._PRE_MEMORY_DIRECT_AGENTS:
            return cast(str, fast_path_agent)
        return "normal"
