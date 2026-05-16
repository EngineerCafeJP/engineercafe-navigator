"""
SimplifiedMemoryHelper - セッションベースメモリ実装

Supabase agent_memoryテーブルを使用したセッションベースメモリシステム。
conversation_sessionsテーブルでセッション境界を判定し、
セッション単位でメッセージをスコープする。

参考: frontend/src/lib/simplified-memory.ts
"""

import os
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from supabase import create_client, Client

from backend.config.routing_constants import extract_request_type
from backend.utils.cafe_entity import (
    canonicalize_facility_aliases,
    canonicalize_facility_memory_key_text,
)
from backend.utils.postgres_sanitizer import sanitize_for_postgres

logger = logging.getLogger(__name__)

_AGENT_MEMORY_SESSION_COLUMN = "value->>sessionId"


def infer_previous_request_type_from_messages(messages: List[Dict[str, Any]]) -> Optional[str]:
    """Infer the latest user request_type from memory-style message rows."""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue

        metadata = message.get("metadata")
        request_type = metadata.get("request_type") if isinstance(metadata, dict) else None
        if isinstance(request_type, str) and request_type.strip():
            return request_type.strip()

        content = str(message.get("content") or "")
        request_type = extract_request_type(content)
        if request_type:
            return request_type

    return None


def _log_memory_event_safely(event: str, **fields: Any) -> None:
    try:
        from backend.observability.structured_logger import log_memory_event

        log_memory_event(event=event, **fields)
    except Exception:
        pass


class SimplifiedMemoryHelper:
    """
    Supabase agent_memoryテーブルを使用したメモリシステム

    セッション単位でメッセージをスコープし、セッションが有効な間は
    全履歴を保持する。セッション終了後は新しいセッションでフレッシュスタート。
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
        self.max_entries = 100  # メッセージ数の上限

        logger.info("SimplifiedMemoryHelper initialized (session-based)")

    async def _is_session_active(self, session_id: str) -> bool:
        """
        セッションがアクティブかどうかを確認

        Args:
            session_id: セッションID

        Returns:
            セッションがアクティブならTrue
        """
        if not self.supabase:
            return False

        try:
            uuid.UUID(session_id)
        except (TypeError, ValueError):
            logger.debug("Skipping conversation_sessions UUID lookup for non-UUID session_id")
            return True

        try:
            response = (
                self.supabase.table("conversation_sessions")
                .select("id, status")
                .eq("id", session_id)
                .execute()
            )

            if not response.data:
                logger.info(
                    "conversation_sessions row not found for UUID session %s; "
                    "treating as active for session-scoped frontend memory",
                    session_id,
                )
                return True

            session = response.data[0]
            return session.get("status") == "active"

        except Exception as e:
            logger.warning("Error checking session status: %s", e)
            # セッション情報取得に失敗した場合はフォールバックとしてTrue
            return True

    async def get_previous_request_type(self, session_id: str) -> Optional[str]:
        """
        前回のリクエストタイプを取得

        Args:
            session_id: セッションID

        Returns:
            前回のリクエストタイプ（hours, price, location など）
            存在しない場合は None
        """
        logger.info("Getting previous request type for session: %s", session_id)

        if not self.supabase:
            logger.warning("Supabase not available")
            return None

        try:
            # セッションIDでスコープしたメッセージを取得
            response = (
                self.supabase.table("agent_memory")
                .select("value")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
                .filter(_AGENT_MEMORY_SESSION_COLUMN, "eq", sanitize_for_postgres(session_id))
                .filter("value->>role", "eq", "user")
                .order("created_at", desc=True)
                .limit(self.max_entries)
                .execute()
            )

            if not response.data:
                return None

            # 最新のuser messageを探す。session_id/role は SQL 側で絞り込み済み。
            for item in response.data:
                value = item.get("value", {})
                request_type = value.get("request_type")
                if request_type:
                    logger.info("Found previous request type: %s", request_type)
                    _log_memory_event_safely(
                        "memory_previous_request_type_load",
                        session_id=session_id,
                        success=True,
                        request_type=request_type,
                    )
                    return request_type

            _log_memory_event_safely(
                "memory_previous_request_type_load",
                session_id=session_id,
                success=True,
                request_type=None,
            )
            return None

        except Exception as e:
            logger.error("Error getting previous request type: %s", e)
            _log_memory_event_safely(
                "memory_previous_request_type_load",
                session_id=session_id,
                success=False,
                error_type=type(e).__name__,
            )
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

        logger.info("Getting context for query: '%s...', session: %s", query[:50], session_id)

        try:
            from backend.utils.memory_feature_flags import get_memory_feature_flags

            memory_flags = get_memory_feature_flags()
        except Exception as flag_error:
            logger.debug("Failed to read memory feature flags: %s", flag_error)
            memory_flags = None

        # 最近のメッセージを取得。STM cutover 後は LangGraph Checkpointer を
        # short-term source とし、agent_memory からの read も止める。
        if memory_flags and not memory_flags.enable_agent_memory_stm_writes:
            recent_messages = []
            _log_memory_event_safely(
                "memory_recent_messages_load",
                session_id=session_id,
                success=True,
                skipped=True,
                reason="agent_memory_stm_writes_disabled",
            )
        else:
            recent_messages = await self._get_recent_messages(session_id)
        logger.info("Found %d recent messages", len(recent_messages))
        _log_memory_event_safely(
            "memory_context_load",
            session_id=session_id,
            success=True,
            recent_messages=len(recent_messages),
        )

        # メッセージをランキング
        if recent_messages:
            recent_messages = self._rank_messages(recent_messages, query)

        # リクエストタイプの継承。現在の発話から明示 intent が取れる場合は、
        # 前ターンの request_type を持ち越さない。
        inherited_request_type: Optional[str] = None
        query_request_type = extract_request_type(query)
        query_intent_override = False
        if inherit_context:
            if memory_flags and not memory_flags.enable_agent_memory_stm_writes:
                inherited_request_type = None
            else:
                inherited_request_type = await self.get_previous_request_type(session_id)
            if query_request_type:
                query_intent_override = inherited_request_type is not None
                inherited_request_type = query_request_type
            logger.info(
                "Found previous request type: %s",
                inherited_request_type,
                extra={"query_intent_override": query_intent_override},
            )

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
                logger.warning("Knowledge base search failed: %s", e)
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
            "query_intent_override": query_intent_override,
        }

    async def _get_recent_messages(self, session_id: str) -> List[Dict]:
        """
        agent_memoryテーブルからセッションに属するメッセージを取得

        セッションがアクティブな場合はそのセッションの全メッセージを返す。
        セッションが非アクティブまたは不明な場合は空リストを返す。

        Args:
            session_id: セッションID

        Returns:
            セッション内のメッセージリスト
        """
        if not self.supabase:
            return []

        try:
            # セッションの有効性を確認
            session_active = await self._is_session_active(session_id)
            if not session_active:
                logger.info("Session %s is not active, returning empty messages", session_id)
                return []

            response = (
                self.supabase.table("agent_memory")
                .select("value")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
                .filter(_AGENT_MEMORY_SESSION_COLUMN, "eq", sanitize_for_postgres(session_id))
                .order("created_at", desc=True)
                .limit(self.max_entries * 3)
                .execute()
            )

            if not response.data:
                return []

            # メッセージを整形。session_id は SQL 側で絞り込み済み。
            messages = []
            for item in response.data:
                value = item.get("value", {})
                content = value.get("content")
                messages.append(
                    {
                        "role": value.get("role"),
                        "content": content,
                        "metadata": {
                            "emotion": value.get("emotion"),
                            "confidence": value.get("confidence"),
                            "timestamp": value.get("timestamp"),
                            "request_type": value.get("request_type"),
                            "canonical_content_key": value.get("canonicalContentKey")
                            or canonicalize_facility_memory_key_text(str(content or "")),
                        },
                    }
                )

            # DESC順で取得しているので時系列順に戻し、max_entriesで制限
            messages = messages[::-1]
            result = messages[-self.max_entries :] if len(messages) > self.max_entries else messages
            _log_memory_event_safely(
                "memory_recent_messages_load",
                session_id=session_id,
                success=True,
                message_count=len(result),
            )
            return result

        except Exception as e:
            logger.error("Error getting recent messages: %s", e)
            _log_memory_event_safely(
                "memory_recent_messages_load",
                session_id=session_id,
                success=False,
                error_type=type(e).__name__,
            )
            return []

    def _rank_messages(self, messages: List[Dict], current_query: str) -> List[Dict]:
        """メッセージをrecency/frequency/relevanceの複合スコアでランキング

        Args:
            messages: メッセージリスト
            current_query: 現在のクエリ

        Returns:
            _rank_score付きのソート済みメッセージリスト
        """
        if not messages:
            return []

        now = datetime.now()
        scored = []

        for msg in messages:
            # Recency (0-1): 新しいほど高い（1週間で0に減衰）
            timestamp = msg.get("metadata", {}).get("timestamp")
            if timestamp:
                age_hours = (now - datetime.fromtimestamp(timestamp / 1000)).total_seconds() / 3600
            else:
                age_hours = 168  # デフォルト: 1週間前
            recency = max(0.0, 1.0 - age_hours / (24 * 7))

            # Frequency (0-1): 同じトピックの出現頻度
            topic_count = sum(1 for m in messages if self._topic_overlap(msg, m) > 0.3)
            frequency = min(1.0, topic_count / max(len(messages), 1))

            # Relevance (0-1): 現在のクエリとの関連性
            relevance = self._compute_relevance(msg, current_query)

            # 複合スコア（重み付き）
            composite = 0.4 * recency + 0.2 * frequency + 0.4 * relevance

            scored.append({**msg, "_rank_score": composite})

        scored.sort(key=lambda x: x["_rank_score"], reverse=True)
        return self._dedupe_ranked_messages(scored)

    @staticmethod
    def _dedupe_ranked_messages(messages: List[Dict]) -> List[Dict]:
        """Keep the highest-ranked message for the same canonical facility content."""
        deduped: List[Dict] = []
        seen: set[str] = set()
        for msg in messages:
            metadata = msg.get("metadata", {})
            key = metadata.get("canonical_content_key") if isinstance(metadata, dict) else None
            if not key:
                key = canonicalize_facility_memory_key_text(str(msg.get("content") or ""))
            normalized_key = " ".join(str(key).strip().lower().split())
            if normalized_key and normalized_key in seen:
                continue
            if normalized_key:
                seen.add(normalized_key)
            deduped.append(msg)
        return deduped

    def _topic_overlap(self, msg_a: Dict, msg_b: Dict) -> float:
        """2メッセージのトピック類似度（bigramマッチ率）

        Args:
            msg_a: メッセージA
            msg_b: メッセージB

        Returns:
            類似度スコア (0.0-1.0)
        """
        content_a = msg_a.get("content", "")
        content_b = msg_b.get("content", "")

        if not content_a or not content_b:
            return 0.0

        bigrams_a = set(content_a[i : i + 2] for i in range(len(content_a) - 1))
        bigrams_b = set(content_b[i : i + 2] for i in range(len(content_b) - 1))

        if not bigrams_a or not bigrams_b:
            return 0.0

        intersection = bigrams_a & bigrams_b
        union = bigrams_a | bigrams_b

        return len(intersection) / len(union) if union else 0.0

    def _compute_relevance(self, msg: Dict, query: str) -> float:
        """クエリとメッセージの関連度（用語マッチ率）

        Args:
            msg: メッセージ
            query: クエリ文字列

        Returns:
            関連度スコア (0.0-1.0)
        """
        content = msg.get("content", "")
        if not content or not query:
            return 0.0

        # 2文字sliding windowでbigramを生成
        query_bigrams = set(query[i : i + 2] for i in range(len(query) - 1))
        content_lower = content.lower()

        if not query_bigrams:
            return 0.0

        match_count = sum(1 for bg in query_bigrams if bg in content_lower)
        return match_count / len(query_bigrams)

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
                "セッション内の会話履歴:" if language == "ja" else "Session conversation history:"
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

        セッションIDに紐づけて保存する。TTLベースのexpires_atは設定せず、
        セッション境界でメッセージのスコープを管理する。

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

        try:
            from backend.utils.memory_feature_flags import get_memory_feature_flags

            if not get_memory_feature_flags().enable_agent_memory_stm_writes:
                logger.info(
                    "Skipping agent_memory STM write; "
                    "LangGraph checkpointer is the short-term source"
                )
                _log_memory_event_safely(
                    "memory_store_message",
                    session_id=session_id,
                    role=role,
                    success=True,
                    skipped=True,
                    reason="agent_memory_stm_writes_disabled",
                )
                return
        except Exception as flag_error:
            logger.debug("Failed to read memory feature flags: %s", flag_error)

        timestamp = int(datetime.now().timestamp() * 1000)
        metadata = sanitize_for_postgres(metadata or {})
        role = sanitize_for_postgres(role)
        content = sanitize_for_postgres(canonicalize_facility_aliases(content))
        canonical_content_key = sanitize_for_postgres(
            canonicalize_facility_memory_key_text(content)
        )
        session_id = sanitize_for_postgres(session_id)

        # リクエストタイプの自動抽出（user messageの場合）
        if role == "user" and "request_type" not in metadata:
            metadata["request_type"] = extract_request_type(content)

        logger.info(
            "Storing %s message for session: %s, request_type: %s",
            role,
            session_id,
            metadata.get("request_type"),
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
                "canonicalContentKey": canonical_content_key,
            }

            # ユニークなキーを生成（タイムスタンプ + UUID）
            unique_id = uuid.uuid4().hex[:8]
            message_key = f"message_{timestamp}_{unique_id}"

            # agent_memoryテーブルにINSERT（expires_atなし: セッション境界で管理）
            self.supabase.table("agent_memory").insert(
                {
                    "agent_name": self.agent_name,
                    "key": message_key,
                    "value": message_data,
                }
            ).execute()

            logger.info("Stored message with key: %s, session: %s", message_key, session_id)
            _log_memory_event_safely(
                "memory_store_message",
                session_id=session_id,
                role=role,
                success=True,
            )

        except Exception as e:
            logger.error("Error storing message: %s", e)
            _log_memory_event_safely(
                "memory_store_message",
                session_id=session_id,
                role=role,
                success=False,
                error_type=type(e).__name__,
            )
            raise

    def _extract_request_type(self, content: str) -> Optional[str]:
        """リクエストタイプ抽出（routing_constantsに委譲）"""
        return extract_request_type(content)

    async def cleanup_session(self, session_id: str) -> None:
        """
        セッション終了時のメッセージアーカイブ

        セッションに紐づくメッセージを削除（またはアーカイブ）する。
        conversation_sessionsのstatus更新と連動して呼ぶことを想定。

        Args:
            session_id: セッションID
        """
        logger.info("Cleaning up messages for session: %s", session_id)

        if not self.supabase:
            return

        try:
            response = (
                self.supabase.table("agent_memory")
                .delete()
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
                .filter(_AGENT_MEMORY_SESSION_COLUMN, "eq", sanitize_for_postgres(session_id))
                .execute()
            )

            deleted_count = len(response.data or [])
            logger.info("Cleaned up %d messages for session: %s", deleted_count, session_id)
            _log_memory_event_safely(
                "memory_cleanup_session",
                session_id=session_id,
                success=True,
                deleted_count=deleted_count,
            )

        except Exception as e:
            logger.error("Error during session cleanup: %s", e)
            _log_memory_event_safely(
                "memory_cleanup_session",
                session_id=session_id,
                success=False,
                error_type=type(e).__name__,
            )

    async def cleanup(self) -> None:
        """
        非アクティブセッションのメッセージクリーンアップ

        conversation_sessionsテーブルでステータスが'ended'のセッションに
        紐づくメッセージを削除する。
        """
        logger.info("Running cleanup for ended session messages")

        if not self.supabase:
            return

        try:
            # 終了済みセッションのIDを取得
            sessions_response = (
                self.supabase.table("conversation_sessions")
                .select("id")
                .neq("status", "active")
                .execute()
            )

            if not sessions_response.data:
                logger.info("No ended sessions to clean up")
                return

            ended_session_ids = {s["id"] for s in sessions_response.data}

            messages_query = (
                self.supabase.table("agent_memory")
                .select("id")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
            )
            messages_response = messages_query.in_(
                _AGENT_MEMORY_SESSION_COLUMN,
                sorted(sanitize_for_postgres(session_id) for session_id in ended_session_ids),
            ).execute()

            if not messages_response.data:
                return

            ids_to_delete = [item["id"] for item in messages_response.data]

            if ids_to_delete:
                for record_id in ids_to_delete:
                    self.supabase.table("agent_memory").delete().eq("id", record_id).execute()

                logger.info("Cleaned up %d messages from ended sessions", len(ids_to_delete))

        except Exception as e:
            logger.error("Error during cleanup: %s", e)

    async def get_memory_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        メモリ統計を取得

        Args:
            session_id: 特定セッションの統計を取得（Noneなら全体）

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
            query = (
                self.supabase.table("agent_memory")
                .select("value")
                .eq("agent_name", self.agent_name)
                .like("key", "message_%")
            )
            if session_id:
                query = query.filter(
                    _AGENT_MEMORY_SESSION_COLUMN,
                    "eq",
                    sanitize_for_postgres(session_id),
                )
            response = query.execute()

            if not response.data:
                return {
                    "active_turns": 0,
                    "oldest_turn": None,
                    "newest_turn": None,
                    "dominant_emotion": None,
                    "time_span": 0.0,
                }

            items = response.data

            if not items:
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

            for item in items:
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
                "active_turns": len(items),
                "oldest_turn": oldest_turn,
                "newest_turn": newest_turn,
                "dominant_emotion": dominant_emotion,
                "time_span": time_span,
            }

        except Exception as e:
            logger.error("Error getting memory stats: %s", e)
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
