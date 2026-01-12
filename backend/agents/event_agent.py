"""
EventAgent - イベント情報エージェント
イベント、カレンダー情報に関する質問に回答
"""

from typing import Dict, Optional
from tools.calendar_service import CalendarService
from llm import get_llm_provider, get_model_config


class EventAgent:
    """イベント情報エージェント"""

    def __init__(self):
        """初期化"""
        self.calendar_service = CalendarService()
        self.llm_provider = get_llm_provider()

    async def answer_event_query(
        self, query: str, language: str = "ja", session_id: Optional[str] = None
    ) -> Dict:
        """
        イベントクエリに回答

        Args:
            query: ユーザークエリ
            language: 言語（ja or en）
            session_id: セッションID

        Returns:
            回答辞書 {answer, emotion, metadata}
        """
        print(f"[EventAgent] Processing query: {query}, language: {language}")

        # クエリから時間範囲を抽出
        time_range = self.calendar_service.extract_time_range_from_query(query)

        # Calendar Serviceでイベント取得
        calendar_result = await self.calendar_service.search_events(time_range)

        if not calendar_result.get("success"):
            return self._get_no_events_response(language, time_range)

        # イベントデータ取得
        events = calendar_result.get("data", {}).get("events", [])
        event_count = calendar_result.get("data", {}).get("eventCount", 0)

        # イベントなしの場合
        if event_count == 0:
            return self._get_no_events_response(language, time_range)

        # イベント情報を整形してプロンプト構築
        events_text = self._format_calendar_events(events, language)
        prompt = self._build_event_prompt(query, events_text, time_range, language)

        # LLM応答生成
        try:
            response_text = await self.llm_provider.generate(
                messages=[{"role": "user", "content": prompt}],
                config=get_model_config("event_info"),
            )

            # イベントがある場合は happy
            emotion = "happy" if event_count > 0 else "sad"

            return {
                "answer": response_text,
                "emotion": emotion,
                "metadata": {
                    "agent": "EventAgent",
                    "time_range": time_range,
                    "event_count": event_count,
                },
            }

        except Exception as e:
            print(f"[EventAgent] LLM error: {e}")
            return self._get_no_events_response(language, time_range)

    def _format_calendar_events(self, events: list, language: str) -> str:
        """カレンダーイベントを整形"""
        if not events:
            return ""

        formatted_lines = []

        for event in events:
            title = event.get("title", "No Title")
            start = event.get("start", "")
            description = event.get("description", "")
            _location = event.get("location", "")  # Reserved for future use

            # 日時を整形
            start_str = start[:10] if start else "日時不明"

            if language == "en":
                event_line = f"- {title} ({start_str})"
                if description:
                    event_line += f" - {description[:100]}"
            else:
                event_line = f"- {title}（{start_str}）"
                if description:
                    event_line += f" - {description[:100]}"

            formatted_lines.append(event_line)

        return "\n".join(formatted_lines)

    def _build_event_prompt(
        self, query: str, events_text: str, time_range: str, language: str
    ) -> str:
        """イベント情報のプロンプト構築"""
        if language == "en":
            time_range_text = {
                "today": "today",
                "thisWeek": "this week",
                "nextWeek": "next week",
                "thisMonth": "this month",
            }.get(time_range, "this week")

            return f"""Based on the following event information for {time_range_text}, answer the question.

Question: {query}

Events {time_range_text}:
{events_text}

Provide a brief and friendly summary of the events. Start your response with [happy] emotion tag.
Maximum 2-3 sentences."""

        else:
            time_range_text = {
                "today": "本日",
                "thisWeek": "今週",
                "nextWeek": "来週",
                "thisMonth": "今月",
            }.get(time_range, "今週")

            return f"""{time_range_text}のイベント情報に基づいて、質問に答えてください。

質問: {query}

{time_range_text}のイベント:
{events_text}

イベントについて簡潔でフレンドリーな説明を提供してください。[happy]の感情タグで回答を始めてください。
最大2-3文。"""

    def _get_no_events_response(self, language: str, time_range: str) -> Dict:
        """イベントなし時の応答"""
        if language == "en":
            time_range_text = {
                "today": "today",
                "thisWeek": "this week",
                "nextWeek": "next week",
                "thisMonth": "this month",
            }.get(time_range, "this week")

            text = f"[sad]I'm sorry, there are no scheduled events for {time_range_text}. Please check back later or contact our staff for the latest information."
        else:
            time_range_text = {
                "today": "本日",
                "thisWeek": "今週",
                "nextWeek": "来週",
                "thisMonth": "今月",
            }.get(time_range, "今週")

            text = f"[sad]申し訳ございません。{time_range_text}の予定されているイベントはございません。後ほどご確認いただくか、スタッフまでお問い合わせください。"

        return {
            "answer": text,
            "emotion": "sad",
            "metadata": {"agent": "EventAgent", "time_range": time_range, "event_count": 0},
        }
