"""
基本的なエージェント実装例
新しいエージェントを実装する際のテンプレート
"""

from typing import Dict, Any
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

# 相対インポートまたは絶対インポートに統一
try:
    from models.types import WorkflowState, UnifiedAgentResponse
    from utils.logger import get_logger
    from utils.error_handler import handle_error, AgentError
    from config.settings import get_settings
except ImportError:
    # フォールバック: 直接インポート（パッケージとして実行する場合）
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.types import WorkflowState, UnifiedAgentResponse
    from utils.logger import get_logger
    from utils.error_handler import handle_error, AgentError
    from config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()


def basic_agent_node(state: WorkflowState) -> Dict[str, Any]:
    """
    基本的なエージェントノードの実装例
    
    Args:
        state: ワークフロー状態
        
    Returns:
        更新された状態
    """
    try:
        query = state.get("query", "")
        session_id = state.get("session_id", "")
        language = state.get("language", "ja")
        
        logger.info(f"[BasicAgent] Processing query: {query}")
        
        # LLMの初期化
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            google_api_key=settings.google_api_key,
            temperature=0.7,
        )
        
        # プロンプトの構築
        system_prompt = f"""あなたはエンジニアカフェのアシスタントです。
ユーザーの質問に日本語で丁寧に答えてください。

現在のセッションID: {session_id}
言語: {language}
"""
        
        # LLMを呼び出し
        messages = [
            HumanMessage(content=system_prompt),
            HumanMessage(content=query)
        ]
        
        response = llm.invoke(messages)
        answer = response.content
        
        # 感情タグの抽出（オプション）
        emotion = extract_emotion(answer)
        
        logger.info(f"[BasicAgent] Response generated: {answer[:100]}...")
        
        return {
            "answer": answer,
            "emotion": emotion,
            "metadata": {
                "agent": "BasicAgent",
                "session_id": session_id,
                "language": language
            }
        }
        
    except Exception as e:
        logger.error(f"[BasicAgent] Error: {e}", exc_info=True)
        error_response = handle_error(e, agent_name="BasicAgent")
        return {
            "answer": error_response.get("error", "エラーが発生しました"),
            "emotion": "sad",
            "metadata": error_response
        }


def extract_emotion(text: str) -> str:
    """
    テキストから感情タグを抽出
    
    Args:
        text: テキスト
        
    Returns:
        感情タグ（happy, sad, angry, relaxed, surprised）
    """
    # 感情タグのパターン
    emotion_patterns = {
        "happy": ["[happy]", "喜", "楽", "嬉"],
        "sad": ["[sad]", "悲", "残念", "申し訳"],
        "angry": ["[angry]", "怒", "困"],
        "relaxed": ["[relaxed]", "落ち着", "静"],
        "surprised": ["[surprised]", "驚", "意外"]
    }
    
    for emotion, patterns in emotion_patterns.items():
        if any(pattern in text for pattern in patterns):
            return emotion
    
    return "relaxed"  # デフォルト


# 使用例
if __name__ == "__main__":
    # サンプル状態
    sample_state: WorkflowState = {
        "messages": [],
        "query": "営業時間は何時ですか？",
        "session_id": "test-session-123",
        "language": "ja",
        "routed_to": None,
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": {}
    }
    
    # エージェントを実行
    result = basic_agent_node(sample_state)
    print(f"Answer: {result['answer']}")
    print(f"Emotion: {result['emotion']}")

