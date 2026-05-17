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
from backend.agents.llm_metadata import merge_llm_metadata
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

            metadata = merge_llm_metadata(
                {
                    "agent": "FacilityAgent",
                    "confidence": 0.85,
                    "category": rag_category,
                    "request_type": request_type,
                    "route": rag_category,
                    "sources": ["enhanced_rag"],
                },
                response_text,
            )

            return {
                "answer": str(response_text),
                "emotion": emotion,
                "metadata": metadata,
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

        if self._asks_cafe_drink_request(normalized):
            answers = {
                "ja": (
                    "[relaxed]コーヒーでしたら、1階のcafe&bar sainoで注文できます。"
                    "ブレンドコーヒー380円、カフェラテ570円、カフェモカ700円があります。"
                    "購入した飲み物は、saino店内、談話室、テラスなど指定エリアでお楽しみください。"
                ),
                "en": (
                    "[relaxed]For coffee, please order at cafe&bar saino on the 1st floor. "
                    "Blend coffee is 380 yen, cafe latte is 570 yen, and cafe mocha is "
                    "700 yen. Drinks bought at saino can be enjoyed in designated areas "
                    "such as saino, the lounge, and the terrace."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_break_request(normalized):
            answers = {
                "ja": (
                    "[relaxed]少し休憩するなら、1階のcafe&bar saino、談話室、"
                    "テラスが使いやすいです。sainoで購入した飲み物や軽食は、"
                    "saino店内、談話室、テラスなど指定エリアで楽しめます。"
                ),
                "en": (
                    "[relaxed]For a short break, cafe&bar saino, the lounge, and the "
                    "terrace on the 1st floor are good options. Food and drinks bought "
                    "at saino can be enjoyed in designated areas such as saino, the "
                    "lounge, and the terrace."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_main_hall(normalized):
            answers = {
                "ja": (
                    "[relaxed]1階メインホールはイベント優先のコワーキングスペースです。"
                    "通常は約30席あり、Wi-Fiと電源を利用できます。4Kモニター貸出や"
                    "VRゴーグルなどの最新機材もあり、イベントや発表にも使われます。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_maker_space_equipment(normalized):
            answers = {
                "ja": (
                    "[relaxed]MAKER'sスペースは地下1階にあり、レーザー加工機、"
                    "3Dプリンター（Bambu Lab P1S）、はんだごて、ボール盤、"
                    "オシロスコープなどを利用できます。機材使用料は無料ですが、"
                    "3Dプリンターのフィラメント代は有料です。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "exclusive_rental" or self._asks_exclusive_rental(normalized):
            answers = {
                "ja": (
                    "[relaxed]メインホールは30〜50名規模のイベントに対応できます。"
                    "エンジニア関連イベントは条件付きで無料になる場合があります。"
                    "貸切やイベント利用は事前予約とコミュニティマネージャー面談が"
                    "必要な場合があるため、早めに相談してください。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

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
                    "[relaxed]3Dプリンターを館内で使う手順は、まず地下1階の"
                    "MAKER'sスペースで約1時間の無料講習を受け、操作方法と"
                    "安全ルールを確認します。講習後はWeb予約優先制で利用でき、"
                    "予約は前日まで受け付けています。"
                ),
                "en": (
                    "[relaxed]To use a 3D printer here, first take the free one-hour "
                    "training in MAKER's Space on B1F to learn the operation steps and "
                    "safety rules. After training, use is prioritized by web reservation, "
                    "accepted until the day before."
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
            if self._asks_multipurpose_toilet(normalized):
                answers = {
                    "ja": (
                        "[relaxed]館内に多目的トイレはありません。"
                        "通常のトイレは1階テラス奥にあります。"
                        "車椅子利用など事前確認が必要な場合は、来館前に"
                        "080-6742-7231へお問い合わせください。"
                    ),
                    "en": (
                        "[relaxed]There is no multipurpose accessible restroom in "
                        "the building. The regular restroom is at the back of the 1F "
                        "terrace. If you need accessibility confirmation before your "
                        "visit, please call 080-6742-7231."
                    ),
                    "zh": (
                        "[relaxed]馆内没有多功能洗手间。普通洗手间在一楼露台深处。"
                        "如需无障碍确认，请来馆前拨打080-6742-7231咨询。"
                    ),
                    "ko": (
                        "[relaxed]건물 안에는 다목적 화장실이 없습니다. 일반 화장실은 "
                        "1층 테라스 안쪽에 있습니다. 접근성 확인이 필요하면 방문 전에 "
                        "080-6742-7231로 문의해 주세요."
                    ),
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

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
            if self._asks_soundproof_room(normalized):
                answers = {
                    "ja": (
                        "[relaxed]防音室は地下1階に1室あります。1回1時間まで、"
                        "先着順で利用でき、予約はできません。オンラインミーティングや"
                        "電話に向いています。"
                    )
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

            answers = {
                "ja": (
                    "[relaxed]通話OKは1階メインホール、談話室、テラス、"
                    "cafe&bar sainoです。通話NGは地下1階の集中スペースです。"
                    "オンラインミーティングには地下1階の防音室が最適で、"
                    "1回1時間まで先着順で使えます。"
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

        if request_type == "children_noise" or self._asks_children_policy(normalized):
            if self._asks_solicitation_or_nap_policy(normalized):
                answers = {
                    "ja": (
                        "[relaxed]営利目的の勧誘、強引な名刺交換、セールス行為は"
                        "禁止されています。公的施設のルールとして、館内での仮眠や"
                        "昼寝もできません。"
                    ),
                    "en": (
                        "[relaxed]Commercial solicitation, aggressive business-card "
                        "exchange, and sales activity are not allowed. Sleeping or "
                        "napping in the facility is also not permitted."
                    ),
                    "zh": (
                        "[relaxed]馆内禁止营利性推销、强行交换名片和销售行为。"
                        "作为公共设施规则，也不能在馆内睡觉或午睡。"
                    ),
                    "ko": (
                        "[relaxed]영리 목적의 권유, 강요하는 명함 교환, 판매 행위는 "
                        "금지되어 있습니다. 공공 시설 규칙상 관내에서 수면이나 낮잠도 불가합니다."
                    ),
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

            answers = {
                "ja": (
                    "[relaxed]お子様連れでも、保護者同伴であれば利用できます。"
                    "特別な年齢制限はありませんが、安全管理のため走り回りや大声は避け、"
                    "お子様から目を離さないでください。専用備品、授乳室、おむつ交換台はありません。"
                ),
                "en": (
                    "[relaxed]Children may visit with a parent or guardian, and there "
                    "is no special age limit. Please keep them supervised, avoid running "
                    "or loud noise, and note that dedicated childcare equipment, nursing "
                    "rooms, and diaper-changing tables are not available."
                ),
                "zh": (
                    "[relaxed]儿童可在监护人陪同下使用，没有特别年龄限制。"
                    "为安全起见，请避免奔跑或大声喧哗，并不要让儿童离开视线。"
                    "馆内没有儿童专用备品、哺乳室或尿布更换台。"
                ),
                "ko": (
                    "[relaxed]어린이는 보호자 동반 시 이용할 수 있으며 특별한 나이 제한은 "
                    "없습니다. 안전을 위해 뛰어다니거나 큰 소리를 내지 않도록 하고, "
                    "전용 비품, 수유실, 기저귀 교환대는 없습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "lost_found" or self._asks_lost_found(normalized):
            answers = {
                "ja": (
                    "[relaxed]コワーキングスペースやカフェエリアでの忘れ物は、"
                    "1階のエンジニアカフェ受付で保管しています。2階会議室やトイレなど"
                    "共用部の忘れ物は赤煉瓦文化館受付の場合もあります。"
                    "電話（080-6742-7231）でお問い合わせください。"
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

        if self._asks_laser_cutter_materials(normalized):
            answers = {
                "ja": (
                    "[relaxed]レーザー加工機では、アクリル、MDF、木材、紙、革、"
                    "フェルトなどが使えます。素材は持ち込み制です。PVC（塩ビ）は"
                    "有毒ガスが出るため禁止で、ポリカーボネート、ガラス、金属、"
                    "発泡スチロールも使えません。"
                ),
                "en": (
                    "[relaxed]The laser cutter can be used with acrylic, MDF, wood, "
                    "paper, leather, and felt brought by the user. PVC is prohibited "
                    "because it releases toxic gas, and polycarbonate, glass, metal, "
                    "and styrofoam cannot be used."
                ),
                "zh": (
                    "[relaxed]激光切割机可使用自带的亚克力、MDF、木材、纸、皮革、"
                    "毛毡等材料。PVC会产生有毒气体，禁止使用；聚碳酸酯、玻璃、金属、"
                    "泡沫塑料也不能使用。"
                ),
                "ko": (
                    "[relaxed]레이저 가공기는 지참한 아크릴, MDF, 목재, 종이, 가죽, "
                    "펠트 등을 사용할 수 있습니다. PVC는 유독 가스가 발생해 금지되며, "
                    "폴리카보네이트, 유리, 금속, 스티로폼도 사용할 수 없습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_laser_cutter_use(normalized):
            answers = {
                "ja": (
                    "[relaxed]レーザー加工機は地下1階のMAKER'sスペースで利用できます。"
                    "初回は約30分の講習が必要で、利用はWeb予約優先制です。"
                    "大きな加工や素材確認は事前にスタッフへ相談してください。"
                ),
                "en": (
                    "[relaxed]The laser cutter is available in MAKER's Space on B1F. "
                    "First-time users need about 30 minutes of training, and use is "
                    "prioritized by web reservation. Please check materials with staff "
                    "in advance."
                ),
                "zh": (
                    "[relaxed]激光切割机可在地下一层MAKER's Space使用。首次使用需要约30分钟讲习，"
                    "使用采用网页预约优先制，材料请事前向工作人员确认。"
                ),
                "ko": (
                    "[relaxed]레이저 가공기는 지하 1층 MAKER's Space에서 이용할 수 있습니다. "
                    "첫 이용 시 약 30분 강습이 필요하며, 웹 예약 우선제로 운영됩니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_projector_or_av_loan(normalized):
            answers = {
                "ja": (
                    "[relaxed]イベントや発表用に、プロジェクター、スクリーン、マイク、"
                    "HDMIケーブル、4Kモニターなどを貸出できます。LT会やハッカソン発表に"
                    "利用でき、大規模利用はコミュニティマネージャーへ相談してください。"
                ),
                "en": (
                    "[relaxed]For events and presentations, equipment such as a "
                    "projector, screen, microphone, HDMI cable, and 4K monitor can be "
                    "borrowed. For larger use, please consult a community manager."
                ),
                "zh": (
                    "[relaxed]活动或发表可借用投影仪、幕布、麦克风、HDMI线、4K显示器等。"
                    "大规模使用请咨询社区经理。"
                ),
                "ko": (
                    "[relaxed]이벤트나 발표용으로 프로젝터, 스크린, 마이크, HDMI 케이블, "
                    "4K 모니터 등을 대여할 수 있습니다. 대규모 이용은 커뮤니티 "
                    "매니저에게 상담해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_water_server(normalized):
            answers = {
                "ja": (
                    "[relaxed]館内にウォーターサーバーや自動販売機はありません。"
                    "ペットボトルや水筒など、ふた付き容器の飲料は持ち込みできます。"
                    "飲み物はcafe&bar sainoや近隣コンビニでも購入できます。"
                ),
                "en": (
                    "[relaxed]There is no water server or vending machine in the "
                    "building. Drinks in lidded containers, such as plastic bottles or "
                    "personal bottles, may be brought in. You can also buy drinks at "
                    "cafe&bar saino or nearby convenience stores."
                ),
                "zh": (
                    "[relaxed]馆内没有饮水机或自动售货机。可携带带盖饮料，如瓶装水或水壶。"
                    "也可在cafe&bar saino或附近便利店购买饮料。"
                ),
                "ko": (
                    "[relaxed]관내에는 워터 서버나 자동판매기가 없습니다. 페트병이나 텀블러처럼 "
                    "뚜껑이 있는 음료는 반입할 수 있으며, cafe&bar saino나 근처 편의점에서도 "
                    "음료를 구매할 수 있습니다."
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

        if request_type == "photography" or self._asks_photography_policy(normalized):
            answers = {
                "ja": (
                    "[relaxed]一般利用時の写真撮影やスナップ撮影は可能です。"
                    "他の利用者の顔や作業内容が写り込む場合はプライバシーに配慮し、"
                    "商業撮影、三脚・フラッシュ、大規模な撮影は事前にスタッフへ確認してください。"
                ),
                "en": (
                    "[relaxed]Casual photos and snapshots are allowed. Please respect "
                    "other visitors' privacy if faces or work screens may be visible. "
                    "Commercial shoots, tripods, flash, or large-scale filming should "
                    "be confirmed with staff in advance."
                ),
                "zh": (
                    "[relaxed]一般参观时可以拍照和进行简单记录。若拍到其他使用者的脸或"
                    "工作内容，请注意隐私。商业拍摄、三脚架、闪光灯或大规模拍摄请事先向工作人员确认。"
                ),
                "ko": (
                    "[relaxed]일반 이용 중 사진 촬영이나 스냅 촬영은 가능합니다. "
                    "다른 이용자의 얼굴이나 작업 내용이 찍힐 수 있으면 개인정보에 유의해 주세요. "
                    "상업 촬영, 삼각대, 플래시, 대규모 촬영은 사전에 직원에게 확인해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "bicycle" or self._asks_bicycle_parking(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェ専用の駐輪場はありません。"
                    "自転車で来館する場合は、近隣の公共駐輪場を利用してください。"
                ),
                "en": (
                    "[relaxed]There is no dedicated bicycle parking at Engineer Cafe. "
                    "Please use nearby public bicycle parking areas."
                ),
                "zh": (
                    "[relaxed]工程师咖啡没有专用自行车停车场。骑自行车来访时，"
                    "请使用附近的公共自行车停车场。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페 전용 자전거 주차장은 없습니다. 자전거로 방문할 때는 "
                    "근처 공공 자전거 주차장을 이용해 주세요."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "meeting_room" or self._asks_meeting_room_pricing(normalized):
            answers = {
                "ja": (
                    "[relaxed]2階会議室は赤煉瓦文化館管理の有料施設です。"
                    "9時〜12時の料金例は、会議室1（12名）が800円〜、"
                    "会議室2（8名）が500円〜、会議室3（30名）が1,700円〜です。"
                    "時間帯により料金が変わるため、詳しくは赤煉瓦文化館側へ確認してください。"
                ),
                "en": (
                    "[relaxed]The 2F meeting rooms are paid facilities managed by the "
                    "Red Brick Culture Hall. Example 9:00-12:00 fees are 800 yen for "
                    "Meeting Room 1 (12 people), 500 yen for Meeting Room 2 (8 people), "
                    "and 1,700 yen for Meeting Room 3 (30 people)."
                ),
                "zh": (
                    "[relaxed]二楼会议室是赤炼瓦文化馆管理的收费设施。"
                    "9:00-12:00的费用例：会议室1（12人）800日元，会议室2（8人）500日元，"
                    "会议室3（30人）1,700日元。"
                ),
                "ko": (
                    "[relaxed]2층 회의실은 아카렌가 문화관이 관리하는 유료 시설입니다. "
                    "9시-12시 요금 예시는 회의실1(12명) 800엔, 회의실2(8명) 500엔, "
                    "회의실3(30명) 1,700엔입니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "access" or self._asks_location(normalized):
            if self._asks_fukuoka_airport_route(normalized):
                answers = {
                    "ja": (
                        "[relaxed]福岡空港からは地下鉄空港線で天神駅まで約11分、"
                        "運賃は260円です。天神駅16番出口から昭和通りを東へ進み、"
                        "徒歩約5分で福岡市赤煉瓦文化館内のエンジニアカフェに着きます。"
                    ),
                    "en": (
                        "[relaxed]From Fukuoka Airport, take the Subway Airport Line "
                        "to Tenjin Station; it takes about 11 minutes and costs 260 yen. "
                        "From Tenjin Station Exit 16, walk east along Showa-dori for "
                        "about five minutes to the Fukuoka City Red Brick Culture Hall."
                    ),
                    "zh": (
                        "[relaxed]从福冈机场乘坐地铁机场线到天神站约11分钟，票价260日元。"
                        "从天神站16号出口沿昭和通步行约5分钟即可到达福冈市赤炼瓦文化馆内的工程师咖啡。"
                    ),
                    "ko": (
                        "[relaxed]후쿠오카공항에서는 지하철 공항선을 타고 텐진역까지 "
                        "약 11분, 요금은 260엔입니다. 텐진역 16번 출구에서 쇼와도리를 "
                        "동쪽으로 약 5분 걸으면 후쿠오카시 아카렌가 문화관 안의 "
                        "엔지니어 카페입니다."
                    ),
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

            if self._asks_hakata_route(normalized):
                answers = {
                    "ja": (
                        "[relaxed]博多駅からは地下鉄空港線で天神駅まで約6分、"
                        "運賃は210円です。バスの場合は天神方面行きで「天神」周辺で下車し、"
                        "天神駅16番出口から徒歩約5分で到着します。"
                    ),
                    "en": (
                        "[relaxed]From Hakata Station, take the Subway Airport Line "
                        "to Tenjin Station; it takes about 6 minutes and costs 210 yen. "
                        "Then walk about five minutes from Tenjin Station Exit 16."
                    ),
                    "zh": (
                        "[relaxed]从博多站乘坐地铁机场线到天神站约6分钟，票价210日元。"
                        "从天神站16号出口步行约5分钟即可到达。"
                    ),
                    "ko": (
                        "[relaxed]하카타역에서는 지하철 공항선을 타고 텐진역까지 "
                        "약 6분, 요금은 210엔입니다. 텐진역 16번 출구에서 약 5분 걸으면 도착합니다."
                    ),
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

            if self._asks_rain_route(normalized):
                answers = {
                    "ja": (
                        "[relaxed]雨の日は、天神駅16番出口から天神地下街とアクロス福岡側の"
                        "通路を経由して、赤煉瓦文化館の近くで地上に出るルートが比較的"
                        "濡れる区間を短くできます。地上に出たら昭和通り沿いに進んでください。"
                    ),
                    "en": (
                        "[relaxed]On rainy days, use the Tenjin underground mall and "
                        "the ACROS Fukuoka side passage from around Tenjin Station Exit 16, "
                        "then come above ground near the Red Brick Culture Hall to minimize "
                        "the exposed walking section."
                    ),
                    "zh": (
                        "[relaxed]雨天可从天神站16号出口附近经由天神地下街和ACROS福冈侧通道，"
                        "在赤炼瓦文化馆附近出地面，可减少淋雨路段。"
                    ),
                    "ko": (
                        "[relaxed]비 오는 날에는 텐진역 16번 출구 주변에서 텐진 지하상가와 "
                        "아크로스 후쿠오카 쪽 통로를 이용한 뒤 아카렌가 문화관 근처에서 "
                        "지상으로 나오면 "
                        "비를 맞는 구간을 줄일 수 있습니다."
                    ),
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

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

        if request_type == "building" or self._asks_building_history(normalized):
            if self._asks_building_architecture(normalized):
                answers = {
                    "ja": (
                        "[relaxed]赤煉瓦文化館は辰野式の建築で、赤煉瓦に花崗岩の帯、"
                        "八角塔屋とドーム、大理石の玄関、アールヌーボーの装飾が特徴です。"
                        "煉瓦造2階・地下1階で、延床面積は約282平方メートルです。"
                    )
                }
                return self._canonical_result(answers.get(language, answers["ja"]), request_type)

            answers = {
                "ja": (
                    "[relaxed]はい、福岡市赤煉瓦文化館は1969年に国の重要文化財に"
                    "指定されました。1909年に日本生命保険株式会社九州支店として"
                    "建てられ、1994年に復元リニューアルし、2019年にエンジニアカフェが"
                    "開設されました。"
                ),
                "en": (
                    "[relaxed]The Fukuoka City Red Brick Culture Hall was built in "
                    "1909 and designated a National Important Cultural Property in "
                    "1969. It was restored and renewed in 1994, and Engineer Cafe "
                    "opened in the building in 2019."
                ),
                "zh": (
                    "[relaxed]福冈市赤炼瓦文化馆建于1909年，1969年被指定为国家重要文化财。"
                    "1994年修复更新，2019年工程师咖啡在馆内开设。"
                ),
                "ko": (
                    "[relaxed]후쿠오카시 아카렌가 문화관은 1909년에 지어졌고 "
                    "1969년에 국가 중요문화재로 지정되었습니다. 1994년에 복원 리뉴얼되었으며, "
                    "2019년에 이 건물 안에 엔지니어 카페가 문을 열었습니다."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "food_drink" or self._asks_food_policy(normalized):
            answers = {
                "ja": (
                    "[relaxed]メインホール、集中スペース、地下施設では飲食できません。"
                    "外部食品の持ち込みは原則禁止で、ふた付きの飲み物は持ち込みできます。"
                    "cafe&bar sainoで購入した飲食物は、"
                    "saino店内、談話室、テラスなど指定エリアで食べられます。"
                ),
                "en": (
                    "[relaxed]You can bring drinks in lidded containers. Outside food "
                    "is generally not allowed. Food and drinks bought at cafe&bar saino "
                    "can be eaten in designated areas such as saino, the lounge, and "
                    "the terrace; eating is not allowed in the main hall, Focus Space, "
                    "or basement facilities."
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

        if self._asks_lounge_room(normalized):
            answers = {
                "ja": (
                    "[relaxed]談話室は1階のcafe&bar saino近くにある休憩・交流スペースです。"
                    "sainoで購入した飲食物を食べられ、軽い打ち合わせや休憩に向いています。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "floor_layout" or self._asks_floor_layout(normalized):
            answers = {
                "ja": (
                    "[relaxed]フロア構成は、1階がメインホール、cafe&bar saino、"
                    "談話室、テラスです。2階は赤煉瓦文化館管理の会議室3室、"
                    "地下1階はMAKER'sスペース、集中スペース、MTGスペース、"
                    "アンダースペース、防音室です。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "accessibility" or self._asks_accessibility(normalized):
            answers = {
                "ja": (
                    "[relaxed]車椅子ではテラス側からスロープを設置して1階を利用できます。"
                    "2階と地下1階は利用できません。来館前に080-6742-7231へ"
                    "事前連絡することをおすすめします。多目的トイレはありません。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_charger_loan(normalized):
            answers = {
                "ja": (
                    "[relaxed]受付でUSB-CやLightningなどの充電器・ケーブルを貸出できます。"
                    "数量限定なので、長時間使う場合は持参がおすすめです。各席には"
                    "電源コンセントもあります。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_summer_heat(normalized):
            answers = {
                "ja": (
                    "[relaxed]赤煉瓦造りの歴史的建造物で蓄熱しやすく、夏場は暑くなりがちです。"
                    "エアコンはありますが、完全に冷えるまで時間がかかる場合があります。"
                    "地下1階のUnder SpaceやFocus Spaceは比較的涼しくおすすめです。"
                    "飲み物をこまめに取りながらご利用ください。"
                )
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if request_type == "nearby" or self._asks_nearby(normalized):
            nearby = self._nearby_canonical_response(normalized, language)
            if nearby:
                return self._canonical_result(nearby, request_type)

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
                    "[relaxed]館内に書類用プリンター、コピー機、スキャナーは"
                    "設置されていません。印刷やコピーが必要な場合は、徒歩2分ほどの"
                    "ファミリーマート天神一丁目店など最寄りコンビニの"
                    "ネットプリントサービスをご利用ください。"
                ),
                "en": (
                    "[relaxed]No. Engineer Cafe does not provide a standard document "
                    "printer, copier, or scanner. The B1F MAKER's Space has 3D printers "
                    "and laser cutters, but for paper printing please ask staff or use "
                    "a nearby convenience store's net-print service."
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

        if self._asks_wifi_credential(normalized) and self._asks_business_hours(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェの開館時間は9:00〜22:00です。"
                    "Wi-FiのSSIDは engnecf-guest-2.4GHz または engnecf-guest-5GHz、"
                    "パスワードは akarenga-112years です。受付カードの裏面にも記載されています。"
                ),
                "en": (
                    "[relaxed]Engineer Cafe is open from 9:00 to 22:00. "
                    "The Wi-Fi SSIDs are engnecf-guest-2.4GHz and engnecf-guest-5GHz, "
                    "and the password is akarenga-112years. It is also printed on the "
                    "back of the reception card."
                ),
            }
            return self._canonical_result(answers.get(language, answers["ja"]), request_type)

        if self._asks_wifi_credential(normalized):
            answers = {
                "ja": (
                    "[relaxed]Wi-FiのSSIDは engnecf-guest-2.4GHz または "
                    "engnecf-guest-5GHz です。パスワードは akarenga-112years です。"
                    "受付カードの裏面にも記載されています。"
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

        if self._asks_available_spaces(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェのスペースについてご案内します。"
                    "メインホール、集中スペース、MAKER'sスペース、MTGスペース、"
                    "防音室、アンダースペース、テラス、談話室、2階会議室などがあります。"
                    "用途に応じてご選択ください。"
                ),
                "en": (
                    "[relaxed]Available spaces include the 1F Main Hall for coworking "
                    "and events; B1F Focus Space with six silent booths, Meeting Space, "
                    "MAKER's Space with 3D printers and laser cutters, Under Space, and "
                    "one Soundproof Room; and three paid meeting rooms on 2F."
                ),
                "zh": (
                    "[relaxed]可使用的主要空间包括一楼主厅（共享办公和活动）、"
                    "地下一层集中空间6席、会议空间、MAKER's Space、Under Space和防音室，"
                    "二楼还有3间收费会议室。"
                ),
                "ko": (
                    "[relaxed]주요 이용 공간은 1층 메인 홀(코워킹・이벤트), "
                    "지하 1층 집중 스페이스 6석, 미팅 스페이스, MAKER's Space, "
                    "언더 스페이스, 방음실이며, 2층에는 유료 회의실 3개가 있습니다."
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
                "route": "facility-info",
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
    def _asks_fukuoka_airport_route(query: str) -> bool:
        return any(keyword in query for keyword in ("福岡空港", "fukuoka airport", "机场", "공항"))

    @staticmethod
    def _asks_hakata_route(query: str) -> bool:
        return any(keyword in query for keyword in ("博多駅", "hakata station", "하카타역"))

    @staticmethod
    def _asks_rain_route(query: str) -> bool:
        return any(keyword in query for keyword in ("雨の日", "rainy", "rain", "下雨", "비 오는"))

    @staticmethod
    def _asks_nearby(query: str) -> bool:
        keywords = (
            "周辺",
            "近く",
            "近隣",
            "ランチ",
            "病院",
            "ホテル",
            "コンビニ",
            "nearby",
            "lunch",
            "clinic",
            "hospital",
            "hotel",
            "convenience store",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _nearby_canonical_response(query: str, language: str) -> Optional[str]:
        if any(keyword in query for keyword in ("ランチ", "lunch", "restaurant", "レストラン")):
            answers = {
                "ja": (
                    "[relaxed]周辺でランチを探すなら、天神地下街に徒歩3〜5分で多数の飲食店があります。"
                    "西中洲エリアも徒歩約5分で、アクロス福岡内にも飲食店があります。"
                    "軽食なら近隣コンビニも利用できます。"
                ),
                "en": (
                    "[relaxed]For lunch nearby, Tenjin Underground Mall has many "
                    "restaurants about a 3 to 5 minute walk away. Nishinakasu is about "
                    "five minutes away, and ACROS Fukuoka also has restaurants. "
                    "Nearby convenience stores are useful for light meals."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("病院", "clinic", "hospital", "医療")):
            answers = {
                "ja": (
                    "[relaxed]近くの医療機関として、アクロス福岡4階の麻生クリニック、"
                    "あやすぎビルクリニック、黒田クリニックが徒歩1〜3分圏内にあります。"
                    "総合病院が必要な場合は博多方面も候補です。緊急時は119番に通報してください。"
                ),
                "en": (
                    "[relaxed]Nearby clinics include Aso Clinic on the 4F of ACROS "
                    "Fukuoka, Ayasugi Building Clinic, and Kuroda Clinic, about a "
                    "1 to 3 minute walk away. For emergencies, call 119."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("ホテル", "hotel", "accommodation", "宿泊")):
            answers = {
                "ja": (
                    "[relaxed]近くのホテルなら、高級ホテルでは西鉄グランドホテルが徒歩約5分、"
                    "ソラリア西鉄ホテルが徒歩約7分です。ビジネス利用ならプラザホテル天神が"
                    "徒歩約3分です。ゲストハウスならWeBase博多なども候補になります。"
                ),
                "en": (
                    "[relaxed]Nearby hotel options include Nishitetsu Grand Hotel "
                    "about five minutes away, Solaria Nishitetsu Hotel about seven "
                    "minutes away, and Plaza Hotel Tenjin about three minutes away."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("コンビニ", "convenience store")):
            answers = {
                "ja": (
                    "[relaxed]近くのコンビニは、ファミリーマート天神一丁目店、"
                    "ファミリーマート天神四丁目店、ローソンS天神ブリック店が徒歩1〜3分圏内です。"
                    "ATMや軽食の利用にも便利です。"
                ),
                "en": (
                    "[relaxed]Nearby convenience stores include FamilyMart Tenjin "
                    "1-chome, FamilyMart Tenjin 4-chome, and Lawson S Tenjin Brick, "
                    "about a 1 to 3 minute walk away."
                ),
            }
            return answers.get(language, answers["ja"])

        return None

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
    def _asks_meeting_room_pricing(query: str) -> bool:
        return any(keyword in query for keyword in ("会議室", "meeting room")) and any(
            keyword in query for keyword in ("料金", "いくら", "fee", "cost", "price")
        )

    @staticmethod
    def _asks_main_hall(query: str) -> bool:
        if not any(keyword in query for keyword in ("メインホール", "main hall")):
            return False
        excluded_markers = ("貸切", "飲食", "食べ", "food", "eat", "exclusive", "rental")
        if any(marker in query for marker in excluded_markers):
            return False
        main_hall_info_markers = (
            "どこ",
            "場所",
            "ありますか",
            "ある",
            "どんなスペース",
            "どんな場所",
            "どの階",
            "何階",
            "where",
            "located",
            "location",
            "what kind",
        )
        return any(marker in query for marker in main_hall_info_markers)

    @staticmethod
    def _asks_maker_space_equipment(query: str) -> bool:
        maker_markers = ("maker'sスペース", "maker's space", "makersスペース", "メイカースペース")
        equipment_markers = ("機材", "設備", "使え", "利用", "equipment", "facilities")
        return any(marker in query for marker in maker_markers) and any(
            marker in query for marker in equipment_markers
        )

    @staticmethod
    def _asks_exclusive_rental(query: str) -> bool:
        rental_markers = ("貸切", "貸し切り", "イベント利用", "exclusive", "rental")
        return any(marker in query for marker in rental_markers)

    @staticmethod
    def _asks_building_architecture(query: str) -> bool:
        architecture_markers = (
            "建築的特徴",
            "建築の特徴",
            "辰野式",
            "花崗岩",
            "八角塔屋",
            "ドーム",
            "アールヌーボー",
            "architectural",
            "architecture",
        )
        return any(marker in query for marker in architecture_markers)

    @staticmethod
    def _asks_building_history(query: str) -> bool:
        return any(
            keyword in query for keyword in ("重要文化財", "赤煉瓦", "red brick", "historic")
        )

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
    def _asks_cafe_drink_request(query: str) -> bool:
        drink_markers = (
            "コーヒー",
            "珈琲",
            "カフェラテ",
            "カフェモカ",
            "エスプレッソ",
            "ドリンク",
            "coffee",
            "latte",
            "espresso",
            "beverage",
        )
        desire_markers = (
            "飲みたい",
            "注文",
            "オーダー",
            "買いたい",
            "ください",
            "want",
            "order",
            "buy",
            "grab",
        )
        return any(marker in query for marker in drink_markers) and (
            any(marker in query for marker in desire_markers)
            or any(marker in query for marker in ("コーヒー", "珈琲", "coffee"))
        )

    @staticmethod
    def _asks_break_request(query: str) -> bool:
        return any(
            marker in query
            for marker in (
                "休憩",
                "休みたい",
                "一息",
                "ゆっくり",
                "ちょっと休",
                "take a break",
                "rest",
                "relax",
            )
        )

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
    def _asks_multipurpose_toilet(query: str) -> bool:
        return any(
            keyword in query
            for keyword in (
                "多目的トイレ",
                "多目的",
                "accessible restroom",
                "accessible toilet",
                "multipurpose",
            )
        )

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
    def _asks_soundproof_room(query: str) -> bool:
        return any(keyword in query for keyword in ("防音室", "soundproof room", "phone booth"))

    @staticmethod
    def _asks_lounge_room(query: str) -> bool:
        return any(keyword in query for keyword in ("談話室", "ラウンジ", "lounge"))

    @staticmethod
    def _asks_floor_layout(query: str) -> bool:
        keywords = (
            "フロア構成",
            "フロアマップ",
            "フロアガイド",
            "floor layout",
            "floor map",
            "floor guide",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_accessibility(query: str) -> bool:
        keywords = (
            "車椅子",
            "バリアフリー",
            "スロープ",
            "エレベーター",
            "wheelchair",
            "accessibility",
            "accessible",
            "barrier-free",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_photography_policy(query: str) -> bool:
        keywords = (
            "撮影",
            "写真",
            "カメラ",
            "スナップ",
            "photo",
            "photography",
            "filming",
            "camera",
            "拍照",
            "摄影",
            "촬영",
            "사진",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_charger_loan(query: str) -> bool:
        charger_markers = ("充電器", "充電ケーブル", "usb-c", "lightning", "charger", "cable")
        loan_markers = ("借り", "貸出", "貸し出し", "ありますか", "borrow", "loan")
        return any(marker in query for marker in charger_markers) and any(
            marker in query for marker in loan_markers
        )

    @staticmethod
    def _asks_summer_heat(query: str) -> bool:
        return any(keyword in query for keyword in ("夏場", "暑い", "暑く", "heat", "hot"))

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
    def _asks_children_policy(query: str) -> bool:
        keywords = (
            "子連れ",
            "子供",
            "子ども",
            "お子様",
            "ベビーカー",
            "children",
            "kids",
            "stroller",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_solicitation_or_nap_policy(query: str) -> bool:
        keywords = (
            "勧誘",
            "名刺交換",
            "セールス",
            "営業行為",
            "営利目的",
            "仮眠",
            "昼寝",
            "solicitation",
            "sales",
            "nap",
            "sleep",
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
    def _asks_laser_cutter_materials(query: str) -> bool:
        laser_markers = (
            "レーザー加工機",
            "レーザーカッター",
            "laser cutter",
            "激光",
            "레이저",
        )
        material_markers = (
            "素材",
            "材料",
            "使える",
            "使えますか",
            "material",
            "materials",
            "acrylic",
            "pvc",
            "材质",
            "材料",
            "소재",
            "재료",
        )
        return any(marker in query for marker in laser_markers) and any(
            marker in query for marker in material_markers
        )

    @staticmethod
    def _asks_laser_cutter_use(query: str) -> bool:
        laser_markers = (
            "レーザー加工機",
            "レーザーカッター",
            "laser cutter",
            "激光",
            "레이저",
        )
        use_markers = (
            "使いたい",
            "使えますか",
            "利用",
            "予約",
            "講習",
            "use",
            "reservation",
            "training",
            "使用",
            "预约",
            "사용",
        )
        return any(marker in query for marker in laser_markers) and any(
            marker in query for marker in use_markers
        )

    @staticmethod
    def _asks_projector_or_av_loan(query: str) -> bool:
        equipment_markers = (
            "プロジェクター",
            "スクリーン",
            "マイク",
            "4kモニター",
            "hdmi",
            "projector",
            "screen",
            "microphone",
            "4k monitor",
        )
        loan_markers = (
            "借り",
            "貸出",
            "貸し出し",
            "使えますか",
            "利用",
            "borrow",
            "loan",
            "lend",
            "available",
            "rent",
        )
        return any(marker in query for marker in equipment_markers) and any(
            marker in query for marker in loan_markers
        )

    @staticmethod
    def _asks_water_server(query: str) -> bool:
        keywords = (
            "ウォーターサーバー",
            "給水",
            "自動販売機",
            "water server",
            "water dispenser",
            "vending machine",
            "饮水机",
            "自动售货机",
            "워터 서버",
            "자판기",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_bicycle_parking(query: str) -> bool:
        keywords = (
            "駐輪場",
            "駐輪",
            "自転車",
            "bicycle parking",
            "bike parking",
            "cycle parking",
            "자전거 주차",
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
    def _asks_available_spaces(query: str) -> bool:
        space_markers = (
            "スペースを使いたい",
            "利用可能スペース",
            "どんなスペース",
            "available spaces",
            "what spaces",
            "spaces are available",
        )
        return any(marker in query for marker in space_markers)

    @staticmethod
    def _asks_wifi_credential(query: str) -> bool:
        keywords = ("ssid", "password", "パスワード", "密码", "비밀번호")
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_business_hours(query: str) -> bool:
        business_hours_markers = (
            "営業時間",
            "開館時間",
            "何時",
            "いつまで",
            "opening hours",
            "business hours",
            "open hours",
        )
        return any(marker in query for marker in business_hours_markers)

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
                "route": request_type or "facility-info",
                "sources": ["fallback"],
            },
        }
