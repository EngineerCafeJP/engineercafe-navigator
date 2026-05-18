"""Slides and character control API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request

logger = logging.getLogger(__name__)

deps = sys.modules[__name__]


def configure_dependencies(module: Any) -> None:
    global deps
    deps = module


# Slides API Models
class SlidesRequest(BaseModel):
    action: str
    slideId: Optional[str] = None
    targetSlide: Optional[int] = None
    slideNumber: Optional[int] = None  # FE互換エイリアス (targetSlide)
    query: Optional[str] = None
    question: Optional[str] = None  # FE互換エイリアス (query)
    sessionId: Optional[str] = None
    language: Optional[str] = "ja"


class SlidesResponse(BaseModel):
    success: bool
    slide: Optional[Dict[str, Any]] = None
    narration: Optional[str] = None
    answer: Optional[str] = None
    emotion: Optional[str] = None
    slideNumber: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


async def slides_api(request: Request, body: SlidesRequest):
    """
    スライド制御エンドポイント
    SlideAgentを使用してスライドナレーションと質問応答を処理
    """
    try:
        slide_agent = deps._get_slide_agent()

        # アクションマッピング（FE互換エイリアス含む）
        action_map = {
            "narrate": "narrate",
            "narrate_current": "narrate",
            "next": "next",
            "previous": "previous",
            "goto": "goto",
            "question": "question",
            "answer_question": "question",
        }

        slide_action = action_map.get(body.action)
        if not slide_action:
            raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

        # FE互換: slideNumber → targetSlide, question → query
        query = body.query or body.question
        target_slide = body.targetSlide or body.slideNumber

        # SlideAgentのhandle_slide_action呼び出し
        result = await slide_agent.handle_slide_action(
            action=slide_action,
            query=query,
            target_slide=target_slide,
            language=body.language,
            session_id=body.sessionId or "default",
        )

        return deps.SlidesResponse(
            success=True,
            answer=result.get("answer"),
            emotion=result.get("emotion"),
            slideNumber=result.get("slideNumber"),
            metadata=result.get("metadata"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )


# Character API Models
class CharacterRequest(BaseModel):
    action: str
    emotion: Optional[str] = None
    animation: Optional[str] = None


class CharacterResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


async def character_get_api(request: Request, action: str = ""):
    """GET handler for character state queries from frontend polling."""
    if action == "supported_features":
        from backend.agents.character_control_agent import CharacterControlAgent

        agent = CharacterControlAgent()
        animations = (
            agent.get_supported_animations() if hasattr(agent, "get_supported_animations") else []
        )
        return {
            "success": True,
            "expressions": [
                "neutral",
                "happy",
                "sad",
                "angry",
                "relaxed",
                "surprised",
            ],
            "animations": animations,
        }
    # Default: return current state
    return {
        "success": True,
        "current_emotion": "neutral",
        "current_expression": "neutral",
    }


async def character_api(request: Request, body: CharacterRequest):
    """
    キャラクター制御エンドポイント
    フロントエンドからのプロキシリクエストを処理
    """
    try:
        from backend.agents.character_control_agent import CharacterControlAgent

        agent = CharacterControlAgent()
        result = await asyncio.wait_for(
            agent.process(
                emotion=body.emotion or "neutral",
                text=None,
                context={"action": body.action, "animation": body.animation},
            ),
            timeout=10.0,
        )
        return deps.CharacterResponse(
            success=True,
            message=(
                json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            ),
        )
    except asyncio.TimeoutError:
        logger.warning("CharacterControlAgent timed out after 10s")
        raise HTTPException(
            status_code=504,
            detail="Character action timed out",
        )
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )


class CharacterAutoRequest(BaseModel):
    """Request body for auto VRM control generation from TTS output."""

    cleanText: str = Field(..., max_length=5000)
    emotion: str = Field(default="neutral", max_length=50)
    ttsWavB64: Optional[str] = None


class CharacterAutoResponse(BaseModel):
    success: bool
    vrmControl: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


async def character_auto_api(request: Request, body: CharacterAutoRequest):
    """Auto-generate VRM control data from TTS output.

    Frontend can call this in parallel with /api/voice to avoid
    blocking the audio response on VRM generation.
    """
    try:
        vrm_result = await asyncio.wait_for(
            deps._generate_vrm_control_for_lab_tts(
                clean_text=body.cleanText,
                emotion=body.emotion,
                tts_wav_b64=body.ttsWavB64,
            ),
            timeout=15.0,
        )
        return deps.CharacterAutoResponse(success=True, vrmControl=vrm_result)
    except asyncio.TimeoutError:
        logger.warning("Character auto VRM timed out after 15s")
        raise HTTPException(status_code=504, detail="VRM generation timed out")
    except Exception as e:
        logger.exception("Character auto VRM error: %s", e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )


def create_router(rate_limit: Callable[[str], Callable[[Any], Any]]) -> APIRouter:
    router = APIRouter(tags=["admin"])
    router.add_api_route(
        "/api/slides",
        rate_limit("20/minute")(slides_api),
        methods=["POST"],
        response_model=SlidesResponse,
    )
    router.add_api_route(
        "/api/character",
        rate_limit("20/minute")(character_get_api),
        methods=["GET"],
    )
    router.add_api_route(
        "/api/character",
        rate_limit("20/minute")(character_api),
        methods=["POST"],
        response_model=CharacterResponse,
    )
    router.add_api_route(
        "/api/character/auto",
        rate_limit("20/minute")(character_auto_api),
        methods=["POST"],
        response_model=CharacterAutoResponse,
    )
    return router
