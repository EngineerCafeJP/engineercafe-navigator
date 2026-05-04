"""Reception workflow subgraph for multi-turn visitor reception.

This module provides a LangGraph subgraph that advances the reception state by
one stage per invocation so it can be called from MainWorkflow's orchestrator
node while also remaining directly testable in isolation.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Annotated, Any, Awaitable, Callable, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
from backend.domain.reception.models import VisitPurpose
from backend.domain.reception.service import ReceptionDomainService
from backend.services.visitor_identification_service import VisitorIdentificationService
from backend.utils.intent_classifier import is_assistant_profile_question
from backend.utils import purpose_classifier as purpose_classifier_module
from backend.utils.reception_templates import (
    get_personalized_greeting,
    get_purpose_followup,
    get_purpose_hearing_prompt,
    get_reception_response,
)

logger = logging.getLogger(__name__)
_DOMAIN_SERVICE = ReceptionDomainService()
_RECEPTION_GRAPH = None
_RECEPTION_LOCK = asyncio.Lock()

if TYPE_CHECKING:
    from backend.workflows.main_workflow import WorkflowStateDict


_PURPOSE_REQUEST_TYPE_MAP: dict[str, str] = {
    "facility_use": "facility",
    "event_participation": "event",
    "tour": "narrate",
    "consultation": "consultation",
    "other": "general",
}


def _assistant_profile_detour(user_response: str, language: str) -> Optional[str]:
    if not is_assistant_profile_question(user_response.lower()):
        return None
    return GeneralKnowledgeAgent.assistant_profile_message(language)


# =============================================================================
# State Definition
# =============================================================================


class ReceptionState(TypedDict):
    """State for the autonomous reception LangGraph workflow.

    Attributes:
        session_id: Conversation session identifier.
        reception_session_id: Reception-specific session ID (UUID).
        messages: Accumulated conversation messages (append-only).
        visitor_identity: Serialized VisitorIdentity dict, or None.
        purpose: Serialized VisitPurpose dict, or None.
        stage: Current ReceptionStage string.
        language: Language code ("ja" or "en").
        trigger_type: How this reception was initiated.
        greeting: The greeting text sent to the visitor, or None.
        response: The most recent response text, or None.
        target_agent: Downstream agent to hand off to after reception completes.
        reception_action: Action label for persistence/metadata.
    """

    session_id: str
    reception_session_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    visitor_identity: Optional[dict]
    purpose: Optional[dict]
    stage: str
    language: str
    trigger_type: str
    greeting: Optional[str]
    response: Optional[str]
    target_agent: Optional[str]
    reception_action: Optional[str]


class ReceptionSubgraphResult(TypedDict):
    """Parent-compatible result returned to MainWorkflow."""

    answer: Optional[str]
    emotion: Optional[str]
    metadata: dict[str, Any]
    routing: Optional[dict[str, Any]]
    target_agent: Optional[str]


PersistReceptionSession = Callable[..., Awaitable[None]]


# =============================================================================
# Node implementations
# =============================================================================


async def greet_visitor(state: ReceptionState) -> dict:
    """Identify the visitor and generate an appropriate greeting.

    Uses VisitorIdentificationService to check whether the visitor is
    returning (via visitor_id or NFC). Generates a personalized greeting
    for returning visitors or a standard first-visit greeting for new ones.

    Args:
        state: Current reception state.

    Returns:
        State update dict with visitor_identity, greeting, response,
        stage, and messages fields populated.
    """
    language = state.get("language", "ja")
    session_id = state.get("session_id", "")
    trigger_type = state.get("trigger_type", "button_press")

    identity_service = VisitorIdentificationService()
    identity_dict: Optional[dict] = None

    # Try to identify by visitor_id carried in trigger metadata
    if trigger_type == "nfc":
        # NFC identification not implemented in this path; falls through to new visitor
        pass
    else:
        # Attempt visitor_id lookup (frontend-persisted UUID in session_id)
        try:
            result = await identity_service.identify_by_visitor_id(session_id)
            if result:
                identity_dict = result
        except Exception as exc:
            logger.warning("Visitor ID lookup failed: %s", exc)

    is_returning = identity_dict is not None and identity_dict.get("visitor_type") == "returning"

    # Generate greeting text
    if is_returning and identity_dict and identity_dict.get("name"):
        result = get_personalized_greeting(
            language=language,
            name=identity_dict["name"],
            last_purpose=identity_dict.get("last_purpose"),
        )
        greeting_text = result.text
    else:
        result = get_reception_response(language=language, is_returning=is_returning)
        greeting_text = result.text

    greeting_message = AIMessage(content=greeting_text)

    return {
        "visitor_identity": identity_dict,
        "stage": "greeting",
        "greeting": greeting_text,
        "response": greeting_text,
        "reception_action": "start_reception",
        "messages": [greeting_message],
    }


async def hear_purpose(state: ReceptionState) -> dict:
    """Send the purpose-hearing prompt to the visitor.

    Advances the stage to purpose_hearing and emits the prompt asking
    the visitor what brings them to Engineer Cafe today.

    Args:
        state: Current reception state.

    Returns:
        State update dict with the purpose-hearing prompt as the response.
    """
    language = state.get("language", "ja")
    result = get_purpose_hearing_prompt(language=language)
    prompt_message = AIMessage(content=result.text)

    return {
        "visitor_identity": state.get("visitor_identity") or {"visitor_type": "new"},
        "stage": "purpose_hearing",
        "response": result.text,
        "reception_action": "hear_purpose",
        "messages": [prompt_message],
    }


async def classify_purpose(state: ReceptionState) -> dict:
    """Classify the visitor's purpose from their last message.

    Reads the most recent human message from the conversation and runs it
    through the purpose classifier. Stores the result in the state.

    Args:
        state: Current reception state containing the visitor's response.

    Returns:
        State update dict with purpose dict and stage set to "routing".
    """
    language = state.get("language", "ja")
    messages = state.get("messages", [])

    # Find the most recent human message
    user_response = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            user_response = msg.content
            break
        if hasattr(msg, "__class__") and msg.__class__.__name__ == "HumanMessage":
            user_response = msg.content
            break

    if not user_response:
        logger.warning("No human message found for purpose classification; defaulting to 'other'")
        purpose_dict = {"category": "other", "detail": None, "confidence": 0.3}
        prompt = get_purpose_hearing_prompt(language=language)
        return {
            "purpose": purpose_dict,
            "stage": "purpose_hearing",
            "response": prompt.text,
            "reception_action": "clarify_purpose",
            "messages": [AIMessage(content=prompt.text)],
        }

    assistant_profile_response = _assistant_profile_detour(user_response, language)
    if assistant_profile_response is not None:
        return {
            "purpose": state.get("purpose"),
            "stage": "purpose_hearing",
            "response": assistant_profile_response,
            "reception_action": "answer_assistant_profile",
            "messages": [AIMessage(content=assistant_profile_response)],
        }

    try:
        category, detail, confidence = await purpose_classifier_module.classify_purpose(
            query=user_response,
            language=language,
        )
    except Exception as exc:
        logger.warning("Purpose classification failed: %s", exc)
        category, detail, confidence = "other", None, 0.3

    purpose_dict = {
        "category": category,
        "detail": detail,
        "confidence": confidence,
    }

    if category == "other":
        prompt = get_purpose_hearing_prompt(language=language)
        return {
            "purpose": purpose_dict,
            "stage": "purpose_hearing",
            "response": prompt.text,
            "reception_action": "clarify_purpose",
            "messages": [AIMessage(content=prompt.text)],
        }

    followup_result = get_purpose_followup(language=language, purpose=category)

    return {
        "purpose": purpose_dict,
        "stage": "routing",
        "response": followup_result.text,
        "reception_action": "classify_purpose",
        "messages": [AIMessage(content=followup_result.text)],
    }


async def route_to_agent(state: ReceptionState) -> dict:
    """Route the visitor to the appropriate agent or generate a follow-up.

    Based on the classified purpose category, determines which downstream
    agent should handle the visitor's request. Emits a follow-up response
    message and marks the stage as completed.

    Args:
        state: Current reception state with purpose populated.

    Returns:
        State update dict with response, stage, and messages updated.
    """
    purpose_dict = state.get("purpose") or {}
    category = purpose_dict.get("category", "other")

    target_agent = _DOMAIN_SERVICE.map_purpose_to_agent(VisitPurpose(category=category))

    logger.info(
        "Routing visitor to agent '%s' for purpose '%s'",
        target_agent,
        category,
    )

    # Update purpose dict with routing information (immutable pattern)
    updated_purpose = {**purpose_dict, "target_agent": target_agent}

    return {
        "purpose": updated_purpose,
        "stage": "completed",
        "target_agent": target_agent,
        "reception_action": "complete_reception",
    }


# =============================================================================
# Conditional edge: should we ask for purpose?
# =============================================================================


def _entry_node_for_stage(state: ReceptionState) -> str:
    """Select the next node based on the persisted reception stage."""
    stage = state.get("stage", "initiated")
    if stage == "initiated":
        return "greet_visitor"
    if stage == "greeting":
        return "hear_purpose"
    if stage == "purpose_hearing":
        return "classify_purpose"
    if stage == "routing":
        return "route_to_agent"
    return "__end__"


# =============================================================================
# Graph factory
# =============================================================================


async def get_reception_workflow() -> StateGraph:
    """Build and compile the ReceptionWorkflow StateGraph.

    Constructs the full LangGraph with nodes and edges for the autonomous
    reception flow. The returned graph is compiled and ready to invoke.

    Returns:
        A compiled LangGraph StateGraph for the reception flow.
    """
    global _RECEPTION_GRAPH
    if _RECEPTION_GRAPH is not None:
        return _RECEPTION_GRAPH

    async with _RECEPTION_LOCK:
        if _RECEPTION_GRAPH is not None:
            return _RECEPTION_GRAPH

        workflow = StateGraph(ReceptionState)
        workflow.add_node("greet_visitor", greet_visitor)
        workflow.add_node("hear_purpose", hear_purpose)
        workflow.add_node("classify_purpose", classify_purpose)
        workflow.add_node("route_to_agent", route_to_agent)
        workflow.add_conditional_edges(
            START,
            _entry_node_for_stage,
            {
                "greet_visitor": "greet_visitor",
                "hear_purpose": "hear_purpose",
                "classify_purpose": "classify_purpose",
                "route_to_agent": "route_to_agent",
                "__end__": END,
            },
        )
        workflow.add_edge("greet_visitor", END)
        workflow.add_edge("hear_purpose", END)
        workflow.add_edge("classify_purpose", END)
        workflow.add_edge("route_to_agent", END)
        _RECEPTION_GRAPH = workflow.compile()
        return _RECEPTION_GRAPH


# =============================================================================
# Helper: initial state factory
# =============================================================================


def make_initial_state(
    session_id: str = "",
    language: str = "ja",
    trigger_type: str = "button_press",
    messages: Optional[list[BaseMessage]] = None,
) -> ReceptionState:
    """Create a fully initialised ReceptionState for a new reception session.

    Args:
        session_id: Conversation session identifier.
        language: Interaction language ("ja" or "en").
        trigger_type: How the reception was triggered.
        messages: Pre-existing messages (e.g. from a prior turn).

    Returns:
        A ReceptionState TypedDict ready to pass to the compiled graph.
    """
    return ReceptionState(
        session_id=session_id,
        reception_session_id=str(uuid.uuid4()),
        messages=messages or [],
        visitor_identity=None,
        purpose=None,
        stage="initiated",
        language=language,
        trigger_type=trigger_type,
        greeting=None,
        response=None,
        target_agent=None,
        reception_action=None,
    )


def workflow_state_to_reception_state(
    state: "WorkflowStateDict",
    reception_status: dict[str, Any],
) -> ReceptionState:
    """Convert MainWorkflow state + persisted reception status into ReceptionState."""
    messages = list(state.get("messages", []))
    query = state.get("query", "")
    if query:
        messages.append(HumanMessage(content=query))

    return ReceptionState(
        session_id=state.get("session_id", ""),
        reception_session_id=reception_status.get("reception_session_id")
        or state.get("session_id", ""),
        messages=messages,
        visitor_identity=reception_status.get("visitor_identity"),
        purpose=reception_status.get("purpose"),
        stage=reception_status.get("stage", "initiated"),
        language=state.get("language", "ja"),
        trigger_type=reception_status.get("trigger_type", "voice"),
        greeting=reception_status.get("greeting"),
        response=None,
        target_agent=None,
        reception_action=None,
    )


def reception_state_to_workflow_result(
    original_state: "WorkflowStateDict",
    reception_state: ReceptionState,
) -> ReceptionSubgraphResult:
    """Convert ReceptionState back into a MainWorkflow-compatible partial update."""
    stage = reception_state.get("stage", "initiated")
    purpose = reception_state.get("purpose") or {}
    target_agent = reception_state.get("target_agent")
    reception_action = reception_state.get("reception_action")
    metadata = {
        **original_state.get("metadata", {}),
        "agent": "reception",
        "reception_stage": stage,
    }
    if reception_action:
        metadata["reception_action"] = reception_action
    if purpose:
        metadata["purpose"] = purpose
    if target_agent:
        metadata["reception_target_agent"] = target_agent
        category = purpose.get("category", "other")
        request_type = _PURPOSE_REQUEST_TYPE_MAP.get(category, "general")
        return ReceptionSubgraphResult(
            answer=None,
            emotion=None,
            metadata=metadata,
            routing={
                "agent": target_agent,
                "category": category,
                "request_type": request_type,
                "confidence": purpose.get("confidence", 1.0),
                "reasoning": "Routed from reception subgraph",
                "debug_info": {},
            },
            target_agent=target_agent,
        )

    return ReceptionSubgraphResult(
        answer=reception_state.get("response"),
        emotion="happy" if stage == "greeting" else "neutral",
        metadata=metadata,
        routing=None,
        target_agent=None,
    )


async def invoke_reception_subgraph(
    state: "WorkflowStateDict",
    reception_status: dict[str, Any],
    persist_session: PersistReceptionSession,
) -> ReceptionSubgraphResult:
    """Advance the reception subgraph by one turn and persist the new stage."""
    graph = await get_reception_workflow()
    reception_state = workflow_state_to_reception_state(state, reception_status)
    updated_state = await graph.ainvoke(reception_state)

    await persist_session(
        session_id=state.get("session_id", ""),
        stage=updated_state.get("stage", reception_state.get("stage", "initiated")),
        language=updated_state.get("language", state.get("language", "ja")),
        trigger_type=updated_state.get("trigger_type", "voice"),
        status="completed" if updated_state.get("stage") == "completed" else "active",
        metadata={"reception_action": updated_state.get("reception_action")},
        purpose=updated_state.get("purpose"),
        visitor_identity=updated_state.get("visitor_identity"),
    )

    return reception_state_to_workflow_result(state, updated_state)
