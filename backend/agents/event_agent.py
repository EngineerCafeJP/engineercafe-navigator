"""
EventAgent - イベント情報エージェント
イベント、カレンダー情報に関する質問に回答
"""

from typing import Dict, Optional
from backend.tools.calendar_service import CalendarService
from backend.llm import get_llm_provider, get_model_config


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

        CalendarServiceとLLMプロバイダーのインスタンスを作成します。
        """
        self.calendar_service = CalendarService()
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
        """カレンダーイベントを整形

        Google Calendar APIの生データをLLMに渡しやすい形式に整形します。

        Args:
            events (list): Google Calendar APIから取得したイベントのリスト
            language (str): 言語（ja or en）

        Returns:
            str: 整形されたイベント情報（箇条書き形式）

        Examples:
            >>> agent = EventAgent()
            >>> events = [
            ...     {"title": "Workshop", "start": "2024-01-15T14:00:00", "description": "Python basics"}
            ... ]
            >>> formatted = agent._format_calendar_events(events, "ja")
            >>> print(formatted)
            - Workshop（2024-01-15） - Python basics

        Notes:
            - 日時はISO8601形式からYYYY-MM-DDに変換
            - 説明文は100文字に制限してトークン数を削減
            - 空のイベントリストには空文字列を返す
        """
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
        """イベント情報のプロンプトを構築

        整形済みイベント情報をLLMプロンプトに組み込みます。
        時間範囲を明示し、簡潔でフレンドリーな応答を促します。

        Args:
            query (str): ユーザークエリ
            events_text (str): 整形済みイベント情報
            time_range (str): 時間範囲（today, thisWeek, nextWeek, thisMonth）
            language (str): 言語（ja or en）

        Returns:
            str: 構築されたプロンプト

        Examples:
            >>> agent = EventAgent()
            >>> prompt = agent._build_event_prompt(
            ...     query="今週のイベントは？",
            ...     events_text="- Workshop（2024-01-15）",
            ...     time_range="thisWeek",
            ...     language="ja"
            ... )
            >>> print(prompt)
            今週のイベント情報に基づいて、質問に答えてください。

            質問: 今週のイベントは？

            今週のイベント:
            - Workshop（2024-01-15）

            イベントについて簡潔でフレンドリーな説明を提供してください。[happy]の感情タグで回答を始めてください。
            最大2-3文。

        Notes:
            - 時間範囲を日本語/英語に変換（thisWeek→"今週"/"this week"）
            - [happy]の感情タグの埋め込みを指示
            - 最大2-3文の簡潔な応答を促す
        """
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
        """イベントなし時の応答を返す

        指定時間範囲にイベントがない場合のフォールバック応答を生成します。

        Args:
            language (str): 言語（ja or en）
            time_range (str): 時間範囲（today, thisWeek, nextWeek, thisMonth）

        Returns:
            Dict: イベントなし応答辞書
                - answer (str): お詫びメッセージ
                - emotion (str): "sad"
                - metadata (Dict): event_count=0

        Examples:
            >>> agent = EventAgent()
            >>> response = agent._get_no_events_response("ja", "today")
            >>> print(response["answer"])
            [sad]申し訳ございません。本日の予定されているイベントはございません。後ほどご確認いただくか、スタッフまでお問い合わせください。

        Notes:
            - 時間範囲を日本語/英語に変換して応答に含める
            - emotion は "sad" に設定
            - event_count は 0 を記録
        """
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
