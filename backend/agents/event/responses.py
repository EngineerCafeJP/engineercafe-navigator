from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.config.prompts.event_prompts import build_event_prompt, get_time_range_label

logger = logging.getLogger(__name__)


class EventResponseMixin:
    @staticmethod
    def _enforce_emotion_tag(response_text: str, event_count: int) -> str:
        """Rewrite [happy] to [sad] when no events are available.

        Issue #509: if the LLM hallucinated events and opened with [happy]
        despite ``event_count == 0``, downgrade the tag to keep the
        emotion consistent with the ground truth.
        """
        if event_count > 0 or not response_text:
            return response_text
        stripped = response_text.lstrip()
        if stripped.startswith("[happy]"):
            logger.warning(
                "EventAgent: LLM returned [happy] with event_count=0; "
                "rewriting to [sad] (Issue #509 safety net)."
            )
            leading_ws_len = len(response_text) - len(stripped)
            leading_ws = response_text[:leading_ws_len]
            rest = stripped[len("[happy]") :]
            return f"{leading_ws}[sad]{rest}"
        return response_text

    @staticmethod
    def _format_event_evidence_line(event: Dict, language: str) -> str:
        title = event.get("title") or event.get("event_title") or "Untitled event"
        start = event.get("start") or event.get("started_at") or ""
        source = event.get("source") or "unknown"
        if language == "ja":
            return f"{title} / 開始: {start} / source: {source}"
        return f"{title} / starts: {start} / source: {source}"

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
            ...     {
            ...         "title": "Workshop",
            ...         "start": "2024-01-15T14:00:00",
            ...         "source": "google_calendar",
            ...     }
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
                if source == "spreadsheet":
                    source_label = "[Event Sheet]"
                elif source == "google_calendar":
                    source_label = "[Calendar]"
                else:
                    source_label = "[Connpass]"
            else:
                if source == "spreadsheet":
                    source_label = "[イベント管理シート]"
                elif source == "google_calendar":
                    source_label = "[カレンダー]"
                else:
                    source_label = "[Connpass]"

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

    @staticmethod
    def _sources_from_events(events: List[Dict]) -> List[str]:
        """Return source labels for actual non-empty merged event results."""
        source_order = ("spreadsheet", "google_calendar", "connpass")
        seen_sources = {
            str(event.get("source", "")).strip()
            for event in events
            if str(event.get("source", "")).strip()
        }
        ordered_sources = [source for source in source_order if source in seen_sources]
        extra_sources = sorted(seen_sources - set(source_order))
        return ordered_sources + extra_sources

    @staticmethod
    def _source_search_metadata(*results: Optional[Dict]) -> tuple[List[str], Dict[str, str]]:
        """Return successful search sources separately from answer evidence sources."""
        source_names = ("spreadsheet", "google_calendar", "connpass")
        searched_sources: List[str] = []
        source_statuses: Dict[str, str] = {}

        for source_name, result in zip(source_names, results):
            if not result or not result.get("success"):
                source_statuses[source_name] = "failed"
                continue

            searched_sources.append(source_name)
            event_count = len(result.get("data", {}).get("events", []))
            source_statuses[source_name] = "ok" if event_count > 0 else "empty"

        return searched_sources, source_statuses

    def _get_no_events_response(
        self,
        language: str,
        time_range: str,
        sources: Optional[List[str]] = None,
        searched_sources: Optional[List[str]] = None,
        source_statuses: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """イベントなし時の応答を返す"""
        time_range_text = get_time_range_label(time_range, language)

        no_events_responses = {
            "ja": (
                f"[sad]申し訳ございません。"
                f"{time_range_text}の"
                "予定されているイベントはございません。"
                "後ほどご確認いただくか、"
                "スタッフまでお問い合わせください。"
            ),
            "en": (
                f"[sad]I'm sorry, there are no scheduled"
                f" events for {time_range_text}."
                " Please check back later or contact"
                " our staff for the latest information."
            ),
            "zh": f"[sad]抱歉，{time_range_text}没有预定的活动。请稍后再查看或联系工作人员。",
            "ko": (
                f"[sad]죄송합니다. "
                f"{time_range_text}에 "
                "예정된 이벤트가 없습니다. "
                "나중에 다시 확인하시거나 "
                "직원에게 문의해 주세요."
            ),
        }
        text = no_events_responses.get(language, no_events_responses["ja"])

        return {
            "answer": text,
            "emotion": "sad",
            "metadata": {
                "agent": "EventAgent",
                "time_range": time_range,
                "event_count": 0,
                "sources": list(sources or []),
                "searched_sources": list(searched_sources or []),
                "source_statuses": dict(source_statuses or {}),
            },
        }

    def _get_event_summary_response(
        self,
        events: List[Dict],
        language: str,
        time_range: str,
        *,
        sources: Optional[List[str]] = None,
        searched_sources: Optional[List[str]] = None,
        source_statuses: Optional[Dict[str, str]] = None,
        include_evidence: bool = False,
    ) -> Dict:
        """Return a deterministic grounded event summary when LLM generation fails."""
        time_range_text = get_time_range_label(time_range, language)
        event_lines = [
            self._format_event_evidence_line(event, language)
            for event in events[:5]
            if event.get("title")
        ]
        joined = " / ".join(event_lines)

        if language == "en":
            answer = f"[happy]For {time_range_text}, these events are scheduled: {joined}."
        elif language == "zh":
            answer = f"[happy]{time_range_text}有以下活动：{joined}。"
        elif language == "ko":
            answer = f"[happy]{time_range_text}에는 다음 이벤트가 예정되어 있습니다: {joined}."
        else:
            answer = f"[happy]{time_range_text}のイベントは、{joined}です。"

        metadata = {
            "agent": "EventAgent",
            "category": "event",
            "request_type": "event",
            "route": "event",
            "time_range": time_range,
            "event_count": len(events),
            "sources": list(sources or self._sources_from_events(events)),
            "searched_sources": list(searched_sources or []),
            "source_statuses": dict(source_statuses or {}),
            "llm_fallback": True,
        }
        if include_evidence:
            metadata["rag_evidence"] = {
                "source": "event_agent",
                "category": "event",
                "context_char_count": len(joined),
                "contexts": [joined],
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
            "answer": answer,
            "emotion": "happy",
            "metadata": metadata,
        }

    @staticmethod
    def _asks_connpass(query: str) -> bool:
        normalized = query.lower()
        return "connpass" in normalized or "コンパス" in normalized or "콘파스" in normalized

    @staticmethod
    def _get_connpass_response(language: str, *, include_evidence: bool = False) -> Dict:
        answers = {
            "ja": (
                "[relaxed]はい、エンジニアカフェのイベント情報や参加申込は"
                "Connpassで確認できます。多くのイベントがConnpassで募集されており、"
                "イベント一覧は https://engineercafe.connpass.com/ から見られるので、"
                "各イベントページで詳細や申込方法を確認してください。"
                "参加費無料のイベントがほとんどで、定員がある場合は先着順が多いため、"
                "早めの申込をおすすめします。"
            ),
            "en": (
                "[relaxed]Yes, you can check Engineer Cafe events on Connpass. "
                "Event listings and sign-up information are available at "
                "https://engineercafe.connpass.com/. Most events are free, and many "
                "are first-come, first-served."
            ),
            "zh": (
                "[relaxed]可以在Connpass上查看工程师咖啡的活动信息。"
                "活动列表和报名信息可以在 https://engineercafe.connpass.com/ 确认。"
                "大多数活动免费，很多活动为先到先得。"
            ),
            "ko": (
                "[relaxed]네, Connpass에서 엔지니어 카페의 이벤트 정보를 확인할 수 "
                "있습니다. 이벤트 목록과 참가 신청 정보는 "
                "https://engineercafe.connpass.com/ 에서 확인할 수 있습니다. "
                "대부분 무료이며 선착순인 경우가 많습니다."
            ),
        }
        answer = answers.get(language, answers["ja"])
        context = answer.split("]", 1)[1] if answer.startswith("[") and "]" in answer else answer
        metadata = {
            "agent": "EventAgent",
            "category": "event",
            "request_type": "event",
            "route": "event",
            "time_range": "thisWeek",
            "event_count": 0,
            "sources": ["connpass"],
        }
        if include_evidence:
            metadata["rag_evidence"] = {
                "source": "event_agent_static_connpass",
                "category": "event",
                "context_char_count": len(context),
                "contexts": [context],
                "results": [
                    {
                        "source": "connpass",
                        "title": "Engineer Cafe Connpass event listings",
                        "content": context,
                    }
                ],
            }
        return {
            "answer": answer,
            "emotion": "relaxed",
            "metadata": metadata,
        }

    @staticmethod
    def _asks_event_hosting(query: str) -> bool:
        normalized = query.lower()
        hosting_markers = (
            "イベントを開催",
            "イベント開催",
            "開催したい",
            "勉強会を開催",
            "イベントを開き",
            "host an event",
            "hold an event",
            "organize an event",
        )
        return any(marker in normalized for marker in hosting_markers)

    @staticmethod
    def _asks_hackathon_schedule(query: str) -> bool:
        normalized = query.lower()
        schedule_markers = ("予定", "開催", "ありますか", "schedule", "upcoming")
        return any(marker in normalized for marker in ("ハッカソン", "hackathon")) and any(
            marker in normalized for marker in schedule_markers
        )

    @staticmethod
    def _get_hackathon_schedule_response(language: str, *, include_evidence: bool = False) -> Dict:
        answers = {
            "ja": (
                "[relaxed]エンジニアカフェではハッカソン、LT会、もくもく会などの"
                "技術イベントが定期的に開催されています。直近の開催予定や申込は"
                "Connpassのイベント一覧 https://engineercafe.connpass.com/ で確認できます。"
                "定員があるイベントは先着順が多いので、気になる回は早めに確認してください。"
            ),
            "en": (
                "[relaxed]Engineer Cafe regularly hosts technical events such as "
                "hackathons, lightning talks, and coworking study sessions. Please "
                "check upcoming schedules and sign-up pages on Connpass: "
                "https://engineercafe.connpass.com/. Many events have capacity limits, "
                "so checking early is recommended."
            ),
        }
        answer = answers.get(language, answers["ja"])
        metadata = {
            "agent": "EventAgent",
            "category": "event",
            "request_type": "event",
            "route": "event",
            "time_range": "upcoming",
            "event_count": 0,
            "sources": ["connpass"],
            "searched_sources": ["connpass"],
            "source_statuses": {"connpass": "static_link"},
        }
        if include_evidence:
            metadata["rag_evidence"] = {
                "source": "event_agent_static_hackathon",
                "category": "event",
                "context_char_count": len(answer),
                "contexts": [answer],
                "results": [
                    {
                        "source": "connpass",
                        "title": "Engineer Cafe Connpass event listings",
                        "content": "https://engineercafe.connpass.com/",
                    }
                ],
            }
        return {
            "answer": answer,
            "emotion": "relaxed",
            "metadata": metadata,
        }

    @staticmethod
    def _get_event_hosting_response(language: str) -> Dict:
        answers = {
            "ja": (
                "[relaxed]エンジニアカフェでイベントを開催したい場合は、事前に"
                "コミュニティマネージャーまたはスタッフへ相談してください。"
                "福岡市の許可が必要になる場合があります。開催が決まったイベントは、"
                "Connpassで情報公開や参加申込の案内を行えます。"
            ),
            "en": (
                "[relaxed]To host an event at Engineer Cafe, please consult the "
                "community manager or staff in advance. Fukuoka City permission may "
                "be required. Once approved, event information and sign-up can be "
                "published on Connpass."
            ),
            "zh": (
                "[relaxed]如果想在工程师咖啡举办活动，请提前咨询社区经理或工作人员。"
                "有时需要福冈市许可。活动确定后，可以在Connpass公开信息并引导报名。"
            ),
            "ko": (
                "[relaxed]엔지니어 카페에서 이벤트를 열고 싶다면 사전에 커뮤니티 매니저나 "
                "직원에게 상담해 주세요. 후쿠오카시의 허가가 필요할 수 있습니다. "
                "확정된 이벤트는 Connpass에 정보와 신청 안내를 공개할 수 있습니다."
            ),
        }
        return {
            "answer": answers.get(language, answers["ja"]),
            "emotion": "relaxed",
            "metadata": {
                "agent": "EventAgent",
                "time_range": "none",
                "event_count": 0,
                "sources": ["connpass", "enhanced_rag"],
            },
        }

    @staticmethod
    def _asks_event_clarification(query: str) -> bool:
        normalized = query.lower().strip()
        return normalized in {"イベントについて", "イベント", "event", "events"}

    @staticmethod
    def _get_event_clarification_response(language: str) -> Dict:
        answers = {
            "ja": (
                "[relaxed]イベントについてお調べします。開催予定や参加申込は"
                "Connpass https://engineercafe.connpass.com/ で確認できます。"
                "参加方法や開催相談も案内できます。"
            ),
            "en": (
                "[relaxed]For events, please tell me whether you want upcoming events, "
                "how to sign up, or how to host an event. Event listings and sign-up "
                "are available on Connpass at https://engineercafe.connpass.com/."
            ),
            "zh": (
                "[relaxed]关于活动，请告诉我是想了解近期活动、报名方法，还是举办活动咨询。"
                "活动列表和报名可在Connpass确认：https://engineercafe.connpass.com/。"
            ),
            "ko": (
                "[relaxed]이벤트에 대해서는 예정된 이벤트, 참가 신청 방법, 이벤트 개최 상담 중 "
                "무엇을 알고 싶은지 알려 주세요. 이벤트 목록과 신청은 Connpass에서 "
                "확인할 수 있습니다: "
                "https://engineercafe.connpass.com/."
            ),
        }
        return {
            "answer": answers.get(language, answers["ja"]),
            "emotion": "relaxed",
            "metadata": {
                "agent": "EventAgent",
                "time_range": "clarification",
                "event_count": 0,
                "sources": ["connpass"],
            },
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
        normalized = normalized.lower().strip()
        # Only strip trailing edition patterns, not all digits
        normalized = re.sub(
            r"\s*(第\d+回|vol\.?\s*\d+|#\d+|\(\d+\))\s*$", "", normalized, flags=re.IGNORECASE
        )
        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized

    def _merge_events(
        self,
        calendar_result: Dict,
        connpass_result: Dict,
        spreadsheet_result: Optional[Dict] = None,
    ) -> List[Dict]:
        """Spreadsheet、Google Calendar、Connpassのイベントをマージ（重複排除付き）

        両方のソースからイベントを取得し、タイトルの正規化ベースで
        重複を排除してから開始日時順にソートして返す。

        優先度: Spreadsheet > Connpass > Google Calendar。

        Args:
            calendar_result: CalendarServiceの結果
            connpass_result: ConnpassServiceの結果

        Returns:
            重複排除済み、開始日時順のイベントリスト
        """
        events: List[Dict] = []
        seen_keys: set[tuple[str, str]] = set()

        ordered_sources = [
            (spreadsheet_result, "spreadsheet"),
            (connpass_result, "connpass"),
            (calendar_result, "google_calendar"),
        ]
        for result, source_name in ordered_sources:
            if not result or not result.get("success"):
                continue
            for event in result.get("data", {}).get("events", []):
                normalized = self._normalize_title(event.get("title", ""))
                if not normalized:
                    continue
                event_date = self._event_date_key(event)
                key = (normalized, event_date)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                events.append({**event, "source": event.get("source") or source_name})

        # 開始日時でソート
        events.sort(key=lambda e: e.get("start", "") or "")

        return events

    @staticmethod
    def _event_date_key(event: Dict) -> str:
        start = str(event.get("start") or event.get("started_at") or event.get("starts_at") or "")
        return start[:10]
