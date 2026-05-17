"""
FarewellAgent - 退館フローエージェント
退館時の「さようなら」フローを処理し、温かい退館メッセージを生成する
"""

import logging
from typing import Dict, Optional

from langchain_core.messages import HumanMessage

from backend.agents.llm_metadata import merge_llm_metadata
from backend.llm import get_llm_provider, get_model_config
from backend.tools.enhanced_rag import EnhancedRAGSearch

logger = logging.getLogger(__name__)


class FarewellAgent:
    """退館フローエージェント

    退館時の挨拶を処理し、RAG検索とLLMを組み合わせて温かい退館メッセージを生成します。
    受付カード返却案内、荷物確認リマインダー、ブランドメッセージを含めます。

    Attributes:
        enhanced_rag (EnhancedRAGSearch): RAG検索ツール
        llm_provider (LLMProvider): LLMプロバイダー

    Examples:
        >>> agent = FarewellAgent()
        >>> result = await agent.handle_farewell(
        ...     query="帰ります",
        ...     language="ja"
        ... )
        >>> print(result["answer"])
        [happy]ありがとうございました！またのご来館をお待ちしております。受付カードのご返却をお忘れなく。

    Notes:
        - RAG検索で退館関連のナレッジを取得
        - LLMで温かい退館メッセージを生成
        - 感情タグ [happy] を付与
        - RAG検索失敗時はデフォルト退館メッセージを返す
    """

    def __init__(self):
        """FarewellAgentを初期化

        EnhancedRAGSearchとLLMプロバイダーのインスタンスを作成します。
        """
        self.enhanced_rag = EnhancedRAGSearch()
        self.llm_provider = get_llm_provider()

    async def handle_farewell(
        self,
        query: str,
        language: str = "ja",
        session_id: Optional[str] = None,
    ) -> Dict:
        """退館メッセージを処理して応答を生成

        RAG検索で退館関連情報を取得し、LLMで温かい退館メッセージを生成します。
        受付カード返却案内、荷物確認リマインダー、ブランドメッセージを含めます。

        Args:
            query (str): ユーザーからの退館メッセージ
                例: "帰ります", "さようなら", "goodbye"
            language (str): 応答言語。デフォルトは"ja"
                - "ja": 日本語
                - "en": 英語
            session_id (Optional[str]): セッションID（将来の拡張用）

        Returns:
            Dict: 退館応答辞書
                - answer (str): 退館メッセージ。感情タグ [happy] 付き
                - emotion (str): 感情タグ（"happy"）
                - metadata (Dict): メタデータ
                    - agent (str): "FarewellAgent"
                    - confidence (float): 信頼度（0.0-1.0）
                    - sources (List[str]): 情報ソース

        Examples:
            >>> agent = FarewellAgent()
            >>> result = await agent.handle_farewell(query="帰ります", language="ja")
            >>> print(result)
            {
                "answer": "[happy]ありがとうございました！またのご来館をお待ちしております。...",
                "emotion": "happy",
                "metadata": {
                    "agent": "FarewellAgent",
                    "confidence": 0.85,
                    "sources": ["enhanced_rag"]
                }
            }

        Notes:
            - RAG検索失敗時はデフォルト退館メッセージを返す（confidence: 0.3）
            - LLMエラー時もフォールバック処理を実行
        """
        logger.info(
            "Processing farewell: %s..., language: %s",
            query[:50],
            language,
        )

        # RAG検索で退館関連情報を取得
        rag_result = await self.enhanced_rag.search(
            query=query,
            category="facility-info",
            language=language,
            include_advice=True,
            max_results=5,
        )

        context = ""
        if rag_result.get("success"):
            context = rag_result.get("data", {}).get("context", "")

        # プロンプトを構築してLLMで応答生成
        prompt = self._build_farewell_prompt(query, context, language)

        try:
            response_text = await self.llm_provider.generate(
                messages=[HumanMessage(content=prompt)],
                config=get_model_config("facility_info"),
            )

            metadata = merge_llm_metadata(
                {
                    "agent": "FarewellAgent",
                    "confidence": 0.85,
                    "category": "farewell",
                    "request_type": "farewell",
                    "route": "farewell",
                    "sources": ["enhanced_rag"],
                },
                response_text,
            )

            return {
                "answer": str(response_text),
                "emotion": "happy",
                "metadata": metadata,
            }

        except Exception as e:
            logger.exception("LLM error in FarewellAgent: %s", e)
            return self._get_default_farewell_response(language)

    def _build_farewell_prompt(self, query: str, context: str, language: str) -> str:
        """退館プロンプトを構築

        ユーザーの退館クエリと取得したコンテキストから、温かい退館メッセージを
        生成するためのプロンプトを作成します。

        Args:
            query (str): ユーザーの退館クエリ
            context (str): RAG検索で取得したコンテキスト
            language (str): 言語（ja or en）

        Returns:
            str: 構築されたプロンプト

        Examples:
            >>> agent = FarewellAgent()
            >>> prompt = agent._build_farewell_prompt(
            ...     query="帰ります",
            ...     context="",
            ...     language="ja"
            ... )
            >>> assert "さようなら" in prompt or "退館" in prompt
        """
        context_section = f"\n参考情報: {context}" if context else ""

        if language == "en":
            return (
                "The visitor is leaving Engineer Cafe. Generate a warm farewell message.\n"
                f"Visitor's message: {query}"
                f"{context_section}\n\n"
                "Your farewell message must include:\n"
                "1. A warm thank-you and farewell\n"
                "2. A reminder to return the reception card\n"
                "3. A reminder to check for personal belongings\n"
                "4. An invitation to visit again\n\n"
                "Keep it concise (2-3 sentences).\n"
                "IMPORTANT: Start your response with [happy]"
            )
        else:
            return (
                "来館者がエンジニアカフェを退館します。温かい退館メッセージを生成してください。\n"
                f"来館者のメッセージ: {query}"
                f"{context_section}\n\n"
                "退館メッセージには以下を含めてください:\n"
                "1. 温かいお礼と別れの挨拶\n"
                "2. 受付カードの返却案内\n"
                "3. お忘れ物の確認リマインダー\n"
                "4. またのご来館への招待\n\n"
                "簡潔にまとめてください（2-3文）。\n"
                "重要: 回答は必ず[happy]で始めてください"
            )

    def _get_default_farewell_response(self, language: str) -> Dict:
        """デフォルト退館応答を返す

        LLMエラー時のフォールバック退館メッセージを返します。
        受付カード返却案内と荷物確認リマインダーを含みます。

        Args:
            language (str): 言語（ja or en）

        Returns:
            Dict: デフォルト退館応答辞書
                - answer (str): 退館メッセージ（[happy]タグ付き）
                - emotion (str): "happy"
                - metadata (Dict): 低信頼度（0.3）とフォールバックソース

        Examples:
            >>> agent = FarewellAgent()
            >>> response = agent._get_default_farewell_response("ja")
            >>> assert response["answer"].startswith("[happy]")
            >>> assert response["emotion"] == "happy"
            >>> assert "受付カード" in response["answer"]
        """
        if language == "en":
            text = (
                "[happy]Thank you for visiting Engineer Cafe!"
                " Please don't forget to return your reception card."
                " Check that you have all your belongings."
                " We hope to see you again soon!"
            )
        else:
            text = (
                "[happy]ありがとうございました！"
                "受付カードのご返却をお忘れなく。"
                "お忘れ物がないかご確認ください。"
                "またのご来館をお待ちしております！"
            )

        return {
            "answer": text,
            "emotion": "happy",
            "metadata": {
                "agent": "FarewellAgent",
                "confidence": 0.3,
                "category": "farewell",
                "request_type": "farewell",
                "route": "farewell",
                "sources": ["fallback"],
            },
        }
