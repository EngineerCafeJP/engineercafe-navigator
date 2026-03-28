"""OCR API endpoint.

Orchestration layer that wraps the existing VisionAgent and integrates
with VisitorIdentificationService for member-card recognition.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Literal, Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.utils.rate_limit import rate_limit

if TYPE_CHECKING:
    from backend.agents.ocr_agent import VisionAgent
    from backend.services.visitor_identification_service import VisitorIdentificationService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons (same pattern as reception.py)
# ---------------------------------------------------------------------------

_vision_agent: Optional["VisionAgent"] = None  # noqa: F821


def _get_vision_agent() -> "VisionAgent":  # noqa: F821
    """Return a module-level VisionAgent singleton, created on first use."""
    global _vision_agent
    if _vision_agent is None:
        from backend.agents.ocr_agent import VisionAgent

        _vision_agent = VisionAgent()
    return _vision_agent


_visitor_id_service: Optional["VisitorIdentificationService"] = None  # noqa: F821


def _get_visitor_id_service() -> "VisitorIdentificationService":  # noqa: F821
    """Return a module-level VisitorIdentificationService singleton."""
    global _visitor_id_service
    if _visitor_id_service is None:
        from backend.services.visitor_identification_service import (
            VisitorIdentificationService,
        )

        _visitor_id_service = VisitorIdentificationService()
    return _visitor_id_service


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

ocr_router = APIRouter(prefix="/api/ocr", tags=["ocr"])

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

_DATA_URI_PREFIX = re.compile(r"^data:image/[a-z]+;base64,", re.IGNORECASE)
# Prefer labeled member numbers (with prefix); fall back to standalone 3-6 digit numbers
_MEMBER_CONTEXT_RE = re.compile(r"(?:No\.?|Member|会員番号|会員No)\s*(\d{1,6})", re.IGNORECASE)
_MEMBER_STANDALONE_RE = re.compile(r"(?<!\d)(\d{3,6})(?!\d)")

# 10 MB base64 ≈ ~7.5 MB decoded (generous for 640px JPEG)
_MAX_IMAGE_DATA_LENGTH = 10 * 1024 * 1024


class OcrRequest(BaseModel):
    image_data: str = Field(
        ...,
        max_length=_MAX_IMAGE_DATA_LENGTH,
        description="JPEG image as base64 string (with or without data URI prefix)",
    )
    mode: Literal["member_card", "handwriting"] = "member_card"
    session_id: str = Field("", max_length=128)


class OcrResponse(BaseModel):
    success: bool
    mode: Literal["member_card", "handwriting"]
    member_number: Optional[int] = None
    recognized_text: Optional[str] = None
    confidence: float = 0.0
    language: Optional[str] = None
    expression: Optional[str] = None
    processing_time_ms: int = 0
    visitor_identity: Optional[dict] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Language detection heuristic
# ---------------------------------------------------------------------------

_CJK_RANGES: dict[str, tuple[tuple[str, str], ...]] = {
    "ja": (
        ("\u3040", "\u309f"),  # Hiragana
        ("\u30a0", "\u30ff"),  # Katakana
        ("\u4e00", "\u9fff"),  # CJK Ideographs (default to ja for Fukuoka venue)
    ),
    "ko": (
        ("\uac00", "\ud7af"),  # Hangul Syllables
        ("\u1100", "\u11ff"),  # Hangul Jamo
    ),
}


def _detect_language(text: str) -> Optional[str]:
    """Detect language from text using unicode range heuristics.

    Checks for Japanese (hiragana/katakana) first, then Korean (hangul),
    then Chinese (CJK ideographs). Falls back to ``"en"`` if mostly ASCII.
    Returns ``None`` for empty text.
    """
    if not text or not text.strip():
        return None

    for lang, ranges in _CJK_RANGES.items():
        for start, end in ranges:
            if any(start <= ch <= end for ch in text):
                return lang

    ascii_ratio = sum(1 for ch in text if ch.isascii()) / max(len(text), 1)
    if ascii_ratio > 0.8:
        return "en"

    return None


# ---------------------------------------------------------------------------
# Confidence estimation
# ---------------------------------------------------------------------------


def _estimate_confidence(
    text_result: dict[str, Any],
    face_result: dict[str, Any],
    *,
    member_number_found: bool = False,
) -> float:
    """Estimate recognition confidence from VisionAgent results.

    Heuristic scoring:
      - text.success          -> +0.5
      - reasonable text len   -> +0.2
      - member_number found   -> +0.3  (member_card mode)
      - face detected         -> +0.1

    NOTE for hisajima000keita: This heuristic confidence estimation is a
    placeholder. Keita will improve this with custom logic in VisionAgent
    that returns native model confidence scores (Issue #314, confirmation
    item 3).
    """
    confidence = 0.0

    if text_result.get("success"):
        confidence += 0.5
        text_content = text_result.get("text") or ""
        if 1 <= len(text_content.strip()) <= 500:
            confidence += 0.2

    if member_number_found:
        confidence += 0.3

    if face_result.get("detected"):
        confidence += 0.1

    return min(confidence, 1.0)


# ---------------------------------------------------------------------------
# Image decoding
# ---------------------------------------------------------------------------


def _decode_image(image_data: str) -> np.ndarray:
    """Decode a base64 image string into an OpenCV ndarray.

    Strips an optional ``data:image/...;base64,`` prefix before decoding.

    Raises:
        HTTPException: If base64 decoding or image parsing fails.
    """
    raw_b64 = _DATA_URI_PREFIX.sub("", image_data)
    try:
        image_bytes = base64.b64decode(raw_b64)
    except Exception as exc:
        logger.warning("Base64 decode failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Invalid image data",
        ) from exc

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    if arr.size == 0:
        raise HTTPException(
            status_code=400,
            detail="Empty image data",
        )
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode image; ensure the payload is a valid JPEG/PNG.",
        )
    return image


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@ocr_router.post("", response_model=OcrResponse)
@rate_limit("10/minute")
async def recognize_image(request: Request, body: OcrRequest) -> OcrResponse:
    """Run OCR on an uploaded image.

    Supports two modes:

    - **member_card** -- Extract a 1-6 digit member number and look up the
      visitor profile via ``VisitorIdentificationService``.
    - **handwriting** -- Return the recognised text with a language hint.
    """
    t0 = time.monotonic()

    # --- Decode image -------------------------------------------------------
    image = _decode_image(body.image_data)

    # --- Run VisionAgent ----------------------------------------------------
    agent = _get_vision_agent()
    try:
        vision_result = await agent.run({"image": image, "mode": body.mode})
    except Exception as exc:
        logger.exception("VisionAgent failed: %s", exc)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return OcrResponse(
            success=False,
            mode=body.mode,
            processing_time_ms=elapsed_ms,
            error="Vision processing failed",
        )

    text_result: dict[str, Any] = vision_result.get("text", {})
    face_result: dict[str, Any] = vision_result.get("face", {})

    recognized_text = text_result.get("text")

    # Parse expression from face result (may be dict or str)
    expression_data = face_result.get("expression")
    expression_str: Optional[str] = None
    if isinstance(expression_data, dict):
        expression_str = expression_data.get("emotion")
    elif isinstance(expression_data, str):
        expression_str = expression_data

    # --- Mode-specific post-processing --------------------------------------
    member_number: Optional[int] = None
    visitor_identity: Optional[dict[str, Any]] = None
    detected_language: Optional[str] = None

    if body.mode == "member_card":
        if recognized_text:
            match = _MEMBER_CONTEXT_RE.search(recognized_text)
            if not match:
                match = _MEMBER_STANDALONE_RE.search(recognized_text)
            if match:
                member_number = int(match.group(1))
                try:
                    svc = _get_visitor_id_service()
                    visitor_identity = await svc.identify_by_member_number(member_number)
                except Exception as exc:
                    logger.warning(
                        "Visitor identification failed for member %s: %s",
                        member_number,
                        exc,
                    )

    elif body.mode == "handwriting":
        if recognized_text:
            detected_language = _detect_language(recognized_text)

    # --- Confidence ---------------------------------------------------------
    confidence = _estimate_confidence(
        text_result,
        face_result,
        member_number_found=member_number is not None,
    )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "OCR completed: mode=%s member=%s confidence=%.2f time=%dms session=%s",
        body.mode,
        member_number,
        confidence,
        elapsed_ms,
        body.session_id or "(none)",
    )

    return OcrResponse(
        success=text_result.get("success", False),
        mode=body.mode,
        member_number=member_number,
        recognized_text=recognized_text,
        confidence=confidence,
        language=detected_language,
        expression=expression_str,
        processing_time_ms=elapsed_ms,
        visitor_identity=visitor_identity,
    )
