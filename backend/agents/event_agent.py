"""
EventAgent - イベント情報エージェント
イベント、カレンダー情報に関する質問に回答

Google CalendarとConnpassの両方からイベント情報を取得し、統合して応答します。
"""

import asyncio
import logging
from typing import Dict, Optional

from langchain_core.messages import HumanMessage

from backend.agents.event.responses import EventResponseMixin
from backend.agents.llm_metadata import merge_llm_metadata
from backend.llm import get_llm_provider, get_model_config
from backend.services.sheets_event_source import SheetsEventSource
from backend.tools.calendar_service import CalendarService
from backend.tools.connpass_service import ConnpassService

logger = logging.getLogger(__name__)


class EventAgent(EventResponseMixin):
    """イベント情報エージェント

    Google Calendar APIからイベント情報を取得し、LLMで自然な応答を生成します。
    時間範囲をクエリから自動抽出し、適切なイベント情報を提供します。

    Attributes:
        calendar_service (CalendarService): Google Calendar APIサービス
        llm_provider (LLMProvider): LLMプロバイダー

    Examples:
        >>> agent = EventAgent()
        >>> result = await agent.answer_event_query(
        ...     query="今週のイベントは？",
        ...     language="ja"
        ... )
        >>> print(result["answer"])
        [happy]今週はPythonワークショップ（2024-01-15）とデザイン勉強会（2024-01-17）がございます。

    Notes:
        - クエリから時間範囲（今日、今週、来週、今月）を自動抽出
        - イベントがない場合は適切なフォールバック応答を返す
        - API失敗時もユーザーフレンドリーなエラーメッセージを提供
    """

    def __init__(self):
        """EventAgentを初期化

        CalendarService、ConnpassService、LLMプロバイダーのインスタンスを作成します。
        """
        self.calendar_service = CalendarService()
        self.connpass_service = ConnpassService()
        self.sheets_event_source = SheetsEventSource()
        self.llm_provider = get_llm_provider()

    async def answer_event_query(
        self,
        query: str,
        language: str = "ja",
        session_id: Optional[str] = None,
        *,
        include_evidence: bool = False,
    ) -> Dict:
        """イベントクエリに回答

        Google Calendar APIからイベント情報を取得し、LLMで自然な応答を生成します。
        クエリから時間範囲を自動抽出し、該当するイベントを検索します。

        Args:
            query (str): ユーザーからの質問文
                例: "今日のイベントは？", "今週のワークショップは？", "来週の予定は？"
            language (str): 応答言語。デフォルトは"ja"
                - "ja": 日本語
                - "en": 英語
            session_id (Optional[str]): セッションID（将来の拡張用）

        Returns:
            Dict: 回答辞書
                - answer (str): 回答テキスト。感情タグ付き
                - emotion (str): 感情タグ（happy: イベントあり, sad: イベントなし）
                - metadata (Dict): メタデータ
                    - agent (str): "EventAgent"
                    - time_range (str): 検索時間範囲（today, thisWeek, nextWeek, thisMonth）
                    - event_count (int): イベント数

        Examples:
            >>> agent = EventAgent()
            >>> result = await agent.answer_event_query(
            ...     query="今週のイベントは？",
            ...     language="ja"
            ... )
            >>> print(result)
            {
                "answer": "[happy]今週はPythonワークショップ"
                "（2024-01-15）と"
                "デザイン勉強会（2024-01-17）が"
                "ございます。",
                "emotion": "happy",
                "metadata": {
                    "agent": "EventAgent",
                    "time_range": "thisWeek",
                    "event_count": 2
                }
            }

            >>> # イベントがない場合
            >>> result = await agent.answer_event_query(
            ...     query="今日のイベントは？",
            ...     language="ja"
            ... )
            >>> print(result)
            {
                "answer": "[sad]申し訳ございません。"
                "本日の予定されているイベントはございません。...",
                "emotion": "sad",
                "metadata": {
                    "agent": "EventAgent",
                    "time_range": "today",
                    "event_count": 0
                }
            }

        Notes:
            - 時間範囲はクエリから自動抽出（"今日"→today, "今週"→thisWeek等）
            - Calendar API失敗時はフォールバック応答を返す
            - イベント説明文は100文字に制限してトークン数を削減
        """
        logger.info("Processing query: %s..., language: %s", query[:50], language)

        if self._asks_event_hosting(query):
            return self._get_event_hosting_response(language)

        if self._asks_connpass(query):
            return self._get_connpass_response(language, include_evidence=include_evidence)

        if self._asks_hackathon_schedule(query):
            return self._get_hackathon_schedule_response(
                language, include_evidence=include_evidence
            )

        if self._asks_event_clarification(query):
            return self._get_event_clarification_response(language)

        # クエリから時間範囲を抽出
        time_range = self.calendar_service.extract_time_range_from_query(query)

        # クエリからキーワードを抽出（Connpass用）
        keyword = self.connpass_service.extract_keyword_from_query(query)

        # Spreadsheet、Google Calendar、Connpassを並列検索（タイムアウト付き）
        source_statuses = {
            "spreadsheet": "timeout",
            "google_calendar": "timeout",
            "connpass": "timeout",
        }
        try:
            spreadsheet_result, calendar_result, connpass_result = await asyncio.wait_for(
                asyncio.gather(
                    self.sheets_event_source.search_events(time_range),
                    self.calendar_service.search_events(time_range),
                    self.connpass_service.search_events(time_range, keyword=keyword),
                    return_exceptions=True,
                ),
                timeout=35.0,
            )
            # Handle individual service failures gracefully
            if isinstance(spreadsheet_result, Exception):
                logger.warning("Spreadsheet event search failed: %s", spreadsheet_result)
                spreadsheet_result = {"success": False, "data": {"events": []}}
            if isinstance(calendar_result, Exception):
                logger.warning("Calendar search failed: %s", calendar_result)
                calendar_result = {"success": False, "data": {"events": []}}
            if isinstance(connpass_result, Exception):
                logger.warning("Connpass search failed: %s", connpass_result)
                connpass_result = {"success": False, "data": {"events": []}}
        except asyncio.TimeoutError:
            logger.warning("Event search timed out after 35s for query: %s", query[:50])
            return self._get_no_events_response(
                language,
                time_range,
                searched_sources=[],
                source_statuses=source_statuses,
            )

        # 両方の結果をマージ
        events = self._merge_events(calendar_result, connpass_result, spreadsheet_result)
        event_count = len(events)
        sources = self._sources_from_events(events)
        searched_sources, source_statuses = self._source_search_metadata(
            spreadsheet_result,
            calendar_result,
            connpass_result,
        )

        # イベントなしの場合
        if event_count == 0:
            return self._get_no_events_response(
                language,
                time_range,
                sources=sources,
                searched_sources=searched_sources,
                source_statuses=source_statuses,
            )

        # イベント情報を整形してプロンプト構築
        events_text = self._format_calendar_events(events, language)
        prompt = self._build_event_prompt(query, events_text, time_range, language)

        # LLM応答生成
        try:
            response_text = await self.llm_provider.generate(
                messages=[HumanMessage(content=prompt)],
                config=get_model_config("event_info"),
            )

            # イベントがある場合は happy
            emotion = "happy" if event_count > 0 else "sad"

            # Issue #509 safety net: if the LLM ignored the grounding rule
            # and produced a [happy] response despite zero (filtered) events,
            # rewrite the emotion tag to [sad]. This is a last-line defence;
            # the prompt should already prevent this.
            response_text = self._enforce_emotion_tag(response_text, event_count)

            metadata = {
                "agent": "EventAgent",
                "category": "event",
                "request_type": "event",
                "route": "event",
                "time_range": time_range,
                "event_count": event_count,
                "sources": sources,
                "searched_sources": searched_sources,
                "source_statuses": source_statuses,
            }
            merge_llm_metadata(metadata, response_text)
            if include_evidence:
                metadata["rag_evidence"] = {
                    "source": "event_agent",
                    "category": "event",
                    "context_char_count": len(events_text),
                    "contexts": [events_text],
                    "results": [
                        {
                            "source": event.get("source", "unknown"),
                            "title": event.get("title"),
                            "start": event.get("start"),
                            "content": self._format_event_evidence_line(event, language),
                        }
                        for event in events[:10]
                    ],
                }

            return {
                "answer": str(response_text),
                "emotion": emotion,
                "metadata": metadata,
            }

        except Exception as e:
            logger.exception("LLM error: %s", e)
            return self._get_event_summary_response(
                events,
                language,
                time_range,
                sources=sources,
                searched_sources=searched_sources,
                source_statuses=source_statuses,
                include_evidence=include_evidence,
            )

    async def get_today_events(self, language: str = "ja") -> Dict:
        """本日のイベント情報を取得

        Google CalendarとConnpassから本日のイベントを検索し、統合して返す。
        受付案内や自動イベント紹介に使用。

        Args:
            language: 応答言語 ("ja" | "en")

        Returns:
            Dict with keys:
                - events (List[Dict]): イベントリスト
                - count (int): イベント数
                - formatted_text (str): 整形済みテキスト
                - has_events (bool): イベントがあるかどうか
        """
        try:
            spreadsheet_result, calendar_result, connpass_result = await asyncio.wait_for(
                asyncio.gather(
                    self.sheets_event_source.search_events("today"),
                    self.calendar_service.search_events("today"),
                    self.connpass_service.search_events("today"),
                    return_exceptions=True,
                ),
                timeout=35.0,
            )
            # Handle individual service failures gracefully
            if isinstance(spreadsheet_result, Exception):
                logger.warning("Spreadsheet event search failed: %s", spreadsheet_result)
                spreadsheet_result = {"success": False, "data": {"events": []}}
            if isinstance(calendar_result, Exception):
                logger.warning("Calendar search failed: %s", calendar_result)
                calendar_result = {"success": False, "data": {"events": []}}
            if isinstance(connpass_result, Exception):
                logger.warning("Connpass search failed: %s", connpass_result)
                connpass_result = {"success": False, "data": {"events": []}}

            events = self._merge_events(calendar_result, connpass_result, spreadsheet_result)
            formatted_text = self._format_calendar_events(events, language)

            return {
                "events": events,
                "count": len(events),
                "formatted_text": formatted_text,
                "has_events": len(events) > 0,
            }
        except Exception as e:
            logger.warning("Failed to get today's events: %s", e)
            return {
                "events": [],
                "count": 0,
                "formatted_text": "",
                "has_events": False,
            }
