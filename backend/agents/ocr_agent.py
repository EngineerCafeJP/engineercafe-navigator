import base64
import time
from typing import TypedDict, List, Dict, Any

import cv2
import numpy as np
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
import os

# =====================================================
# Env
# =====================================================
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")

# =====================================================
# Tools (LLM専用)
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


# =====================================================
# QR code (将来用・絶対に消さない)
# =====================================================
def recognize_qr(image: np.ndarray) -> str | None:
    """
    OpenCV による QRコード検出
    将来的に recognition_type == "qr" の場合に使用
    """
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(image)
    return data if data else None


# =====================================================
# State
# =====================================================
class VisionState(TypedDict):
    messages: List


# =====================================================
# Agent
# =====================================================
class VisionAgent:
    """
    Vision Agent
    - LLMによる文字認識
    - LLMによる表情分類
    - QRコード（将来拡張用）
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4.1-nano",
            temperature=0.0,
            api_key=API_KEY,
        )

        self.vision_llm = self.llm.bind_tools(
            [face_recognition, text_recognition]
        )

        self.app = self._build_graph()

    # -----------------------------
    # Graph
    # -----------------------------
    def _build_graph(self):
        graph = StateGraph(VisionState)

        graph.add_node("vision", self._vision_node)
        graph.add_node(
            "tools",
            ToolNode([face_recognition, text_recognition])
        )

        graph.add_edge(START, "vision")
        graph.add_edge("vision", "tools")
        graph.add_edge("tools", END)

        return graph.compile()

    def _vision_node(self, state: VisionState):
        response = self.vision_llm.invoke(state["messages"])
        return {"messages": state["messages"] + [response]}

    # =====================================================
    # Public API（外部から呼ばれる）
    # =====================================================
    async def run(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """
        input:
          {
            "image": np.ndarray,
            "recognition_type": "text" | "qr"
          }
        """

        frame: np.ndarray = input["image"]
        recognition_type: str = input.get("recognition_type", "text")

        # ---------- QR専用ルート（将来用） ----------
        if recognition_type == "qr":
            qr_data = recognize_qr(frame)
            return {
                "qr": {
                    "success": qr_data is not None,
                    "data": qr_data,
                    "error": None if qr_data else "QR not detected",
                }
            }

        # ---------- Resize ----------
        MAX_WIDTH = 640
        h, w = frame.shape[:2]
        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            frame = cv2.resize(
                frame,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )

        # ---------- Encode ----------
        _, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        )
        image_base64 = base64.b64encode(buffer).decode("utf-8")

        # ---------- Prompt ----------
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "画像を解析してください。\n"
                        "表情は次のいずれかのみ:\n"
                        "happy | confused | sad | angry | neutral | surprised \n"
                        "文字は検出された文字列のみ返してください。\n"
                        "見つからない場合は None を返してください。"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    },
                },
            ]
        )

        start = time.time()
        result = self.app.invoke({"messages": [message]})
        elapsed = time.time() - start

        # ---------- Parse ----------
        text_result = {"success": False, "text": None, "error": None}
        face_result = {
            "success": False,
            "detected": False,
            "expression": None,
            "error": None,
        }

        for msg in result["messages"]:
            if isinstance(msg, ToolMessage):
                if msg.name == "text_recognition":
                    if msg.content:
                        text_result["success"] = True
                        text_result["text"] = msg.content
                    else:
                        text_result["error"] = "text not detected"

                if msg.name == "face_recognition":
                    face_result["success"] = True
                    if msg.content and msg.content.lower() != "none":
                        face_result["detected"] = True
                        face_result["expression"] = {
                            "emotion": msg.content
                        }
                    else:
                        face_result["error"] = "face not detected"

        return {
            "text": text_result,
            "face": face_result,
        }
