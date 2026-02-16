"""
Tavily Web Search Tool

Tavily APIを使用したWeb検索ツール。
既存のWebSearchTool(Gemini)を置き換え、より精度の高い検索を提供。
"""

import logging
import os
from typing import Dict, Any, List, Literal

logger = logging.getLogger(__name__)

SupportedLanguage = Literal["ja", "en"]


class TavilySearchTool:
    """
    Tavily APIを使用したWeb検索ツール

    TAVILY_API_KEY が設定されていない場合は client=None で初期化し、
    search() 時に WebSearchTool(Gemini) にフォールバック。
    """

    def __init__(self):
        self.name = "tavily_search"
        self.client = None

        api_key = os.getenv("TAVILY_API_KEY")
        if api_key:
            try:
                from tavily import TavilyClient

                self.client = TavilyClient(api_key=api_key)
                logger.info("TavilySearchTool initialized with API key")
            except ImportError:
                logger.warning("tavily-python not installed, falling back to WebSearchTool")
            except Exception as e:
                logger.warning(f"Tavily client init failed: {e}")
        else:
            logger.warning("TAVILY_API_KEY not set, will fall back to WebSearchTool")

    async def search(
        self,
        query: str,
        language: SupportedLanguage = "ja",
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """
        Web検索を実行

        Tavily client が利用可能な場合はTavily APIを使用。
        利用不可の場合はWebSearchTool(Gemini)にフォールバック。

        Returns:
            {"success": bool, "text": str, "results": List[Dict], "sources": List[Dict]}
        """
        if not self.client:
            return await self._fallback_search(query, language)

        try:
            search_params = {
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": True,
            }

            response = self.client.search(**search_params)

            answer = response.get("answer", "")
            results = response.get("results", [])

            sources: List[Dict[str, str]] = [
                {"uri": r.get("url", ""), "title": r.get("title", "")}
                for r in results
                if r.get("url")
            ]

            text_parts: List[str] = []
            if answer:
                text_parts.append(answer)
            for r in results[:3]:
                content = r.get("content", "")
                if content:
                    text_parts.append(content)

            text = "\n\n".join(text_parts)

            logger.info(f"Tavily search completed: {len(text)} chars, {len(sources)} sources")

            return {
                "success": True,
                "text": text,
                "results": results,
                "sources": sources,
            }

        except Exception as e:
            logger.error(f"Tavily search error: {e}", exc_info=True)
            return await self._fallback_search(query, language)

    async def _fallback_search(
        self, query: str, language: SupportedLanguage = "ja"
    ) -> Dict[str, Any]:
        """WebSearchTool(Gemini)にフォールバック"""
        try:
            from backend.tools.web_search import WebSearchTool

            fallback = WebSearchTool()
            result = await fallback.search(query=query, language=language)
            logger.info("Fell back to WebSearchTool (Gemini)")
            return {
                "success": result.get("success", False),
                "text": result.get("text", ""),
                "results": [],
                "sources": result.get("sources", []),
            }
        except Exception as e:
            logger.error(f"Fallback search also failed: {e}")
            return {"success": False, "text": "", "results": [], "sources": []}

    @staticmethod
    def should_use_web_search(query: str) -> bool:
        """Web検索が必要かどうか判定（WebSearchToolに委譲）"""
        from backend.tools.web_search import WebSearchTool

        return WebSearchTool.should_use_web_search(query)
