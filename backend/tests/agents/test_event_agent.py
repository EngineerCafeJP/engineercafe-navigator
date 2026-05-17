"""
EventAgent のユニットテスト
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.event_agent import EventAgent


class TestEventAgent:
    """EventAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = EventAgent()
        self.agent.sheets_event_source.search_events = AsyncMock(
            return_value={"success": True, "data": {"events": []}}
        )

    def test_format_calendar_events_japanese(self):
        """日本語のイベント整形をテスト"""
        events = [
            {
                "title": "LT会",
                "start": "2025-01-15T19:00:00Z",
                "description": "Lightning Talk Event",
                "location": "Engineer Cafe",
            },
            {"title": "勉強会", "start": "2025-01-20", "description": "", "location": ""},
        ]

        formatted = self.agent._format_calendar_events(events, "ja")

        assert "LT会" in formatted
        assert "2025-01-15" in formatted
        assert "Lightning Talk Event" in formatted
        assert "勉強会" in formatted
        assert "2025-01-20" in formatted

    def test_format_spreadsheet_events_japanese(self):
        events = [
            {
                "title": "スプレッドシート管理イベント",
                "start": "2026-05-20T19:00:00+09:00",
                "description": "公開済みイベント",
                "source": "spreadsheet",
            }
        ]

        formatted = self.agent._format_calendar_events(events, "ja")

        assert "スプレッドシート管理イベント" in formatted
        assert "[イベント管理シート]" in formatted

    def test_format_calendar_events_english(self):
        """英語のイベント整形をテスト"""
        events = [
            {
                "title": "Tech Meetup",
                "start": "2025-01-25T18:00:00Z",
                "description": "Monthly meetup",
                "location": "",
            }
        ]

        formatted = self.agent._format_calendar_events(events, "en")

        assert "Tech Meetup" in formatted
        assert "2025-01-25" in formatted
        assert "Monthly meetup" in formatted

    def test_format_calendar_events_empty(self):
        """空のイベントリストをテスト"""
        formatted = self.agent._format_calendar_events([], "ja")
        assert formatted == ""

    def test_get_no_events_response_japanese(self):
        """日本語のイベントなし応答をテスト"""
        response = self.agent._get_no_events_response("ja", "thisWeek")

        assert response["answer"].startswith("[sad]")
        assert "今週" in response["answer"]
        assert response["emotion"] == "sad"
        assert response["metadata"]["agent"] == "EventAgent"
        assert response["metadata"]["time_range"] == "thisWeek"
        assert response["metadata"]["event_count"] == 0

    def test_get_no_events_response_english(self):
        """英語のイベントなし応答をテスト"""
        response = self.agent._get_no_events_response("en", "today")

        assert response["answer"].startswith("[sad]")
        assert "today" in response["answer"].lower()
        assert response["emotion"] == "sad"
        assert response["metadata"]["agent"] == "EventAgent"

    def test_get_no_events_response_various_time_ranges(self):
        """各時間範囲のイベントなし応答をテスト"""
        for time_range in ["today", "tomorrow", "thisWeek", "nextWeek", "thisMonth"]:
            response_ja = self.agent._get_no_events_response("ja", time_range)
            response_en = self.agent._get_no_events_response("en", time_range)

            assert response_ja["metadata"]["time_range"] == time_range
            assert response_en["metadata"]["time_range"] == time_range
            assert response_ja["emotion"] == "sad"
            assert response_en["emotion"] == "sad"

    def test_connpass_canonical_response_english(self):
        """Connpass質問には実際の一覧URLと申込確認を返す"""
        response = self.agent._get_connpass_response("en")

        assert "Connpass" in response["answer"]
        assert "you can check Engineer Cafe events on Connpass" in response["answer"]
        assert "sign-up" in response["answer"].lower()
        assert "https://engineercafe.connpass.com/" in response["answer"]
        assert "free" in response["answer"].lower()
        assert "first-come, first-served" in response["answer"].lower()
        assert response["metadata"]["sources"] == ["connpass"]

    def test_connpass_canonical_response_japanese_mentions_recruitment(self):
        """日本語Connpass案内は募集・申込確認まで含める"""
        response = self.agent._get_connpass_response("ja")

        assert "多くのイベント" in response["answer"]
        assert "https://engineercafe.connpass.com/" in response["answer"]
        assert "申込" in response["answer"] or "申し込み" in response["answer"]
        assert "参加費無料" in response["answer"]
        assert "早めの申込" in response["answer"]

    def test_connpass_canonical_response_multilingual_includes_url(self):
        for language in ("zh", "ko"):
            response = self.agent._get_connpass_response(language)

            assert "Connpass" in response["answer"]
            assert "https://engineercafe.connpass.com/" in response["answer"]
            assert response["metadata"]["sources"] == ["connpass"]

    def test_connpass_canonical_response_can_include_eval_evidence(self):
        response = self.agent._get_connpass_response("zh", include_evidence=True)
        evidence = response["metadata"]["rag_evidence"]

        assert evidence["source"] == "event_agent_static_connpass"
        assert evidence["category"] == "event"
        assert "https://engineercafe.connpass.com/" in evidence["contexts"][0]
        assert evidence["results"][0]["source"] == "connpass"

    @pytest.mark.asyncio
    async def test_event_hosting_canonical_skips_live_calendar(self):
        """gt-030: イベント開催相談は予定イベント一覧に倒さない"""
        self.agent.calendar_service.search_events = AsyncMock(
            side_effect=AssertionError("event hosting should skip live calendar")
        )
        self.agent.connpass_service.search_events = AsyncMock(
            side_effect=AssertionError("event hosting should skip live connpass search")
        )

        response = await self.agent.answer_event_query(
            "エンジニアカフェでイベントを開催したいのですが", "ja"
        )

        assert "コミュニティマネージャー" in response["answer"]
        assert "福岡市の許可" in response["answer"]
        assert "Connpass" in response["answer"]

    @pytest.mark.asyncio
    async def test_event_clarification_canonical_skips_live_calendar(self):
        """gt-083: 曖昧なイベント発話は確認案内とConnpass参照にする"""
        self.agent.calendar_service.search_events = AsyncMock(
            side_effect=AssertionError("event clarification should skip live calendar")
        )
        self.agent.connpass_service.search_events = AsyncMock(
            side_effect=AssertionError("event clarification should skip live connpass search")
        )

        response = await self.agent.answer_event_query("イベントについて", "ja")

        assert "イベントについてお調べします" in response["answer"]
        assert "開催予定" in response["answer"]
        assert "参加方法" in response["answer"]
        assert "Connpass" in response["answer"]


class TestEventDeduplication:
    """イベント重複排除テスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = EventAgent()

    def test_deduplicate_same_title_events(self):
        """同じタイトルのイベントが重複排除されることを確認"""
        calendar_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop #3",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "From Calendar",
                    }
                ]
            },
        }
        connpass_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop #3",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "From Connpass",
                        "source": "connpass",
                    }
                ]
            },
        }

        events = self.agent._merge_events(calendar_result, connpass_result)

        # 重複排除で1件になる
        assert len(events) == 1
        # Connpass takes priority over Google Calendar for public event metadata.
        assert events[0].get("source") == "connpass"
        assert events[0]["description"] == "From Connpass"

    def test_spreadsheet_takes_priority_over_connpass_and_calendar(self):
        """同じ日付・タイトルならイベント管理シートを優先する"""
        spreadsheet_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop #3",
                        "start": "2025-02-15T14:00:00+09:00",
                        "description": "From Spreadsheet",
                        "source": "spreadsheet",
                    }
                ]
            },
        }
        calendar_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop #3",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "From Calendar",
                    }
                ]
            },
        }
        connpass_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop #3",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "From Connpass",
                        "source": "connpass",
                    }
                ]
            },
        }

        events = self.agent._merge_events(calendar_result, connpass_result, spreadsheet_result)

        assert len(events) == 1
        assert events[0]["source"] == "spreadsheet"
        assert events[0]["description"] == "From Spreadsheet"

    def test_keep_different_events(self):
        """異なるタイトルのイベントは保持されることを確認"""
        calendar_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "Python Workshop",
                        "start": "2025-02-15T14:00:00Z",
                        "description": "Python event",
                    }
                ]
            },
        }
        connpass_result = {
            "success": True,
            "data": {
                "events": [
                    {
                        "title": "React Meetup",
                        "start": "2025-02-16T18:00:00Z",
                        "description": "React event",
                        "source": "connpass",
                    }
                ]
            },
        }

        events = self.agent._merge_events(calendar_result, connpass_result)

        # 異なるイベントなので2件
        assert len(events) == 2
        titles = [e["title"] for e in events]
        assert "Python Workshop" in titles
        assert "React Meetup" in titles


class TestGetTodayEvents:
    """get_today_events() のテスト"""

    def setup_method(self):
        self.agent = EventAgent()
        self.agent.sheets_event_source.search_events = AsyncMock(
            return_value={"success": True, "data": {"events": []}}
        )

    @pytest.mark.asyncio
    async def test_returns_events_when_available(self):
        """イベントがある場合に正しく返すこと"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.return_value = {
                "success": True,
                "data": {
                    "events": [
                        {
                            "title": "Today's Workshop",
                            "start": "2026-02-28T14:00:00Z",
                            "description": "A workshop",
                        }
                    ]
                },
            }
            mock_conn.return_value = {"success": True, "data": {"events": []}}

            result = await self.agent.get_today_events("ja")

            assert result["has_events"] is True
            assert result["count"] == 1
            assert len(result["events"]) == 1
            assert result["events"][0]["title"] == "Today's Workshop"
            assert len(result["formatted_text"]) > 0
            mock_cal.assert_called_once_with("today")

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_events(self):
        """イベントがない場合に空を返すこと"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.return_value = {"success": True, "data": {"events": []}}
            mock_conn.return_value = {"success": True, "data": {"events": []}}

            result = await self.agent.get_today_events("ja")

            assert result["has_events"] is False
            assert result["count"] == 0
            assert result["formatted_text"] == ""

    @pytest.mark.asyncio
    async def test_merges_calendar_and_connpass(self):
        """CalendarとConnpassのイベントを統合すること"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.return_value = {
                "success": True,
                "data": {
                    "events": [
                        {
                            "title": "Cal Event",
                            "start": "2026-02-28T10:00:00Z",
                            "description": "",
                        }
                    ]
                },
            }
            mock_conn.return_value = {
                "success": True,
                "data": {
                    "events": [
                        {
                            "title": "Connpass Event",
                            "start": "2026-02-28T15:00:00Z",
                            "description": "",
                            "source": "connpass",
                        }
                    ]
                },
            }

            result = await self.agent.get_today_events("ja")

            assert result["count"] == 2
            titles = [e["title"] for e in result["events"]]
            assert "Cal Event" in titles
            assert "Connpass Event" in titles

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        """API失敗時にエラーなく空結果を返すこと"""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.side_effect = Exception("API error")
            mock_conn.side_effect = Exception("API error")

            result = await self.agent.get_today_events("ja")

            assert result["has_events"] is False
            assert result["count"] == 0


# =========================================================================
# Issue #509: EventAgent hallucination — emotion tag + grounding regression tests
# =========================================================================


class TestEventAgentHallucinationGuards:
    """Ensure EventAgent never hallucinates events or emotion tags.

    Corresponds to Issue #509 — the bug where the agent:
    - read "Busy" ICS entries as real events,
    - returned [happy] even when event_count == 0,
    - fabricated specific future event names/dates.
    """

    def setup_method(self):
        self.agent = EventAgent()
        self.agent.sheets_event_source.search_events = AsyncMock(
            return_value={"success": True, "data": {"events": []}}
        )

    @pytest.mark.asyncio
    async def test_no_events_returns_sad_emotion(self):
        """When both calendar and connpass return zero events, response is [sad]."""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
        ):
            mock_cal.return_value = {"success": True, "data": {"events": []}}
            mock_conn.return_value = {"success": True, "data": {"events": []}}

            result = await self.agent.answer_event_query("今日のイベントは？", "ja")

            assert result["emotion"] == "sad"
            assert result["answer"].startswith("[sad]")
            assert result["metadata"]["event_count"] == 0

    @pytest.mark.asyncio
    async def test_llm_hallucination_is_corrected_to_sad(self):
        """If the LLM ignores the prompt and returns [happy] with no events,
        the post-LLM safety net must rewrite the prefix to [sad]."""
        with (
            patch.object(
                self.agent.calendar_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_cal,
            patch.object(
                self.agent.connpass_service,
                "search_events",
                new_callable=AsyncMock,
            ) as mock_conn,
            patch.object(
                self.agent.llm_provider,
                "generate",
                new_callable=AsyncMock,
            ) as mock_llm,
        ):
            mock_cal.return_value = {"success": True, "data": {"events": []}}
            mock_conn.return_value = {"success": True, "data": {"events": []}}
            mock_llm.return_value = "[happy]本日はランチ交流会があります！"

            result = await self.agent.answer_event_query("今日は？", "ja")

            # With zero events, _get_no_events_response short-circuits
            # before the LLM is ever invoked, so emotion stays sad.
            assert result["emotion"] == "sad"
            assert result["answer"].startswith("[sad]")

    def test_enforce_emotion_tag_rewrites_happy_to_sad(self):
        """Direct unit test on the safety-net helper."""
        text = "[happy] We have a Python workshop today!"
        result = EventAgent._enforce_emotion_tag(text, event_count=0)
        assert result.startswith("[sad]")
        assert "[happy]" not in result

    def test_enforce_emotion_tag_preserves_happy_when_events_exist(self):
        """Safety net must NOT touch responses when events are real."""
        text = "[happy] Python workshop at 2pm."
        result = EventAgent._enforce_emotion_tag(text, event_count=2)
        assert result == text

    def test_enforce_emotion_tag_preserves_sad_tag(self):
        """If LLM already said [sad] with zero events, leave it alone."""
        text = "[sad] No events today."
        result = EventAgent._enforce_emotion_tag(text, event_count=0)
        assert result == text

    def test_enforce_emotion_tag_handles_empty_string(self):
        """Empty / None response must not crash the safety net."""
        assert EventAgent._enforce_emotion_tag("", event_count=0) == ""

    def test_prompt_forbids_fabrication_ja(self):
        """Japanese prompt must contain an explicit 'do not invent' rule."""
        from backend.config.prompts.event_prompts import build_event_prompt

        prompt = build_event_prompt(
            query="今日のイベント", events_text="", time_range="today", language="ja"
        )

        # The prompt must explicitly forbid invention and require [sad] on empty.
        assert "作り出さない" in prompt or "でっち上げ" in prompt
        assert "[sad]" in prompt

    def test_prompt_forbids_fabrication_en(self):
        """English prompt must contain an explicit 'do not invent' rule."""
        from backend.config.prompts.event_prompts import build_event_prompt

        prompt = build_event_prompt(
            query="today's events", events_text="", time_range="today", language="en"
        )

        assert "Do not invent" in prompt or "do not invent" in prompt.lower()
        assert "[sad]" in prompt

    def test_prompt_hints_happy_when_events_present(self):
        """When events are present, the prompt suggests the [happy] tag."""
        from backend.config.prompts.event_prompts import build_event_prompt

        prompt = build_event_prompt(
            query="今日のイベント",
            events_text="- Python Workshop（2026-04-23）[カレンダー]",
            time_range="today",
            language="ja",
        )

        assert "[happy]" in prompt
