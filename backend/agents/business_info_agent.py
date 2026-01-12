"""
BusinessInfoAgent - 営業情報エージェント
営業時間、料金、場所に関する質問に回答
"""

from typing import Dict, Optional
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.llm import get_llm_provider, get_model_config


class BusinessInfoAgent:
    """営業情報エージェント"""

    def __init__(self):
        """初期化"""
        self.enhanced_rag = EnhancedRAGSearch()
        self.llm_provider = get_llm_provider()

    async def answer_business_query(
        self,
        query: str,
        request_type: Optional[str] = None,
        language: str = "ja",
        session_id: Optional[str] = None,
    ) -> Dict:
        """
        営業情報クエリに回答

        Args:
            query: ユーザークエリ
            request_type: リクエストタイプ（hours, price, location）
            language: 言語（ja or en）
            session_id: セッションID

        Returns:
            回答辞書 {answer, emotion, metadata}
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
        """requestTypeをEnhanced RAGカテゴリにマッピング"""
        category_mapping = {
            "hours": "hours",
            "price": "pricing",
            "location": "location",
            "access": "location",
            "basement": "facility-info",
            "facility": "facility-info",
            "wifi": "facility-info",
        }

        return category_mapping.get(request_type or "", "general")

    def _build_prompt(
        self, query: str, context: str, request_type: Optional[str], language: str
    ) -> str:
        """プロンプト構築"""
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
        if request_type in ["hours", "price"]:
            return "informative"
        elif request_type == "location":
            return "guiding"

        return "helpful"

    def _get_default_response(self, language: str, request_type: Optional[str]) -> Dict:
        """デフォルト応答（情報が見つからない場合）"""
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
