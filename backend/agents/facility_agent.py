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
        if cached and cached.get("success") and cached.get("category") == "facility-info":
            context = cached.get("context_string", "")
            logger.info("Using cached RAG results for facility-info")
        else:
            # クエリ拡張（requestTypeに応じて）
            enhanced_query = self._enhance_query(query, request_type, language)

            # Enhanced RAG検索
            rag_result = await self.enhanced_rag.search(
                query=enhanced_query,
                category="facility-info",
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
                    "category": "facility-info",
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
        if request_type == "access" or self._asks_location(normalized):
            answers = {
                "ja": (
                    "[relaxed]エンジニアカフェは福岡市中央区天神1丁目15番30号、"
                    "福岡市赤煉瓦文化館の中にあります。地下鉄空港線の天神駅から"
                    "徒歩約5分で、16番出口から昭和通りを東へ進むと赤煉瓦の建物が目印です。"
                    "専用駐車場はないため、車の場合は天神地下街など近隣の有料駐車場を"
                    "利用してください。"
                ),
                "en": (
                    "[relaxed]Engineer Cafe is inside the Fukuoka City Red Brick "
                    "Culture Hall at 1-15-30 Tenjin, Chuo-ku, Fukuoka. It is about a "
                    "5-minute walk from Tenjin Station and is also close to the "
                    "Tenjin 4-chome bus stop. Please ask staff if you need help on arrival."
                ),
                "zh": (
                    "[relaxed]工程师咖啡位于福冈市中央区天神1丁目15番30号的"
                    "福冈市赤炼瓦文化馆内，在一楼，进门后左手边可以找到接待处。"
                    "从天神站步行约5分钟。"
                ),
                "ko": (
                    "[relaxed]엔지니어 카페는 후쿠오카시 주오구 텐진 1-15-30, "
                    "아카렌가 문화관 안에 있습니다. 텐진역에서 걸어서 약 5분 "
                    "거리이며 니시테츠 버스 텐진 4초메 정류장에서도 가깝습니다. "
                    "방문 시 직원에게 문의하시면 안내받을 수 있어요."
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
            "饮料",
            "음식",
            "음료",
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
