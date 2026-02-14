"""
SimplifiedMemoryHelper - 完全実装

Supabase agent_memoryテーブルを使用した3分間TTL付きメモリシステム。
フロントエンドのSimplifiedMemorySystemを参考にしたPython実装。

参考: frontend/src/lib/simplified-memory.ts
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

from supabase import create_client, Client

from backend.config.routing_constants import extract_request_type

logger = logging.getLogger(__name__)


class SimplifiedMemoryHelper:
    """
    Supabase agent_memoryテーブルを使用したメモリシステム

    3分間のTTL（有効期限）付きで会話履歴を管理。
    フロントエンドのSimplifiedMemorySystemと同様のインターフェースを提供。
    """

    def __init__(self):
        """
        初期化

        環境変数から Supabase の接続情報を取得します。
        SUPABASE_URL: Supabase プロジェクトの URL
        SUPABASE_KEY: サービスロールキー（server-side用）
        """
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found. Memory system will be disabled.")
            self.supabase: Optional[Client] = None
        else:
            self.supabase: Optional[Client] = create_client(supabase_url, supabase_key)

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
        """
        logger.info(f"Getting previous request type for session: {session_id}")

        if not self.supabase:
            logger.warning("Supabase not available")
            return None

        try:
            current_time = datetime.now().isoformat()

            # agent_memoryテーブルから有効なメッセージを取得
            response = (
                self.supabase.table("agent_memory")
                .select("*")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
                .gt("expires_at", current_time)
                .order("created_at", desc=True)
                .execute()
            )

            if not response.data:
                return None

            # session_idでフィルタリングし、最新のuser messageを探す
            for item in response.data:
                value = item.get("value", {})
                if value.get("role") == "user" and value.get("sessionId") == session_id:
                    request_type = value.get("request_type")
                    if request_type:
                        logger.info(f"Found previous request type: {request_type}")
                        return request_type

            return None

        except Exception as e:
            logger.error(f"Error getting previous request type: {e}")
            return None

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
                "knowledge_results": List[Dict],  # ナレッジベース検索結果
                "context_string": str,  # フォーマット済みコンテキスト文字列
                "inherited_request_type": Optional[str]  # 継承されたリクエストタイプ
            }
        """
        options = options or {}
        language = options.get("language", "ja")
        inherit_context = options.get("inherit_context", True)

        logger.info(f"Getting context for query: '{query[:50]}...', session: {session_id}")

        # 最近のメッセージを取得
        recent_messages = await self._get_recent_messages(session_id)
        logger.info(f"Found {len(recent_messages)} recent messages")

        # リクエストタイプの継承
        inherited_request_type: Optional[str] = None
        if inherit_context:
            inherited_request_type = await self.get_previous_request_type(session_id)

        # ナレッジベース検索
        include_knowledge_base = options.get("include_knowledge_base", True)
        knowledge_results: List[Dict] = []

        if include_knowledge_base:
            try:
                from backend.tools.enhanced_rag import EnhancedRAGSearch

                rag = EnhancedRAGSearch()
                # extract_request_typeでカテゴリを判定
                request_type = extract_request_type(query) or "general"
                rag_result = await rag.search(
                    query=query,
                    category=request_type,
                    language=language,
                    max_results=5,
                )

                if rag_result.get("success") and rag_result.get("data", {}).get("results"):
                    knowledge_results = [
                        {
                            "content": r.get("content", ""),
                            "category": r.get("entity", "general"),
                        }
                        for r in rag_result["data"]["results"]
                    ]
            except Exception as e:
                logger.warning(f"Knowledge base search failed: {e}")
                knowledge_results = []

        # コンテキスト文字列のフォーマット
        context_string = self._build_comprehensive_context(
            recent_messages, knowledge_results, language
        )

        return {
            "recent_messages": recent_messages,
            "knowledge_results": knowledge_results,
            "context_string": context_string,
            "inherited_request_type": inherited_request_type,
        }

    async def _get_recent_messages(self, session_id: str) -> List[Dict]:
        """
        agent_memoryテーブルから有効なメッセージを取得

        Args:
            session_id: セッションID

        Returns:
            最近のメッセージのリスト
        """
        if not self.supabase:
            return []

        try:
            current_time = datetime.now().isoformat()

            response = (
                self.supabase.table("agent_memory")
                .select("*")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
                .gt("expires_at", current_time)
                .order("created_at", desc=False)
                .limit(self.max_entries)
                .execute()
            )

            if not response.data:
                return []

            # session_idでフィルタリングしてメッセージを整形
            messages = []
            for item in response.data:
                value = item.get("value", {})
                if value.get("sessionId") == session_id:
                    messages.append(
                        {
                            "role": value.get("role"),
                            "content": value.get("content"),
                            "metadata": {
                                "emotion": value.get("emotion"),
                                "confidence": value.get("confidence"),
                                "timestamp": value.get("timestamp"),
                                "request_type": value.get("request_type"),
                            },
                        }
                    )

            return messages

        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []

    def _build_comprehensive_context(
        self,
        recent_messages: List[Dict],
        knowledge_results: List[Dict],
        language: str,
    ) -> str:
        """
        会話履歴とナレッジベース結果からコンテキスト文字列を構築

        Args:
            recent_messages: 最近のメッセージリスト
            knowledge_results: ナレッジベース検索結果
            language: 言語設定（"ja" or "en"）

        Returns:
            フォーマット済みコンテキスト文字列
        """
        lines: List[str] = []

        # 会話履歴の追加
        if recent_messages:
            header = (
                "最近の会話履歴（直近3分）:"
                if language == "ja"
                else "Recent conversation (last 3 minutes):"
            )
            lines.append(header)

            for msg in recent_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                role_label = (
                    ("ユーザー" if role == "user" else "アシスタント")
                    if language == "ja"
                    else ("User" if role == "user" else "Assistant")
                )
                emotion = msg.get("metadata", {}).get("emotion")
                emotion_info = f" [{emotion}]" if emotion else ""
                lines.append(f"{role_label}: {content}{emotion_info}")

        # ナレッジベース結果の追加
        if knowledge_results:
            lines.append("")  # 空行
            header = (
                "関連するエンジニアカフェ情報:"
                if language == "ja"
                else "Relevant Engineer Cafe information:"
            )
            lines.append(header)

            for i, result in enumerate(knowledge_results, 1):
                category = result.get("category", "")
                category_info = f" [{category}]" if category else ""
                lines.append(f"{i}. {result.get('content', '')}{category_info}")

        if not lines:
            return "会話履歴がありません。" if language == "ja" else "No conversation context."

        return "\n".join(lines)

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
        """
        if not self.supabase:
            logger.warning("Supabase not available, skipping message storage")
            return

        timestamp = int(datetime.now().timestamp() * 1000)
        metadata = metadata or {}

        # リクエストタイプの自動抽出（user messageの場合）
        if role == "user" and "request_type" not in metadata:
            metadata["request_type"] = extract_request_type(content)

        logger.info(
            f"Storing {role} message for session: {session_id}, "
            f"request_type: {metadata.get('request_type')}"
        )

        try:
            # メッセージデータの構築
            message_data = {
                "role": role,
                "content": content,
                "timestamp": timestamp,
                "sessionId": session_id,
                "emotion": metadata.get("emotion"),
                "confidence": metadata.get("confidence"),
                "request_type": metadata.get("request_type"),
            }

            # TTL設定
            expires_at = (datetime.now() + timedelta(seconds=self.ttl_seconds)).isoformat()

            # agent_memoryテーブルにINSERT
            self.supabase.table("agent_memory").insert(
                {
                    "agent_name": self.agent_name,
                    "key": f"message_{timestamp}",
                    "value": message_data,
                    "expires_at": expires_at,
                }
            ).execute()

            logger.info(f"Stored message with key: message_{timestamp}, expires_at: {expires_at}")

        except Exception as e:
            logger.error(f"Error storing message: {e}")
            raise

    def _extract_request_type(self, content: str) -> Optional[str]:
        """リクエストタイプ抽出（routing_constantsに委譲）"""
        return extract_request_type(content)

    async def cleanup(self) -> None:
        """
        期限切れエントリのクリーンアップ

        Supabaseが自動的にTTLで削除するが、手動でも実行可能。
        """
        logger.info("Running cleanup for expired memory entries")

        if not self.supabase:
            return

        try:
            current_time = datetime.now().isoformat()
            self.supabase.table("agent_memory").delete().eq("agent_name", self.agent_name).lt(
                "expires_at", current_time
            ).execute()

            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

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
        """
        logger.info("Getting memory statistics")

        if not self.supabase:
            return {
                "active_turns": 0,
                "oldest_turn": None,
                "newest_turn": None,
                "dominant_emotion": None,
                "time_span": 0.0,
            }

        try:
            current_time = datetime.now().isoformat()

            response = (
                self.supabase.table("agent_memory")
                .select("*")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
                .gt("expires_at", current_time)
                .execute()
            )

            if not response.data:
                return {
                    "active_turns": 0,
                    "oldest_turn": None,
                    "newest_turn": None,
                    "dominant_emotion": None,
                    "time_span": 0.0,
                }

            # 統計情報を計算
            timestamps = []
            emotions = []

            for item in response.data:
                value = item.get("value", {})
                ts = value.get("timestamp")
                if ts:
                    timestamps.append(ts)
                emotion = value.get("emotion")
                if emotion:
                    emotions.append(emotion)

            oldest_turn = min(timestamps) if timestamps else None
            newest_turn = max(timestamps) if timestamps else None
            time_span = (
                (newest_turn - oldest_turn) / (1000 * 60) if oldest_turn and newest_turn else 0.0
            )

            # 最も多い感情を取得
            dominant_emotion = None
            if emotions:
                emotion_counts: Dict[str, int] = {}
                for e in emotions:
                    emotion_counts[e] = emotion_counts.get(e, 0) + 1
                dominant_emotion = max(emotion_counts, key=lambda k: emotion_counts[k])

            return {
                "active_turns": len(response.data),
                "oldest_turn": oldest_turn,
                "newest_turn": newest_turn,
                "dominant_emotion": dominant_emotion,
                "time_span": time_span,
            }

        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
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
