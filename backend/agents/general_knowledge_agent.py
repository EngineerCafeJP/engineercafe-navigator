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
from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import get_model_config
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.tools.tavily_search import TavilySearchTool
from backend.utils.memory_interface import MemorySystemInterface

logger = logging.getLogger(__name__)

SupportedLanguage = Literal["ja", "en"]
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
        self.model_config = get_model_config("qa_response")
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
            return await self._handle_memory_query(query, session_id or "", language)
        return await self.answer_general_query(
            query, language, session_id, state_context, context_signals
        )

    async def answer_general_query(
        self,
        query: str,
        language: SupportedLanguage = "ja",
        session_id: Optional[str] = None,
        state_context: Optional[Dict] = None,
        context_signals=None,
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
            # 1. Web検索の必要性判定（適応的）
            needs_web_search = self._should_use_web_search_adaptive(query, context_signals)
            logger.info("Web検索必要性判定: %s", needs_web_search)

            # 2. ナレッジベース検索（キャッシュチェック付き）
            context = ""
            sources: List[str] = []

            cached = state_context if state_context else None
            if cached and cached.get("success") and cached.get("category") == "general":
                context = cached.get("context_string", "")
                sources.append("knowledge_base_cached")
                logger.info("Using cached RAG results: %d chars", len(context))
            else:
                kb_result = await self.rag_search.search(
                    query=query,
                    category="general",
                    language=language,
                    max_results=5,
                    context_signals=context_signals,
                )

                if kb_result.get("success") and kb_result.get("data"):
                    context = kb_result["data"].get("context", "")
                    sources.append("knowledge_base")
                    logger.info("ナレッジベース検索成功: %d chars", len(context))

            # 3. Web検索(条件付き)
            if needs_web_search or not context:
                logger.info("Web検索を実行します")
                web_result = await self.web_search.search(query=query, language=language)

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

            # 4. コンテキストがない場合はフォールバック
            if not context:
                logger.warning("コンテキストが取得できませんでした")
                return self._handle_error(language)

            # 5. プロンプト構築
            prompt = self._build_general_prompt(query, context, sources, language)

            # 6. LLM生成
            from langchain_core.messages import HumanMessage

            messages = [HumanMessage(content=prompt)]
            response_text = await self.provider.generate(
                messages=messages, config=self.model_config
            )

            # 7. 感情・信頼度抽出
            emotion = self._extract_emotion(response_text)
            confidence = self._calculate_confidence(sources)

            logger.info("回答生成完了: emotion=%s, confidence=%s", emotion, confidence)

            return {
                "answer": response_text,
                "emotion": emotion,
                "metadata": {
                    "agent": self.name,
                    "status": "success",
                    "confidence": confidence,
                    "category": "general_knowledge",
                    "sources": sources,
                },
            }

        except Exception as e:
            logger.exception("GeneralKnowledgeAgent処理エラー: %s", e)
            return self._handle_error(language)

    # =========================================================================
    # メモリクエリ処理
    # =========================================================================

    async def _handle_memory_query(
        self, query: str, session_id: str, language: str = "ja"
    ) -> Dict[str, Any]:
        """メモリ関連クエリを処理"""
        if not self.memory_system:
            return self._handle_no_memory_system(language)

        try:
            query_type = self._detect_memory_query_type(query)
            context = await self.memory_system.get_context(
                query, session_id, {"language": language, "inherit_context": True}
            )

            if not context.get("recent_messages"):
                return self._no_history_response(language)

            prompt = self._build_memory_prompt(query, context, query_type, language)

            from langchain_core.messages import HumanMessage

            messages = [HumanMessage(content=prompt)]
            answer = await self.provider.generate(messages=messages, config=self.model_config)

            emotion = self._determine_memory_emotion(context, query_type)

            return {
                "answer": answer,
                "emotion": emotion,
                "metadata": {
                    "agent": self.name,
                    "status": "success",
                    "query_type": query_type,
                    "message_count": len(context.get("recent_messages", [])),
                    "inherited_request_type": context.get("inherited_request_type"),
                },
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

    def _build_memory_prompt(
        self, query: str, context: Dict, query_type: str, language: str
    ) -> str:
        """メモリプロンプト構築（memory_prompts.pyに委譲）"""
        return build_memory_prompt(query, context, query_type, language)

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

    # =========================================================================
    # 一般クエリ ヘルパーメソッド
    # =========================================================================

    def _should_use_web_search_adaptive(self, query: str, context_signals=None) -> bool:
        """適応的Web検索判定

        context_signals が None の場合は静的判定にフォールバック。
        RAGキャッシュスコア高い + 具体性高い → Web検索不要
        RAGキャッシュスコア低い + 会話浅い → Web検索推奨
        """
        if context_signals is None:
            return self._should_use_web_search(query)

        # High confidence RAG + specific query → skip web
        if context_signals.rag_cache_top_score > 0.8 and context_signals.request_specificity > 0.7:
            return False

        # Low confidence + shallow conversation → try web
        if context_signals.rag_cache_top_score < 0.5 and context_signals.conversation_depth < 3:
            return True

        # Otherwise fall back to static heuristic
        return self._should_use_web_search(query)

    def _should_use_web_search(self, query: str) -> bool:
        """Web検索が必要かどうか判定"""
        return TavilySearchTool.should_use_web_search(query)

    def _build_general_prompt(
        self, query: str, context: str, sources: List[str], language: SupportedLanguage
    ) -> str:
        """プロンプトを構築"""
        source_info = " and ".join(sources) if sources else "available information"

        if language == "en":
            header = (
                "Answer the following question using"
                f" the provided information from {source_info}."
            )
            return f"""{header}

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
Be helpful and informative."""
        else:
            return f"""{source_info}から提供された情報を使用して、次の質問に答えてください。

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

包括的だが簡潔な回答を提供してください。情報がウェブ検索からのものである場合は、それが最新の情報であることを述べてください。役立つ情報を提供してください。"""

    def _calculate_confidence(self, sources: List[str]) -> float:
        """信頼度を計算"""
        has_kb = "knowledge_base" in sources
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
        if language == "en":
            message = "I'm sorry, something went wrong. Please try again later."
        else:
            message = (
                "申し訳ございません。エラーが発生しました。しばらくしてからもう一度お試しください。"
            )

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
