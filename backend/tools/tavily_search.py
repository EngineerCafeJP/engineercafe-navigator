"""
Tavily Web Search Tool

Tavily APIを使用したWeb検索ツール。
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
    search() 時に空結果を返す。
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
                logger.warning("tavily-python not installed")
            except Exception as e:
                logger.warning("Tavily client init failed: %s", e)
        else:
            logger.warning("TAVILY_API_KEY not set, web search unavailable")

    async def search(
        self,
        query: str,
        language: SupportedLanguage = "ja",
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Web検索を実行"""
        if not self.client:
            return {"success": False, "text": "", "results": [], "sources": []}

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

            logger.info("Tavily search completed: %d chars, %d sources", len(text), len(sources))

            return {
                "success": True,
                "text": text,
                "results": results,
                "sources": sources,
            }

        except Exception as e:
            logger.exception("Tavily search error: %s", e)
            return {"success": False, "text": "", "results": [], "sources": []}

    @staticmethod
    def should_use_web_search(query: str) -> bool:
        """Web検索が必要かどうか判定"""
        from backend.tools.web_search import should_use_web_search

        return should_use_web_search(query)
