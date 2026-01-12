"""
Engineer Cafe Navigator Backend
FastAPIアプリケーションとLangGraphエージェントの統合
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

app = FastAPI(
    title="Engineer Cafe Navigator Backend",
    description="Python LangGraph backend for Engineer Cafe Navigator",
    version="0.1.0",
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # NextJSのデフォルトポート
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

        workflow = get_workflow()
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/invoke")
async def invoke_agent(request: ChatRequest):
    """
    LangGraphエージェントの直接実行エンドポイント
    """
    try:
        from workflows.main_workflow import get_workflow

        workflow = get_workflow()
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
        raise HTTPException(status_code=500, detail=str(e))


# Voice API Models
class VoiceRequest(BaseModel):
    action: str
    audioData: Optional[str] = None
    sessionId: Optional[str] = None
    language: Optional[str] = "ja"
    text: Optional[str] = None
    streaming: Optional[bool] = False


class VoiceResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    response: Optional[str] = None
    audioResponse: Optional[str] = None
    emotion: Optional[str] = None
    sessionId: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/voice", response_model=VoiceResponse)
async def voice_api(request: VoiceRequest):
    """
    音声処理エンドポイント
    フロントエンドからのプロキシリクエストを処理
    """
    try:
        # TODO: 音声処理ロジックをLangGraphワークフローで実装
        # 現在はプレースホルダー
        if request.action == "process_voice":
            return VoiceResponse(
                success=True,
                transcript="音声処理中...",
                response="音声処理機能は実装中です。",
                emotion="neutral",
                sessionId=request.sessionId,
            )
        elif request.action == "text_to_speech":
            return VoiceResponse(
                success=True,
                audioResponse="",  # base64 audio
                sessionId=request.sessionId,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Slides API Models
class SlidesRequest(BaseModel):
    action: str
    slideId: Optional[str] = None
    sessionId: Optional[str] = None
    language: Optional[str] = "ja"


class SlidesResponse(BaseModel):
    success: bool
    slide: Optional[Dict[str, Any]] = None
    narration: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/slides", response_model=SlidesResponse)
async def slides_api(request: SlidesRequest):
    """
    スライド制御エンドポイント
    フロントエンドからのプロキシリクエストを処理
    """
    try:
        # TODO: スライド処理ロジックを実装
        # 現在はプレースホルダー
        if request.action == "get_slide":
            return SlidesResponse(
                success=True,
                slide={"id": request.slideId, "content": "スライド内容"},
                narration="スライド説明文",
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
