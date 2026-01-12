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

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

from backend.llm.models import get_model_config
from backend.llm.openrouter import OpenRouterProvider
from backend.utils.language_processor import LanguageProcessor, SupportedLanguage
from backend.utils.query_classifier import QueryClassifier

# Type aliases
AgentName = Literal[
    "BusinessInfoAgent",
    "FacilityAgent",
    "EventAgent",
    "MemoryAgent",
    "GeneralKnowledgeAgent",
    "ClarificationAgent",
    "TimeAgent",
    "SlideAgent",
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
                        "detected": language_result.detected,
                        "confidence": language_result.confidence,
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
                            print(f"[RouterAgent] Context inheritance: {query} -> {request_type}")
                except Exception as error:
                    print(f"[RouterAgent] Failed to get previous request type: {error}")

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
                    "detected": language_result.detected,
                    "confidence": language_result.confidence,
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
                print(f"[RouterAgent] Context-dependent query detected: {query}")

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
            # 料金に関する質問はBusinessInfoAgentへ
            if request_type in ["price", "hours", "location"]:
                return "BusinessInfoAgent"
            # Wi-Fi・設備に関する質問はFacilityAgentへ
            if request_type in ["wifi", "facility", "basement"]:
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
        """
        クエリから具体的なリクエストタイプを抽出

        Args:
            query: ユーザーからのクエリ

        Returns:
            Optional[str]: リクエストタイプ（wi-fi, hours, price等）
        """
        lower_question = query.lower()

        # Wi-Fi関連
        if any(
            keyword in lower_question for keyword in ["wi-fi", "wifi", "インターネット", "ネット"]
        ):
            return "wifi"

        # 営業時間関連
        if any(
            keyword in lower_question
            for keyword in [
                "営業時間",
                "hours",
                "何時まで",
                "何時から",
                "開いて",
                "閉まる",
                "open",
                "close",
            ]
        ):
            return "hours"

        # 料金関連
        if any(
            keyword in lower_question
            for keyword in [
                "料金",
                "price",
                "いくら",
                "値段",
                "cost",
                "fee",
            ]
        ):
            return "price"

        # 場所関連
        if any(
            keyword in lower_question
            for keyword in [
                "場所",
                "location",
                "どこ",
                "where",
                "アクセス",
                "access",
                "住所",
                "address",
            ]
        ):
            return "location"

        # 設備関連
        if any(
            keyword in lower_question
            for keyword in [
                "設備",
                "facility",
                "equipment",
                "電源",
                "プリンター",
                "printer",
            ]
        ):
            return "facility"

        # 地下施設関連 - Enhanced detection (prioritize over meeting-room)
        basement_keywords = [
            "地下",
            "basement",
            "b1",
            "階下",
            "ちか",
            "チカ",  # Add speech recognition variations
            "underground",
            "mtgスペース",
            "集中スペース",
            "アンダースペース",
            "makersスペース",
            "focus space",
            "meeting space",
            "makers space",
        ]
        basement_patterns = [
            r"地下.*スペース",
            r"地下.*施設",
            r"地下.*会議",
            r"ちか.*ミーティング",
            r"ちか.*スペース",
        ]

        if any(keyword in lower_question for keyword in basement_keywords) or any(
            re.search(pattern, lower_question) for pattern in basement_patterns
        ):
            return "basement"

        # 会議室関連 (but not if already caught by basement above)
        if any(
            keyword in lower_question
            for keyword in [
                "会議室",
                "meeting room",
                "ミーティングルーム",
                "会議スペース",
            ]
        ):
            return "meeting-room"

        # イベント関連
        if any(
            keyword in lower_question
            for keyword in [
                "イベント",
                "event",
                "勉強会",
                "セミナー",
                "workshop",
                "meetup",
            ]
        ):
            return "event"

        # スライド関連
        if any(
            keyword in lower_question
            for keyword in [
                "スライド",
                "slide",
                "プレゼン",
                "presentation",
                "次のスライド",
                "前のスライド",
                "説明して",
                "ナレーション",
                "narration",
            ]
        ):
            return "slide"

        return None

    def _is_memory_related_question(self, question: str) -> bool:
        """
        メモリ関連の質問かどうかを判定

        Args:
            question: ユーザーからの質問

        Returns:
            bool: メモリ関連の質問ならTrue
        """
        lower_question = question.lower()

        # Exclude business-related questions even if they contain memory keywords like "どんな"
        business_keywords = [
            "メニュー",
            "menu",
            "料金",
            "price",
            "pricing",
            "営業時間",
            "hours",
            "場所",
            "location",
            "アクセス",
            "access",
            "設備",
            "facility",
            "サイノカフェ",
            "saino",
            "エンジニアカフェ",
            "engineer",
        ]
        if any(keyword in lower_question for keyword in business_keywords):
            return False

        # Exclude basement/facility-related questions even if they contain memory keywords
        facility_keywords = [
            "地下",
            "basement",
            "スペース",
            "space",
            "mtg",
            "会議室",
            "施設",
            "facility",
            "equipment",
            "makers",
        ]
        if any(keyword in lower_question for keyword in facility_keywords):
            return False

        # Check for "other one" patterns that refer to clarification options
        other_one_patterns = [
            # Japanese
            "もう一つ",
            "もうひとつ",
            "もう1つ",
            "もう一方",
            "もう片方",
            "他の方",
            "ほかの方",
            "別の方",
            "そっち",
            "あっち",
            # English
            "the other",
            "other one",
            "other option",
            "the alternative",
        ]

        if any(pattern in lower_question for pattern in other_one_patterns):
            return True

        # Memory-related keywords (from EnhancedQAAgent)
        memory_keywords = [
            # Japanese
            "さっき",
            "前に",
            "覚えて",
            "記憶",
            "質問",
            "聞いた",
            "話した",
            "どんな",
            "何を",
            "言った",
            "会話",
            "履歴",
            "先ほど",
            # English
            "remember",
            "recall",
            "earlier",
            "before",
            "previous",
            "asked",
            "said",
            "mentioned",
            "conversation",
            "history",
            "what did i",
        ]

        return any(keyword in lower_question for keyword in memory_keywords)

    def _is_context_dependent_query(self, question: str) -> bool:
        """
        文脈依存クエリかどうかを判定

        Args:
            question: ユーザーからの質問

        Returns:
            bool: 文脈依存クエリならTrue
        """
        trimmed = question.strip()

        # Short questions that likely depend on context
        context_patterns = [
            r"^土曜[日]?[はも].*",  # 土曜日は... 土曜は... 土曜日も... 土曜も...
            r"^日曜[日]?[はも].*",  # 日曜日は... 日曜は... 日曜日も... 日曜も...
            r"^平日[はも].*",  # 平日は... 平日も...
            r"^saino[のは方も]?.*",  # sainoの方は... sainoは... sainoも...
            r"^そっち[のはも]?.*",  # そっちの方は... そっちは... そっちも...
            r"^あっち[のはも]?.*",  # あっちの方は... あっちは... あっちも...
            r"^それ[のはも]?.*",  # それの方は... それは... それも...
            r"^そこ[のはも]?.*",  # そこの方は... そこは... そこも...
            r"^(じゃあ|それでは|では).*(エンジニア|engineer).*(カフェ|cafe)",  # じゃあエンジニアカフェ！
            r"^エンジニア.*(カフェ|cafe)[!！]?$",  # エンジニアカフェ！
            r"^(エンジニア|engineer).*(の方|にして|で)[!！]?$",  # エンジニアの方で！
            r"^(じゃあ|それでは|では).*(saino|サイノ).*(カフェ|cafe|の方|方は)",  # じゃあsainoカフェの方は？
        ]

        return any(re.search(pattern, trimmed, re.IGNORECASE) for pattern in context_patterns)

    async def close(self):
        """リソースのクリーンアップ"""
        await self.provider.close()
