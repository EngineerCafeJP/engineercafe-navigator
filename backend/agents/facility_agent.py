"""
FacilityAgent - 施設情報エージェント
Wi-Fi、電源、設備、地下施設に関する質問に回答
"""

from typing import Dict, Optional
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.llm import get_llm_provider, get_model_config


class FacilityAgent:
    """施設情報エージェント"""

    def __init__(self):
        """初期化"""
        self.enhanced_rag = EnhancedRAGSearch()
        self.llm_provider = get_llm_provider()

    async def answer_facility_query(
        self,
        query: str,
        request_type: Optional[str] = None,
        language: str = "ja",
        session_id: Optional[str] = None,
    ) -> Dict:
        """
        施設情報クエリに回答

        Args:
            query: ユーザークエリ
            request_type: リクエストタイプ（wifi, facility, basement）
            language: 言語（ja or en）
            session_id: セッションID

        Returns:
            回答辞書 {answer, emotion, metadata}
        """
        print(
            f"[FacilityAgent] Processing query: {query}, request_type: {request_type}, language: {language}"
        )

        # クエリ拡張（requestTypeに応じて）
        enhanced_query = self._enhance_query(query, request_type, language)

        # Enhanced RAG検索
        rag_result = await self.enhanced_rag.search(
            query=enhanced_query,
            category="facility-info",
            language=language,
            include_advice=True,
            max_results=10,
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
                messages=[{"role": "user", "content": prompt}],
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
            print(f"[FacilityAgent] LLM error: {e}")
            return self._get_default_response(language, request_type)

    def _enhance_query(self, query: str, request_type: Optional[str], language: str) -> str:
        """クエリ拡張ロジック"""
        # requestTypeに応じたキーワード追加
        enhancement_keywords = {
            "wifi": {
                "ja": "無料Wi-Fi インターネット 接続方法 パスワード",
                "en": "free Wi-Fi internet connection method password",
            },
            "facility": {
                "ja": "設備 電源 コンセント プリンター 利用方法",
                "en": "facilities power outlet printer usage",
            },
            "basement": {
                "ja": "地下 B1 MTGスペース 集中スペース アンダースペース Makersスペース 予約 利用方法",
                "en": "basement B1 MTG space focus space under space makers space reservation",
            },
        }

        if request_type in enhancement_keywords:
            keywords = enhancement_keywords[request_type].get(
                language, enhancement_keywords[request_type].get("ja", "")
            )
            return f"{query} {keywords}"

        return query

    def _filter_basement_context(self, context: str, query: str, language: str) -> str:
        """地下施設に関連するコンテキストのみに絞り込む"""
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
        """プロンプト構築"""
        print(
            f"[FacilityAgent] Building prompt with query_length: {len(query)}, context_length: {len(context)}, request_type: {request_type}, language: {language}"
        )

        # requestTypeに応じたプロンプト
        if request_type:
            request_type_prompt = self._get_request_type_prompt(request_type, language)

            if language == "en":
                return f"""Extract ONLY the {request_type_prompt} from the following information to answer the question.

Question: {query}
Information: {context}

Answer with ONLY the {request_type_prompt}. Maximum 2-3 sentences. Do not include any other information.
IMPORTANT: Start your response with [relaxed] for information or [happy] for positive news."""
            else:
                return f"""次の情報から{request_type_prompt}のみを抽出して質問に答えてください。

質問: {query}
情報: {context}

{request_type_prompt}のみを答えてください。最大2-3文。他の情報は含めないでください。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。"""

        else:
            if language == "en":
                return f"""Answer the question using the provided information. Be concise and direct.

Question: {query}
Information: {context}

Answer briefly (2-3 sentences) with only the relevant information.
IMPORTANT: Start your response with an emotion tag: [relaxed] for information, [happy] for positive news, [sad] for unavailable services."""
            else:
                return f"""提供された情報を使って質問に答えてください。簡潔で直接的に答えてください。

質問: {query}
情報: {context}

関連する情報のみを簡潔に（2-3文）答えてください。
重要: 感情タグで回答を始めてください: 情報提供は[relaxed]、良いニュースは[happy]、利用できないサービスは[sad]。"""

    def _get_request_type_prompt(self, request_type: str, language: str) -> str:
        """requestTypeに応じたプロンプト文言を取得"""
        prompt_map = {
            "wifi": {"en": "Wi-Fi information", "ja": "Wi-Fi情報"},
            "facility": {"en": "facility information", "ja": "設備情報"},
            "basement": {"en": "basement facility information", "ja": "地下施設情報"},
        }

        prompt = prompt_map.get(
            request_type, {"en": "requested information", "ja": "要求された情報"}
        )
        return prompt.get(language, prompt.get("ja", ""))

    def _determine_emotion(self, request_type: Optional[str], response_text: str) -> str:
        """感情タグを決定"""
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

    def _get_default_response(self, language: str, request_type: Optional[str]) -> Dict:
        """デフォルト応答（情報が見つからない場合）"""
        if language == "en":
            text = "[sad]I'm sorry, I couldn't find the specific facility information you're looking for. Please try rephrasing your question or contact the staff for assistance."
        else:
            text = "[sad]申し訳ございません。お探しの施設情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。"

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
