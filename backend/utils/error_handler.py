"""
エラーハンドリングユーティリティ
統一されたエラー処理
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """エージェント関連のエラー"""
    
    def __init__(
        self,
        message: str,
        agent_name: Optional[str] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.agent_name = agent_name
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


def handle_error(
    error: Exception,
    agent_name: Optional[str] = None,
    default_message: str = "エラーが発生しました"
) -> Dict[str, Any]:
    """エラーを処理して統一された形式で返す"""
    
    logger.error(
        f"[{agent_name or 'Unknown'}] Error: {str(error)}",
        exc_info=True
    )
    
    if isinstance(error, AgentError):
        return {
            "error": error.message,
            "agent": error.agent_name,
            "error_code": error.error_code,
            "details": error.details
        }
    elif isinstance(error, HTTPException):
        return {
            "error": error.detail,
            "status_code": error.status_code
        }
    else:
        return {
            "error": default_message,
            "agent": agent_name,
            "details": {"original_error": str(error)}
        }

