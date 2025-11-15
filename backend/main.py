"""
Engineer Cafe Navigator Backend
FastAPIアプリケーションとLangGraphエージェントの統合
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

app = FastAPI(
    title="Engineer Cafe Navigator Backend",
    description="Python LangGraph backend for Engineer Cafe Navigator",
    version="0.1.0"
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
        # TODO: LangGraphワークフローの実装後に統合
        # from workflows.main_workflow import get_workflow
        # workflow = get_workflow()
        # result = await workflow.ainvoke({
        #     "query": request.query,
        #     "session_id": request.session_id,
        #     "language": request.language,
        #     "context": request.context or {}
        # })
        
        # 暫定的な応答
        return ChatResponse(
            answer="LangGraphワークフローは実装中です。",
            emotion="neutral",
            metadata={
                "status": "pending",
                "query": request.query,
                "session_id": request.session_id
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/invoke")
async def invoke_agent(request: ChatRequest):
    """
    LangGraphエージェントの直接実行エンドポイント
    """
    try:
        # TODO: LangGraphワークフローの実装後に統合
        return {
            "status": "pending",
            "message": "LangGraphワークフローは実装中です。"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

