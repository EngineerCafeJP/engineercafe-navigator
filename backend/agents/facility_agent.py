"""
FacilityAgent - 施設情報エージェント
Wi-Fi、電源、設備、地下施設に関する質問に回答
"""

import logging
from typing import Dict, Optional

from langchain_core.messages import HumanMessage

from backend.config.prompts.facility_prompts import (
    FACILITY_ENHANCEMENT_KEYWORDS,
    build_facility_prompt,
)
from backend.config.routing_constants import match_pet_policy_keywords
from backend.llm import get_llm_provider, get_model_config
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.utils.language_types import DEFAULT_NOT_FOUND_RESPONSE

logger = logging.getLogger(__name__)


class FacilityAgent:
    """施設情報エージェント

    Wi-Fi、電源、設備、地下施設に関する質問にRAG検索とクエリ拡張で回答します。
    リクエストタイプに応じてクエリを拡張し、検索精度を向上させます。

    Attributes:
        enhanced_rag (EnhancedRAGSearch): RAG検索ツール
        llm_provider (LLMProvider): LLMプロバイダー

    Examples:
        >>> agent = FacilityAgent()
        >>> result = await agent.answer_facility_query(
        ...     query="Wi-Fiは使えますか？",
        ...     request_type="wifi",
        ...     language="ja"
        ... )
        >>> print(result["answer"])
        [relaxed]はい、無料Wi-Fiをご利用いただけます。接続方法はスタッフにお尋ねください。

    Notes:
        - クエリ拡張で関連キーワードを追加して検索精度を向上
        - 地下施設の場合、特定施設名を含む段落のみに絞り込み
        - RAG検索失敗時やLLMエラー時はデフォルト応答を返す
    """

    def __init__(self):
        """FacilityAgentを初期化

        EnhancedRAGSearchとLLMプロバイダーのインスタンスを作成します。
        """
        self.enhanced_rag = EnhancedRAGSearch()
        self.llm_provider = get_llm_provider()

    async def answer_facility_query(
        self,
        query: str,
        request_type: Optional[str] = None,
        language: str = "ja",
        session_id: Optional[str] = None,
        state_context: Optional[Dict] = None,
        context_signals=None,
    ) -> Dict:
        """施設情報クエリに回答

        RAG検索で施設情報を取得し、LLMで自然な応答を生成します。
        リクエストタイプに応じてクエリを拡張し、検索精度を向上させます。

        Args:
            query (str): ユーザーからの質問文
                例: "Wi-Fiは使えますか？", "電源はありますか？", "地下の集中スペースの予約方法は？"
            request_type (Optional[str]): リクエストタイプ
                - "wifi": Wi-Fi情報
                - "facility": 設備情報（電源、プリンター等）
                - "basement": 地下施設情報
                - None: 一般的な施設質問
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
                    - agent (str): "FacilityAgent"
                    - confidence (float): 信頼度（0.0-1.0）
                    - category (str): "facility-info"
                    - request_type (str): リクエストタイプ
                    - sources (List[str]): 情報ソース

        Examples:
            >>> agent = FacilityAgent()
            >>> result = await agent.answer_facility_query(
            ...     query="Wi-Fiは使えますか？",
            ...     request_type="wifi",
            ...     language="ja"
            ... )
            >>> print(result)
            {
                "answer": "[relaxed]はい、無料Wi-Fiをご利用いただけます。"
                "接続方法はスタッフにお尋ねください。",
                "emotion": "relaxed",
                "metadata": {
                    "agent": "FacilityAgent",
                    "confidence": 0.85,
                    "category": "facility-info",
                    "request_type": "wifi",
                    "sources": ["enhanced_rag"]
                }
            }

            >>> # 地下施設の例
            >>> result = await agent.answer_facility_query(
            ...     query="MTGスペースの予約方法は？",
            ...     request_type="basement",
            ...     language="ja"
            ... )

        Notes:
            - クエリ拡張で関連キーワードを追加（wifi→"無料Wi-Fi インターネット 接続方法"等）
            - 地下施設の場合、特定施設名を含む段落のみに絞り込み
            - RAG検索失敗時はデフォルト応答を返す（confidence: 0.3）
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

        # Check cached RAG results
        cached = state_context if state_context else None
        rag_category = self._map_request_type_to_rag_category(request_type)

        if cached and cached.get("success") and cached.get("category") == rag_category:
            context = cached.get("context_string", "")
            logger.info("Using cached RAG results for %s", rag_category)
        else:
            # クエリ拡張（requestTypeに応じて）
            enhanced_query = self._enhance_query(query, request_type, language)

            # Enhanced RAG検索
            rag_result = await self.enhanced_rag.search(
                query=enhanced_query,
                category=rag_category,
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

        # 地下施設フィルタリング（basement requestTypeの場合）
        if request_type == "basement":
            context = self._filter_basement_context(context, query, language)

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
                    "agent": "FacilityAgent",
                    "confidence": 0.85,
                    "category": rag_category,
                    "request_type": request_type,
                    "sources": ["enhanced_rag"],
                },
            }

        except Exception as e:
            logger.exception("LLM error: %s", e)
            return self._get_default_response(language, request_type)

    def _enhance_query(self, query: str, request_type: Optional[str], language: str) -> str:
        """クエリ拡張ロジック: リクエストタイプに応じて関連キーワードを追加"""
        if request_type in FACILITY_ENHANCEMENT_KEYWORDS:
            keywords = FACILITY_ENHANCEMENT_KEYWORDS[request_type].get(
                language, FACILITY_ENHANCEMENT_KEYWORDS[request_type].get("ja", "")
            )
            return f"{query} {keywords}"
        return query

    @staticmethod
    def _map_request_type_to_rag_category(request_type: Optional[str]) -> str:
        """Map facility request types to the narrowest RAG category available."""
        category_by_request_type = {
            "smoking": "smoking",
            "food_drink": "food_drink",
            "parking": "parking",
            "bicycle": "bicycle",
            "pets": "policy",
        }
        return category_by_request_type.get(request_type or "", "facility-info")

    def _filter_basement_context(self, context: str, query: str, language: str) -> str:
        """地下施設に関連するコンテキストのみに絞り込む

        地下施設の質問に対して、関連する施設の情報のみを抽出してノイズを削減します。

        Args:
            context (str): RAG検索で取得したコンテキスト
            query (str): ユーザークエリ
            language (str): 言語（ja or en）

        Returns:
            str: フィルタリングされたコンテキスト

        Examples:
            >>> agent = FacilityAgent()
            >>> context = '''
            ... MTGスペースは予約制です。\\n
            ... 集中スペースは予約不要です。\\n
            ... Wi-Fiは無料です。
            ... '''
            >>> filtered = agent._filter_basement_context(context, "MTGスペースの予約方法", "ja")
            >>> print(filtered)
            MTGスペースは予約制です.

        Notes:
            - クエリに特定施設名が含まれる場合、その施設の情報のみを抽出
            - 特定施設名がない場合は全地下施設情報を返す
            - 地下施設キーワード: MTGスペース、集中スペース、アンダースペース、Makersスペース等
        """
        # 地下施設名キーワード
        basement_keywords_ja = [
            "MTGスペース",
            "ミーティングスペース",
            "集中スペース",
            "アンダースペース",
            "Makersスペース",
            "地下",
            "B1",
            "basement",
        ]

        basement_keywords_en = [
            "MTG space",
            "meeting space",
            "focus space",
            "under space",
            "makers space",
            "basement",
            "B1",
        ]

        keywords = basement_keywords_ja if language == "ja" else basement_keywords_en

        # クエリに特定の施設名が含まれているかチェック
        query_lower = query.lower()
        for keyword in keywords:
            if keyword.lower() in query_lower:
                # 該当キーワードを含む段落のみを抽出
                filtered_lines = []
                for line in context.split("\n"):
                    if keyword.lower() in line.lower():
                        filtered_lines.append(line)

                if filtered_lines:
                    return "\n".join(filtered_lines)

        # 特定の施設名がない場合は全地下施設情報を返す
        return context

    def _build_prompt(
        self, query: str, context: str, request_type: Optional[str], language: str
    ) -> str:
        """LLMプロンプトを構築（外部テンプレートに委譲）"""
        logger.debug(
            "Building prompt: query_length=%d, context_length=%d, request_type=%s, language=%s",
            len(query),
            len(context),
            request_type,
            language,
        )
        return build_facility_prompt(query, context, request_type, language)

    def _determine_emotion(self, request_type: Optional[str], response_text: str) -> str:
        """感情タグを決定

        LLM応答テキストから感情タグを抽出、または request_type に基づいて決定します。

        Args:
            request_type (Optional[str]): リクエストタイプ
            response_text (str): LLMの応答テキスト

        Returns:
            str: 感情タグ（happy, sad, relaxed, informative, guiding, helpful）

        Examples:
            >>> agent = FacilityAgent()
            >>> agent._determine_emotion("wifi", "[relaxed]Wi-Fiは...")
            'relaxed'
            >>> agent._determine_emotion("wifi", "Wi-Fiは...")
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
        if request_type in ["wifi", "facility"]:
            return "informative"
        elif request_type == "basement":
            return "guiding"

        return "helpful"

    def _get_canonical_response(
        self, query: str, request_type: Optional[str], language: str
    ) -> Optional[Dict]:
        """Return complete answers for common visitor-critical facility questions."""
        normalized = query.lower()
        from backend.agents.business_info_agent import BusinessInfoAgent

        if BusinessInfoAgent._asks_saino_cafe(normalized):
            answer = BusinessInfoAgent._saino_cafe_answer(normalized, language)
            if answer:
                return self._canonical_result(answer, request_type)

        if self._asks_3d_printer_filament_price(normalized):
            answers = {
                "ja": (
                    "[relaxed]MAKER'sスペースの3Dプリンター用フィラメントは"
                    "使用分を買い取り方式で精算します。Bambu Lab P1S用の"
                    "PLA白・黒とABS白・黒は2円/gで、使用量に単価をかけて"
                    "10円未満は切り捨てです。福岡市在住の学生は無料です。"
                ),
                "en": (
                    "[relaxed]3D printer filament in MAKER's Space is charged by "
                    "the amount used. Standard PLA and ABS for the Bambu Lab P1S are "
                    "2 yen per gram, with amounts under 10 yen rounded down. Students "
                    "living in Fukuoka City can use filament for free."
                ),
                "zh": (
                    "[relaxed]MAKER's Space的3D打印机耗材按实际使用量结算。"
                    "Bambu Lab P1S用的PLA白色、黑色和ABS白色、黑色都是2日元/g，"
                    "不足10日元会舍去。福冈市在住学生免费。"
                ),
                "ko": (
                    "[relaxed]MAKER's Space의 3D 프린터 필라멘트는 사용량만큼 "
                    "정산합니다. Bambu Lab P1S용 PLA 흰색・검정색과 ABS 흰색・검정색은 "
                    "2엔/g이며, 10엔 미만은 절사됩니다. 후쿠오카시 거주 학생은 무료입니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_3d_printer_use(normalized):
            answers = {
                "ja": (
                    "[relaxed]3Dプリンターは地下1階のMAKER'sスペースで利用できます。"
                    "初回は約1時間の無料講習が必要で、講習後はWeb予約優先制です。"
                    "予約は前日まで受け付けています。"
                ),
                "en": (
                    "[relaxed]You can use 3D printers in MAKER's Space on B1F. "
                    "First-time users need a free training session of about one hour; "
                    "after that, use is prioritized by web reservation, accepted until "
                    "the day before."
                ),
                "zh": (
                    "[relaxed]3D打印机可在地下一层MAKER's Space使用。"
                    "首次使用需要参加约1小时的免费讲习；讲习后采用网页预约优先制，"
                    "预约受理到前一天为止。"
                ),
                "ko": (
                    "[relaxed]3D 프린터는 지하 1층 MAKER's Space에서 이용할 수 있습니다. "
                    "처음 이용할 때는 약 1시간의 무료 강습이 필요하며, 이후에는 "
                    "웹 예약 우선제로 전날까지 예약할 수 있습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "toilet" or self._asks_toilet(normalized):
            answers = {
                "ja": (
                    "[relaxed]トイレは1階テラスの奥にあります。館内から直接は"
                    "行けないため、受付奥の通路からテラスに出て、テラス奥へ"
                    "進んでください。"
                ),
                "en": (
                    "[relaxed]The restroom is at the back of the 1F terrace. "
                    "You cannot access it directly from inside the building, so go "
                    "through the passage behind reception to the terrace, then continue "
                    "to the back."
                ),
                "zh": (
                    "[relaxed]洗手间在一楼露台深处。馆内不能直接过去，"
                    "请从前台后方通道到露台，再往露台里面走。"
                ),
                "ko": (
                    "[relaxed]화장실은 1층 테라스 안쪽에 있습니다. 건물 안에서는 "
                    "바로 갈 수 없으니, 접수대 안쪽 통로로 테라스에 나간 뒤 "
                    "안쪽으로 이동해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_online_meeting_place(normalized):
            answers = {
                "ja": (
                    "[relaxed]電話やオンラインミーティングは、1階メインホール、"
                    "談話室、テラス、cafe&bar sainoで可能です。地下1階には"
                    "1回1時間まで使える防音室が1室あり、オンラインミーティングや"
                    "電話に向いています。集中スペースは会話・電話禁止です。"
                ),
                "en": (
                    "[relaxed]For calls or online meetings, you can use the 1F main "
                    "hall, lounge, terrace, or cafe&bar saino. There is also one "
                    "soundproof room on B1F for up to one hour at a time. The B1F "
                    "Focus Space does not allow talking or phone calls."
                ),
                "zh": (
                    "[relaxed]电话或线上会议可以在一楼主厅、谈话室、露台或"
                    "cafe&bar saino进行。地下一层有一间防音室，每次最多可用1小时，"
                    "适合线上会议和电话。集中空间禁止交谈和通话。"
                ),
                "ko": (
                    "[relaxed]전화나 온라인 미팅은 1층 메인 홀, 담화실, 테라스, "
                    "cafe&bar saino에서 가능합니다. 지하 1층에는 1회 1시간까지 "
                    "쓸 수 있는 방음실이 1개 있으며, 집중 스페이스에서는 대화와 전화가 금지됩니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_focus_space(normalized):
            answers = {
                "ja": (
                    "[relaxed]集中スペースは地下1階にある静かなブース型スペースです。"
                    "6席あり、座席指定制・先着順で予約はできません。会話や電話は"
                    "できないので、静かに作業したい方向けです。"
                ),
                "en": (
                    "[relaxed]The Focus Space is a quiet booth-style work area on B1F. "
                    "It has six seats, is first-come first-served with assigned seating, "
                    "and cannot be reserved. Talking and phone calls are not allowed."
                ),
                "zh": (
                    "[relaxed]集中空间位于地下一层，是安静的隔间式工作区。"
                    "共有6个座位，指定座位、先到先用，不能预约。这里禁止交谈和通话。"
                ),
                "ko": (
                    "[relaxed]집중 스페이스는 지하 1층의 조용한 부스형 작업 공간입니다. "
                    "6석이 있으며 좌석 지정제와 선착순으로 운영되고 예약은 불가합니다. "
                    "대화와 전화는 할 수 없습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "lost_found" or self._asks_lost_found(normalized):
            answers = {
                "ja": (
                    "[relaxed]忘れ物や落とし物は、まず1階のエンジニアカフェ受付に"
                    "お声がけください。2階会議室やトイレなど共用部の忘れ物は、"
                    "赤煉瓦文化館受付で保管される場合もあります。電話は080-6742-7231です。"
                ),
                "en": (
                    "[relaxed]For lost items, please ask the 1F Engineer Cafe reception "
                    "first. Items found in shared areas such as the 2F meeting rooms or "
                    "restrooms may be kept at the Red Brick Culture Hall reception. "
                    "You can also call 080-6742-7231."
                ),
                "zh": (
                    "[relaxed]遗失物请先询问一楼工程师咖啡前台。"
                    "二楼会议室或洗手间等公共区域的遗失物，也可能由赤炼瓦文化馆前台保管。"
                    "电话是080-6742-7231。"
                ),
                "ko": (
                    "[relaxed]분실물은 먼저 1층 엔지니어 카페 접수에 문의해 주세요. "
                    "2층 회의실이나 화장실 같은 공용부의 분실물은 아카렌가 문화관 접수에서 "
                    "보관하는 경우도 있습니다. 전화번호는 080-6742-7231입니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_power_outlet(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェでは作業席の周辺で電源コンセントを"
                    "利用できます。見つからない場合や席の移動が必要な場合は、"
                    "受付スタッフに確認してください。"
                ),
                "en": (
                    "[relaxed]Power outlets are available around the coworking and "
                    "work areas at Engineer Cafe. If you cannot find one nearby, "
                    "please ask the reception staff."
                ),
                "zh": (
                    "[relaxed]工程师咖啡的共享办公和工作区域附近可以使用电源插座。"
                    "如果找不到，请向前台工作人员确认。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페의 코워킹 및 작업 공간 주변에서 전원 "
                    "콘센트를 이용할 수 있습니다. 찾기 어려우면 접수 직원에게 문의해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "access" or self._asks_location(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェは福岡市中央区天神1丁目15番30号、"
                    "福岡市赤煉瓦文化館の中にあります。地下鉄空港線の天神駅から"
                    "徒歩約5分で、16番出口から昭和通りを東へ進むと赤煉瓦の建物が目印です。"
                    "西鉄バスの場合は「天神4丁目」バス停で降りるとすぐです。"
                    "専用駐車場はないため、車の場合は天神地下街など近隣の有料駐車場を"
                    "利用してください。"
                ),
                "en": (
                    "[relaxed]Engineer Cafe is located in the Fukuoka City Red Brick "
                    "Culture Hall in Tenjin, Fukuoka. It is about a five-minute walk "
                    "from Tenjin Station."
                ),
                "zh": (
                    "[relaxed]工程师咖啡位于福冈市中央区天神1丁目15番30号的"
                    "福冈市赤炼瓦文化馆内，在一楼，进门后左手边可以找到接待处。"
                    "从天神站步行约5分钟。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페는 텐진 아카렌가 문화관 안에 있습니다. "
                    "텐진역에서 걸어서 약 5분 거리이며, 방문 시 직원에게 문의하시면 "
                    "안내받을 수 있습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "food_drink" or self._asks_food_policy(normalized):
            answers = {
                "ja": (
                    "[relaxed]ふた付きの飲み物は持ち込みできますが、食べ物の持ち込みは"
                    "原則として案内に従ってください。cafe&bar sainoで購入した飲食物は、"
                    "テラスやラウンジなど指定エリアで食べられます。"
                ),
                "en": (
                    "[relaxed]You can bring drinks in lidded containers. Outside food "
                    "is not generally listed as allowed; food from cafe&bar saino can "
                    "be eaten in designated areas such as the terrace and lounge."
                ),
                "zh": (
                    "[relaxed]可以携带有盖饮料。外带食物原则上不允许；"
                    "在cafe&bar saino购买的餐饮可以在露台和休息区等指定区域食用。"
                ),
                "ko": (
                    "[relaxed]뚜껑이 있는 음료는 반입할 수 있습니다. 외부 음식은 "
                    "원칙적으로 허용되지 않으며, cafe&bar saino에서 구매한 음식은 "
                    "테라스나 라운지 같은 지정 구역에서 드실 수 있어요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "temporary_exit" or self._asks_temporary_exit_policy(normalized):
            answers = {
                "ja": (
                    "[relaxed]15分以内の一時外出は、受付カードを持ったまま自由に"
                    "出入りできます。15分以上離席する場合は、受付カードを返却して"
                    "一度退館手続きをしてください。"
                ),
                "en": (
                    "[relaxed]You may step out freely for up to 15 minutes while "
                    "keeping your reception card. If you will be away for 15 minutes "
                    "or longer, please return the card and complete checkout once."
                ),
                "zh": (
                    "[relaxed]15分钟以内的临时外出可以保留接待卡自由进出。"
                    "如果离开15分钟以上，请归还接待卡并先办理退馆手续。"
                ),
                "ko": (
                    "[relaxed]15분 이내의 일시 외출은 접수 카드를 가지고 자유롭게 "
                    "출입할 수 있습니다. 15분 이상 자리를 비울 때는 접수 카드를 "
                    "반납하고 한 번 퇴관 절차를 해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "pets" or self._asks_pet_policy(normalized):
            answers = {
                "ja": (
                    "[relaxed]盲導犬、聴導犬、介助犬などの補助犬は同伴できます。"
                    "それ以外のペットは、テラス席を含めて施設全域で同伴できません。"
                ),
                "en": (
                    "[relaxed]Service dogs, such as guide, hearing, or assistance "
                    "dogs, are allowed. Other pets are not allowed anywhere in the "
                    "facility, including the terrace."
                ),
                "zh": (
                    "[relaxed]导盲犬、助听犬、介助犬等辅助犬可以同行。"
                    "除此之外的宠物，包括露台座位在内，设施全域都不能带入。"
                ),
                "ko": (
                    "[relaxed]안내견, 청각도우미견, 보조견 같은 보조견은 동반할 "
                    "수 있습니다. 그 외 반려동물은 테라스를 포함한 시설 전체에 "
                    "동반할 수 없습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_printer_or_copier(normalized):
            answers = {
                "ja": (
                    "[relaxed]館内で一般的な書類用プリンターやコピー機が使えるとは"
                    "案内されていません。地下1階のMAKER's Spaceには3Dプリンターや"
                    "レーザーカッターがありますが、紙の印刷はスタッフに確認するか、"
                    "近隣のコンビニ利用を検討してください。"
                ),
                "en": (
                    "[relaxed]A standard document printer or copier is not listed as "
                    "available in the building. The B1F MAKER's Space has 3D printers "
                    "and laser cutters, so for paper printing please ask staff or use "
                    "a nearby convenience store."
                ),
                "zh": (
                    "[relaxed]馆内没有提供普通文件打印机、复印机或扫描仪的信息。"
                    "地下一层MAKER's Space有3D打印机和激光切割机；如需纸张打印，"
                    "请询问工作人员或使用附近便利店。"
                ),
                "ko": (
                    "[relaxed]건물 안에 일반 문서용 프린터나 복사기가 제공된다는 "
                    "안내는 없습니다. 지하 1층 MAKER's Space에는 3D 프린터와 "
                    "레이저 커터가 있으니, 종이 출력은 직원에게 문의하거나 "
                    "근처 편의점을 이용해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_wifi_credential(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェでは無料Wi-Fiを利用できます。SSIDや"
                    "パスワードは受付カードの裏面で確認するか、受付スタッフに確認してください。"
                ),
                "en": (
                    "[relaxed]Free Wi-Fi is available at Engineer Cafe. The SSIDs are "
                    "engnecf-guest-2.4GHz and engnecf-guest-5GHz, and the password is "
                    "akarenga-112years. It is also printed on the back of the reception "
                    "card and can be used in the facility, including the terrace."
                ),
                "zh": (
                    "[relaxed]工程师咖啡可以使用免费Wi-Fi。SSID为 "
                    "engnecf-guest-2.4GHz 或 engnecf-guest-5GHz，密码是 "
                    "akarenga-112years。接待卡背面也有记载，设施内包括露台都可以使用。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페의 무료 Wi-Fi SSID는 "
                    "engnecf-guest-2.4GHz 또는 engnecf-guest-5GHz이고, "
                    "비밀번호는 akarenga-112years입니다. 접수 카드 뒷면에서도 "
                    "확인할 수 있으며 테라스를 포함한 시설 내에서 이용할 수 있습니다."
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
                "agent": "FacilityAgent",
                "confidence": 0.95,
                "category": "facility-info",
                "request_type": request_type,
                "sources": ["enhanced_rag"],
            },
        }

    @staticmethod
    def _asks_location(query: str) -> bool:
        keywords = (
            "where",
            "located",
            "access",
            "アクセス",
            "どこ",
            "在哪里",
            "위치",
            "어디",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_power_outlet(query: str) -> bool:
        keywords = (
            "power",
            "outlet",
            "outlets",
            "socket",
            "sockets",
            "plug",
            "電源",
            "コンセント",
            "插座",
            "电源",
            "전원",
            "콘센트",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_food_policy(query: str) -> bool:
        keywords = (
            "food",
            "drink",
            "eat",
            "outside food",
            "食べ物",
            "飲み物",
            "飲食",
            "食物",
            "自带食物",
            "带食物",
            "带吃的",
            "外带食物",
            "饮料",
            "餐饮",
            "음식",
            "음료",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_temporary_exit_policy(query: str) -> bool:
        keywords = (
            "一時外出",
            "途中外出",
            "外出のルール",
            "出入り",
            "再入館",
            "再入場",
            "離席",
            "15分以内",
            "15分以上",
            "temporary exit",
            "step out",
            "leave temporarily",
            "re-enter",
            "reentry",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_pet_policy(query: str) -> bool:
        return match_pet_policy_keywords(query)

    @staticmethod
    def _asks_3d_printer_filament_price(query: str) -> bool:
        printer_markers = ("3dプリンター", "3d printer", "3d打印", "3d 프린터")
        material_markers = ("フィラメント", "filament", "材料", "素材", "耗材")
        price_markers = (
            "料金",
            "価格",
            "費用",
            "値段",
            "いくら",
            "price",
            "fee",
            "cost",
            "收费",
            "费用",
        )
        has_printer_or_material = any(marker in query for marker in printer_markers) or any(
            marker in query for marker in material_markers
        )
        return has_printer_or_material and any(marker in query for marker in price_markers)

    @staticmethod
    def _asks_3d_printer_use(query: str) -> bool:
        printer_markers = ("3dプリンター", "3d printer", "3d打印", "3d 프린터")
        use_markers = (
            "使い方",
            "使いたい",
            "使えますか",
            "利用",
            "予約",
            "講習",
            "use",
            "reservation",
            "reserve",
            "training",
            "使用",
            "预约",
            "사용",
            "예약",
        )
        return any(marker in query for marker in printer_markers) and any(
            marker in query for marker in use_markers
        )

    @staticmethod
    def _asks_toilet(query: str) -> bool:
        keywords = (
            "トイレ",
            "お手洗い",
            "おてあらい",
            "化粧室",
            "toilet",
            "restroom",
            "bathroom",
            "洗手间",
            "厕所",
            "화장실",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_online_meeting_place(query: str) -> bool:
        keywords = (
            "オンライン会議",
            "オンラインミーティング",
            "web会議",
            "通話",
            "電話できる場所",
            "電話したい",
            "防音室",
            "phone booth",
            "online meeting",
            "video call",
            "take a call",
            "线上会议",
            "在线会议",
            "通话",
            "화상 회의",
            "온라인 미팅",
            "통화",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_focus_space(query: str) -> bool:
        keywords = (
            "集中スペース",
            "focus space",
            "静かに作業",
            "静かな作業",
            "集中できる",
            "集中空间",
            "집중 스페이스",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_lost_found(query: str) -> bool:
        keywords = (
            "忘れ物",
            "落とし物",
            "なくした",
            "失くした",
            "置き忘れ",
            "紛失",
            "lost",
            "missing",
            "left behind",
            "left my",
            "forgot",
            "遗失",
            "丢失",
            "분실",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_printer_or_copier(query: str) -> bool:
        keywords = (
            "printer",
            "copier",
            "print",
            "copy",
            "プリンター",
            "コピー",
            "打印",
            "复印",
            "프린터",
            "복사",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_wifi_credential(query: str) -> bool:
        keywords = ("ssid", "password", "パスワード", "密码", "비밀번호")
        return any(keyword in query for keyword in keywords)

    async def get_accessibility_summary(self, language: str = "ja") -> Dict:
        """アクセシビリティ情報のサマリーを取得

        RAG検索でアクセシビリティ関連情報を集約し、LLMでサマリーを生成。
        RAG失敗時はデフォルトのアクセシビリティ情報を返す。

        Args:
            language: 応答言語 ("ja" | "en")

        Returns:
            Dict with keys:
                - summary (str): アクセシビリティサマリーテキスト
                - details (Dict): 詳細情報
                - has_info (bool): RAG情報が取得できたか
        """
        default_info = self._get_default_accessibility_info(language)

        try:
            rag_result = await self.enhanced_rag.search(
                query=(
                    "バリアフリー 車椅子 アクセシビリティ エレベーター 段差"
                    if language == "ja"
                    else "accessibility wheelchair elevator barrier-free ramp"
                ),
                category="facility-info",
                language=language,
                max_results=10,
            )

            if not rag_result.get("success"):
                return {
                    "summary": default_info["summary"],
                    "details": default_info,
                    "has_info": False,
                }

            context = rag_result.get("data", {}).get("context", "")
            if not context:
                return {
                    "summary": default_info["summary"],
                    "details": default_info,
                    "has_info": False,
                }

            # LLMでサマリー生成
            if language == "en":
                prompt = (
                    "Summarize the accessibility information for Engineer Cafe "
                    "based on the following data. Include wheelchair access, "
                    "elevator availability, and any limitations.\n\n"
                    f"Information: {context}\n\n"
                    "Provide a concise 2-3 sentence summary."
                )
            else:
                prompt = (
                    "以下の情報からエンジニアカフェのアクセシビリティ情報を"
                    "まとめてください。車椅子アクセス、エレベーターの有無、"
                    "制限事項を含めてください。\n\n"
                    f"情報: {context}\n\n"
                    "簡潔に2-3文でまとめてください。"
                )

            summary = await self.llm_provider.generate(
                messages=[HumanMessage(content=prompt)],
                config=get_model_config("facility_info"),
            )

            return {
                "summary": summary,
                "details": {"raw_context": context},
                "has_info": True,
            }

        except Exception as e:
            logger.warning("Accessibility summary generation failed: %s", e)
            return {
                "summary": default_info["summary"],
                "details": default_info,
                "has_info": False,
            }

    @staticmethod
    def _get_default_accessibility_info(language: str) -> Dict:
        """デフォルトのアクセシビリティ情報を返す

        RAG検索が失敗した場合のフォールバック。
        1909年築の歴史的建造物としての制約を含む。

        Args:
            language: 応答言語 ("ja" | "en")

        Returns:
            Dict: デフォルトアクセシビリティ情報
        """
        if language == "en":
            return {
                "summary": (
                    "Engineer Cafe is located in a historic building built in 1909. "
                    "The 1st floor is wheelchair accessible. "
                    "The basement (B1) and upper floors have limited accessibility "
                    "due to the building's historic structure. "
                    "Please contact staff for assistance."
                ),
                "wheelchair": "1F accessible, B1/upper floors limited",
                "elevator": "Not available (historic building)",
                "building_note": "Built in 1909, Important Cultural Property",
            }
        return {
            "summary": (
                "エンジニアカフェは1909年築の歴史的建造物（重要文化財）内にあります。"
                "1階は車椅子でご利用いただけます。"
                "地下1階や上階は建物の構造上、アクセスに制限がございます。"
                "お困りの際はスタッフまでお声がけください。"
            ),
            "wheelchair": "1階は利用可、地下・上階は制限あり",
            "elevator": "なし（歴史的建造物のため）",
            "building_note": "1909年築、重要文化財",
        }

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
            >>> agent = FacilityAgent()
            >>> response = agent._get_default_response("ja", "wifi")
            >>> print(response["answer"])
            [sad]申し訳ございません。お探しの施設情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。

        Notes:
            - confidence は 0.3 に設定（低信頼度）
            - sources は ["fallback"] を記録
        """
        text = DEFAULT_NOT_FOUND_RESPONSE.get(language, DEFAULT_NOT_FOUND_RESPONSE["ja"])

        return {
            "answer": text,
            "emotion": "apologetic",
            "metadata": {
                "agent": "FacilityAgent",
                "confidence": 0.3,
                "request_type": request_type,
                "sources": ["fallback"],
            },
        }
