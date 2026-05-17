"""
GeneralKnowledgeAgent完全実装

一般的な質問に対応するエージェント。
Engineer Cafeに関する一般情報、AI・技術トピック、福岡のテックシーンなどに回答。
メモリ関連クエリも統合して処理する。

参考:
- docs/migration/agents/general-knowledge-agent/README.md
- docs/migration/agents/general-knowledge-agent/MIGRATION-GUIDE.md

実装済み機能:
1. Web検索機能の実装(tavily_search.py統合) ✓
2. OpenRouter APIを使用した回答生成 ✓
3. ナレッジベースとWeb検索の組み合わせ ✓
4. should_use_web_search()ロジック実装 ✓
5. 信頼度計算の最適化 ✓
6. 感情タグの適切な設定 ✓
7. エラーハンドリングとフォールバック ✓
8. メモリクエリハンドリング統合 ✓
"""

import logging
from typing import Dict, Any, List, Optional, Literal

from backend.config.prompts.memory_prompts import build_memory_prompt
from backend.agents.llm_metadata import merge_llm_metadata
from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import get_model_config
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.tools.tavily_search import TavilySearchTool
from backend.utils.language_types import (
    DEFAULT_ERROR_RESPONSE,
    LANGUAGE_INSTRUCTION,
    SupportedLanguage,
)
from backend.utils.memory_interface import MemorySystemInterface

logger = logging.getLogger(__name__)

EmotionType = Literal["helpful", "apologetic", "neutral", "happy", "sad", "relaxed", "surprised"]


class GeneralKnowledgeAgent:
    """
    GeneralKnowledgeAgent完全実装

    一般的な質問に対応し、ナレッジベースとWeb検索を組み合わせて回答を生成します。
    Engineer Cafeに関する一般情報、AI・技術トピック、福岡のテックシーンなどに対応。
    メモリ関連クエリ（会話履歴の参照）も統合して処理します。
    """

    def __init__(self, memory_system: Optional[MemorySystemInterface] = None):
        """
        初期化

        Args:
            memory_system: メモリシステムのインスタンス（オプショナル）
        """
        self.name = "GeneralKnowledgeAgent"
        logger.info("GeneralKnowledgeAgent初期化")

        self.provider = OpenRouterProvider()
        self.model_config = get_model_config("general_knowledge")
        self.web_search = TavilySearchTool()
        self.rag_search = EnhancedRAGSearch()
        self.memory_system = memory_system

        memory_status = "enabled" if memory_system else "disabled"
        logger.info(
            "GeneralKnowledgeAgent initialized with model: %s, memory: %s",
            self.model_config.model_id,
            memory_status,
        )

    async def answer_query(
        self,
        query: str,
        language: SupportedLanguage = "ja",
        session_id: Optional[str] = None,
        query_type: str = "general",
        state_context: Optional[Dict] = None,
        context_signals=None,
        long_term_memory: Optional[list] = None,
    ) -> Dict[str, Any]:
        """統合クエリハンドラ: query_typeに応じて処理を分岐"""
        if query_type == "memory":
            return await self._handle_memory_query(
                query,
                session_id or "",
                language,
                long_term_memory=long_term_memory,
            )
        if query_type == "assistant_profile":
            return self._assistant_profile_response(language)
        if query_type == "daily_conversation":
            return self._daily_conversation_response(query, language)
        if query_type == "current_info":
            return await self.answer_general_query(
                query,
                language,
                session_id,
                state_context,
                context_signals,
                long_term_memory=long_term_memory,
                query_type="current_info",
            )
        return await self.answer_general_query(
            query,
            language,
            session_id,
            state_context,
            context_signals,
            long_term_memory=long_term_memory,
            query_type=query_type,
        )

    async def answer_general_query(
        self,
        query: str,
        language: SupportedLanguage = "ja",
        session_id: Optional[str] = None,
        state_context: Optional[Dict] = None,
        context_signals=None,
        long_term_memory: Optional[list] = None,
        query_type: str = "general",
    ) -> Dict[str, Any]:
        """
        一般的な質問に回答

        Args:
            query: ユーザーからの質問
            language: 言語設定("ja" or "en")
            session_id: セッションID(オプショナル)
            state_context: RAGキャッシュからのコンテキスト（オプショナル）

        Returns:
            {"answer": str, "emotion": str, "metadata": Dict}
        """
        logger.info("一般質問処理開始: query=%s..., language=%s", query[:50], language)

        try:
            mode = self._resolve_general_mode(query, query_type)
            if mode == "assistant_profile":
                return self._assistant_profile_response(language)
            if mode == "daily_conversation":
                return self._daily_conversation_response(query, language)

            # 1. current-info のみ Web 検索を許可する。
            needs_web_search = mode == "current_info"
            logger.info("Web検索必要性判定: %s", needs_web_search)

            # 2. ナレッジベース検索（キャッシュチェック付き）
            context = ""
            sources: List[str] = []
            rag_category = self._rag_category_for_query_type(query_type)

            cached = state_context if state_context else None
            if cached and cached.get("success") and cached.get("category") == rag_category:
                context = cached.get("context_string", "")
                sources.append("knowledge_base_cached")
                logger.info("Using cached RAG results: %d chars", len(context))
            else:
                kb_result = await self.rag_search.search(
                    query=query,
                    category=rag_category,
                    language=language,
                    max_results=5,
                    context_signals=context_signals,
                )

                if kb_result.get("success") and kb_result.get("data"):
                    context = kb_result["data"].get("context", "")
                    sources.append("knowledge_base")
                    logger.info("ナレッジベース検索成功: %d chars", len(context))

            # 3. Web検索(条件付き)
            if needs_web_search:
                logger.info("Web検索を実行します")
                web_result = await self.web_search.search(
                    query=self._normalize_current_info_query(query),
                    language=language,
                )

                if web_result.get("success"):
                    web_text = web_result.get("text", "")
                    web_sources = web_result.get("sources", [])

                    if web_text:
                        if context:
                            context += f"\n\n【Web検索結果】\n{web_text}"
                        else:
                            context = web_text

                        sources.append("web_search")
                        logger.info(
                            "Web検索成功: %d chars, %d sources", len(web_text), len(web_sources)
                        )

            long_term_text = self._format_long_term_memory_context(long_term_memory, language)
            if long_term_text:
                context = f"{context}\n\n{long_term_text}".strip()
                sources.append("long_term_memory")

            # 4. current-info で外部情報が取れない場合だけ、古い情報で断言しない。
            if mode == "current_info" and "web_search" not in sources:
                return self._current_info_unavailable_response(language)

            # 5. プロンプト構築
            prompt = self._build_general_prompt(query, context, sources, language, mode=mode)

            # 6. LLM生成
            from langchain_core.messages import HumanMessage

            messages = [HumanMessage(content=prompt)]
            model_config = (
                get_model_config("deep_reasoning")
                if mode == "deep_reasoning"
                else self.model_config
            )
            response_text = await self.provider.generate(messages=messages, config=model_config)

            # 7. 感情・信頼度抽出
            emotion = self._extract_emotion(response_text)
            confidence = self._calculate_confidence(sources)

            logger.info("回答生成完了: emotion=%s, confidence=%s", emotion, confidence)

            metadata = merge_llm_metadata(
                {
                    "agent": self.name,
                    "status": "success",
                    "confidence": confidence,
                    "category": "general_knowledge",
                    "request_type": mode,
                    "route": "general_knowledge",
                    "query_type": mode,
                    "model_use_case": (
                        "deep_reasoning" if mode == "deep_reasoning" else "general_knowledge"
                    ),
                    "sources": sources,
                    "web_search_used": "web_search" in sources,
                    "rag_used": any(source.startswith("knowledge_base") for source in sources),
                },
                response_text,
            )

            return {
                "answer": str(response_text),
                "emotion": emotion,
                "metadata": metadata,
            }

        except Exception as e:
            logger.exception("GeneralKnowledgeAgent処理エラー: %s", e)
            return self._handle_error(language)

    @staticmethod
    def _rag_category_for_query_type(query_type: str) -> str:
        """Keep general-knowledge routes on specific local KB slices when known."""
        category_by_query_type = {
            "consultation": "consultation",
            "community": "community",
        }
        return category_by_query_type.get(query_type, "general")

    # =========================================================================
    # メモリクエリ処理
    # =========================================================================

    async def _handle_memory_query(
        self,
        query: str,
        session_id: str,
        language: str = "ja",
        long_term_memory: Optional[list] = None,
    ) -> Dict[str, Any]:
        """メモリ関連クエリを処理"""
        if not self.memory_system:
            return self._handle_no_memory_system(language)

        try:
            query_type = self._detect_memory_query_type(query)
            context = await self.memory_system.get_context(
                query, session_id, {"language": language, "inherit_context": True}
            )
            context = self._merge_long_term_memory_context(
                context,
                long_term_memory,
                language,
            )

            if not context.get("recent_messages") and not context.get("long_term_memory"):
                if self._is_memory_write_query(query):
                    return self._memory_write_ack_response(language)
                return self._no_history_response(language)

            prompt = self._build_memory_prompt(query, context, query_type, language)

            from langchain_core.messages import HumanMessage

            messages = [HumanMessage(content=prompt)]
            answer = await self.provider.generate(messages=messages, config=self.model_config)

            emotion = self._determine_memory_emotion(context, query_type)

            metadata = merge_llm_metadata(
                {
                    "agent": self.name,
                    "status": "success",
                    "category": "general_knowledge",
                    "request_type": query_type,
                    "route": "general_knowledge",
                    "query_type": query_type,
                    "message_count": len(context.get("recent_messages", [])),
                    "inherited_request_type": context.get("inherited_request_type"),
                    "long_term_memory_count": len(context.get("long_term_memory", [])),
                },
                answer,
            )

            return {
                "answer": str(answer),
                "emotion": emotion,
                "metadata": metadata,
            }
        except Exception as e:
            logger.exception("Memory query error: %s", e)
            return {
                "answer": (
                    "メモリの処理中にエラーが発生しました。"
                    if language == "ja"
                    else "An error occurred while processing memory."
                ),
                "emotion": "surprised",
                "metadata": {"agent": self.name, "status": "error", "error": str(e)},
            }

    def _detect_memory_query_type(self, query: str) -> str:
        """メモリ質問タイプの判定"""
        lower_query = query.lower()

        question_keywords = [
            "何を聞いた",
            "何聞いた",
            "質問した",
            "さっき聞いた",
            "前に聞いた",
            "what did i ask",
            "what i asked",
            "my question",
            "previous question",
        ]
        if any(kw in lower_query for kw in question_keywords):
            return "question_history"

        answer_keywords = [
            "答え",
            "回答",
            "何て言った",
            "何と言った",
            "教えてくれた",
            "answer",
            "response",
            "what did you say",
            "you told me",
            "your answer",
        ]
        if any(kw in lower_query for kw in answer_keywords):
            return "answer_history"

        other_keywords = [
            "もう一つの方",
            "もう一つ",
            "もうひとつ",
            "他の方",
            "別の方",
            "the other one",
            "the other",
            "another one",
            "alternative",
        ]
        if any(kw in lower_query for kw in other_keywords):
            return "other_option"

        return "general_memory"

    @staticmethod
    def _is_memory_write_query(query: str) -> bool:
        """初回の記憶登録依頼を、履歴参照質問と区別する。"""
        lower_query = query.lower()
        remember_keywords = [
            "覚えて",
            "憶えて",
            "覚えといて",
            "覚えておいて",
            "記憶して",
            "忘れないで",
            "remember",
            "memorize",
            "keep in mind",
        ]
        self_disclosure_keywords = [
            "私の名前",
            "僕の名前",
            "俺の名前",
            "名前は",
            "わたしは",
            "私は",
            "ぼくは",
            "僕は",
            "my name is",
            "i am ",
            "i'm ",
            "call me",
        ]
        if any(kw in lower_query for kw in remember_keywords):
            try:
                from backend.utils.memory_extractor import _extract_remember_request

                if _extract_remember_request(query, "ja") or _extract_remember_request(
                    query,
                    "en",
                ):
                    return True
            except Exception:
                pass

        return any(kw in lower_query for kw in remember_keywords) and any(
            kw in lower_query for kw in self_disclosure_keywords
        )

    def _build_memory_prompt(
        self, query: str, context: Dict, query_type: str, language: str
    ) -> str:
        """メモリプロンプト構築（memory_prompts.pyに委譲）"""
        return build_memory_prompt(query, context, query_type, language)

    def _merge_long_term_memory_context(
        self,
        context: Dict[str, Any],
        long_term_memory: Optional[list],
        language: str,
    ) -> Dict[str, Any]:
        """セッション履歴コンテキストへ長期メモリを追記する。"""
        if not long_term_memory:
            return context

        merged = dict(context or {})
        long_term_text = self._format_long_term_memory_context(long_term_memory, language)
        if not long_term_text:
            return merged

        existing_context = str(merged.get("context_string") or "").strip()
        merged["context_string"] = f"{existing_context}\n\n{long_term_text}".strip()
        merged["long_term_memory"] = long_term_memory
        return merged

    @staticmethod
    def _format_long_term_memory_context(
        long_term_memory: Optional[list],
        language: str,
    ) -> str:
        """長期メモリをプロンプトへ渡せる短い箇条書きに整形する。"""
        if not long_term_memory:
            return ""

        lines: list[str] = []
        for memory in long_term_memory:
            if isinstance(memory, dict):
                content = str(
                    memory.get("data")
                    or memory.get("content")
                    or memory.get("summary")
                    or memory.get("text")
                    or ""
                ).strip()
                memory_type = str(memory.get("type") or memory.get("candidate_type") or "").strip()
                if content and memory_type:
                    lines.append(f"- [{memory_type}] {content}")
                elif content:
                    lines.append(f"- {content}")
            else:
                content = str(memory).strip()
                if content:
                    lines.append(f"- {content}")

        if not lines:
            return ""

        title = (
            "長期メモリ（過去セッションから保持された利用者情報）"
            if language == "ja"
            else ("Long-term memory (visitor facts retained across sessions)")
        )
        return f"{title}:\n" + "\n".join(lines)

    def _determine_memory_emotion(self, context: Dict, query_type: str) -> str:
        """メモリクエリの感情タグ決定"""
        if not context.get("recent_messages"):
            return "sad"
        if query_type == "other_option":
            return "happy"
        if query_type in ["question_history", "answer_history"]:
            return "relaxed"
        return "neutral"

    def _handle_no_memory_system(self, language: str) -> Dict[str, Any]:
        """メモリシステム利用不可時の応答"""
        message = (
            "メモリシステムが利用できません。しばらくしてからもう一度お試しください。"
            if language == "ja"
            else "Memory system is not available at the moment. Please try again later."
        )
        return {
            "answer": message,
            "emotion": "sad",
            "metadata": {
                "agent": self.name,
                "status": "memory_unavailable",
                "error": "no_memory_system",
            },
        }

    def _no_history_response(self, language: str) -> Dict[str, Any]:
        """会話履歴なし時の応答"""
        message = (
            "まだ会話履歴がありません。何か質問してみてください！"
            if language == "ja"
            else "I don't have any conversation history yet. Let's start chatting!"
        )
        return {
            "answer": message,
            "emotion": "sad",
            "metadata": {"agent": self.name, "status": "no_history", "query_type": "memory"},
        }

    def _memory_write_ack_response(self, language: str) -> Dict[str, Any]:
        """初回の記憶登録依頼に対する応答。"""
        message = (
            "承知しました。今後の会話で参照できるように覚えておきます。"
            if language == "ja"
            else "Got it. I'll remember that so I can refer to it in future conversations."
        )
        return {
            "answer": message,
            "emotion": "helpful",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "query_type": "memory_write",
            },
        }

    # =========================================================================
    # 一般クエリ ヘルパーメソッド
    # =========================================================================

    def _should_use_web_search_adaptive(self, query: str, context_signals=None) -> bool:
        """適応的Web検索判定

        context_signals が None の場合は静的判定にフォールバック。
        RAGキャッシュスコア高い + 具体性高い → Web検索不要
        RAGキャッシュスコア低い + 会話浅い → Web検索推奨
        """
        # Alpha strict mode: context quality alone must not enable web search.
        # Only explicit current-info markers may do so.
        return self._should_use_web_search(query)

    def _should_use_web_search(self, query: str) -> bool:
        """Web検索が必要かどうか判定"""
        return TavilySearchTool.should_use_web_search(query)

    def _resolve_general_mode(self, query: str, query_type: str) -> str:
        if query_type in {
            "assistant_profile",
            "daily_conversation",
            "general_light",
            "current_info",
            "deep_reasoning",
        }:
            return query_type
        lower_query = query.lower()
        if self._is_deep_reasoning_query(lower_query):
            return "deep_reasoning"
        if self._is_current_info_query(lower_query):
            return "current_info"
        if self._is_daily_conversation_query(lower_query):
            return "daily_conversation"
        return "general_light"

    @staticmethod
    def _is_current_info_query(lower_query: str) -> bool:
        markers = (
            "今日",
            "明日",
            "今朝",
            "今夜",
            "今週",
            "最新",
            "現在",
            "ニュース",
            "天気",
            "気温",
            "雨",
            "today",
            "tomorrow",
            "this week",
            "latest",
            "current",
            "news",
            "weather",
            "temperature",
            "rain",
        )
        return any(marker in lower_query for marker in markers)

    @staticmethod
    def _is_deep_reasoning_query(lower_query: str) -> bool:
        markers = (
            "弁証法",
            "複雑推論",
            "比較分析",
            "多面的に分析",
            "深く考察",
            "詳細に考察",
            "dialectical",
            "complex reasoning",
            "comparative analysis",
            "analyze in depth",
            "deep reasoning",
        )
        return any(marker in lower_query for marker in markers)

    @staticmethod
    def _is_daily_conversation_query(lower_query: str) -> bool:
        markers = (
            "雑談",
            "おしゃべり",
            "少し話",
            "ちょっと話",
            "話し相手",
            "元気",
            "疲れた",
            "ひま",
            "暇",
            "ありがとう",
            "サンキュー",
            "small talk",
            "chat with me",
            "talk with me",
            "talk to me",
            "how are you",
            "i am tired",
            "i'm tired",
            "thanks",
            "thank you",
        )
        return any(marker in lower_query for marker in markers)

    @staticmethod
    def _normalize_current_info_query(query: str) -> str:
        lower_query = query.lower()
        asks_weather = any(
            marker in lower_query for marker in ("天気", "気温", "雨", "weather", "temperature")
        )
        has_location = any(
            marker in lower_query for marker in ("福岡", "fukuoka", "天神", "tenjin")
        )
        if asks_weather and not has_location:
            return f"福岡市 天神 {query}"
        return query

    # Hardcoded multilingual self-introduction. Must NEVER reference any LLM
    # provider (Google/OpenAI/etc). See issue #615 — web_search previously
    # leaked "I am trained by Google..." into identity replies.
    _ASSISTANT_PROFILE_MESSAGES: Dict[str, str] = {
        "ja": (
            "私はエンナビです。福岡市のエンジニアカフェの受付キオスクとして、"
            "施設利用、イベント、会員証、Wi-Fi、スライド案内に加えて、"
            "受付でよくある日常的な質問にもお答えします。"
            "「Wi-Fiを教えて」「イベントに参加したい」「施設を使いたい」のように聞いてください。"
        ),
        "en": (
            "I am EnNavi, the reception kiosk for Engineer Cafe in "
            "Fukuoka. I can help with facilities, events, membership check-in, Wi-Fi, "
            "slide guidance, and everyday questions visitors commonly ask at reception."
        ),
        "ko": (
            "저는 엔나비입니다. 후쿠오카의 엔지니어 카페 안내 키오스크로서, "
            "시설 이용, 이벤트, 회원증, Wi-Fi, 슬라이드 안내와 함께 접수처에서 자주 받는 "
            "일상적인 질문에도 답해 드립니다."
        ),
        "zh": (
            "我是 EnNavi，福冈工程师咖啡馆的前台导览终端。我可以为您介绍"
            "设施使用、活动信息、会员证、Wi-Fi、幻灯片导览，以及前台常见的日常问题。"
        ),
    }

    @classmethod
    def assistant_profile_message(cls, language: str) -> str:
        """Return the deterministic assistant self-introduction without constructing an agent."""
        return cls._ASSISTANT_PROFILE_MESSAGES.get(language, cls._ASSISTANT_PROFILE_MESSAGES["ja"])

    def _assistant_profile_response(self, language: SupportedLanguage) -> Dict[str, Any]:
        """Return the hardcoded self-introduction; never calls any LLM/web_search.

        Args:
            language: Visitor language (ja/en/ko/zh). Falls back to ja when unknown.

        Returns:
            Response dict with metadata.web_search_used=False and provider_called=False.
        """
        message = self.assistant_profile_message(language)
        logger.info(
            "Identity fast-path response served (language=%s, no LLM, no web_search)",
            language,
        )
        return {
            "answer": message,
            "emotion": "helpful",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "category": "general_knowledge",
                "request_type": "assistant_profile",
                "route": "general_knowledge",
                "query_type": "assistant_profile",
                "sources": [],
                "web_search_used": False,
                "rag_used": False,
                "provider_called": False,
            },
        }

    def _daily_conversation_response(
        self, query: str, language: SupportedLanguage
    ) -> Dict[str, Any]:
        lower_query = query.lower()
        if any(
            marker in lower_query for marker in ("ありがとう", "サンキュー", "thanks", "thank you")
        ):
            message = (
                "どういたしまして。ほかにも気になることがあれば、気軽に聞いてください。"
                if language == "ja"
                else "You're welcome. Feel free to ask me anything else."
            )
        elif any(marker in lower_query for marker in ("疲れた", "i am tired", "i'm tired")):
            message = (
                "少し休憩しましょう。エンジニアカフェでは、落ち着いて作業したり一息ついたりできます。"
                if language == "ja"
                else "Take a short break. Engineer Cafe is a good place to settle in and recharge."
            )
        elif any(marker in lower_query for marker in ("元気", "how are you")):
            message = (
                "元気です。今日は受付として、施設案内でも雑談でもすぐお手伝いできます。"
                if language == "ja"
                else "I'm doing well. I can help with reception guidance or a quick casual chat."
            )
        else:
            message = (
                "もちろんです。短くお話ししましょう。施設のことでも、今日の過ごし方でも気軽に聞いてください。"
                if language == "ja"
                else (
                    "Of course. We can keep it light. Ask me about the facility "
                    "or anything practical for your visit."
                )
            )
        return {
            "answer": message,
            "emotion": "relaxed",
            "metadata": {
                "agent": self.name,
                "status": "success",
                "category": "general_knowledge",
                "request_type": "daily_conversation",
                "route": "general_knowledge",
                "query_type": "daily_conversation",
                "sources": [],
                "web_search_used": False,
                "rag_used": False,
                "provider_called": False,
            },
        }

    def _current_info_unavailable_response(self, language: SupportedLanguage) -> Dict[str, Any]:
        message = (
            "最新情報を確認できませんでした。少し時間をおいてもう一度聞いてください。"
            if language == "ja"
            else (
                "I couldn't confirm the latest information right now. "
                "Please ask again in a moment."
            )
        )
        return {
            "answer": message,
            "emotion": "apologetic",
            "metadata": {
                "agent": self.name,
                "status": "current_info_unavailable",
                "category": "general_knowledge",
                "request_type": "current_info",
                "route": "general_knowledge",
                "query_type": "current_info",
                "sources": [],
                "web_search_used": False,
                "rag_used": False,
            },
        }

    def _build_general_prompt(
        self,
        query: str,
        context: str,
        sources: List[str],
        language: SupportedLanguage,
        *,
        mode: str = "general_light",
    ) -> str:
        """プロンプトを構築"""
        source_info = " and ".join(sources) if sources else "available information"
        if not context:
            context = (
                "No trusted local or current external context was found. "
                "Answer from stable general knowledge only. Do not claim to have searched."
            )

        oral_instruction_ja = (
            "回答は口語（話し言葉）で返してください。"
            "Markdownの見出し・箇条書き・太字・表などは使わないでください。"
            "音声で読み上げた時に自然に聞こえるような文章にしてください。"
        )
        oral_instruction_en = (
            "Respond in natural spoken language. "
            "Do NOT use Markdown formatting such as "
            "headers, bullet points, bold, or tables. "
            "Write as if speaking aloud to someone."
        )

        # Multilingual: append language instruction for zh/ko
        lang_suffix = LANGUAGE_INSTRUCTION.get(language, "")
        scope_instruction_ja = (
            "あなた自身の正体を聞かれていない限り、モデル名や提供会社名を自分の正体として述べないでください。"
            "回答は受付での会話として短く自然にしてください。"
        )
        scope_instruction_en = (
            "Do not describe your model provider as your identity unless explicitly asked. "
            "Keep the answer short and natural for a reception conversation."
        )
        if mode == "current_info":
            scope_instruction_ja += (
                " 最新情報として扱う場合は、確認できた範囲で断定しすぎず答えてください。"
            )
            scope_instruction_en += (
                " For current information, answer only within what the provided context supports."
            )
        else:
            scope_instruction_ja += " 最新情報や検索結果を確認したとは言わないでください。"
            scope_instruction_en += " Do not say you checked current information or search results."

        if language == "en":
            header = (
                "Answer the following question using"
                f" the provided information from {source_info}."
            )
            prompt = f"""{header}

IMPORTANT: Start your response with an emotion tag.
Available emotions: [happy], [sad], [relaxed], [surprised], [helpful], [apologetic]

Use [relaxed] for informational responses about general topics
Use [happy] when sharing exciting tech news or positive information
Use [surprised] for unexpected or innovative topics
Use [helpful] for answering practical questions
Use [apologetic] when unable to find complete information

Question: {query}

Information:
{context}

Provide a comprehensive but concise answer.
If the information is from web search, mention that it's current information.
Be helpful and informative.
{scope_instruction_en}
{oral_instruction_en}"""
            if lang_suffix:
                prompt += f"\n{lang_suffix}"
            return prompt
        else:
            prompt = f"""{source_info}から提供された情報を使用して、次の質問に答えてください。

重要: 回答の最初に感情タグを付けてください。
利用可能な感情: [happy], [sad], [relaxed], [surprised], [helpful], [apologetic]

一般的なトピックの情報提供には[relaxed]を使用
エキサイティングな技術ニュースやポジティブな情報には[happy]を使用
予想外のトピックや革新的な内容には[surprised]を使用
実用的な質問への回答には[helpful]を使用
完全な情報が見つからない場合は[apologetic]を使用

質問: {query}

情報:
{context}

包括的だが簡潔な回答を提供してください。情報がウェブ検索からのものである場合は、それが最新の情報であることを述べてください。役立つ情報を提供してください。
{scope_instruction_ja}
{oral_instruction_ja}"""
            if lang_suffix:
                prompt += f"\n{lang_suffix}"
            return prompt

    def _calculate_confidence(self, sources: List[str]) -> float:
        """信頼度を計算"""
        has_kb = any(source.startswith("knowledge_base") for source in sources)
        has_web = "web_search" in sources

        if has_kb and has_web:
            return 0.9
        elif has_kb:
            return 0.8
        elif has_web:
            return 0.6
        else:
            return 0.3

    def _extract_emotion(self, text: str) -> EmotionType:
        """テキストから感情タグを抽出"""
        if "[sad]" in text:
            return "sad"
        elif "[happy]" in text:
            return "happy"
        elif "[relaxed]" in text:
            return "relaxed"
        elif "[surprised]" in text:
            return "surprised"
        elif "[apologetic]" in text:
            return "apologetic"
        else:
            return "neutral"

    def _handle_error(self, language: SupportedLanguage) -> Dict[str, Any]:
        """エラー時の処理"""
        message = DEFAULT_ERROR_RESPONSE.get(language, DEFAULT_ERROR_RESPONSE["ja"])

        logger.warning("GeneralKnowledgeAgent エラー")

        return {
            "answer": message,
            "emotion": "apologetic",
            "metadata": {
                "agent": self.name,
                "status": "error",
                "error": "internal_error",
            },
        }
