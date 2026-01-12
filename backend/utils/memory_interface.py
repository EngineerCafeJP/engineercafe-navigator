"""
メモリシステムインターフェース

RouterAgentやその他のエージェントが使用する最小限のインターフェース。
オプショナルな連携を可能にする設計。

参考: frontend/src/lib/simplified-memory.ts
"""

from typing import Protocol, Optional, Dict, Any


class MemorySystemInterface(Protocol):
    """
    メモリシステムのインターフェース（任意の形式で実装可能）

    このProtocolを実装することで、異なるメモリシステム（SimplifiedMemoryHelper、
    LangGraphの組み込みメモリ、カスタムメモリシステムなど）を統一的に扱える。
    """

    async def get_previous_request_type(self, session_id: str) -> Optional[str]:
        """
        前回のリクエストタイプを取得

        Args:
            session_id: セッションID

        Returns:
            前回のリクエストタイプ（hours, price, location, facility, events など）
            存在しない場合は None

        Example:
            >>> request_type = await memory.get_previous_request_type("session_123")
            >>> print(request_type)  # "hours" or None
        """
        ...

    async def get_context(
        self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        会話コンテキストを取得

        Args:
            query: ユーザーのクエリ
            session_id: セッションID
            options: オプション設定
                - include_knowledge_base: bool - ナレッジベースを含めるか
                - language: str - 言語設定 ("ja" or "en")
                - inherit_context: bool - コンテキストを継承するか

        Returns:
            コンテキスト情報を含む辞書
            {
                "recent_messages": List[Dict],  # 最近のメッセージ履歴
                "knowledge_results": List[Dict],  # ナレッジベース検索結果
                "context_string": str,  # フォーマット済みコンテキスト文字列
                "inherited_request_type": Optional[str]  # 継承されたリクエストタイプ
            }

        Example:
            >>> context = await memory.get_context(
            ...     "エンジニアカフェ",
            ...     "session_123",
            ...     {"include_knowledge_base": True, "language": "ja"}
            ... )
            >>> print(context["context_string"])
        """
        ...

    async def store_message(
        self,
        role: str,
        content: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        メッセージを保存

        Args:
            role: ロール ("user" or "assistant")
            content: メッセージ内容
            session_id: セッションID
            metadata: メタデータ
                - emotion: str - 感情情報
                - confidence: float - 信頼度
                - request_type: str - リクエストタイプ
                - timestamp: int - タイムスタンプ

        Example:
            >>> await memory.store_message(
            ...     "user",
            ...     "エンジニアカフェの営業時間は？",
            ...     "session_123",
            ...     {"emotion": "curious", "request_type": "hours"}
            ... )
        """
        ...


class MemoryNotAvailableError(Exception):
    """メモリシステムが利用できない場合のエラー"""

    pass
