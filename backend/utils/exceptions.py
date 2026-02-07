"""
カスタム例外階層

エージェントシステム全体で使用するドメイン固有の例外を定義。
bare `except Exception` を段階的に具体的例外に置換するために使用。
"""


class AgentSystemError(Exception):
    """エージェントシステムの基底例外"""


class RoutingError(AgentSystemError):
    """ルーティング処理中のエラー"""


class LLMGenerationError(AgentSystemError):
    """LLM応答生成中のエラー"""


class MemorySystemError(AgentSystemError):
    """メモリシステムのエラー"""


class RAGSearchError(AgentSystemError):
    """RAG検索のエラー"""


class ExternalServiceError(AgentSystemError):
    """外部サービス（Calendar API, Connpass等）のエラー"""
