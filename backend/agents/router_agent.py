"""
RouterAgent - クエリルーティングエージェント

TypeScript版から移植:
frontend/src/mastra/agents/router-agent.ts

責任範囲:
- 言語検出
- クエリ分類
- エージェント選択
- コンテキスト継承
- メモリ関連判定
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.config.routing_constants import (
    MEMORY_EXCLUSION_BUSINESS_EXTENDED,
    MEMORY_EXCLUSION_FACILITY_EXTENDED,
    MEMORY_KEYWORDS_EXTENDED,
    OTHER_ONE_PATTERNS,
    AgentName,
    extract_request_type,
    match_keywords,
)
from backend.llm.models import get_model_config
from backend.llm.openrouter import OpenRouterProvider
from backend.utils.language_processor import LanguageProcessor, SupportedLanguage
from backend.utils.query_classifier import QueryClassifier

logger = logging.getLogger(__name__)

# Pre-compiled context-dependent query patterns (MEDIUM-4)
_CONTEXT_PATTERNS = [
    re.compile(r"^土曜[日]?[はも].*", re.IGNORECASE),
    re.compile(r"^日曜[日]?[はも].*", re.IGNORECASE),
    re.compile(r"^平日[はも].*", re.IGNORECASE),
    re.compile(r"^saino[のは方も]?.*", re.IGNORECASE),
    re.compile(r"^そっち[のはも]?.*", re.IGNORECASE),
    re.compile(r"^あっち[のはも]?.*", re.IGNORECASE),
    re.compile(r"^それ[のはも]?.*", re.IGNORECASE),
    re.compile(r"^そこ[のはも]?.*", re.IGNORECASE),
    re.compile(r"^(じゃあ|それでは|では).*(エンジニア|engineer).*(カフェ|cafe)", re.IGNORECASE),
    re.compile(r"^エンジニア.*(カフェ|cafe)[!！]?$", re.IGNORECASE),
    re.compile(r"^(エンジニア|engineer).*(の方|にして|で)[!！]?$", re.IGNORECASE),
    re.compile(r"^(じゃあ|それでは|では).*(saino|サイノ).*(カフェ|cafe|の方|方は)", re.IGNORECASE),
]


@dataclass
class RouteResult:
    """ルーティング結果"""

    agent: AgentName
    category: str
    request_type: Optional[str]
    language: SupportedLanguage
    confidence: float
    debug_info: Dict[str, Any] = field(default_factory=dict)


class RouterAgent:
    """
    RouterAgent - クエリを適切なエージェントにルーティング

    OpenRouter APIを使用してクエリを分析し、
    最適な専門エージェントを選択します。
    """

    def __init__(self, api_key: Optional[str] = None, debug_mode: bool = False):
        """
        Args:
            api_key: OpenRouter API key (optional, uses env var if not provided)
            debug_mode: デバッグモードの有効/無効
        """
        self.provider = OpenRouterProvider(api_key=api_key)
        self.query_classifier = QueryClassifier(debug_mode=debug_mode)
        self.language_processor = LanguageProcessor()
        self.debug_mode = debug_mode

        # OpenRouter API設定（router用の設定を使用）
        self.model_config = get_model_config("router")

    async def route_query(
        self, query: str, session_id: str, memory_system: Optional[Any] = None
    ) -> RouteResult:
        """
        クエリをルーティング

        Args:
            query: ユーザーからのクエリ
            session_id: セッションID
            memory_system: メモリシステム（オプション）

        Returns:
            RouteResult: ルーティング結果
        """
        # 言語検出
        language_result = self.language_processor.detect_language(query)
        response_language = self.language_processor.determine_response_language(language_result)

        # メモリー関連の質問を先にチェック
        if self._is_memory_related_question(query):
            return RouteResult(
                agent="MemoryAgent",
                category="memory",
                request_type=None,
                language=response_language,
                confidence=1.0,
                debug_info={
                    "language_detection": {
                        "detected": language_result["detected"],
                        "confidence": language_result["confidence"],
                    },
                    "classification": {"reason": "Memory-related question detected"},
                },
            )

        # クエリ分類
        classification = await self.query_classifier.classify_with_details(query)

        # 特定リクエストタイプの抽出
        request_type = self._extract_request_type(query)

        # 文脈依存クエリの場合、前回のrequestTypeを継承
        if self._is_context_dependent_query(query) and not request_type:
            if memory_system:
                try:
                    previous_request_type = await memory_system.get_previous_request_type(
                        session_id
                    )
                    if previous_request_type:
                        request_type = previous_request_type
                        if self.debug_mode:
                            logger.debug(f"Context inheritance: {query} -> {request_type}")
                except Exception as error:
                    logger.warning(f"Failed to get previous request type: {error}")

        # エージェント選択
        selected_agent = self._select_agent(classification.category, request_type, query)

        return RouteResult(
            agent=selected_agent,
            category=classification.category,
            request_type=request_type,
            language=response_language,
            confidence=classification.confidence,
            debug_info={
                "language_detection": {
                    "detected": language_result["detected"],
                    "confidence": language_result["confidence"],
                },
                "classification": classification.debug_info,
            },
        )

    def _select_agent(
        self, category: str, request_type: Optional[str], query: Optional[str] = None
    ) -> AgentName:
        """
        カテゴリとリクエストタイプからエージェントを選択

        Args:
            category: クエリカテゴリ
            request_type: リクエストタイプ
            query: 元のクエリ（オプション）

        Returns:
            AgentName: 選択されたエージェント名
        """
        # Context-dependent queries: try to route to appropriate agent instead of memory
        if query and self._is_context_dependent_query(query):
            if self.debug_mode:
                logger.debug(f"Context-dependent query detected: {query}")

            # Check for specific entities/topics to determine agent
            lower_query = query.lower()

            if "saino" in lower_query:
                return "BusinessInfoAgent"  # saino-related queries

            if "土曜" in lower_query or "日曜" in lower_query or "平日" in lower_query:
                return "BusinessInfoAgent"  # hours-related queries

        # Check if clarification is needed first
        if category in ["cafe-clarification-needed", "meeting-room-clarification-needed"]:
            return "ClarificationAgent"

        # requestTypeに基づく特別なルーティング
        if request_type:
            # 料金・営業時間・場所・相談・コミュニティはBusinessInfoAgentへ
            if request_type in ["price", "hours", "location", "consultation", "community"]:
                return "BusinessInfoAgent"
            # Wi-Fi・設備・建物・アクセス方法はFacilityAgentへ
            if request_type in ["wifi", "facility", "basement", "access", "building"]:
                return "FacilityAgent"
            # イベントに関する質問はEventAgentへ
            if request_type == "event":
                return "EventAgent"
            # スライドに関する質問はSlideAgentへ
            if request_type == "slide":
                return "SlideAgent"

        # カテゴリベースのマッピング
        agent_map: Dict[str, AgentName] = {
            "facility-info": "FacilityAgent" if request_type == "wifi" else "BusinessInfoAgent",
            "saino-cafe": "BusinessInfoAgent",
            "calendar": "EventAgent",
            "events": "EventAgent",
            "current-time": "TimeAgent",
            "general": "GeneralKnowledgeAgent",
            "memory": "MemoryAgent",
            "cafe-clarification-needed": "ClarificationAgent",
            "meeting-room-clarification-needed": "ClarificationAgent",
        }

        return agent_map.get(category, "GeneralKnowledgeAgent")

    def _extract_request_type(self, query: str) -> Optional[str]:
        """クエリから具体的なリクエストタイプを抽出（routing_constantsに委譲）"""
        return extract_request_type(query)

    def _is_memory_related_question(self, question: str) -> bool:
        """
        メモリ関連の質問かどうかを判定

        Args:
            question: ユーザーからの質問

        Returns:
            bool: メモリ関連の質問ならTrue
        """
        lower_question = question.lower()

        if match_keywords(lower_question, MEMORY_EXCLUSION_BUSINESS_EXTENDED):
            return False

        if match_keywords(lower_question, MEMORY_EXCLUSION_FACILITY_EXTENDED):
            return False

        if match_keywords(lower_question, OTHER_ONE_PATTERNS):
            return True

        return match_keywords(lower_question, MEMORY_KEYWORDS_EXTENDED)

    def _is_context_dependent_query(self, question: str) -> bool:
        """
        文脈依存クエリかどうかを判定

        Args:
            question: ユーザーからの質問

        Returns:
            bool: 文脈依存クエリならTrue
        """
        trimmed = question.strip()
        return any(p.search(trimmed) for p in _CONTEXT_PATTERNS)

    async def close(self):
        """リソースのクリーンアップ"""
        await self.provider.close()
