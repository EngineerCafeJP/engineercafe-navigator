"""
SimplifiedMemoryHelper - 暫定実装

Supabase agent_memoryテーブルを使用した3分間TTL付きメモリシステム。
フロントエンドのSimplifiedMemorySystemを参考にしたPython実装。

参考: frontend/src/lib/simplified-memory.ts

TODO (専門エンジニア向け):
- RAGツールとの統合（現在はプレースホルダー）
- 完全なエラーハンドリング
- パフォーマンス最適化
- メッセージインデックスの実装
"""

from typing import Optional, Dict, Any, List

# from datetime import datetime  # TODO: 完全実装時に使用
import logging

# Supabaseクライアントのインポート（実装時に調整）
# from supabase import create_client, Client

logger = logging.getLogger(__name__)


class SimplifiedMemoryHelper:
    """
    暫定実装：Supabase agent_memoryテーブルを使用

    3分間のTTL（有効期限）付きで会話履歴を管理。
    フロントエンドのSimplifiedMemorySystemと同様のインターフェースを提供。
    """

    def __init__(self):
        """
        初期化

        環境変数から Supabase の接続情報を取得します。
        SUPABASE_URL: Supabase プロジェクトの URL
        SUPABASE_SERVICE_ROLE_KEY: サービスロールキー（server-side用）
        """
        # TODO: Supabaseクライアントの初期化
        # supabase_url = os.getenv("SUPABASE_URL")
        # supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        # self.supabase: Client = create_client(supabase_url, supabase_key)

        self.agent_name = "langgraph_memory"
        self.ttl_seconds = 180  # 3 minutes（フロントエンドと同じ）
        self.max_entries = 100  # メッセージ数の上限

        logger.info(f"SimplifiedMemoryHelper initialized with TTL={self.ttl_seconds}s")

    async def get_previous_request_type(self, session_id: str) -> Optional[str]:
        """
        前回のリクエストタイプを取得

        Args:
            session_id: セッションID

        Returns:
            前回のリクエストタイプ（hours, price, location など）
            存在しない場合は None

        TODO:
        - agent_memoryテーブルから最新のuser messageを取得
        - metadataからrequest_typeを抽出
        """
        logger.info(f"Getting previous request type for session: {session_id}")

        # TODO: 実装
        # 1. agent_memoryテーブルから recent messages を取得
        # 2. session_idでフィルタリング
        # 3. 最新のuser messageのmetadata.request_typeを返す

        return None  # プレースホルダー

    async def get_context(
        self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        会話コンテキストを取得

        Args:
            query: ユーザーのクエリ
            session_id: セッションID
            options: オプション設定
                - include_knowledge_base: bool - ナレッジベースを含めるか（デフォルト: True）
                - language: str - 言語設定（デフォルト: "ja"）
                - inherit_context: bool - コンテキストを継承するか（デフォルト: True）

        Returns:
            {
                "recent_messages": List[Dict],  # 最近のメッセージ履歴
                "knowledge_results": List[Dict],  # ナレッジベース検索結果（未実装）
                "context_string": str,  # フォーマット済みコンテキスト文字列
                "inherited_request_type": Optional[str]  # 継承されたリクエストタイプ
            }

        TODO:
        - agent_memoryテーブルから recent messages を取得（3分以内）
        - RAGツールでナレッジベース検索
        - コンテキスト文字列のフォーマット
        """
        options = options or {}
        # include_knowledge_base = options.get("include_knowledge_base", True)  # TODO: RAG統合時に使用
        language = options.get("language", "ja")
        # inherit_context = options.get("inherit_context", True)  # TODO: 完全実装時に使用

        logger.info(f"Getting context for query: '{query[:50]}...', session: {session_id}")

        # TODO: 実装
        # 1. get_recent_messages() で履歴を取得
        # 2. inherit_context=True なら get_previous_request_type() を呼び出し
        # 3. include_knowledge_base=True なら RAG検索
        # 4. build_comprehensive_context() でフォーマット

        recent_messages: List[Dict] = []
        knowledge_results: List[Dict] = []
        inherited_request_type: Optional[str] = None

        # プレースホルダー
        context_string = (
            "会話履歴がありません。" if language == "ja" else "No conversation context."
        )

        return {
            "recent_messages": recent_messages,
            "knowledge_results": knowledge_results,
            "context_string": context_string,
            "inherited_request_type": inherited_request_type,
        }

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

        TODO:
        - agent_memoryテーブルにメッセージを保存
        - TTL（expires_at）を設定
        - メッセージインデックスを更新
        """
        # timestamp = int(datetime.now().timestamp() * 1000)  # TODO: 完全実装時に使用
        metadata = metadata or {}

        # リクエストタイプの自動抽出（user messageの場合）
        if role == "user" and "request_type" not in metadata:
            metadata["request_type"] = self._extract_request_type(content)

        logger.info(
            f"Storing {role} message for session: {session_id}, "
            f"request_type: {metadata.get('request_type')}"
        )

        # TODO: 実装
        # 1. message_data = { role, content, timestamp, ...metadata }
        # 2. expires_at = now() + ttl_seconds
        # 3. supabase.from('agent_memory').insert({ ... })
        # 4. update_message_index(timestamp)

    def _extract_request_type(self, content: str) -> Optional[str]:
        """
        コンテンツからリクエストタイプを抽出（フロントエンド実装の移植）

        Args:
            content: ユーザーのメッセージ

        Returns:
            リクエストタイプ（hours, price, location, facility, events, booking など）
            マッチしない場合は None
        """
        lower_content = content.lower()

        # 営業時間系
        if any(
            keyword in lower_content
            for keyword in [
                "営業時間",
                "hours",
                "time",
                "何時",
                "いつまで",
                "when",
                "open",
                "close",
            ]
        ):
            return "hours"

        # 料金系
        if any(
            keyword in lower_content
            for keyword in ["料金", "cost", "price", "値段", "いくら", "how much"]
        ):
            return "price"

        # 場所系
        if any(
            keyword in lower_content
            for keyword in ["どこ", "where", "場所", "location", "アクセス", "address"]
        ):
            return "location"

        # 予約系
        if any(
            keyword in lower_content for keyword in ["予約", "booking", "reservation", "reserve"]
        ):
            return "booking"

        # 設備系
        if any(
            keyword in lower_content
            for keyword in ["設備", "facility", "equipment", "何がある", "利用できる"]
        ):
            return "facility"

        # イベント系
        if any(
            keyword in lower_content
            for keyword in ["イベント", "event", "勉強会", "セミナー", "workshop"]
        ):
            return "events"

        return None

    async def cleanup(self) -> None:
        """
        期限切れエントリのクリーンアップ

        Supabaseが自動的にTTLで削除するが、手動でも実行可能。

        TODO:
        - agent_memoryテーブルから expires_at < now() のエントリを削除
        """
        logger.info("Running cleanup for expired memory entries")

        # TODO: 実装
        # await self.supabase.from('agent_memory').delete().lt('expires_at', datetime.now().isoformat())

    async def get_memory_stats(self) -> Dict[str, Any]:
        """
        メモリ統計を取得

        Returns:
            {
                "active_turns": int,  # アクティブな会話ターン数
                "oldest_turn": Optional[int],  # 最古のタイムスタンプ
                "newest_turn": Optional[int],  # 最新のタイムスタンプ
                "dominant_emotion": Optional[str],  # 主な感情
                "time_span": float  # 会話の時間範囲（分）
            }

        TODO:
        - agent_memoryテーブルから統計情報を計算
        """
        logger.info("Getting memory statistics")

        # TODO: 実装
        return {
            "active_turns": 0,
            "oldest_turn": None,
            "newest_turn": None,
            "dominant_emotion": None,
            "time_span": 0.0,
        }


# シングルトンインスタンス（フロントエンドのrealtimeMemoryに相当）
_memory_helper_instance: Optional[SimplifiedMemoryHelper] = None


def get_memory_helper() -> SimplifiedMemoryHelper:
    """
    SimplifiedMemoryHelperのシングルトンインスタンスを取得

    Returns:
        SimplifiedMemoryHelperのインスタンス
    """
    global _memory_helper_instance
    if _memory_helper_instance is None:
        _memory_helper_instance = SimplifiedMemoryHelper()
    return _memory_helper_instance
