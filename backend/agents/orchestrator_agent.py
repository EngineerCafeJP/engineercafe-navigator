"""
OrchestratorAgent - Supervisor Pattern による Multi-Agent オーケストレーション

LangGraph の Supervisor Agent パターンに従い、クエリを適切なエージェントに
ルーティングし、エージェント間の制御フローを管理する。

参考: langgraph-reference/docs/docs/concepts/multi_agent.md

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
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command

from backend.llm.models import ModelConfig, SupportedModel, get_model_config
from backend.llm.openrouter import OpenRouterProvider
from backend.utils.language_processor import LanguageProcessor, SupportedLanguage
from backend.utils.query_classifier import QueryClassifier

logger = logging.getLogger(__name__)

# エージェントノード名の型定義
AgentNodeName = Literal[
    "business_info",
    "facility",
    "event",
    "memory_agent",
    "general_knowledge",
    "clarification",
    "slide",
]

# 終了を含む完全なルーティングターゲット
RoutingTarget = Literal[
    "business_info",
    "facility",
    "event",
    "memory_agent",
    "general_knowledge",
    "clarification",
    "slide",
    "__end__",
]


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

    # キーワード定数（テストと拡張のため）
    WIFI_KEYWORDS = ["wi-fi", "wifi", "ワイファイ", "インターネット"]
    BUSINESS_HOURS_KEYWORDS = ["営業時間", "何時まで", "何時から", "開いて", "閉まる"]
    PRICING_KEYWORDS = ["料金", "いくら", "値段", "価格", "cost", "price"]
    BASEMENT_KEYWORDS = ["地下", "basement", "b1", "mtgスペース", "集中スペース"]
    EVENT_KEYWORDS = ["イベント", "勉強会", "セミナー", "ミートアップ"]
    SLIDE_KEYWORDS = ["スライド", "プレゼン", "次のスライド", "前のスライド"]

    BUSINESS_EXCLUSION_KEYWORDS = [
        "メニュー", "料金", "営業時間", "場所", "設備", "saino", "エンジニアカフェ"
    ]
    FACILITY_EXCLUSION_KEYWORDS = ["地下", "スペース", "会議室", "施設"]
    MEMORY_KEYWORDS = [
        "さっき", "前に", "覚えて", "記憶", "聞いた", "話した",
        "何を", "言った", "会話", "履歴", "先ほど",
        "remember", "earlier", "previous", "asked", "said",
    ]

    # エージェントの説明（LLMがルーティング決定に使用）
    AGENT_DESCRIPTIONS = {
        "business_info": "営業情報エージェント: 営業時間、料金、場所、アクセス方法など施設の基本情報を回答",
        "facility": "施設エージェント: Wi-Fi、電源、会議室、地下スペースなど設備に関する情報を回答",
        "event": "イベントエージェント: イベント情報、勉強会、セミナーなどの予定を回答",
        "memory_agent": "メモリエージェント: 過去の会話履歴に関する質問に回答（「さっき何を聞いた？」など）",
        "general_knowledge": "一般知識エージェント: 上記以外の一般的な質問に回答",
        "clarification": "明確化エージェント: 曖昧な質問に対して詳細を確認",
        "slide": "スライドエージェント: スライドのナレーション、操作、質問応答を処理",
    }

    # ルーティング用システムプロンプト
    ROUTING_SYSTEM_PROMPT = """あなたはエンジニアカフェの受付AIアシスタントのオーケストレーターです。
ユーザーの質問を分析し、最適な専門エージェントを選択してください。

利用可能なエージェント:
{agent_descriptions}

ルーティングルール:
1. 営業時間、料金、場所に関する質問 → business_info
2. Wi-Fi、電源、設備、地下スペースに関する質問 → facility
3. イベント、勉強会、セミナーに関する質問 → event
4. 過去の会話や「さっき」「前に」などメモリ関連の質問 → memory_agent
5. スライド操作やプレゼン関連の質問 → slide
6. 曖昧で詳細確認が必要な質問 → clarification
7. その他の一般的な質問 → general_knowledge

次のJSON形式で回答してください:
{{
    "next_agent": "エージェント名",
    "reasoning": "選択理由（簡潔に）",
    "category": "質問カテゴリ",
    "request_type": "具体的なリクエストタイプ（wifi, hours, price等）またはnull"
}}"""

    # 入力サニタイズ設定
    MAX_QUERY_LENGTH = 1000
    MAX_CONTEXT_LENGTH = 500

    # プロンプトインジェクション検出パターン
    DANGEROUS_PATTERNS = [
        r"(?i)(ignore|forget|disregard)\s*(the\s*)?(above|previous|instructions)",
        r"(?i)system\s*prompt",
        r"(?i)new\s*instructions?",
        r"(?i)you\s*are\s*now",
        r"(?i)act\s*as\s*if",
    ]

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

    def _sanitize_input(self, text: str, max_length: int) -> str:
        """
        ユーザー入力をサニタイズ

        Args:
            text: サニタイズする文字列
            max_length: 最大長

        Returns:
            サニタイズされた文字列
        """
        if not text:
            return ""

        # 制御文字の除去
        sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

        # 長さ制限
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        # プロンプトインジェクションパターンの検出とフィルタリング
        for pattern in self.DANGEROUS_PATTERNS:
            sanitized = re.sub(pattern, "[FILTERED]", sanitized)

        return sanitized

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
        # JSON部分を抽出
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

        # 型検証
        if not isinstance(raw_decision, dict):
            raise ValueError("Response must be a JSON object")

        # 必須フィールドの検証
        next_agent = raw_decision.get("next_agent")
        if not isinstance(next_agent, str):
            raise ValueError("next_agent must be a string")

        # ホワイトリスト検証
        if next_agent not in self.AGENT_DESCRIPTIONS:
            next_agent = "general_knowledge"

        # 長さ制限を適用
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
        # 入力サニタイズ
        sanitized_query = self._sanitize_input(query, self.MAX_QUERY_LENGTH)

        # 言語検出
        language_result = self.language_processor.detect_language(sanitized_query)
        response_language = self.language_processor.determine_response_language(language_result)

        # 高速パス: メモリ関連の質問は即座にルーティング
        if self._is_memory_related_question(sanitized_query):
            return OrchestratorDecision(
                next_agent="memory_agent",
                language=response_language,
                category="memory",
                request_type=None,
                confidence=1.0,
                reasoning="Memory-related question detected",
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
            f"- {name}: {desc}" for name, desc in self.AGENT_DESCRIPTIONS.items()
        )

        system_prompt = self.ROUTING_SYSTEM_PROMPT.format(
            agent_descriptions=agent_descriptions
        )

        user_message = f"ユーザーの質問: {sanitized_query}"
        if memory_context:
            sanitized_context = self._sanitize_input(
                str(memory_context.get("summary", "")),
                self.MAX_CONTEXT_LENGTH,
            )
            user_message += f"\n\n会話コンテキスト: {sanitized_context}"

        try:
            lc_messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]

            # ModelConfigを作成してgenerateを呼び出し
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

            # レスポンスを安全にパース
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
            logger.warning(f"LLM routing failed: {e}")

            # フォールバック: QueryClassifierを使用
            classification = await self.query_classifier.classify_with_details(sanitized_query)
            next_agent = self._map_category_to_agent(classification.category)

            return OrchestratorDecision(
                next_agent=next_agent,
                language=response_language,
                category=classification.category,
                request_type=self._extract_request_type(sanitized_query),
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
        """
        エージェント処理後に続行か終了かを決定

        Args:
            agent_response: エージェントの応答
            original_query: 元のクエリ

        Returns:
            "orchestrator": 再ルーティングが必要
            END: 処理完了
        """
        # 明確化が必要な場合は続行（ユーザー入力待ち）
        if agent_response.get("metadata", {}).get("requires_followup"):
            return END  # ユーザー入力を待つ

        # 通常は終了
        return END

    def _try_fast_routing(self, query: str) -> Optional[dict]:
        """キーワードベースの高速ルーティング"""
        lower_query = query.lower()

        # Wi-Fi関連
        if any(kw in lower_query for kw in self.WIFI_KEYWORDS):
            return {
                "agent": "facility",
                "category": "facility-info",
                "request_type": "wifi",
                "reasoning": "Wi-Fi keyword detected",
            }

        # 営業時間関連
        if any(kw in lower_query for kw in self.BUSINESS_HOURS_KEYWORDS):
            return {
                "agent": "business_info",
                "category": "business-hours",
                "request_type": "hours",
                "reasoning": "Business hours keyword detected",
            }

        # 料金関連
        if any(kw in lower_query for kw in self.PRICING_KEYWORDS):
            return {
                "agent": "business_info",
                "category": "pricing",
                "request_type": "price",
                "reasoning": "Pricing keyword detected",
            }

        # 地下施設関連
        if any(kw in lower_query for kw in self.BASEMENT_KEYWORDS):
            return {
                "agent": "facility",
                "category": "basement-facility",
                "request_type": "basement",
                "reasoning": "Basement facility keyword detected",
            }

        # イベント関連
        if any(kw in lower_query for kw in self.EVENT_KEYWORDS):
            return {
                "agent": "event",
                "category": "events",
                "request_type": "event",
                "reasoning": "Event keyword detected",
            }

        # スライド関連
        if any(kw in lower_query for kw in self.SLIDE_KEYWORDS):
            return {
                "agent": "slide",
                "category": "slide",
                "request_type": "slide",
                "reasoning": "Slide keyword detected",
            }

        # 明確化が必要なパターン
        if any(kw in lower_query for kw in ["カフェ", "cafe"]) and "どっち" in lower_query:
            return {
                "agent": "clarification",
                "category": "cafe-clarification-needed",
                "request_type": None,
                "reasoning": "Cafe clarification needed",
            }

        return None

    def _is_memory_related_question(self, query: str) -> bool:
        """メモリ関連の質問かどうかを判定"""
        lower_query = query.lower()

        # ビジネス関連のキーワードは除外
        if any(kw in lower_query for kw in self.BUSINESS_EXCLUSION_KEYWORDS):
            return False

        # 施設関連のキーワードは除外
        if any(kw in lower_query for kw in self.FACILITY_EXCLUSION_KEYWORDS):
            return False

        # メモリ関連のキーワード
        return any(kw in lower_query for kw in self.MEMORY_KEYWORDS)

    def _map_category_to_agent(self, category: str) -> AgentNodeName:
        """カテゴリをエージェントノード名にマッピング"""
        mapping = {
            "facility-info": "facility",
            "saino-cafe": "business_info",
            "calendar": "event",
            "events": "event",
            "current-time": "general_knowledge",
            "general": "general_knowledge",
            "memory": "memory_agent",
            "cafe-clarification-needed": "clarification",
            "meeting-room-clarification-needed": "clarification",
        }
        return mapping.get(category, "general_knowledge")

    def _extract_request_type(self, query: str) -> Optional[str]:
        """クエリから具体的なリクエストタイプを抽出"""
        lower_query = query.lower()

        if any(kw in lower_query for kw in ["wi-fi", "wifi", "インターネット"]):
            return "wifi"
        if any(kw in lower_query for kw in ["営業時間", "何時まで", "何時から"]):
            return "hours"
        if any(kw in lower_query for kw in ["料金", "いくら", "値段"]):
            return "price"
        if any(kw in lower_query for kw in ["場所", "どこ", "アクセス", "住所"]):
            return "location"
        if any(kw in lower_query for kw in ["設備", "電源", "プリンター"]):
            return "facility"
        if any(kw in lower_query for kw in ["地下", "basement"]):
            return "basement"
        if any(kw in lower_query for kw in ["イベント", "勉強会"]):
            return "event"
        if any(kw in lower_query for kw in ["スライド", "プレゼン"]):
            return "slide"

        return None

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
