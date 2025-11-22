"""
エージェント応答モデル
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class AgentResponse(BaseModel):
    """エージェント応答のPydanticモデル"""
    
    answer: str = Field(..., description="エージェントの応答テキスト")
    emotion: Optional[str] = Field(None, description="感情タグ（happy, sad, angry, relaxed, surprised）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="追加メタデータ")
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "営業時間は9:00〜22:00です。",
                "emotion": "relaxed",
                "metadata": {
                    "agent": "BusinessInfoAgent",
                    "category": "business",
                    "request_type": "hours"
                }
            }
        }

