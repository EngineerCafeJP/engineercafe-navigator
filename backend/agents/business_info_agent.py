"""
BusinessInfoAgent - 営業情報エージェント
営業時間、料金、場所に関する質問に回答
"""

from typing import Dict, Optional
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.llm import get_llm_provider, get_model_config


class BusinessInfoAgent:
    """営業情報エージェント

    営業時間、料金、場所に関する質問にRAG検索とLLMを組み合わせて回答します。

    Attributes:
        enhanced_rag (EnhancedRAGSearch): RAG検索ツール
        llm_provider (LLMProvider): LLMプロバイダー

    Examples:
        >>> agent = BusinessInfoAgent()
        >>> result = await agent.answer_business_query(
        ...     query="営業時間は何時までですか？",
        ...     request_type="hours",
        ...     language="ja"
        ... )
        >>> print(result["answer"])
        [relaxed]平日は9:00-22:00、土日祝は10:00-20:00まで営業しております。

    Notes:
        - リクエストタイプをRAGカテゴリにマッピングして検索精度を向上
        - LLMプロンプトで感情タグの埋め込みを指示
        - RAG検索失敗時やLLMエラー時はデフォルト応答を返す
    """

    def __init__(self):
        """BusinessInfoAgentを初期化

        EnhancedRAGSearchとLLMプロバイダーのインスタンスを作成します。
        """
        self.enhanced_rag = EnhancedRAGSearch()
        self.llm_provider = get_llm_provider()

    async def answer_business_query(
        self,
        query: str,
        request_type: Optional[str] = None,
        language: str = "ja",
        session_id: Optional[str] = None,
    ) -> Dict:
        """営業情報クエリに回答

        RAG検索で関連情報を取得し、LLMで自然な応答を生成します。
        リクエストタイプに応じてRAGカテゴリをマッピングし、検索精度を向上させます。

        Args:
            query (str): ユーザーからの質問文
                例: "営業時間は何時までですか？", "料金はいくらですか？"
            request_type (Optional[str]): リクエストタイプ
                - "hours": 営業時間
                - "price": 料金
                - "location": 場所・アクセス
                - "access": アクセス情報
                - "basement": 地下施設
                - "facility": 施設情報
                - "wifi": Wi-Fi情報
                - None: 一般的な質問
            language (str): 応答言語。デフォルトは"ja"
                - "ja": 日本語
                - "en": 英語
            session_id (Optional[str]): セッションID（将来の拡張用）

        Returns:
            Dict: 回答辞書
                - answer (str): 回答テキスト。感情タグ付き
                - emotion (str): 感情タグ（happy, relaxed, sad, informative, guiding, helpful, apologetic）
                - metadata (Dict): メタデータ
                    - agent (str): エージェント名
                    - confidence (float): 信頼度（0.0-1.0）
                    - category (str): RAGカテゴリ
                    - request_type (str): リクエストタイプ
                    - sources (List[str]): 情報ソース

        Examples:
            >>> agent = BusinessInfoAgent()
            >>> result = await agent.answer_business_query(
            ...     query="営業時間は？",
            ...     request_type="hours",
            ...     language="ja"
            ... )
            >>> print(result)
            {
                "answer": "[relaxed]平日は9:00-22:00、土日祝は10:00-20:00まで営業しております。",
                "emotion": "relaxed",
                "metadata": {
                    "agent": "BusinessInfoAgent",
                    "confidence": 0.85,
                    "category": "hours",
                    "request_type": "hours",
                    "sources": ["enhanced_rag"]
                }
            }

        Notes:
            - RAG検索失敗時はデフォルト応答を返す（confidence: 0.3）
            - LLMエラー時もフォールバック処理を実行
            - 感情タグはLLM応答から抽出、または request_type に基づいて決定
        """
        print(
            f"[BusinessInfoAgent] Processing query: {query}, request_type: {request_type}, language: {language}"
        )

        # requestTypeをcategoryにマッピング
        category = self._map_request_type_to_category(request_type)

        # Enhanced RAG検索
        rag_result = await self.enhanced_rag.search(
            query=query, category=category, language=language, include_advice=True, max_results=10
        )

        if not rag_result.get("success"):
            return self._get_default_response(language, request_type)

        # コンテキスト取得
        context = rag_result.get("data", {}).get("context", "")

        if not context:
            return self._get_default_response(language, request_type)

        # プロンプト構築
        prompt = self._build_prompt(query, context, request_type, language)

        # LLM応答生成
        try:
            response_text = await self.llm_provider.generate(
                messages=[{"role": "user", "content": prompt}],
                config=get_model_config("facility_info"),
            )

            # 感情タグを決定
            emotion = self._determine_emotion(request_type, response_text)

            return {
                "answer": response_text,
                "emotion": emotion,
                "metadata": {
                    "agent": "BusinessInfoAgent",
                    "confidence": 0.85,
                    "category": category,
                    "request_type": request_type,
                    "sources": ["enhanced_rag"],
                },
            }

        except Exception as e:
            print(f"[BusinessInfoAgent] LLM error: {e}")
            return self._get_default_response(language, request_type)

    def _map_request_type_to_category(self, request_type: Optional[str]) -> str:
        """requestTypeをEnhanced RAGカテゴリにマッピング

        Args:
            request_type (Optional[str]): リクエストタイプ

        Returns:
            str: RAGカテゴリ（hours, pricing, location, consultation, community, facility-info, general）

        Examples:
            >>> agent = BusinessInfoAgent()
            >>> agent._map_request_type_to_category("hours")
            'hours'
            >>> agent._map_request_type_to_category("price")
            'pricing'
            >>> agent._map_request_type_to_category("consultation")
            'consultation'
            >>> agent._map_request_type_to_category("community")
            'community'
            >>> agent._map_request_type_to_category("wifi")
            'facility-info'
        """
        category_mapping = {
            "hours": "hours",
            "price": "pricing",
            "location": "location",
            "access": "location",
            "consultation": "consultation",
            "community": "community",
            "basement": "facility-info",
            "facility": "facility-info",
            "wifi": "facility-info",
        }

        return category_mapping.get(request_type or "", "general")

    def _build_prompt(
        self, query: str, context: str, request_type: Optional[str], language: str
    ) -> str:
        """LLMプロンプトを構築

        リクエストタイプと言語に応じて適切なプロンプトを生成します。
        感情タグの埋め込みを指示し、簡潔な応答を促します。

        Args:
            query (str): ユーザークエリ
            context (str): RAG検索で取得したコンテキスト
            request_type (Optional[str]): リクエストタイプ
            language (str): 言語（ja or en）

        Returns:
            str: 構築されたプロンプト

        Examples:
            >>> agent = BusinessInfoAgent()
            >>> prompt = agent._build_prompt(
            ...     query="営業時間は？",
            ...     context="平日9:00-22:00です。",
            ...     request_type="hours",
            ...     language="ja"
            ... )
            >>> print(prompt)
            次の情報から営業時間のみを抽出して質問に答えてください。

            質問: 営業時間は？
            情報: 平日9:00-22:00です。

            営業時間のみを答えてください。最大1-2文。他の情報は含めないでください。
            重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。

        Notes:
            - request_typeがある場合は特定情報の抽出を指示
            - 感情タグの埋め込みを"重要"として強調
            - 最大1-2文の簡潔な応答を促す
        """
        print(
            f"[BusinessInfoAgent] Building prompt with query_length: {len(query)}, context_length: {len(context)}, request_type: {request_type}, language: {language}"
        )

        if request_type:
            request_type_prompt = self._get_request_type_prompt(request_type, language)

            if language == "en":
                return f"""Extract ONLY the {request_type_prompt} from the following information to answer the question.

Question: {query}
Information: {context}

Answer with ONLY the {request_type_prompt}. Maximum 1-2 sentences. Do not include any other information.
IMPORTANT: Start your response with [relaxed] for information or [happy] for positive news."""
            else:
                return f"""次の情報から{request_type_prompt}のみを抽出して質問に答えてください。

質問: {query}
情報: {context}

{request_type_prompt}のみを答えてください。最大1-2文。他の情報は含めないでください。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。"""

        else:
            if language == "en":
                return f"""Answer the question using the provided information. Be concise and direct.

Question: {query}
Information: {context}

Answer briefly (1-2 sentences) with only the relevant information.
IMPORTANT: Start your response with an emotion tag: [relaxed] for information, [happy] for positive news, [sad] for unavailable services."""
            else:
                return f"""提供された情報を使って質問に答えてください。簡潔で直接的に答えてください。

質問: {query}
情報: {context}

関連する情報のみを簡潔に（1-2文）答えてください。
重要: 感情タグで回答を始めてください: 情報提供は[relaxed]、良いニュースは[happy]、利用できないサービスは[sad]。"""

    def _get_request_type_prompt(self, request_type: str, language: str) -> str:
        """requestTypeに応じたプロンプト文言を取得"""
        prompt_map = {
            "hours": {"en": "operating hours", "ja": "営業時間"},
            "price": {"en": "pricing information", "ja": "料金情報"},
            "location": {"en": "location information", "ja": "場所情報"},
            "access": {"en": "access information", "ja": "アクセス情報"},
            "basement": {"en": "basement facility information", "ja": "地下施設情報"},
            "consultation": {"en": "consultation and career advice services", "ja": "相談・キャリアアドバイスサービス"},
            "community": {"en": "community membership (Engineer Cafe Lab, EIC)", "ja": "コミュニティ（Engineer Cafe Lab、EIC）"},
        }

        prompt = prompt_map.get(
            request_type, {"en": "requested information", "ja": "要求された情報"}
        )
        return prompt.get(language, prompt.get("ja", ""))

    def _determine_emotion(self, request_type: Optional[str], response_text: str) -> str:
        """感情タグを決定

        LLM応答テキストから感情タグを抽出、または request_type に基づいて決定します。

        Args:
            request_type (Optional[str]): リクエストタイプ
            response_text (str): LLMの応答テキスト

        Returns:
            str: 感情タグ（happy, sad, relaxed, informative, guiding, helpful）

        Examples:
            >>> agent = BusinessInfoAgent()
            >>> agent._determine_emotion("hours", "[relaxed]営業時間は...")
            'relaxed'
            >>> agent._determine_emotion("hours", "営業時間は...")
            'informative'

        Notes:
            - 優先順位: 応答テキスト内のタグ > request_type 基準 > デフォルト
            - タグがない場合は request_type に応じた適切な感情を返す
        """
        # レスポンステキストから感情タグを抽出
        if "[happy]" in response_text.lower():
            return "happy"
        elif "[sad]" in response_text.lower():
            return "sad"
        elif "[relaxed]" in response_text.lower():
            return "relaxed"

        # request_typeに基づくデフォルト感情
        if request_type in ["hours", "price"]:
            return "informative"
        elif request_type == "location":
            return "guiding"

        return "helpful"

    def _get_default_response(self, language: str, request_type: Optional[str]) -> Dict:
        """デフォルト応答を返す

        RAG検索失敗またはLLMエラー時のフォールバック応答を生成します。

        Args:
            language (str): 言語（ja or en）
            request_type (Optional[str]): リクエストタイプ

        Returns:
            Dict: デフォルト応答辞書
                - answer (str): お詫びメッセージ
                - emotion (str): "apologetic"
                - metadata (Dict): 低信頼度（0.3）とフォールバックソース

        Examples:
            >>> agent = BusinessInfoAgent()
            >>> response = agent._get_default_response("ja", "hours")
            >>> print(response["answer"])
            [sad]申し訳ございません。お探しの情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。

        Notes:
            - confidence は 0.3 に設定（低信頼度）
            - sources は ["fallback"] を記録
        """
        if language == "en":
            text = "[sad]I'm sorry, I couldn't find the specific information you're looking for. Please try rephrasing your question or contact the staff for assistance."
        else:
            text = "[sad]申し訳ございません。お探しの情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。"

        return {
            "answer": text,
            "emotion": "apologetic",
            "metadata": {
                "agent": "BusinessInfoAgent",
                "confidence": 0.3,
                "request_type": request_type,
                "sources": ["fallback"],
            },
        }
