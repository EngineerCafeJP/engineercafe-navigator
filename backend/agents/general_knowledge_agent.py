"""
GeneralKnowledgeAgent完全実装

一般的な質問に対応するエージェント。
Engineer Cafeに関する一般情報、AI・技術トピック、福岡のテックシーンなどに回答。

参考:
- docs/migration/agents/general-knowledge-agent/README.md
- docs/migration/agents/general-knowledge-agent/MIGRATION-GUIDE.md

実装済み機能:
1. Web検索機能の実装(web_search.py統合) ✓
2. OpenRouter APIを使用した回答生成 ✓
3. ナレッジベースとWeb検索の組み合わせ ✓
4. should_use_web_search()ロジック実装 ✓
5. 信頼度計算の最適化 ✓
6. 感情タグの適切な設定 ✓
7. エラーハンドリングとフォールバック ✓
"""

import logging
from typing import Dict, Any, List, Optional, Literal

from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import get_model_config
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)

SupportedLanguage = Literal["ja", "en"]
EmotionType = Literal["helpful", "apologetic", "neutral", "happy", "sad", "relaxed", "surprised"]


class GeneralKnowledgeAgent:
    """
    GeneralKnowledgeAgent完全実装

    一般的な質問に対応し、ナレッジベースとWeb検索を組み合わせて回答を生成します。
    Engineer Cafeに関する一般情報、AI・技術トピック、福岡のテックシーンなどに対応。
    """

    def __init__(self):
        """
        初期化

        - OpenRouterProviderの初期化
        - モデル設定の取得(get_model_config("qa_response"))
        - Web検索ツールの初期化
        - RAG検索ツールの初期化
        """
        self.name = "GeneralKnowledgeAgent"
        logger.info("GeneralKnowledgeAgent完全実装初期化")

        # OpenRouterProvider初期化
        self.provider = OpenRouterProvider()

        # モデル設定取得
        self.model_config = get_model_config("qa_response")

        # Web検索ツール初期化
        self.web_search = WebSearchTool()

        # RAG検索ツール初期化
        self.rag_search = EnhancedRAGSearch()

        logger.info(f"GeneralKnowledgeAgent initialized with model: {self.model_config.model_id}")

    async def answer_general_query(
        self, query: str, language: SupportedLanguage = "ja", session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        一般的な質問に回答

        Args:
            query: ユーザーからの質問
            language: 言語設定("ja" or "en")
            session_id: セッションID(オプショナル)

        Returns:
            {
                "answer": str,  # 回答テキスト
                "emotion": str,  # 感情タグ
                "metadata": Dict  # メタデータ(信頼度、ソースなど)
            }

        TODO (専門エンジニア向け):
        1. Web検索が必要かどうか判定(_should_use_web_search)
        2. ナレッジベース検索の実行(rag_search_tool)
        3. 必要に応じてWeb検索の実行(general_web_search)
        4. プロンプトの構築(_build_general_prompt)
        5. OpenRouter APIで回答生成
        6. 信頼度の計算(_calculate_confidence)
        7. 感情タグの抽出(_extract_emotion)
        """
        logger.info(f"一般質問処理開始: query={query[:50]}..., language={language}")

        try:
            # 1. Web検索の必要性判定
            needs_web_search = self._should_use_web_search(query)
            logger.info(f"Web検索必要性判定: {needs_web_search}")

            # 2. ナレッジベース検索
            kb_result = await self.rag_search.search(
                query=query, category="general", language=language, max_results=5
            )

            context = ""
            sources = []

            if kb_result.get("success") and kb_result.get("data"):
                context = kb_result["data"].get("context", "")
                sources.append("knowledge_base")
                logger.info(f"ナレッジベース検索成功: {len(context)} chars")

            # 3. Web検索(条件付き)
            if needs_web_search or not context:
                logger.info("Web検索を実行します")
                web_result = await self.web_search.search(query=query, language=language)

                if web_result.get("success"):
                    web_text = web_result.get("text", "")
                    web_sources = web_result.get("sources", [])

                    if web_text:
                        # コンテキストに追加
                        if context:
                            context += f"\n\n【Web検索結果】\n{web_text}"
                        else:
                            context = web_text

                        sources.append("web_search")
                        logger.info(
                            f"Web検索成功: {len(web_text)} chars, {len(web_sources)} sources"
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

            logger.info(f"回答生成完了: emotion={emotion}, confidence={confidence}")

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
            logger.error(f"GeneralKnowledgeAgent処理エラー: {e}", exc_info=True)
            return self._handle_error(language)

    def _should_use_web_search(self, query: str) -> bool:
        """
        Web検索が必要かどうか判定

        Args:
            query: ユーザーの質問

        Returns:
            True: Web検索が必要, False: ナレッジベースのみで十分

        キーワードベース判定(最新、ニュース、トレンド、スタートアップなど)
        日本語・英語両対応

        参考キーワード:
        日本語: 最新、現在、今、ニュース、トレンド、スタートアップ、ベンチャー、技術、AI、人工知能、機械学習
        英語: latest, current, now, news, trend, startup, venture, technology, ai, artificial intelligence, machine learning
        """
        # WebSearchToolの静的メソッドを使用
        return WebSearchTool.should_use_web_search(query)

    def _build_general_prompt(
        self, query: str, context: str, sources: List[str], language: SupportedLanguage
    ) -> str:
        """
        プロンプトを構築

        Args:
            query: ユーザーの質問
            context: コンテキスト情報(ナレッジベース + Web検索結果)
            sources: 情報ソースのリスト
            language: 言語設定

        Returns:
            構築されたプロンプト文字列

        - 質問タイプ別のプロンプトテンプレート
        - ソース情報の適切な埋め込み
        - 感情タグ指示の追加
        - 日本語・英語両対応
        """
        source_info = " and ".join(sources) if sources else "available information"

        if language == "en":
            return f"""Answer the following question using the provided information from {source_info}.

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

Provide a comprehensive but concise answer. If the information is from web search, mention that it's current information. Be helpful and informative."""
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
        """
        信頼度を計算

        Args:
            sources: 情報ソースのリスト

        Returns:
            信頼度スコア(0.0-1.0)

        ルール:
        - ナレッジベース + Web検索: 0.9
        - ナレッジベースのみ: 0.8
        - Web検索のみ: 0.6
        - フォールバック: 0.3

        TODO:
        - ソースの質による重み付け
        - コンテキストの充実度による調整
        """
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
        """
        テキストから感情タグを抽出

        Args:
            text: LLMの応答テキスト

        Returns:
            感情タグ(helpful, apologetic, neutral, happy, sad, relaxed, surprised)

        TODO:
        - LLMの応答から[emotion]タグを抽出
        - タグがない場合のデフォルト値
        - コンテキストに応じた感情の自動判定
        """
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
        """
        エラー時の処理

        Args:
            language: 言語設定

        Returns:
            エラーメッセージを含む応答
        """
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
