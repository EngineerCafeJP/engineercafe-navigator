"""
Web Search Tool using Google Gemini API with Google Search Grounding

Google Gemini APIのGoogle Search Grounding機能を使用したWeb検索ツール。
最新情報や一般的な知識を取得するために使用される。

参考:
- https://ai.google.dev/docs/grounding_with_google_search
"""

import logging
import os
from typing import Dict, Any, List, Optional, Literal
import google.generativeai as genai

logger = logging.getLogger(__name__)

SupportedLanguage = Literal["ja", "en"]


class Source:
    """Web検索のソース情報"""

    def __init__(self, uri: str, title: str):
        self.uri = uri
        self.title = title

    def to_dict(self) -> Dict[str, str]:
        return {"uri": self.uri, "title": self.title}


class WebSearchTool:
    """
    Google Gemini API with Google Search Grounding を使用したWeb検索ツール

    使用例:
        tool = WebSearchTool()
        result = await tool.search("最新のAI技術", language="ja")
        print(result["text"])  # 検索結果のテキスト
        print(result["sources"])  # ソース情報のリスト
    """

    def __init__(self):
        """
        初期化

        環境変数:
            GOOGLE_API_KEY: Gemini API Key
            GEMINI_MODEL: 使用するモデル名 (デフォルト: gemini-2.0-flash-exp)

        Note:
            APIキーが設定されていない場合は警告を出して初期化する。
            実際の検索時にAPIキーがないとエラーを発生させる。
        """
        self.name = "web_search"
        self.description = "一般的な質問に対してGoogle検索で最新情報を取得"
        self.model = None
        self._api_key = None
        self._model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

        # API Key取得（遅延初期化対応）
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        if not api_key:
            logger.warning(
                "GOOGLE_API_KEY or GOOGLE_GENERATIVE_AI_API_KEY not set. "
                "Web search will fail at runtime."
            )
        else:
            self._api_key = api_key
            # Gemini API設定
            genai.configure(api_key=api_key)
            # モデル初期化
            self.model = genai.GenerativeModel(self._model_name)
            logger.info(f"WebSearchTool initialized with model: {self._model_name}")

    async def search(
        self, query: str, language: SupportedLanguage = "ja", context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Web検索を実行

        Args:
            query: 検索クエリ
            language: 言語設定 ("ja" or "en")
            context: 追加コンテキスト (オプショナル)

        Returns:
            {
                "success": bool,
                "text": str,  # 検索結果のテキスト
                "sources": List[Dict],  # ソース情報のリスト
                "error": Optional[str]
            }
        """
        # APIキーチェック
        if not self._api_key or not self.model:
            logger.error("WebSearchTool: API key not configured")
            return {
                "success": False,
                "text": "",
                "sources": [],
                "error": "GOOGLE_API_KEY or GOOGLE_GENERATIVE_AI_API_KEY is required",
            }

        try:
            logger.info(f"Web search started: query={query[:50]}..., language={language}")

            # プロンプト構築
            prompt = query
            if context:
                prompt = f"{context}\n\n質問: {query}"

            # システムインストラクション
            system_instruction = self._get_system_instruction(language)

            # Google Search Grounding を有効にして生成
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=500,
                ),
                safety_settings={
                    genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                },
                tools=[{"google_search": {}}],  # Google Search Grounding有効化
                system_instruction=system_instruction,  # システムインストラクション追加
            )

            # レスポンステキスト取得
            text = response.text

            # ソース情報抽出
            sources = self._extract_sources(response)

            logger.info(f"Web search completed: {len(text)} chars, {len(sources)} sources")

            return {"success": True, "text": text, "sources": sources}

        except Exception as e:
            logger.error(f"Web search error: {e}", exc_info=True)
            return {
                "success": False,
                "text": "",
                "sources": [],
                "error": str(e),
            }

    def _get_system_instruction(self, language: SupportedLanguage) -> str:
        """システムインストラクション取得"""
        if language == "ja":
            return """あなたは親切なAIアシスタントです。質問に対してGoogle検索を使って最新で正確な情報を提供してください。
回答は簡潔で分かりやすく、1-2文程度でお願いします。
情報源がある場合は信頼できるソースを優先してください。"""
        else:
            return """You are a helpful AI assistant. Use Google search to provide current and accurate information for questions.
Keep responses brief and clear - typically 1-2 sentences.
Prioritize reliable sources when available."""

    def _extract_sources(self, response) -> List[Dict[str, str]]:
        """
        レスポンスからソース情報を抽出

        Args:
            response: Gemini APIのレスポンス

        Returns:
            ソース情報のリスト [{"uri": str, "title": str}, ...]
        """
        sources = []

        try:
            # candidates[0].grounding_metadata.grounding_chunks から抽出
            if (
                hasattr(response, "candidates")
                and response.candidates
                and len(response.candidates) > 0
            ):
                candidate = response.candidates[0]
                if hasattr(candidate, "grounding_metadata"):
                    grounding_metadata = candidate.grounding_metadata
                    if hasattr(grounding_metadata, "grounding_chunks"):
                        for chunk in grounding_metadata.grounding_chunks:
                            if hasattr(chunk, "web") and chunk.web:
                                web_source = chunk.web
                                uri = getattr(web_source, "uri", None)
                                title = getattr(web_source, "title", None)

                                if uri:
                                    # titleがない場合はドメイン名を使用
                                    if not title:
                                        try:
                                            from urllib.parse import urlparse

                                            title = urlparse(uri).hostname or uri
                                        except Exception:
                                            title = uri

                                    sources.append({"uri": uri, "title": title})

        except Exception as e:
            logger.warning(f"Failed to extract sources: {e}")

        return sources

    def format_results_with_sources(
        self, text: str, sources: List[Dict[str, str]], language: SupportedLanguage
    ) -> str:
        """
        検索結果とソース情報をフォーマット

        Args:
            text: 検索結果テキスト
            sources: ソース情報のリスト
            language: 言語設定

        Returns:
            フォーマットされたテキスト
        """
        if not sources:
            return text

        sources_title = "情報源:" if language == "ja" else "Sources:"
        formatted = f"{text}\n\n{sources_title}\n"

        for i, source in enumerate(sources, 1):
            formatted += f"{i}. {source['title']}: {source['uri']}\n"

        return formatted

    @staticmethod
    def should_use_web_search(query: str) -> bool:
        """
        Web検索が必要かどうか判定

        Args:
            query: ユーザーの質問

        Returns:
            True: Web検索が必要, False: ナレッジベースのみで十分
        """
        lower_query = query.lower()

        # キーワードベース判定
        web_search_keywords = [
            # 最新情報・ニュース関連（日本語）
            "最新",
            "現在",
            "今",
            "今日",
            "昨日",
            "ニュース",
            "トレンド",
            # スタートアップ・技術関連（日本語）
            "スタートアップ",
            "ベンチャー",
            "技術",
            "ai",
            "人工知能",
            "機械学習",
            "プログラミング",
            # スポーツ関連（日本語）
            "野球",
            "サッカー",
            "試合",
            "結果",
            "スコア",
            "ホークス",
            "ソフトバンク",
            # 天気関連（日本語）
            "天気",
            "気温",
            "雨",
            # 最新情報・ニュース関連（英語）
            "latest",
            "current",
            "now",
            "today",
            "yesterday",
            "news",
            "trend",
            # スタートアップ・技術関連（英語）
            "startup",
            "venture",
            "technology",
            "artificial intelligence",
            "machine learning",
            "programming",
            # スポーツ関連（英語）
            "baseball",
            "soccer",
            "game",
            "result",
            "score",
            "hawks",
            "softbank",
            # 天気関連（英語）
            "weather",
            "temperature",
            "rain",
        ]

        return any(keyword in lower_query for keyword in web_search_keywords)


# シングルトンインスタンス（必要に応じて）
_web_search_tool_instance: Optional[WebSearchTool] = None


def get_web_search_tool() -> WebSearchTool:
    """WebSearchToolのシングルトンインスタンスを取得"""
    global _web_search_tool_instance
    if _web_search_tool_instance is None:
        _web_search_tool_instance = WebSearchTool()
    return _web_search_tool_instance
