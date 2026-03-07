"""Reception Workflow - Autonomous LangGraph StateGraph for visitor reception.

Separate from MainWorkflow, this graph handles the end-to-end reception flow:
visitor identification -> greeting -> purpose hearing -> routing.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Optional

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from backend.services.visitor_identification_service import VisitorIdentificationService
from backend.utils import purpose_classifier as purpose_classifier_module
from backend.utils.reception_templates import (
    get_personalized_greeting,
    get_purpose_followup,
    get_purpose_hearing_prompt,
    get_reception_response,
)

logger = logging.getLogger(__name__)

# Purpose category to target agent mapping
_PURPOSE_AGENT_MAPPING: dict[str, str] = {
    "facility_use": "facility",
    "event_participation": "event",
    "tour": "slide",
    "consultation": "general_knowledge",
    "other": "general_knowledge",
}


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
        "stage": "purpose_hearing",
        "response": result.text,
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
        return {"purpose": purpose_dict, "stage": "routing"}

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

    return {
        "purpose": purpose_dict,
        "stage": "routing",
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
    language = state.get("language", "ja")
    purpose_dict = state.get("purpose") or {}
    category = purpose_dict.get("category", "other")

    target_agent = _PURPOSE_AGENT_MAPPING.get(category, "general_knowledge")
    followup_result = get_purpose_followup(language=language, purpose=category)
    followup_message = AIMessage(content=followup_result.text)

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
        "response": followup_result.text,
        "messages": [followup_message],
    }


# =============================================================================
# Conditional edge: should we ask for purpose?
# =============================================================================


def _should_hear_purpose(state: ReceptionState) -> str:
    """Determine if we need to ask the visitor about their purpose.

    Returns "hear_purpose" when the purpose has not yet been identified,
    "classify_purpose" when the visitor has already provided their purpose
    (e.g. if routed back after a human message).

    Args:
        state: Current reception state.

    Returns:
        Node name to transition to.
    """
    if state.get("purpose") is None:
        return "hear_purpose"
    return "classify_purpose"


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
    workflow = StateGraph(ReceptionState)

    # Register nodes
    workflow.add_node("greet_visitor", greet_visitor)
    workflow.add_node("hear_purpose", hear_purpose)
    workflow.add_node("classify_purpose", classify_purpose)
    workflow.add_node("route_to_agent", route_to_agent)

    # Entry point
    workflow.add_edge(START, "greet_visitor")

    # After greeting: ask for purpose if not yet known
    workflow.add_conditional_edges(
        "greet_visitor",
        _should_hear_purpose,
        {
            "hear_purpose": "hear_purpose",
            "classify_purpose": "classify_purpose",
        },
    )

    # After purpose prompt: wait for user response (ends turn)
    # In a real multi-turn setup the human response triggers classify_purpose.
    # In this single-graph representation we wire hear_purpose -> classify_purpose
    # so tests can drive the full flow end-to-end.
    workflow.add_edge("hear_purpose", "classify_purpose")

    # Classification -> routing
    workflow.add_edge("classify_purpose", "route_to_agent")

    # Routing -> end
    workflow.add_edge("route_to_agent", END)

    return workflow.compile()


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
    )
