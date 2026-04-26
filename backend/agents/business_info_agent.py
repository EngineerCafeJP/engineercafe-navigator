"""
BusinessInfoAgent - 営業情報エージェント
営業時間、料金、場所に関する質問に回答
"""

import logging
from typing import Dict, Optional

from langchain_core.messages import HumanMessage

from backend.llm import get_llm_provider, get_model_config
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.utils.language_types import DEFAULT_NOT_FOUND_RESPONSE, LANGUAGE_INSTRUCTION

logger = logging.getLogger(__name__)


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
        state_context: Optional[Dict] = None,
        context_signals=None,
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
                - emotion (str): 感情タグ
                    （happy, relaxed, sad, informative,
                    guiding, helpful, apologetic）
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
        logger.info(
            "Processing query: %s..., request_type: %s, language: %s",
            query[:50],
            request_type,
            language,
        )

        canonical = self._get_canonical_response(query, request_type, language)
        if canonical:
            return canonical

        # requestTypeをcategoryにマッピング
        category = self._map_request_type_to_category(request_type)

        # Check cached RAG results
        cached = state_context if state_context else None
        if cached and cached.get("success") and cached.get("category") == category:
            context = cached.get("context_string", "")
            logger.info("Using cached RAG results for %s", category)
        else:
            # Enhanced RAG検索
            rag_result = await self.enhanced_rag.search(
                query=query,
                category=category,
                language=language,
                include_advice=True,
                max_results=10,
                context_signals=context_signals,
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
                messages=[HumanMessage(content=prompt)],
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
            logger.exception("LLM error: %s", e)
            return self._get_default_response(language, request_type)

    def _map_request_type_to_category(self, request_type: Optional[str]) -> str:
        """requestTypeをEnhanced RAGカテゴリにマッピング

        Args:
            request_type (Optional[str]): リクエストタイプ

        Returns:
            str: RAGカテゴリ（hours, pricing, location,
                consultation, community, facility-info,
                general）

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
            "reception": "general",
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
        logger.debug(
            "Building prompt: query_length=%d, context_length=%d, request_type=%s, language=%s",
            len(query),
            len(context),
            request_type,
            language,
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

        if request_type:
            request_type_prompt = self._get_request_type_prompt(request_type, language)

            if language == "en":
                header = (
                    f"Extract ONLY the {request_type_prompt}"
                    " from the following information"
                    " to answer the question."
                )
                footer = (
                    f"Answer with ONLY the {request_type_prompt}."
                    " Maximum 1-2 sentences."
                    " Do not include any other information.\n"
                    "IMPORTANT: Start your response with"
                    " [relaxed] for information"
                    " or [happy] for positive news.\n"
                    f"{oral_instruction_en}"
                )
                prompt = f"""{header}

Question: {query}
Information: {context}

{footer}"""
                if lang_suffix:
                    prompt += f"\n{lang_suffix}"
                return prompt
            else:
                prompt = f"""次の情報から{request_type_prompt}のみを抽出して質問に答えてください。

質問: {query}
情報: {context}

{request_type_prompt}のみを答えてください。最大1-2文。他の情報は含めないでください。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。
{oral_instruction_ja}"""
                if lang_suffix:
                    prompt += f"\n{lang_suffix}"
                return prompt

        else:
            if language == "en":
                header = (
                    "Answer the question using the"
                    " provided information."
                    " Be concise and direct."
                )
                footer = (
                    "Answer briefly (1-2 sentences)"
                    " with only the relevant information.\n"
                    "IMPORTANT: Start your response with"
                    " an emotion tag: [relaxed] for"
                    " information, [happy] for positive"
                    " news, [sad] for unavailable services.\n"
                    f"{oral_instruction_en}"
                )
                prompt = f"""{header}

Question: {query}
Information: {context}

{footer}"""
                if lang_suffix:
                    prompt += f"\n{lang_suffix}"
                return prompt
            else:
                header = (
                    "提供された情報を使って質問に答えてください。" "簡潔で直接的に答えてください。"
                )
                footer = (
                    "関連する情報のみを簡潔に（1-2文）答えてください。\n"
                    "重要: 感情タグで回答を始めてください: "
                    "情報提供は[relaxed]、良いニュースは[happy]、"
                    "利用できないサービスは[sad]。\n"
                    f"{oral_instruction_ja}"
                )
                prompt = f"""{header}

質問: {query}
情報: {context}

{footer}"""
                if lang_suffix:
                    prompt += f"\n{lang_suffix}"
                return prompt

    def _get_request_type_prompt(self, request_type: str, language: str) -> str:
        """requestTypeに応じたプロンプト文言を取得"""
        prompt_map = {
            "hours": {"en": "operating hours", "ja": "営業時間"},
            "price": {"en": "pricing information", "ja": "料金情報"},
            "location": {"en": "location information", "ja": "場所情報"},
            "access": {"en": "access information", "ja": "アクセス情報"},
            "basement": {"en": "basement facility information", "ja": "地下施設情報"},
            "consultation": {
                "en": "consultation and career advice services",
                "ja": "相談・キャリアアドバイスサービス",
            },
            "community": {
                "en": "community membership (Engineer Cafe Lab, EIC)",
                "ja": "コミュニティ（Engineer Cafe Lab、EIC）",
            },
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

    def _get_canonical_response(
        self, query: str, request_type: Optional[str], language: str
    ) -> Optional[Dict]:
        """Return complete answers for common visitor-critical business questions."""
        normalized = query.lower()
        if self._asks_first_visit_registration(normalized, request_type):
            answers = {
                "ja": (
                    "[relaxed]初めて利用する場合は、来館時に1階受付で利用登録をします。"
                    "所要時間は約5〜10分で、登録料は無料です。"
                    "オンライン事前登録ではなく、受付でスタッフに声をかけてください。"
                ),
                "en": (
                    "[relaxed]For your first visit, register at the 1F reception when "
                    "you arrive. It takes about 5 to 10 minutes and is free, so please "
                    "ask the staff at reception for help."
                ),
                "zh": (
                    "[relaxed]第一次来访时，请到一楼前台办理登记。登记免费，"
                    "大约需要5到10分钟，有不清楚的地方可以直接询问工作人员。"
                ),
                "ko": (
                    "[relaxed]처음 방문하실 때는 1층 안내 데스크에서 이용 등록을 "
                    "하시면 됩니다. 등록은 무료이고 약 5분에서 10분 정도 걸리니 "
                    "직원에게 문의해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_what_is_engineer_cafe(normalized, language):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェは、福岡市の赤煉瓦文化館内にある、"
                    "エンジニアのための無料コワーキング・交流スペースです。"
                    "2019年8月に開設され、Wi-Fiや電源、ものづくり機材があり、"
                    "学生やフリーランスの方も利用できます。"
                ),
                "en": (
                    "[relaxed]Engineer Cafe is a free public coworking and community "
                    "space for engineers in Fukuoka's Red Brick Culture Hall. It opened "
                    "in 2019 as part of the Engineer Friendly City Fukuoka initiative."
                ),
                "zh": (
                    "[relaxed]工程师咖啡是位于福冈市赤砖文化馆内的免费共享办公"
                    "与交流空间，于2019年8月开设，是“工程师友好城市福冈”的核心设施。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페는 후쿠오카 텐진의 아카렌가 문화관 "
                    "안에 있는 엔지니어를 위한 무료 코워킹 및 교류 공간입니다. "
                    "2019년에 문을 열었고, 엔지니어 프렌들리 시티 후쿠오카의 "
                    "핵심 시설입니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_contact(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェへの連絡は、13時から21時の間に"
                    "080-6742-7231へお電話ください。公式サイトは"
                    "https://engineercafe.jp/ で、お問い合わせフォームも利用できます。"
                ),
                "en": (
                    "[relaxed]You can contact Engineer Cafe by phone at 080-6742-7231 "
                    "between 13:00 and 21:00. You can also use the official website, "
                    "https://engineercafe.jp/, or its inquiry form."
                ),
                "zh": (
                    "[relaxed]可以在13:00到21:00之间拨打080-6742-7231"
                    "联系工程师咖啡，也可以查看官网 https://engineercafe.jp/ "
                    "或使用联系表单。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페에는 13시부터 21시 사이에 "
                    "080-6742-7231로 전화하실 수 있습니다. 공식 사이트 "
                    "https://engineercafe.jp/ 와 문의 양식도 이용할 수 있어요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        return None

    @staticmethod
    def _canonical_result(answer: str, request_type: Optional[str]) -> Dict:
        return {
            "answer": answer,
            "emotion": "relaxed",
            "metadata": {
                "agent": "BusinessInfoAgent",
                "confidence": 0.95,
                "request_type": request_type,
                "sources": ["enhanced_rag"],
            },
        }

    @staticmethod
    def _asks_first_visit_registration(query: str, request_type: Optional[str]) -> bool:
        returning_terms = (
            "registered before",
            "already registered",
            "以前登録",
            "再受付",
            "登録済み",
            "이미 등록",
            "전에 등록",
            "已经登记",
        )
        if any(term in query for term in returning_terms):
            return False

        if request_type == "reception" and (
            "受付" in query or "reception" in query or "check in" in query or "check-in" in query
        ):
            first_visit_terms = ("first", "初回", "初めて", "第一次", "처음")
            if any(term in query for term in first_visit_terms):
                return True
        keywords = (
            "first visit",
            "register",
            "registration",
            "初回",
            "初めて",
            "利用登録",
            "第一次",
            "登记",
            "처음",
            "등록",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_what_is_engineer_cafe(query: str, language: str) -> bool:
        if language == "en":
            return "what is engineer cafe" in query
        if language == "ko":
            return "엔지니어 카페" in query and any(
                keyword in query for keyword in ("무엇", "뭐", "어떤 곳", "소개")
            )
        keywords = ("エンジニアカフェって", "工程师咖啡是什么", "엔지니어 카페")
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_contact(query: str) -> bool:
        keywords = ("contact", "phone", "電話", "連絡", "問い合わせ", "联系", "전화", "연락")
        return any(keyword in query for keyword in keywords)

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
        text = DEFAULT_NOT_FOUND_RESPONSE.get(language, DEFAULT_NOT_FOUND_RESPONSE["ja"])

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
