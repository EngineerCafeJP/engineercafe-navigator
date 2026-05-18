"""Chat and agent invocation API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from typing import Any, Callable, Dict, Optional, cast

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.requests import Request

from backend.observability.structured_logger import log_chat_response  # noqa: F401
from backend.utils.intent_classifier import classify_fast_intent
from backend.utils.structured_logging import generate_request_id, get_request_id

logger = logging.getLogger(__name__)

_SUPPORTED_RESPONSE_LANGUAGES = frozenset({"ja", "en", "zh", "ko"})

deps = sys.modules[__name__]


def configure_dependencies(module: Any) -> None:
    global deps
    deps = module


class ChatRequest(BaseModel):
    query: str = Field(max_length=2000)
    session_id: Optional[str] = None
    language: Optional[str] = Field(default="ja", max_length=10)
    context: Optional[Dict[str, Any]] = None
    visitor_id: Optional[str] = None  # Cross-session visitor identification
    image_data: str | None = None  # Base64 encoded image


class ChatResponse(BaseModel):
    answer: str
    emotion: str
    metadata: Dict[str, Any]
    vrm_control: Optional[Dict[str, Any]] = None
    requestId: Optional[str] = None
    phase: Optional[str] = None
    upstreamStatus: Optional[Dict[str, Any]] = None


class InterruptRequest(BaseModel):
    session_id: str


async def interrupt_session(request: Request, body: InterruptRequest):
    """フロントエンドからの割り込みシグナルを受信"""
    from backend.utils.interrupt_manager import get_interrupt_manager

    manager = get_interrupt_manager()
    manager.request_interrupt(body.session_id)
    return {"status": "interrupted", "session_id": body.session_id}


async def _run_workflow_with_tracking(payload: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    from backend.workflows.main_workflow import get_workflow

    workflow = await get_workflow()
    await deps._get_stm().register_session(session_id)
    llm_task = asyncio.create_task(workflow.ainvoke(payload))
    await deps._get_stm().set_llm_task(session_id, llm_task)

    try:
        return cast(Dict[str, Any], await llm_task)
    except asyncio.CancelledError:
        logger.info("LLM task cancelled for session %s", session_id)
        raise HTTPException(status_code=409, detail="Request interrupted")


def _build_workflow_payload(body: ChatRequest, session_id: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "query": body.query,
        "session_id": session_id,
        "language": body.language,
        "context": body.context or {},
        "visitor_id": body.visitor_id,
    }
    if body.image_data:
        payload["image_data"] = body.image_data
    return payload


def _general_fast_path_answer(query: str, language: str, request_type: str) -> tuple[str, str]:
    lower_query = query.lower()
    if request_type == "assistant_profile":
        if language == "en":
            return (
                "I am Engineer Cafe Navigator, the reception kiosk for Engineer Cafe in "
                "Fukuoka. I can help with facilities, events, membership check-in, Wi-Fi, "
                "slide guidance, and everyday questions visitors commonly ask at reception.",
                "helpful",
            )
        if language == "ko":
            return (
                "저는 Engineer Cafe Navigator 입니다. 후쿠오카의 엔지니어 카페 안내 키오스크로서, "
                "시설 이용, 이벤트, 회원증, Wi-Fi, 슬라이드 안내와 함께 접수처에서 자주 받는 "
                "일상적인 질문에도 답해 드립니다.",
                "helpful",
            )
        if language == "zh":
            return (
                "我是 Engineer Cafe Navigator，福冈工程师咖啡馆的前台导览终端。我可以为您介绍"
                "设施使用、活动信息、会员证、Wi-Fi、幻灯片导览，以及前台常见的日常问题。",
                "helpful",
            )
        return (
            "私は Engineer Cafe Navigator です。福岡市のエンジニアカフェの受付キオスク"
            "として、施設利用、イベント、会員証、Wi-Fi、スライド案内に加えて、"
            "受付でよくある日常的な質問にもお答えします。",
            "helpful",
        )

    if any(marker in lower_query for marker in ("ありがとう", "サンキュー", "thanks", "thank you")):
        return (
            (
                "どういたしまして。ほかにも気になることがあれば、気軽に聞いてください。"
                if language == "ja"
                else "You're welcome. Feel free to ask me anything else."
            ),
            "relaxed",
        )
    if any(marker in lower_query for marker in ("疲れた", "i am tired", "i'm tired")):
        return (
            (
                "少し休憩しましょう。エンジニアカフェでは、落ち着いて作業したり一息ついたりできます。"
                if language == "ja"
                else "Take a short break. Engineer Cafe is a good place to settle in and recharge."
            ),
            "relaxed",
        )
    if any(marker in lower_query for marker in ("元気", "how are you")):
        return (
            (
                "元気です。今日は受付として、施設案内でも雑談でもすぐお手伝いできます。"
                if language == "ja"
                else "I'm doing well. I can help with reception guidance or a quick casual chat."
            ),
            "relaxed",
        )
    return (
        (
            "もちろんです。短くお話ししましょう。施設のことでも、今日の過ごし方でも気軽に聞いてください。"
            if language == "ja"
            else (
                "Of course. We can keep it light. Ask me about the facility "
                "or anything practical for your visit."
            )
        ),
        "relaxed",
    )


def _general_static_fast_path_answer(query: str, language: str) -> tuple[str, str, str] | None:
    """Return stable general-knowledge answers that do not need workflow/LLM."""
    if language != "ja":
        return None

    normalized_query = re.sub(r"\s+", "", query.lower())
    python_definition_queries = {
        "pythonって何?",
        "pythonって何？",
        "pythonとは何?",
        "pythonとは何？",
        "pythonとは何ですか?",
        "pythonとは何ですか？",
    }
    if normalized_query not in python_definition_queries:
        return None

    return (
        "Pythonは、読み書きしやすい文法が特徴のプログラミング言語です。"
        "Webアプリ、データ分析、AI、自動化など幅広い用途で使われ、"
        "初心者にも学びやすい言語としてよく選ばれます。",
        "helpful",
        "general_light",
    )


def _try_chat_general_fast_path(
    body: ChatRequest,
    *,
    session_id: str,
    request_id: str,
    started_at: float,
) -> ChatResponse | None:
    if body.image_data or body.context or body.visitor_id:
        return None

    intent = classify_fast_intent(body.query)
    language = body.language or "ja"
    static_answer = _general_static_fast_path_answer(body.query, language)
    if intent is None and static_answer is not None:
        answer, emotion, request_type = static_answer
        metadata = {
            "query": body.query,
            "session_id": session_id,
            "agent": "GeneralKnowledgeAgent",
            "category": "general_knowledge",
            "route": "general_knowledge",
            "request_type": request_type,
            "query_type": request_type,
            "sources": [],
            "web_search_used": False,
            "rag_used": False,
            "provider_called": False,
            "fast_path": "chat_endpoint",
        }
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        deps.log_chat_response(
            request_id=request_id,
            language=language,
            metadata=metadata,
            latency_ms=latency_ms,
        )
        return deps.ChatResponse(
            answer=answer,
            emotion=emotion,
            metadata=metadata,
            requestId=request_id,
            phase="chat",
            upstreamStatus=deps._upstream_status(
                "chat_endpoint_fast_path",
                route="general_knowledge",
            ),
        )

    if (
        intent is None
        or intent.agent != "general_knowledge"
        or intent.request_type not in {"assistant_profile", "daily_conversation"}
    ):
        return None

    answer, emotion = _general_fast_path_answer(body.query, language, intent.request_type)
    metadata = {
        "query": body.query,
        "session_id": session_id,
        "agent": "GeneralKnowledgeAgent",
        "category": "general_knowledge",
        "route": "general_knowledge",
        "request_type": intent.request_type,
        "query_type": intent.request_type,
        "sources": [],
        "web_search_used": False,
        "rag_used": False,
        "provider_called": False,
        "fast_path": "chat_endpoint",
    }
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    deps.log_chat_response(
        request_id=request_id,
        language=language,
        metadata=metadata,
        latency_ms=latency_ms,
    )
    return deps.ChatResponse(
        answer=answer,
        emotion=emotion,
        metadata=metadata,
        requestId=request_id,
        phase="chat",
        upstreamStatus=deps._upstream_status("chat_endpoint_fast_path", route="general_knowledge"),
    )


def _request_id_from_request(request: Request) -> str:
    return get_request_id() or request.headers.get("X-Request-ID") or generate_request_id()


def _upstream_status(phase: str, ok: bool = True, **extra: Any) -> Dict[str, Any]:
    return {"phase": phase, "ok": ok, **extra}


def _normalize_response_language(value: Any, fallback: str = "ja") -> str:
    if isinstance(value, str) and value.strip():
        normalized = value.strip().lower().split("-", 1)[0]
        if normalized in _SUPPORTED_RESPONSE_LANGUAGES:
            return normalized
    return fallback if fallback in _SUPPORTED_RESPONSE_LANGUAGES else "ja"


def _resolve_chat_response_language(
    *,
    query: str,
    requested_language: Optional[str],
    result: Dict[str, Any],
    metadata: Dict[str, Any],
) -> str:
    fallback = _normalize_response_language(requested_language)
    for key in ("response_language", "language", "detected_language"):
        if key in metadata:
            return _normalize_response_language(metadata.get(key), fallback)
    for key in ("response_language", "language", "detected_language"):
        if key in result:
            return _normalize_response_language(result.get(key), fallback)

    try:
        from backend.utils.language_processor import LanguageProcessor

        language_processor = LanguageProcessor()
        language_result = language_processor.detect_language(query)
        detected = language_processor.determine_response_language(language_result)
        return _normalize_response_language(detected, fallback)
    except Exception as exc:
        logger.debug("Response language detection skipped: %s", exc)
        return fallback


async def chat(request: Request, body: ChatRequest):
    """
    チャットエンドポイント
    LangGraphエージェントを使用してクエリを処理します

    Frontend proxy note: `/api/chat` responses include requestId, phase, and
    upstreamStatus so `frontend/src/app/api/qa` can surface traceable failures.
    """
    import uuid as _uuid

    from backend.utils.interrupt_manager import get_interrupt_manager
    from backend.utils.input_sanitizer import (
        contains_prompt_injection,
        prompt_injection_refusal,
        sanitize_input,
    )

    started_at = time.perf_counter()
    session_id = body.session_id or str(_uuid.uuid4())
    request_id = deps._request_id_from_request(request)

    get_interrupt_manager().clear_interrupt(session_id)

    try:
        if contains_prompt_injection(body.query):
            sanitized_query = sanitize_input(body.query)
            metadata = {
                "query": sanitized_query,
                "session_id": session_id,
                "agent": "SafetyGuard",
                "category": "safety",
                "route": "safety_guard",
                "safety_guard": True,
                "sources": [],
                "rag_fallback": False,
            }
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            deps.log_chat_response(
                request_id=request_id,
                language=body.language,
                metadata=metadata,
                latency_ms=latency_ms,
            )
            return deps.ChatResponse(
                answer=prompt_injection_refusal(body.language),
                emotion="neutral",
                metadata=metadata,
                requestId=request_id,
                phase="chat",
                upstreamStatus=deps._upstream_status("safety_guard"),
            )

        body = body.copy(update={"query": sanitize_input(body.query)})
        fast_response = deps._try_chat_general_fast_path(
            body,
            session_id=session_id,
            request_id=request_id,
            started_at=started_at,
        )
        if fast_response is not None:
            return fast_response

        result = await deps._run_workflow_with_tracking(
            payload=deps._build_workflow_payload(body, session_id),
            session_id=session_id,
        )

        raw_answer = result.get("answer", "回答を生成できませんでした。")

        # Strip emotion tags (emotion is carried separately in the response)
        from backend.utils.emotion_utils import strip_emotion_tags

        answer = strip_emotion_tags(raw_answer)

        # Output PII scanning
        try:
            from backend.utils.pii_scanner import scan_and_mask

            masked_answer, pii_items = scan_and_mask(answer)
            if pii_items:
                logger.warning(
                    "PII detected in response (%d items), masked before delivery",
                    len(pii_items),
                )
                answer = masked_answer
        except Exception as e:
            logger.debug("PII scan skipped (non-critical): %s", e)

        metadata = result.get("metadata", {"query": body.query, "session_id": session_id})
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        response_language = deps._resolve_chat_response_language(
            query=body.query,
            requested_language=body.language,
            result=result,
            metadata=metadata_dict,
        )
        if isinstance(metadata, dict):
            metadata.setdefault("response_language", response_language)
            metadata.setdefault("language", response_language)
            deps._attach_latest_llm_metadata(metadata)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        deps.log_chat_response(
            request_id=request_id,
            language=response_language,
            metadata=metadata_dict,
            latency_ms=latency_ms,
        )

        return deps.ChatResponse(
            answer=answer,
            emotion=result.get("emotion", "neutral"),
            metadata=metadata,
            vrm_control=metadata_dict.get("vrm_control"),
            requestId=request_id,
            phase="chat",
            upstreamStatus=deps._upstream_status(
                "workflow",
                route=metadata_dict.get("route") or metadata_dict.get("category"),
            ),
        )
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )


async def chat_stream(request: Request, body: ChatRequest):
    """
    SSEストリーミングチャットエンドポイント
    Server-Sent Events でレスポンスをストリーミング
    """
    import uuid as _uuid

    from backend.utils.interrupt_manager import get_interrupt_manager

    session_id = body.session_id or str(_uuid.uuid4())

    interrupt_mgr = get_interrupt_manager()
    interrupt_mgr.clear_interrupt(session_id)

    async def event_generator():
        try:
            from backend.workflows.main_workflow import get_workflow

            workflow = await get_workflow()

            # Use astream for streaming
            async for event in workflow.astream(deps._build_workflow_payload(body, session_id)):
                if interrupt_mgr.is_interrupted(body.session_id):
                    yield f"data: {json.dumps({'type': 'interrupted'})}\n\n"
                    break
                if isinstance(event, dict):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("SSE stream error: %s", e)
            yield f"data: {json.dumps({'error': 'An internal error occurred'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def invoke_agent(request: Request, body: ChatRequest):
    """
    LangGraphエージェントの直接実行エンドポイント
    """
    import uuid as _uuid

    from backend.utils.interrupt_manager import get_interrupt_manager

    session_id = body.session_id or str(_uuid.uuid4())
    get_interrupt_manager().clear_interrupt(session_id)

    try:
        result = await deps._run_workflow_with_tracking(
            payload=deps._build_workflow_payload(body, session_id),
            session_id=session_id,
        )

        return {"status": "success", "result": result}
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )


def create_router(rate_limit: Callable[[str], Callable[[Any], Any]]) -> APIRouter:
    router = APIRouter(tags=["chat"])
    router.add_api_route(
        "/api/interrupt",
        rate_limit("60/minute")(interrupt_session),
        methods=["POST"],
    )
    router.add_api_route(
        "/api/chat",
        rate_limit("30/minute")(chat),
        methods=["POST"],
        response_model=ChatResponse,
    )
    router.add_api_route(
        "/api/chat/stream",
        rate_limit("30/minute")(chat_stream),
        methods=["POST"],
    )
    router.add_api_route(
        "/api/agent/invoke",
        rate_limit("30/minute")(invoke_agent),
        methods=["POST"],
    )
    return router
