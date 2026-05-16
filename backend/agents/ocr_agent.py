import base64
import json
import logging
import re
import time
from typing import Annotated, Dict, Any, TypedDict

import cv2
import numpy as np
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import get_model_config

logger = logging.getLogger(__name__)

# When the vision model misuses text_recognition,
# it sometimes passes the user prompt back as "text".
_HANDWRITING_PROMPT_MARKERS = (
    "手書き文字をOCRしてください",
    "手書き文字だけを読み取るOCRエンジン",
    "画像から読み取れる文字列だけ",
    "JSONやMarkdownは禁止",
    "・推測は禁止",
    "読めない場合は None",
    "transcribe only",
    "do not repeat",
    "do not explain",
    "text_recognition",
)
_MEMBER_CARD_PROMPT_MARKERS = (
    "会員証画像を解析してください",
    "・会員番号を含む文字列を正確に抽出",
    "・検出不能なら None",
)


def _ocr_text_looks_like_prompt_echo(text: str, mode: str) -> bool:
    """True if the model echoed our instruction instead of OCR output."""
    stripped = (text or "").strip()
    if len(stripped) < 12:
        return False
    lower = stripped.lower()
    if mode == "handwriting":
        if "手書き文字をOCRしてください" in stripped or "手書き文字だけを読み取る" in stripped:
            return True
        if "do not repeat" in lower or "transcribe only" in lower:
            return True
        hits = sum(1 for m in _HANDWRITING_PROMPT_MARKERS if m.lower() in lower)
        return hits >= 2
    if mode == "member_card":
        if "会員証画像を解析してください" in stripped:
            return True
        hits = sum(1 for m in _MEMBER_CARD_PROMPT_MARKERS if m.lower() in lower)
        return hits >= 2
    return False


def _message_content_to_text(content: Any) -> str:
    """Extract text from a LangChain message content payload."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content or "")


def _strip_wrapping_markup(text: str) -> str:
    """Remove common assistant wrapping around short OCR answers."""
    cleaned = text.strip()
    fence_match = re.fullmatch(r"```(?:json|text)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        else:
            for key in ("text", "recognized_text", "transcription", "value"):
                value = data.get(key)
                if isinstance(value, str):
                    cleaned = value.strip()
                    break

    return cleaned.strip().strip('"').strip("'").strip()


def _parse_text_recognition_content(raw_content: Any, mode: str) -> dict[str, Any]:
    """Normalize OCR text and apply prompt-echo / no-text guards."""
    raw = _strip_wrapping_markup(_message_content_to_text(raw_content))
    if not raw or raw.lower() in {"none", "null", "n/a"}:
        return {"success": False, "text": None, "error": "no_text_detected"}
    if _ocr_text_looks_like_prompt_echo(raw, mode):
        logger.warning("OCR returned prompt echo; treating as no text (mode=%s)", mode)
        return {"success": False, "text": None, "error": "prompt_echo"}
    return {"success": True, "text": raw, "error": None}


# =====================================================
# Tools
# =====================================================


@tool
def face_recognition(expression: str):
    """表情を以下の7つに分類する
    happy | sad | angry | neutral | surprised | confused
    見つからない場合は None"""
    return expression


@tool
def text_recognition(text: str):
    """画像内の文字を返す。見つからない場合は None"""
    return text


TOOLS = [face_recognition, text_recognition]


# =====================================================
# State
# =====================================================


class VisionState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# =====================================================
# Agent
# =====================================================


class VisionAgent:

    def __init__(self):
        provider = OpenRouterProvider()
        config = get_model_config("vision")
        handwriting_config = get_model_config("vision_handwriting")

        self.llm = provider.get_langchain_llm(config=config)
        self.handwriting_llm = provider.get_langchain_llm(config=handwriting_config)
        self.vision_llm = self.llm.bind_tools(TOOLS)

        self.app = self._build_graph()

    # -------------------------------------------------
    # Graph
    # -------------------------------------------------
    def _build_graph(self):
        graph = StateGraph(VisionState)

        graph.add_node("vision", self._vision_node)
        graph.add_node("tools", ToolNode(TOOLS))

        graph.add_edge(START, "vision")

        graph.add_conditional_edges(
            "vision",
            tools_condition,
            {"tools": "tools", "__end__": END},
        )

        graph.add_edge("tools", "vision")

        return graph.compile()

    async def _vision_node(self, state: VisionState):
        response = await self.vision_llm.ainvoke(state["messages"])
        return {"messages": [response]}

    async def _run_handwriting_ocr(self, message: HumanMessage) -> dict[str, Any]:
        """Run handwriting OCR without tool-calling to avoid prompt echo tool args."""
        response = await self.handwriting_llm.ainvoke([message])
        return _parse_text_recognition_content(
            getattr(response, "content", response),
            "handwriting",
        )

    # =====================================================
    # Prompt Builder (⭐ NEW)
    # =====================================================
    def _build_prompt(self, mode: str, image_base64: str):

        if mode == "member_card":
            instruction = (
                "会員証画像を解析してください。\n"
                "・会員番号を含む文字列を正確に抽出\n"
                "・印刷文字を優先\n"
                "・余計な説明は禁止\n"
                "・検出不能なら None\n"
            )

        elif mode == "handwriting":
            instruction = (
                "あなたは手書き文字だけを読み取るOCRエンジンです。\n"
                "画像から読み取れる文字列だけを、そのまま1行で返してください。\n"
                "・説明、前置き、翻訳、要約は禁止\n"
                "・JSONやMarkdownは禁止\n"
                "・この指示文を繰り返すことは禁止\n"
                "・推測は禁止\n"
                "・読めない場合は None だけを返す\n"
            )

        else:
            instruction = "画像を解析してください。"

        return HumanMessage(
            content=[
                {"type": "text", "text": instruction},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                },
            ]
        )

    # =====================================================
    # Confidence (⭐ NEW)
    # =====================================================
    def _estimate_confidence(
        self,
        text_result: dict,
        face_result: dict,
        mode: str,
    ) -> float:

        score = 0.0

        if text_result.get("success"):
            score += 0.6

            text = text_result.get("text") or ""
            length = len(text.strip())

            if 3 <= length <= 200:
                score += 0.2

        if face_result.get("detected"):
            score += 0.1

        # handwritingは曖昧なので減衰
        if mode == "handwriting":
            score *= 0.9

        return round(min(score, 1.0), 3)

    # =====================================================
    # Public API
    # =====================================================
    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:

        t0 = time.monotonic()

        frame: np.ndarray = input["image"]

        # ⭐ 新仕様（後方互換あり）
        mode: str = input.get("mode") or input.get("recognition_type") or "member_card"

        # ---------- resize ----------
        MAX_WIDTH = 640
        h, w = frame.shape[:2]
        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            frame = cv2.resize(
                frame,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )

        # ---------- encode ----------
        _, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        image_base64 = base64.b64encode(buffer).decode()

        message = self._build_prompt(mode, image_base64)

        # ---------- parse ----------
        text_result = {"success": False, "text": None, "error": None}
        face_result = {
            "success": False,
            "detected": False,
            "expression": None,
            "error": None,
        }

        if mode == "handwriting":
            text_result = await self._run_handwriting_ocr(message)
        else:
            result = await self.app.ainvoke({"messages": [message]})
            for msg in result["messages"]:
                if not isinstance(msg, ToolMessage):
                    continue

                if msg.name == "text_recognition":
                    text_result = _parse_text_recognition_content(msg.content, mode)

                elif msg.name == "face_recognition":
                    face_result["success"] = True
                    if msg.content and msg.content.lower() != "none":
                        face_result["detected"] = True
                        face_result["expression"] = {"emotion": msg.content}

        confidence = self._estimate_confidence(
            text_result,
            face_result,
            mode,
        )

        elapsed = int((time.monotonic() - t0) * 1000)

        return {
            "text": text_result,
            "face": face_result,
            "confidence": confidence,
            "processing_time_ms": elapsed,
        }

    # -------------------------------------------------
    async def close(self):
        if hasattr(self.llm, "aclose"):
            await self.llm.aclose()
        if hasattr(self.handwriting_llm, "aclose"):
            await self.handwriting_llm.aclose()
