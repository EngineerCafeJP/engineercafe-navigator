"""
Engineer Cafe Navigator Backend
FastAPIアプリケーションとLangGraphエージェントの統合
"""

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Engineer Cafe Navigator Backend",
    description="Python LangGraph backend for Engineer Cafe Navigator",
    version="0.1.0",
)


@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の環境変数バリデーション"""
    from backend.utils.env_validator import validate_startup

    try:
        validate_startup()
    except ValueError:
        logger.error("起動時バリデーション失敗。環境変数を確認してください。")
        raise


# CORS設定
_default_origins = ["http://localhost:3000", "http://localhost:3001"]
_allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
] or _default_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class ChatRequest(BaseModel):
    query: str
    session_id: str
    language: Optional[str] = "ja"
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    answer: str
    emotion: str
    metadata: Dict[str, Any]


@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "ok", "service": "engineer-cafe-navigator-backend"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    チャットエンドポイント
    LangGraphエージェントを使用してクエリを処理します
    """
    try:
        from workflows.main_workflow import get_workflow

        workflow = await get_workflow()
        result = await workflow.ainvoke(
            {
                "query": request.query,
                "session_id": request.session_id,
                "language": request.language,
                "context": request.context or {},
            }
        )

        return ChatResponse(
            answer=result.get("answer", "回答を生成できませんでした。"),
            emotion=result.get("emotion", "neutral"),
            metadata=result.get(
                "metadata", {"query": request.query, "session_id": request.session_id}
            ),
        )
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


@app.post("/api/agent/invoke")
async def invoke_agent(request: ChatRequest):
    """
    LangGraphエージェントの直接実行エンドポイント
    """
    try:
        from workflows.main_workflow import get_workflow

        workflow = await get_workflow()
        result = await workflow.ainvoke(
            {
                "query": request.query,
                "session_id": request.session_id,
                "language": request.language,
                "context": request.context or {},
            }
        )

        return {"status": "success", "result": result}
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


# Voice API Models
class VoiceRequest(BaseModel):
    action: str
    audioData: Optional[str] = None
    sessionId: Optional[str] = None
    language: Optional[str] = "ja"
    text: Optional[str] = None
    streaming: Optional[bool] = False
    conversationStage: Optional[str] = None


class VoiceResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    response: Optional[str] = None
    audioResponse: Optional[str] = None
    emotion: Optional[str] = None
    sessionId: Optional[str] = None
    error: Optional[str] = None
    detectedLanguage: Optional[str] = None
    confidence: Optional[float] = None


# @app.post("/api/voice", response_model=VoiceResponse)
# async def voice_api(request: VoiceRequest):
#     """
#     音声処理エンドポイント
#     フロントエンドからのプロキシリクエストを処理
#     """
#     try:
#         # TODO: 音声処理ロジックをLangGraphワークフローで実装
#         # 現在はプレースホルダー
#         if request.action == "process_voice":
#             return VoiceResponse(
#                 success=True,
#                 transcript="音声処理中...",
#                 response="音声処理機能は実装中です。",
#                 emotion="neutral",
#                 sessionId=request.sessionId,
#             )
#         elif request.action == "text_to_speech":
#             return VoiceResponse(
#                 success=True,
#                 audioResponse="",  # base64 audio
#                 sessionId=request.sessionId,
#             )
#         else:
#             raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# backend/main.py（PR3差分イメージ）
from agents.voice_agent import VoiceAgent  # noqa: E402 # 追加
from agents.stt_agent import STTAgent  # noqa: E402

voice_agent = VoiceAgent()  # アプリ起動時に1回生成
stt_agent = STTAgent()  # STT: Vosk自動言語切換え対応


@app.post("/api/voice", response_model=VoiceResponse)
async def voice_api(request: VoiceRequest):
    try:
        if request.action == "text_to_speech":
            if not request.text or not request.text.strip():
                raise HTTPException(status_code=400, detail="Missing text for text_to_speech")

            result = await voice_agent.text_to_speech(
                text=request.text,
                language=request.language or "ja",
                emotion=None,  # request側でemotion渡す設計にするならここで拾う（現状VoiceRequestにはない） [3](https://scskinfo-my.sharepoint.com/personal/162179_cpsginfo_jp/Documents/Microsoft%20Copilot%20Chat%20%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB/emotion-mapping.txt)
            )
            if not result.get("success"):
                return VoiceResponse(
                    success=False,
                    error=result.get("error", "TTS failed"),
                    emotion=result.get("emotion"),
                    sessionId=request.sessionId,
                )

            return VoiceResponse(
                success=True,
                audioResponse=result.get("audioResponse"),
                emotion=result.get("emotion"),
                sessionId=request.sessionId,
            )

        elif request.action == "process_voice":
            if not request.audioData:
                raise HTTPException(status_code=400, detail="Missing audioData for process_voice")

            import base64

            audio_bytes = base64.b64decode(request.audioData)

            stt_result = await stt_agent.speech_to_text(
                audio_bytes,
                language=request.language,
                conversation_stage=request.conversationStage,
            )

            if not stt_result["success"]:
                return VoiceResponse(
                    success=False,
                    error=stt_result.get("error", "STT failed"),
                    sessionId=request.sessionId,
                )

            return VoiceResponse(
                success=True,
                transcript=stt_result["transcript"],
                emotion="neutral",
                detectedLanguage=stt_result.get("language"),
                confidence=stt_result.get("confidence"),
                sessionId=request.sessionId,
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


# Slides API Models
class SlidesRequest(BaseModel):
    action: str
    slideId: Optional[str] = None
    targetSlide: Optional[int] = None
    query: Optional[str] = None
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


@app.post("/api/slides", response_model=SlidesResponse)
async def slides_api(request: SlidesRequest):
    """
    スライド制御エンドポイント
    SlideAgentを使用してスライドナレーションと質問応答を処理
    """
    try:
        from backend.agents.slide_agent import SlideAgent

        slide_agent = SlideAgent()

        # アクションマッピング
        action_map = {
            "narrate": "narrate",
            "next": "next",
            "previous": "previous",
            "goto": "goto",
            "question": "question",
        }

        slide_action = action_map.get(request.action)
        if not slide_action:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        # SlideAgentのhandle_slide_action呼び出し
        result = await slide_agent.handle_slide_action(
            action=slide_action,
            query=request.query,
            target_slide=request.targetSlide,
            language=request.language,
        )

        return SlidesResponse(
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
            status_code=500, detail="An internal error occurred. Please try again later."
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


@app.post("/api/character", response_model=CharacterResponse)
async def character_api(request: CharacterRequest):
    """
    キャラクター制御エンドポイント
    フロントエンドからのプロキシリクエストを処理
    """
    try:
        # TODO: キャラクター制御ロジックを実装
        # 現在はプレースホルダー
        return CharacterResponse(success=True, message="キャラクター制御機能は実装中です。")
    except Exception as e:
        logger.exception("Endpoint error: %s", e)
        raise HTTPException(
            status_code=500, detail="An internal error occurred. Please try again later."
        )


# Knowledge CRUD API Router
from api.knowledge import router as knowledge_router  # noqa: E402

app.include_router(knowledge_router, prefix="/api")

# STT Custom Vocabulary API Router
from api.stt_vocabulary import router as stt_vocabulary_router  # noqa: E402

app.include_router(stt_vocabulary_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
