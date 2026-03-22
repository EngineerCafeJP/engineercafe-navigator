import base64
import logging
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

        self.llm = provider.get_langchain_llm(config=config)
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
            {"tools": "tools", "end": END},
        )

        graph.add_edge("tools", "vision")

        return graph.compile()

    async def _vision_node(self, state: VisionState):
        response = await self.vision_llm.ainvoke(state["messages"])
        return {"messages": [response]}

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
                "手書き文字をOCRしてください。\n"
                "・自然な文章として復元\n"
                "・改行やノイズを補正\n"
                "・意味が通る文章に整形\n"
                "・推測は禁止\n"
                "・読めない場合は None\n"
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
        mode: str = input.get("mode", "member_card")

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

        result = await self.app.ainvoke({"messages": [message]})

        # ---------- parse ----------
        text_result = {"success": False, "text": None, "error": None}
        face_result = {
            "success": False,
            "detected": False,
            "expression": None,
            "error": None,
        }

        for msg in result["messages"]:
            if not isinstance(msg, ToolMessage):
                continue

            if msg.name == "text_recognition":
                if msg.content and msg.content.lower() != "none":
                    text_result["success"] = True
                    text_result["text"] = msg.content
                else:
                    text_result["error"] = "no_text_detected"

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
