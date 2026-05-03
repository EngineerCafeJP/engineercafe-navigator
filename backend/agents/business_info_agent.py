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
            "contact": "contact",
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
        if self._asks_saino_cafe(normalized):
            answer = self._saino_cafe_answer(normalized, language)
            if answer:
                return self._canonical_result(answer, request_type)

        if self._asks_closed_days(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェの休館日は毎月最終月曜日です。"
                    "その日が祝休日の場合は翌平日が休館日になり、年末年始は"
                    "12月29日から1月3日まで休館です。"
                ),
                "en": (
                    "[relaxed]Engineer Cafe is closed on the last Monday of each month. "
                    "If that day is a public holiday, the next weekday is closed instead. "
                    "It is also closed from December 29 to January 3."
                ),
                "zh": (
                    "[relaxed]工程师咖啡每月最后一个星期一闭馆。"
                    "如果当天是节假日，则顺延到下一个工作日闭馆；"
                    "年末年初12月29日至1月3日也闭馆。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페는 매월 마지막 월요일에 휴관합니다. "
                    "그날이 공휴일이면 다음 평일이 휴관일이며, 연말연시에는 "
                    "12월 29일부터 1월 3일까지 휴관합니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_community_program(normalized, request_type):
            if "devday" in normalized:
                answers = {
                    "ja": (
                        "[relaxed]DevDayはENGINEER IGNITION CAMP（EIC）の"
                        "最終展示会で、2026年2月23日18:00から開催されます。"
                        "ピッチではなく展示形式で実施されます。"
                    ),
                    "en": (
                        "[relaxed]DevDay is the final exhibition for ENGINEER IGNITION "
                        "CAMP (EIC). It is scheduled for February 23, 2026 at 18:00, "
                        "and is held as an exhibition rather than a pitch event."
                    ),
                    "zh": (
                        "[relaxed]DevDay是ENGINEER IGNITION CAMP（EIC）的最终展示会，"
                        "预定于2026年2月23日18:00举行。形式是展示，不是路演。"
                    ),
                    "ko": (
                        "[relaxed]DevDay는 ENGINEER IGNITION CAMP(EIC)의 최종 전시회로, "
                        "2026년 2월 23일 18:00에 열릴 예정입니다. 피치가 아니라 "
                        "전시 형식으로 진행됩니다."
                    ),
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

            if self._asks_eic_completion_conditions(normalized):
                answers = {
                    "ja": (
                        "[relaxed]EICの修了認定には、講義3回への参加、LT発表、"
                        "Dev & Tips 5回中3回への参加、Boot Camp 2日間への参加、"
                        "DevDayでの展示発表の5要件をすべて満たす必要があります。"
                    ),
                    "en": (
                        "[relaxed]To complete EIC, participants must attend three "
                        "lectures, give an LT presentation, attend three of five "
                        "Dev & Tips sessions, join the two-day Boot Camp, and exhibit "
                        "at DevDay."
                    ),
                    "zh": (
                        "[relaxed]EIC的结业认定需要满足五项条件：参加3次讲义、"
                        "进行LT发表、参加5次Dev & Tips中的3次、参加2天Boot Camp、"
                        "并在DevDay进行展示发表。"
                    ),
                    "ko": (
                        "[relaxed]EIC 수료 인정에는 강의 3회 참가, LT 발표, "
                        "Dev & Tips 5회 중 3회 참가, Boot Camp 2일 참가, "
                        "DevDay 전시 발표의 5가지 조건을 모두 충족해야 합니다."
                    ),
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

            answers = {
                "ja": (
                    "[relaxed]ENGINEER IGNITION CAMP（EIC）は、エンジニアカフェが"
                    "主催する短期集中・実践型プログラムです。参加費は無料で、"
                    "「つくりたい物をつくる」をコンセプトに、事業化や対価を得ることを"
                    "目指します。"
                ),
                "en": (
                    "[relaxed]ENGINEER IGNITION CAMP (EIC) is a short, intensive, "
                    "hands-on program hosted by Engineer Cafe. Participation is free, "
                    "and the concept is to build what you want to build while aiming "
                    "toward commercialization or earning value from it."
                ),
                "zh": (
                    "[relaxed]ENGINEER IGNITION CAMP（EIC）是工程师咖啡主办的"
                    "短期集中实践型项目，参加免费。理念是“制作自己想做的东西”，"
                    "并以事业化或获得对价为目标。"
                ),
                "ko": (
                    "[relaxed]ENGINEER IGNITION CAMP(EIC)는 엔지니어 카페가 주최하는 "
                    "단기 집중 실천형 프로그램입니다. 참가비는 무료이며, "
                    "'만들고 싶은 것을 만든다'는 콘셉트로 사업화나 가치 창출을 목표로 합니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_opening_hours(normalized, request_type):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェの開館時間は朝9時から夜22時まで"
                    "（9:00〜22:00）です。コミュニティマネージャーへの"
                    "相談受付は13:00〜21:00です。"
                ),
                "en": (
                    "[relaxed]Engineer Cafe is open from 9:00 AM to 10:00 PM " "(9:00 to 22:00)."
                ),
                "zh": (
                    "[relaxed]工程师咖啡的开放时间是早上9点到晚上10点"
                    "（9:00到22:00）。社区经理咨询时间是13:00到21:00。"
                    "每月最后一个星期一和年底年初闭馆休息。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페의 운영 시간은 오전 9시부터 밤 10시까지"
                    "(9:00-22:00)입니다. 궁금한 점은 직원에게 문의해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_pricing(normalized, request_type):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェの利用登録、コワーキングスペース、"
                    "施設・設備の利用料は無料です。ただしcafe&bar sainoの飲食代と"
                    "3Dプリンターのフィラメント代は有料です。"
                ),
                "en": (
                    "[relaxed]Engineer Cafe registration, coworking space use, and "
                    "most equipment use are free. Food and drinks at cafe&bar saino, "
                    "3D printer filament, and some paid spaces such as second-floor "
                    "meeting rooms are charged separately."
                ),
                "zh": (
                    "[relaxed]工程师咖啡的使用登记、共享办公空间和大部分设备都是免费的。"
                    "cafe&bar saino的餐饮、3D打印机耗材以及二楼会议室等部分空间需要另外付费。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페의 이용 등록, 코워킹 공간, 대부분의 설비 이용은 "
                    "무료입니다. cafe&bar saino의 음식과 음료, 3D 프린터 필라멘트, "
                    "2층 회의실 같은 일부 유료 공간은 별도 비용이 필요합니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_first_visit_registration(normalized, request_type):
            answers = {
                "ja": (
                    "[relaxed]初めて利用する場合は、来館時に1階受付で利用登録をします。"
                    "所要時間は約5〜10分で、登録料は無料です。"
                    "受付で案内されるWebフォームに入力します。オンライン事前登録ではなく、"
                    "受付でスタッフに声をかけてください。"
                ),
                "en": (
                    "[relaxed]For your first visit, register at the 1F reception when "
                    "you arrive. Please ask the reception staff for assistance. "
                    "Registration is free, takes about 5 to 10 minutes, and staff "
                    "can help you complete the web form."
                ),
                "zh": (
                    "[relaxed]第一次来访时，请到一楼前台办理登记。登记免费，"
                    "大约需要5到10分钟，需要在前台填写网页表单。不能在线预先登记，"
                    "有不清楚的地方可以直接询问工作人员。"
                ),
                "ko": (
                    "[relaxed]처음 방문하실 때는 1층 안내 데스크에서 등록하시면 "
                    "됩니다. 등록은 무료이고 약 5분에서 10분 정도 걸리며, "
                    "직원에게 문의하시면 안내받을 수 있습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_reservation_requirement(normalized):
            answers = {
                "ja": (
                    "[relaxed]通常のコワーキング利用は予約なしで利用できます。"
                    "来館したら1階受付でチェックインしてください。"
                ),
                "en": (
                    "[relaxed]Yes. You can use the regular coworking space at "
                    "Engineer Cafe without a reservation. Please check in at the "
                    "1F reception when you arrive."
                ),
                "zh": (
                    "[relaxed]普通共享办公空间无需预约即可使用。" "到馆后请先到一楼前台办理签到。"
                ),
                "ko": (
                    "[relaxed]일반 코워킹 공간은 예약 없이 이용할 수 있습니다. "
                    "방문하시면 1층 안내 데스크에서 체크인해 주세요."
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
                    "https://engineercafe.jp/, or its inquiry form. For second-floor "
                    "meeting rooms, please use the separate inquiry path or ask at "
                    "reception during opening hours."
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
    def _asks_saino_cafe(query: str) -> bool:
        return any(
            keyword in query
            for keyword in (
                "saino",
                "サイノ",
                "サイノカフェ",
                "cafe&bar",
                "併設カフェ",
            )
        )

    @staticmethod
    def _saino_cafe_answer(query: str, language: str) -> Optional[str]:
        if any(
            keyword in query for keyword in ("営業時間", "business hours", "opening hours", "hours")
        ):
            answers = {
                "ja": (
                    "[relaxed]cafe&bar sainoの営業時間は、平日はDay Time "
                    "12:00〜17:00、Night Time 18:00〜20:00、土日祝は"
                    "11:00〜20:00です。定休日は月曜と水曜です。"
                ),
                "en": (
                    "[relaxed]cafe&bar saino is open on weekdays from 12:00 to "
                    "17:00 for Day Time and 18:00 to 20:00 for Night Time, and "
                    "on weekends and holidays from 11:00 to 20:00. It is closed "
                    "on Mondays and Wednesdays."
                ),
                "zh": (
                    "[relaxed]cafe&bar saino平日Day Time为12:00到17:00，"
                    "Night Time为18:00到20:00；周末和节假日为11:00到20:00。"
                    "周一和周三定休。"
                ),
                "ko": (
                    "[relaxed]cafe&bar saino의 영업시간은 평일 Day Time "
                    "12:00-17:00, Night Time 18:00-20:00이며, 주말과 공휴일은 "
                    "11:00-20:00입니다. 정기 휴일은 월요일과 수요일입니다."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("フード", "food", "menu", "メニュー", "ランチ")):
            answers = {
                "ja": (
                    "[relaxed]サイノカフェのフードは、てりたまハンバーグサンド"
                    "700円、ツナチーズメルトサンド700円、あんバター白玉サンド"
                    "650円、ワッフル420円、アイスクリーム420円などがあります。"
                    "ドリンクセットは50円引きです。"
                ),
                "en": (
                    "[relaxed]cafe&bar saino serves food such as teritama hamburger "
                    "sandwiches for 700 yen, tuna cheese melt sandwiches for 700 yen, "
                    "an-butter shiratama sandwiches for 650 yen, waffles for 420 yen, "
                    "and ice cream for 420 yen. Drink sets are 50 yen off."
                ),
                "zh": (
                    "[relaxed]saino咖啡有照烧鸡蛋汉堡三明治700日元、金枪鱼芝士"
                    "热三明治700日元、红豆黄油白玉三明治650日元、华夫饼420日元、"
                    "冰淇淋420日元等。饮料套餐可减50日元。"
                ),
                "ko": (
                    "[relaxed]saino 카페의 푸드 메뉴에는 데리타마 햄버그 샌드 "
                    "700엔, 참치 치즈 멜트 샌드 700엔, 앙버터 시라타마 샌드 "
                    "650엔, 와플 420엔, 아이스크림 420엔 등이 있습니다. "
                    "드링크 세트는 50엔 할인됩니다."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(
            keyword in query for keyword in ("コーヒー", "coffee", "カフェラテ", "値段", "price")
        ):
            answers = {
                "ja": (
                    "[relaxed]サイノカフェのコーヒーは、ブレンドコーヒー380円、"
                    "シングルオリジン460円から、エスプレッソ400円、カフェラテ"
                    "570円、カフェモカ700円です。"
                ),
                "en": (
                    "[relaxed]At cafe&bar saino, blended coffee is 380 yen, single "
                    "origin coffee starts at 460 yen, espresso is 400 yen, cafe latte "
                    "is 570 yen, and cafe mocha is 700 yen."
                ),
                "zh": (
                    "[relaxed]saino咖啡的拼配咖啡是380日元，单品咖啡460日元起，"
                    "浓缩咖啡400日元，拿铁570日元，摩卡700日元。"
                ),
                "ko": (
                    "[relaxed]saino 카페의 커피는 블렌드 커피 380엔, 싱글 오리진 "
                    "460엔부터, 에스프레소 400엔, 카페라테 570엔, 카페모카 700엔입니다."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("アルコール", "お酒", "alcohol", "beer", "bar")):
            answers = {
                "ja": (
                    "[relaxed]はい、cafe&bar sainoはNight Timeの18:00〜20:00に"
                    "バー営業をしています。ハイネケン500円、ハイボール450円から、"
                    "カクテル各700円などがあります。"
                ),
                "en": (
                    "[relaxed]Yes. cafe&bar saino operates as a bar during Night "
                    "Time from 18:00 to 20:00. Heineken is 500 yen, highballs start "
                    "at 450 yen, and cocktails are 700 yen each."
                ),
                "zh": (
                    "[relaxed]可以。cafe&bar saino在Night Time 18:00到20:00作为酒吧营业。"
                    "喜力啤酒500日元，Highball 450日元起，鸡尾酒每杯700日元等。"
                ),
                "ko": (
                    "[relaxed]네, cafe&bar saino는 Night Time인 18:00-20:00에 "
                    "바로도 운영합니다. 하이네켄은 500엔, 하이볼은 450엔부터, "
                    "칵테일은 각 700엔입니다."
                ),
            }
            return answers.get(language, answers["ja"])

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
            first_visit_terms = (
                "first",
                "first-time",
                "first time",
                "初回",
                "初めて",
                "第一次",
                "처음",
            )
            if any(term in query for term in first_visit_terms):
                return True
        keywords = (
            "first visit",
            "first-time visitor",
            "first time visitor",
            "first-time",
            "first time here",
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
    def _asks_opening_hours(query: str, request_type: Optional[str]) -> bool:
        if request_type == "hours":
            return True
        keywords = (
            "opening hours",
            "open hours",
            "business hours",
            "what time",
            "営業時間",
            "開館時間",
            "何時から",
            "何時まで",
            "营业时间",
            "几点",
            "운영 시간",
            "이용 시간",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_closed_days(query: str) -> bool:
        keywords = (
            "休館日",
            "休業日",
            "定休日",
            "休みの日",
            "お休みの日",
            "閉まっている日",
            "閉まってる日",
            "closed day",
            "closed days",
            "holiday",
            "holidays",
            "闭馆",
            "休馆",
            "闭馆日",
            "休馆日",
            "휴관일",
            "쉬는 날",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_community_program(query: str, request_type: Optional[str]) -> bool:
        if request_type != "community":
            return False
        keywords = ("engineer ignition camp", "eic", "devday")
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_eic_completion_conditions(query: str) -> bool:
        if not any(keyword in query for keyword in ("eic", "engineer ignition camp")):
            return False
        keywords = (
            "修了",
            "認定",
            "条件",
            "completion",
            "complete",
            "certificate",
            "requirements",
            "结业",
            "认定",
            "条件",
            "수료",
            "인정",
            "조건",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_pricing(query: str, request_type: Optional[str]) -> bool:
        if request_type in ("price", "pricing"):
            return True
        keywords = (
            "cost",
            "fee",
            "price",
            "charge",
            "料金",
            "費用",
            "いくら",
            "收费",
            "费用",
            "요금",
            "비용",
            "얼마",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_reservation_requirement(query: str) -> bool:
        excluded_targets = (
            "event",
            "events",
            "event room",
            "workshop",
            "meetup",
            "seminar",
            "meeting room",
            "conference room",
            "room",
            "イベント",
            "イベントスペース",
            "勉強会",
            "セミナー",
            "ミートアップ",
            "会議室",
            "ミーティングルーム",
            "会议室",
            "活动",
            "이벤트",
            "회의실",
        )
        if any(target in query for target in excluded_targets):
            return False

        reservation_markers = (
            "without a reservation",
            "no reservation",
            "need a reservation",
            "reservation needed",
            "reservation required",
            "予約なし",
            "予約無し",
            "予約不要",
            "予約は必要",
            "予約が必要",
            "予約必要",
            "无需预约",
            "需要预约",
            "예약 없이",
            "예약 필요",
        )
        if not any(marker in query for marker in reservation_markers):
            return False

        regular_use_markers = (
            "engineer cafe",
            "coworking",
            "regular",
            "use",
            "visit",
            "利用",
            "使え",
            "コワーキング",
            "普通",
            "通常",
            "使用",
            "共享办公",
            "이용",
            "코워킹",
        )
        return any(marker in query for marker in regular_use_markers)

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
