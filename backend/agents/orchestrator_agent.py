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
import time
from dataclasses import dataclass, field, replace
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END

from backend.config.routing_constants import (
    AGENT_DESCRIPTIONS,
    MEMORY_EXCLUSION_BUSINESS,
    MEMORY_EXCLUSION_FACILITY,
    MEMORY_KEYWORDS,
    RoutingTarget,
    extract_request_type,
    match_keywords,
    normalize_agent_node,
)
from backend.llm.models import get_model_config
from backend.llm.provider import resolve_llm_provider
from backend.observability.structured_logger import log_agent_routing
from backend.utils.input_sanitizer import (
    MAX_CONTEXT_LENGTH,
    MAX_QUERY_LENGTH,
    sanitize_input,
)
from backend.utils.language_processor import LanguageProcessor, SupportedLanguage
from backend.utils.query_classifier import QueryClassifier
from backend.utils.intent_classifier import (
    classify_fast_intent,
    is_assistant_profile_question,
    is_current_info_request,
    is_daily_conversation_request,
)

logger = logging.getLogger(__name__)

_RECEPTION_MEMORY_FACT_MARKERS = (
    "希望席",
    "好きな席",
    "座席希望",
    "席の希望",
    "利用目的",
    "来館目的",
    "訪問目的",
)
_RECEPTION_MEMORY_RECALL_MARKERS = (
    "確認",
    "教えて",
    "覚えていますか",
    "覚えてますか",
    "覚えてる",
    "覚えている",
    "知っていますか",
    "知ってますか",
    "わかりますか",
    "分かりますか",
)
_RECEPTION_MEMORY_CONTEXT_MARKERS = (
    "私の",
    "わたしの",
    "僕の",
    "ぼくの",
    "俺の",
    "この会話",
    "先ほど",
    "さっき",
    "前に",
    "前回",
    "以前",
)


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
        self.provider = resolve_llm_provider(api_key=api_key)
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

        raw_next_agent = raw_decision.get("next_agent")
        if not isinstance(raw_next_agent, str):
            raise ValueError("next_agent must be a string")

        reasoning = str(raw_decision.get("reasoning", ""))[:200]
        category = str(raw_decision.get("category", "general"))[:50]
        request_type = raw_decision.get("request_type")
        if request_type is not None:
            request_type = str(request_type)[:50]

        next_agent, resolution_source = normalize_agent_node(
            raw_next_agent,
            category=category,
            request_type=request_type,
            prefer_category=True,
        )

        return {
            "next_agent": next_agent,
            "raw_next_agent": raw_next_agent,
            "agent_resolution_source": resolution_source,
            "reasoning": reasoning,
            "category": category,
            "request_type": request_type,
        }

    def _log_routing_decision(
        self,
        *,
        decision: OrchestratorDecision,
        session_id: str,
        started_at: float,
    ) -> None:
        """Emit Wave 3 agent routing telemetry without affecting routing."""
        try:
            log_agent_routing(
                routed_to=str(decision.next_agent),
                intent=decision.request_type or decision.category,
                confidence=decision.confidence,
                fallback_used=bool(decision.debug_info.get("fallback")),
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                session_id=session_id,
                language=str(decision.language),
                category=decision.category,
                request_type=decision.request_type,
                fast_path=bool(decision.debug_info.get("fast_path")),
                reasoning=decision.reasoning[:200],
            )
        except Exception as exc:
            logger.debug("Agent routing telemetry skipped: %s", exc)

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
        started_at = time.perf_counter()
        sanitized_query = sanitize_input(query, MAX_QUERY_LENGTH)

        language_result = self.language_processor.detect_language(sanitized_query)
        response_language = self.language_processor.determine_response_language(language_result)

        # 高速パス: メモリ関連の質問は即座にルーティング
        if self._is_memory_related_question(sanitized_query):
            decision = OrchestratorDecision(
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
            self._log_routing_decision(
                decision=decision,
                session_id=session_id,
                started_at=started_at,
            )
            return decision

        # 高速パス: 明確なキーワードマッチングでルーティング
        fast_route = self._try_fast_routing(sanitized_query)
        if fast_route:
            decision = OrchestratorDecision(
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
            self._log_routing_decision(
                decision=decision,
                session_id=session_id,
                started_at=started_at,
            )
            return decision

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

            routing_config = replace(
                get_model_config("router"),
                temperature=0.15,
                max_tokens=200,
            )

            response_content = await self.provider.generate(
                messages=lc_messages,
                config=routing_config,
            )

            parsed_decision = self._parse_llm_response(response_content)

            decision = OrchestratorDecision(
                next_agent=parsed_decision["next_agent"],
                language=response_language,
                category=parsed_decision["category"],
                request_type=parsed_decision["request_type"],
                confidence=0.8,
                reasoning=parsed_decision["reasoning"],
                debug_info=self._create_debug_info(
                    fast_path=False,
                    language_result=language_result,
                    llm_response_length=len(response_content),
                    raw_next_agent=parsed_decision["raw_next_agent"],
                    agent_resolution_source=parsed_decision["agent_resolution_source"],
                ),
            )
            self._log_routing_decision(
                decision=decision,
                session_id=session_id,
                started_at=started_at,
            )
            return decision

        except Exception as e:
            logger.warning("LLM routing failed: %s", e, exc_info=True)

            classification = await self.query_classifier.classify_with_details(sanitized_query)
            request_type = extract_request_type(sanitized_query)
            next_agent, resolution_source = normalize_agent_node(
                None,
                category=classification.category,
                request_type=request_type,
                prefer_category=True,
            )

            decision = OrchestratorDecision(
                next_agent=next_agent,
                language=response_language,
                category=classification.category,
                request_type=request_type,
                confidence=classification.confidence,
                reasoning="Fallback to QueryClassifier",
                debug_info=self._create_debug_info(
                    fast_path=False,
                    language_result=language_result,
                    fallback=True,
                    error_type=type(e).__name__,
                    agent_resolution_source=resolution_source,
                ),
            )
            self._log_routing_decision(
                decision=decision,
                session_id=session_id,
                started_at=started_at,
            )
            return decision

    def _create_debug_info(
        self,
        fast_path: bool,
        language_result=None,
        llm_response_length: Optional[int] = None,
        fallback: bool = False,
        error_type: Optional[str] = None,
        raw_next_agent: Optional[str] = None,
        agent_resolution_source: Optional[str] = None,
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

        if raw_next_agent:
            info["raw_next_agent"] = raw_next_agent

        if agent_resolution_source:
            info["agent_resolution_source"] = agent_resolution_source

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
        route = classify_fast_intent(query)
        return route.as_route() if route else None

    @staticmethod
    def _is_assistant_profile_question(lower_query: str) -> bool:
        """Detect questions about this kiosk assistant, not the visitor's name."""
        return is_assistant_profile_question(lower_query)

    @staticmethod
    def _is_daily_conversation_request(lower_query: str) -> bool:
        """Detect lightweight small-talk requests that should not invoke search."""
        return is_daily_conversation_request(lower_query)

    @staticmethod
    def _is_current_info_request(lower_query: str) -> bool:
        """Detect daily receptionist questions that need current external facts."""
        return is_current_info_request(lower_query)

    def _is_memory_related_question(self, query: str) -> bool:
        """メモリ関連の質問かどうかを判定"""
        lower_query = query.lower()

        if match_keywords(lower_query, MEMORY_EXCLUSION_BUSINESS):
            return False

        if match_keywords(lower_query, MEMORY_EXCLUSION_FACILITY):
            return False

        if self._is_reception_memory_confirmation_question(lower_query):
            return True

        return match_keywords(lower_query, MEMORY_KEYWORDS)

    @staticmethod
    def _is_reception_memory_confirmation_question(lower_query: str) -> bool:
        """Detect receptionist recall of practical visit facts without catching statements."""
        has_fact = any(marker in lower_query for marker in _RECEPTION_MEMORY_FACT_MARKERS)
        if not has_fact:
            return False

        has_recall_action = any(
            marker in lower_query for marker in _RECEPTION_MEMORY_RECALL_MARKERS
        )
        if not has_recall_action:
            return False

        return any(marker in lower_query for marker in _RECEPTION_MEMORY_CONTEXT_MARKERS)

    async def close(self):
        """リソースのクリーンアップ"""
        await self.provider.close()
