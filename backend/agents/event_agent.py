"""
EventAgent - イベント情報エージェント
イベント、カレンダー情報に関する質問に回答

Google CalendarとConnpassの両方からイベント情報を取得し、統合して応答します。
"""

import asyncio
import logging
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage

from backend.config.prompts.event_prompts import build_event_prompt, get_time_range_label
from backend.llm import get_llm_provider, get_model_config
from backend.tools.calendar_service import CalendarService
from backend.tools.connpass_service import ConnpassService

logger = logging.getLogger(__name__)


class EventAgent:
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
        self.llm_provider = get_llm_provider()

    async def answer_event_query(
        self, query: str, language: str = "ja", session_id: Optional[str] = None
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
                "answer": "[happy]今週はPythonワークショップ（2024-01-15）とデザイン勉強会（2024-01-17）がございます。",
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
                "answer": "[sad]申し訳ございません。本日の予定されているイベントはございません。...",
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
        logger.info(f"Processing query: {query[:50]}..., language: {language}")

        # クエリから時間範囲を抽出
        time_range = self.calendar_service.extract_time_range_from_query(query)

        # クエリからキーワードを抽出（Connpass用）
        keyword = self.connpass_service.extract_keyword_from_query(query)

        # Google CalendarとConnpassを並列検索
        calendar_result, connpass_result = await asyncio.gather(
            self.calendar_service.search_events(time_range),
            self.connpass_service.search_events(time_range, keyword=keyword),
        )

        # 両方の結果をマージ
        events = self._merge_events(calendar_result, connpass_result)
        event_count = len(events)

        # イベントなしの場合
        if event_count == 0:
            return self._get_no_events_response(language, time_range)

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

            # ソース別のイベント数をカウント
            calendar_count = sum(1 for e in events if e.get("source") == "google_calendar")
            connpass_count = sum(1 for e in events if e.get("source") == "connpass")

            return {
                "answer": response_text,
                "emotion": emotion,
                "metadata": {
                    "agent": "EventAgent",
                    "time_range": time_range,
                    "event_count": event_count,
                    "sources": {
                        "google_calendar": calendar_count,
                        "connpass": connpass_count,
                    },
                },
            }

        except Exception as e:
            logger.error(f"LLM error: {e}")
            return self._get_no_events_response(language, time_range)

    def _format_calendar_events(self, events: list, language: str) -> str:
        """イベントを整形（Google Calendar + Connpass両対応）

        Google CalendarとConnpassのイベントをLLMに渡しやすい形式に整形します。

        Args:
            events (list): イベントのリスト（source フィールドでソース判定）
            language (str): 言語（ja or en）

        Returns:
            str: 整形されたイベント情報（箇条書き形式）

        Examples:
            >>> agent = EventAgent()
            >>> events = [
            ...     {"title": "Workshop", "start": "2024-01-15T14:00:00", "source": "google_calendar"}
            ... ]
            >>> formatted = agent._format_calendar_events(events, "ja")
            >>> print(formatted)
            - Workshop（2024-01-15）[カレンダー]

        Notes:
            - 日時はISO8601形式からYYYY-MM-DDに変換
            - 説明文は100文字に制限してトークン数を削減
            - Connpassの場合は参加者数も表示
            - 空のイベントリストには空文字列を返す
        """
        if not events:
            return ""

        formatted_lines = []

        for event in events:
            title = event.get("title", "No Title")
            start = event.get("start", "")
            description = event.get("description", "")
            source = event.get("source", "unknown")
            location = event.get("location", "")

            # 日時を整形
            start_str = start[:10] if start else "日時不明"

            # ソースラベル
            if language == "en":
                source_label = "[Calendar]" if source == "google_calendar" else "[Connpass]"
            else:
                source_label = "[カレンダー]" if source == "google_calendar" else "[Connpass]"

            # Connpassの場合は参加者情報を追加
            participant_info = ""
            if source == "connpass":
                accepted = event.get("accepted", 0)
                limit = event.get("limit")
                if limit:
                    if language == "en":
                        participant_info = f" ({accepted}/{limit} participants)"
                    else:
                        participant_info = f"（{accepted}/{limit}名参加）"
                elif accepted > 0:
                    if language == "en":
                        participant_info = f" ({accepted} participants)"
                    else:
                        participant_info = f"（{accepted}名参加）"

            if language == "en":
                event_line = f"- {title} ({start_str}){participant_info} {source_label}"
                if location:
                    event_line += f" @ {location}"
                if description:
                    event_line += f" - {description[:80]}"
            else:
                event_line = f"- {title}（{start_str}）{participant_info} {source_label}"
                if location:
                    event_line += f" @ {location}"
                if description:
                    event_line += f" - {description[:80]}"

            formatted_lines.append(event_line)

        return "\n".join(formatted_lines)

    def _build_event_prompt(
        self, query: str, events_text: str, time_range: str, language: str
    ) -> str:
        """イベント情報のプロンプトを構築（外部テンプレートに委譲）"""
        return build_event_prompt(query, events_text, time_range, language)

    def _get_no_events_response(self, language: str, time_range: str) -> Dict:
        """イベントなし時の応答を返す"""
        time_range_text = get_time_range_label(time_range, language)

        if language == "en":
            text = f"[sad]I'm sorry, there are no scheduled events for {time_range_text}. Please check back later or contact our staff for the latest information."
        else:
            text = f"[sad]申し訳ございません。{time_range_text}の予定されているイベントはございません。後ほどご確認いただくか、スタッフまでお問い合わせください。"

        return {
            "answer": text,
            "emotion": "sad",
            "metadata": {"agent": "EventAgent", "time_range": time_range, "event_count": 0},
        }

    @staticmethod
    def _normalize_title(title: str) -> str:
        """イベントタイトルを正規化して重複比較に使用

        空白除去、全角→半角変換、エディション番号除去など
        """
        import re
        import unicodedata

        # NFKC正規化（全角→半角等）
        normalized = unicodedata.normalize("NFKC", title)
        # 小文字化
        normalized = normalized.lower()
        # エディション番号除去（#1, #2, Vol.1, vol.2等）
        normalized = re.sub(r"[#＃]?\d+", "", normalized)
        normalized = re.sub(r"vol\.?\s*\d*", "", normalized, flags=re.IGNORECASE)
        # 余分な空白除去
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def _merge_events(self, calendar_result: Dict, connpass_result: Dict) -> List[Dict]:
        """Google CalendarとConnpassのイベントをマージ（重複排除付き）

        両方のソースからイベントを取得し、タイトルの正規化ベースで
        重複を排除してから開始日時順にソートして返す。

        Google Calendar優先: 重複時はGoogle Calendarの情報を優先する。

        Args:
            calendar_result: CalendarServiceの結果
            connpass_result: ConnpassServiceの結果

        Returns:
            重複排除済み、開始日時順のイベントリスト
        """
        events: List[Dict] = []
        seen_titles: set[str] = set()

        # Google Calendarイベント（優先: 先に登録）
        if calendar_result.get("success"):
            calendar_events = calendar_result.get("data", {}).get("events", [])
            for event in calendar_events:
                normalized = self._normalize_title(event.get("title", ""))
                if normalized and normalized not in seen_titles:
                    seen_titles.add(normalized)
                    events.append({**event, "source": "google_calendar"})

        # Connpassイベント（重複時はスキップ）
        if connpass_result.get("success"):
            connpass_events = connpass_result.get("data", {}).get("events", [])
            for event in connpass_events:
                normalized = self._normalize_title(event.get("title", ""))
                if normalized and normalized not in seen_titles:
                    seen_titles.add(normalized)
                    events.append(event)

        # 開始日時でソート
        events.sort(key=lambda e: e.get("start", "") or "")

        return events
