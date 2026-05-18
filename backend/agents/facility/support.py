from __future__ import annotations

import logging
from typing import Dict, Optional

from langchain_core.messages import HumanMessage

from backend.llm import get_model_config
from backend.utils.language_types import DEFAULT_NOT_FOUND_RESPONSE

logger = logging.getLogger(__name__)


class FacilitySupportMixin:
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
