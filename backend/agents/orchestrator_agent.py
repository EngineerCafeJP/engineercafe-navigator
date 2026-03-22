"""
OrchestratorAgent - Supervisor Pattern による Multi-Agent オーケストレーション

LangGraph の Supervisor Agent パターンに従い、クエリを適切なエージェントに
ルーティングし、エージェント間の制御フローを管理する。

参考: https://langchain-ai.github.io/langgraph/concepts/multi_agent/

責任範囲:
- 言語検出
- クエリ分類
- 動的エージェント選択（LLM使用）
- Command patternによるルーティング
- エージェント処理後の次ステップ決定
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command

from backend.config.routing_constants import (
    ACCESSIBILITY_KEYWORDS,
    AGENT_DESCRIPTIONS,
    CATEGORY_TO_AGENT_MAP,
    ACCESS_DIRECTION_KEYWORDS,
    BASEMENT_KEYWORDS,
    BICYCLE_KEYWORDS,
    BUILDING_KEYWORDS,
    BUSINESS_HOURS_KEYWORDS,
    CHILDREN_NOISE_KEYWORDS,
    COMMUNITY_KEYWORDS,
    CONSULTATION_KEYWORDS,
    EMERGENCY_KEYWORDS,
    EXCLUSIVE_RENTAL_KEYWORDS,
    EVENT_KEYWORDS,
    GREETING_KEYWORDS,
    FACILITY_EQUIPMENT_KEYWORDS,
    FLOOR_KEYWORDS,
    FLOOR_LAYOUT_KEYWORDS,
    FOOD_DRINK_KEYWORDS,
    FOOD_DRINK_VERBS,
    MEETING_ROOM_KEYWORDS,
    MEMORY_EXCLUSION_BUSINESS,
    MEMORY_EXCLUSION_FACILITY,
    MEMORY_KEYWORDS,
    PARKING_KEYWORDS,
    PHOTOGRAPHY_KEYWORDS,
    PRICING_KEYWORDS,
    RECEPTION_KEYWORDS,
    SLIDE_KEYWORDS,
    SMOKING_KEYWORDS,
    TOILET_KEYWORDS,
    WIFI_KEYWORDS,
    RoutingTarget,
    extract_request_type,
    match_keywords,
)
from backend.llm.models import ModelConfig, SupportedModel
from backend.llm.openrouter import OpenRouterProvider
from backend.utils.input_sanitizer import (
    MAX_CONTEXT_LENGTH,
    MAX_QUERY_LENGTH,
    sanitize_input,
)
from backend.utils.language_processor import LanguageProcessor, SupportedLanguage
from backend.utils.query_classifier import QueryClassifier

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorDecision:
    """オーケストレーターの決定結果"""

    next_agent: RoutingTarget
    language: SupportedLanguage
    category: str
    request_type: Optional[str]
    confidence: float
    reasoning: str
    debug_info: dict = field(default_factory=dict)


class OrchestratorAgent:
    """
    OrchestratorAgent - Supervisor Pattern によるマルチエージェントオーケストレーション

    LangGraphのSupervisor Agentパターンに従い、LLMを使用して
    クエリを適切な専門エージェントにルーティングし、
    エージェント間の制御フローを動的に管理する。
    """

    # ルーティング用システムプロンプト
    ROUTING_SYSTEM_PROMPT = """\
あなたはエンジニアカフェの受付AIアシスタントのオーケストレーターです。
ユーザーの質問を分析し、最適な専門エージェントを選択してください。

利用可能なエージェント:
{agent_descriptions}

ルーティングルール:
1. 営業時間、料金、休館日、定休日、利用料、受付方法、初回利用、
   コミュニティ（Engineer Cafe Lab等）、キャリア相談等 → business_info
2. Wi-Fi、電源、設備、地下スペース、建物の歴史・構造、
   アクセス方法・行き方、フロアマップ、館内案内 → facility
3. イベント、勉強会、セミナーに関する質問 → event
4. 過去の会話や「さっき」「前に」などメモリ関連の質問 → general_knowledge (request_type: memory)
5. スライド操作やプレゼン関連の質問 → slide
6. その他の一般的な質問 → general_knowledge

重要な判断基準:
- 料金・営業時間・休館日に関する質問は必ず business_info にルーティング
- 「いくら」「タダ」「free」「無料」を含む質問 → business_info
- 「受付」「初回利用」「利用方法」を含む質問 → business_info
- 「フロアマップ」「館内案内」「floor map」を含む質問 → facility

ルーティング例:
- "エンジニアカフェの営業時間は？" → business_info (hours)
- "利用料金はいくらですか？" → business_info (price)
- "休館日はありますか？" → business_info (hours)
- "WiFiのパスワードは？" → facility (wifi)
- "フロアマップを見せてください" → facility (floor_layout)
- "次のイベントはいつ？" → event (event)
- "What are the opening hours?" → business_info (hours)
- "Is it free to use?" → business_info (price)

次のJSON形式で回答してください:
{{
    "next_agent": "エージェント名",
    "reasoning": "選択理由（簡潔に）",
    "category": "質問カテゴリ",
    "request_type": "具体的なリクエストタイプ（wifi, hours, price等）またはnull"
}}"""

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
        self._is_production = os.getenv("ENVIRONMENT") == "production"

    def _parse_llm_response(self, content: str) -> dict:
        """
        LLMレスポンスを安全にパース

        Args:
            content: LLMからのレスポンス文字列

        Returns:
            パースされた辞書

        Raises:
            ValueError: パースに失敗した場合
        """
        try:
            if "```json" in content:
                parts = content.split("```json")
                if len(parts) > 1:
                    content = parts[1].split("```")[0]
            elif "```" in content:
                parts = content.split("```")
                if len(parts) > 1:
                    content = parts[1].split("```")[0]

            raw_decision = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError) as e:
            raise ValueError(f"Invalid JSON response: {e}")

        if not isinstance(raw_decision, dict):
            raise ValueError("Response must be a JSON object")

        next_agent = raw_decision.get("next_agent")
        if not isinstance(next_agent, str):
            raise ValueError("next_agent must be a string")

        if next_agent not in AGENT_DESCRIPTIONS:
            next_agent = "general_knowledge"

        reasoning = str(raw_decision.get("reasoning", ""))[:200]
        category = str(raw_decision.get("category", "general"))[:50]
        request_type = raw_decision.get("request_type")
        if request_type is not None:
            request_type = str(request_type)[:50]

        return {
            "next_agent": next_agent,
            "reasoning": reasoning,
            "category": category,
            "request_type": request_type,
        }

    async def decide_next_agent(
        self,
        query: str,
        session_id: str,
        memory_context: Optional[dict] = None,
        previous_agent_response: Optional[str] = None,
    ) -> OrchestratorDecision:
        """
        次に実行すべきエージェントを決定

        Args:
            query: ユーザーからのクエリ
            session_id: セッションID
            memory_context: メモリコンテキスト（オプション）
            previous_agent_response: 前のエージェントの応答（オプション、再ルーティング時）

        Returns:
            OrchestratorDecision: オーケストレーターの決定結果
        """
        sanitized_query = sanitize_input(query, MAX_QUERY_LENGTH)

        language_result = self.language_processor.detect_language(sanitized_query)
        response_language = self.language_processor.determine_response_language(language_result)

        # 高速パス: メモリ関連の質問は即座にルーティング
        if self._is_memory_related_question(sanitized_query):
            return OrchestratorDecision(
                next_agent="general_knowledge",
                language=response_language,
                category="memory",
                request_type="memory",
                confidence=1.0,
                reasoning="Memory-related question detected, routing to GKA",
                debug_info=self._create_debug_info(
                    fast_path=True,
                    language_result=language_result,
                ),
            )

        # 高速パス: 明確なキーワードマッチングでルーティング
        fast_route = self._try_fast_routing(sanitized_query)
        if fast_route:
            return OrchestratorDecision(
                next_agent=fast_route["agent"],
                language=response_language,
                category=fast_route["category"],
                request_type=fast_route["request_type"],
                confidence=0.9,
                reasoning=fast_route["reasoning"],
                debug_info=self._create_debug_info(
                    fast_path=True,
                    language_result=language_result,
                ),
            )

        # LLMによる動的ルーティング
        agent_descriptions = "\n".join(
            f"- {name}: {desc}" for name, desc in AGENT_DESCRIPTIONS.items()
        )

        system_prompt = self.ROUTING_SYSTEM_PROMPT.format(agent_descriptions=agent_descriptions)

        user_message = f"ユーザーの質問: {sanitized_query}"
        if memory_context:
            sanitized_context = sanitize_input(
                str(memory_context.get("summary", "")),
                MAX_CONTEXT_LENGTH,
            )
            user_message += f"\n\n会話コンテキスト: {sanitized_context}"

        try:
            lc_messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]

            routing_config = ModelConfig(
                model_id=SupportedModel.GEMINI_3_FLASH,
                temperature=0.0,
                max_tokens=200,
                fallback_model=SupportedModel.GEMINI_2_5_FLASH,
            )

            response_content = await self.provider.generate(
                messages=lc_messages,
                config=routing_config,
            )

            decision = self._parse_llm_response(response_content)

            return OrchestratorDecision(
                next_agent=decision["next_agent"],
                language=response_language,
                category=decision["category"],
                request_type=decision["request_type"],
                confidence=0.8,
                reasoning=decision["reasoning"],
                debug_info=self._create_debug_info(
                    fast_path=False,
                    language_result=language_result,
                    llm_response_length=len(response_content),
                ),
            )

        except Exception as e:
            logger.warning("LLM routing failed: %s", e, exc_info=True)

            classification = await self.query_classifier.classify_with_details(sanitized_query)
            next_agent = CATEGORY_TO_AGENT_MAP.get(classification.category, "general_knowledge")

            return OrchestratorDecision(
                next_agent=next_agent,
                language=response_language,
                category=classification.category,
                request_type=extract_request_type(sanitized_query),
                confidence=classification.confidence,
                reasoning="Fallback to QueryClassifier",
                debug_info=self._create_debug_info(
                    fast_path=False,
                    language_result=language_result,
                    fallback=True,
                    error_type=type(e).__name__,
                ),
            )

    def _create_debug_info(
        self,
        fast_path: bool,
        language_result=None,
        llm_response_length: Optional[int] = None,
        fallback: bool = False,
        error_type: Optional[str] = None,
    ) -> dict:
        """デバッグ情報を作成（本番環境では最小限）"""
        if self._is_production:
            return {"fast_path": fast_path}

        info = {"fast_path": fast_path}

        if language_result:
            info["language_detection"] = {
                "detected": language_result["detected"],
                "confidence": language_result["confidence"],
            }

        if llm_response_length is not None:
            info["llm_response_length"] = llm_response_length

        if fallback:
            info["fallback"] = True

        if error_type:
            info["error_type"] = error_type

        return info

    def should_continue_or_end(
        self,
        agent_response: dict,
        original_query: str,
    ) -> RoutingTarget:
        """エージェント処理後に続行か終了かを決定"""
        return END

    def _try_fast_routing(self, query: str) -> Optional[dict]:
        """キーワードベースの高速ルーティング"""
        lower_query = query.lower()

        # 緊急キーワード → facility（最優先）
        if match_keywords(lower_query, EMERGENCY_KEYWORDS):
            return {
                "agent": "facility",
                "category": "emergency",
                "request_type": "emergency",
                "reasoning": "Emergency keyword detected",
            }

        # 挨拶キーワード → greeting（インライン処理）
        # Only treat as pure greeting if query is short (<=20 chars).
        # Longer queries likely contain an actual question after the greeting.
        if match_keywords(lower_query, GREETING_KEYWORDS):
            stripped = lower_query.strip()
            if len(stripped) <= 20:
                return {
                    "agent": "business_info",
                    "category": "greeting",
                    "request_type": "greeting",
                    "reasoning": "Greeting keyword detected",
                }

        # カフェ曖昧性: "カフェ" + "どっち/どちら/which" → clarification
        # (orchestrator_node がcategory基準でインライン処理する)
        if any(kw in lower_query for kw in ["カフェ", "cafe"]) and any(
            kw in lower_query for kw in ["どっち", "どちら", "which"]
        ):
            return {
                "agent": "general_knowledge",
                "category": "cafe-clarification-needed",
                "request_type": "clarification",
                "reasoning": "Ambiguous cafe reference detected",
            }

        if match_keywords(lower_query, WIFI_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "wifi",
                "reasoning": "Wi-Fi keyword detected",
            }

        if match_keywords(lower_query, BUSINESS_HOURS_KEYWORDS):
            return {
                "agent": "business_info",
                "category": "business-hours",
                "request_type": "hours",
                "reasoning": "Business hours keyword detected",
            }

        # 会議室 + 料金 → facility（会議室の料金情報はfacilityが保持）
        if any(kw in lower_query for kw in MEETING_ROOM_KEYWORDS) and match_keywords(
            lower_query, PRICING_KEYWORDS
        ):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "meeting_room",
                "reasoning": "Meeting room pricing query detected",
            }

        if match_keywords(lower_query, PRICING_KEYWORDS):
            return {
                "agent": "business_info",
                "category": "pricing",
                "request_type": "price",
                "reasoning": "Pricing keyword detected",
            }

        if match_keywords(lower_query, BASEMENT_KEYWORDS):
            return {
                "agent": "facility",
                "category": "basement-facility",
                "request_type": "basement",
                "reasoning": "Basement facility keyword detected",
            }

        if match_keywords(lower_query, EVENT_KEYWORDS):
            return {
                "agent": "event",
                "category": "events",
                "request_type": "event",
                "reasoning": "Event keyword detected",
            }

        if match_keywords(lower_query, SLIDE_KEYWORDS):
            return {
                "agent": "slide",
                "category": "slide",
                "request_type": "slide",
                "reasoning": "Slide keyword detected",
            }

        if match_keywords(lower_query, COMMUNITY_KEYWORDS):
            return {
                "agent": "business_info",
                "category": "community",
                "request_type": "community",
                "reasoning": "Community/program keyword detected",
            }

        if match_keywords(lower_query, CONSULTATION_KEYWORDS):
            return {
                "agent": "business_info",
                "category": "consultation",
                "request_type": "consultation",
                "reasoning": "Consultation keyword detected",
            }

        if match_keywords(lower_query, ACCESS_DIRECTION_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "access",
                "reasoning": "Access/direction keyword detected",
            }

        if match_keywords(lower_query, BUILDING_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "building",
                "reasoning": "Building keyword detected",
            }

        if match_keywords(lower_query, PARKING_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "parking",
                "reasoning": "Parking keyword detected",
            }

        if match_keywords(lower_query, BICYCLE_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "bicycle",
                "reasoning": "Bicycle parking keyword detected",
            }

        if match_keywords(lower_query, SMOKING_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "smoking",
                "reasoning": "Smoking policy keyword detected",
            }

        if match_keywords(lower_query, EXCLUSIVE_RENTAL_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "exclusive_rental",
                "reasoning": "Exclusive rental keyword detected",
            }

        if match_keywords(lower_query, TOILET_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "toilet",
                "reasoning": "Toilet/restroom keyword detected",
            }

        if match_keywords(lower_query, ACCESSIBILITY_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "accessibility",
                "reasoning": "Accessibility/wheelchair keyword detected",
            }

        if match_keywords(lower_query, PHOTOGRAPHY_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "photography",
                "reasoning": "Photography policy keyword detected",
            }

        if match_keywords(lower_query, CHILDREN_NOISE_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "children_noise",
                "reasoning": "Children/noise policy keyword detected",
            }

        if match_keywords(lower_query, FACILITY_EQUIPMENT_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "facility",
                "reasoning": "Facility equipment keyword detected",
            }

        if match_keywords(lower_query, RECEPTION_KEYWORDS):
            return {
                "agent": "business_info",
                "category": "reception",
                "request_type": "reception",
                "reasoning": "Reception/check-in keyword detected",
            }

        if match_keywords(lower_query, FLOOR_LAYOUT_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "floor_layout",
                "reasoning": "Floor layout/map keyword detected",
            }

        # 会議室 + 階情報 → facility（具体的な質問なのでclarificationスキップ）
        if any(kw in lower_query for kw in MEETING_ROOM_KEYWORDS) and any(
            kw in lower_query for kw in FLOOR_KEYWORDS
        ):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "meeting_room",
                "reasoning": "Meeting room with floor info detected",
            }

        # 飲食動詞（「飲めますか」「食べられますか」等）→ facility
        if any(kw in lower_query for kw in FOOD_DRINK_VERBS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "food_drink",
                "reasoning": "Food/drink verb detected",
            }

        if match_keywords(lower_query, FOOD_DRINK_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "food_drink",
                "reasoning": "Food/drink policy keyword detected",
            }

        return None

    def _is_memory_related_question(self, query: str) -> bool:
        """メモリ関連の質問かどうかを判定"""
        lower_query = query.lower()

        if match_keywords(lower_query, MEMORY_EXCLUSION_BUSINESS):
            return False

        if match_keywords(lower_query, MEMORY_EXCLUSION_FACILITY):
            return False

        return match_keywords(lower_query, MEMORY_KEYWORDS)

    async def close(self):
        """リソースのクリーンアップ"""
        await self.provider.close()


# Supervisor Node用のヘルパー関数
def create_orchestrator_node(orchestrator: OrchestratorAgent):
    """
    LangGraph Supervisor Node を作成するファクトリ関数

    Returns:
        Command を返すノード関数
    """

    async def orchestrator_node(state: dict) -> Command[RoutingTarget]:
        """Supervisor ノード: クエリを適切なエージェントにルーティング"""
        query = state.get("query", "")
        session_id = state.get("session_id", "")
        memory_context = state.get("context", {}).get("memory")

        decision = await orchestrator.decide_next_agent(
            query=query,
            session_id=session_id,
            memory_context=memory_context,
        )

        return Command(
            goto=decision.next_agent,
            update={
                "language": decision.language,
                "routing": {
                    "agent": decision.next_agent,
                    "category": decision.category,
                    "request_type": decision.request_type,
                    "confidence": decision.confidence,
                    "reasoning": decision.reasoning,
                    "debug_info": decision.debug_info,
                },
            },
        )

    return orchestrator_node
