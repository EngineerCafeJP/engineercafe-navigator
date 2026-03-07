"""Purpose-specific flow handlers for the reception workflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Mapping, Optional
from zoneinfo import ZoneInfo

from backend.domain.reception.models import VisitPurpose, VisitorIdentity
from backend.domain.reception.service import ReceptionDomainService
from backend.utils.discord_escalation import send_escalation_notification
from backend.utils.supabase_helper import get_supabase_client

logger = logging.getLogger(__name__)

SupportedLanguage = str
EscalationNotifier = Callable[[str, str, Optional[str], str], Awaitable[bool]]

_SUPPORTED_LANGUAGES = {"ja", "en", "zh", "ko"}
_JST = ZoneInfo("Asia/Tokyo")
_EVENT_DATE_KEYS = ("event_date", "date", "start_date", "starts_on")
_EVENT_DATETIME_KEYS = ("start_at", "starts_at", "start_time", "starts_on", "datetime")

_TEXT_TEMPLATES: dict[str, Mapping[str, Mapping[str, str]]] = {
    "facility_use": {
        "ja": {
            "new": (
                "エンジニアカフェの施設利用ですね。"
                "利用方法をご案内しますので、そのままお待ちください。"
            ),
            "returning": (
                "本日も施設利用ですね。" "利用方法をご案内しますので、そのままお待ちください。"
            ),
        },
        "en": {
            "new": (
                "You're here to use the facility. "
                "I'll guide you through the usage information shortly."
            ),
            "returning": (
                "You're here to use the facility again today. "
                "I'll guide you through the usage information shortly."
            ),
        },
        "zh": {
            "new": "您今天是来使用馆内设施的。我将为您说明使用方法，请稍候。",
            "returning": "您今天也是来使用馆内设施的。我将为您说明使用方法，请稍候。",
        },
        "ko": {
            "new": (
                "시설 이용을 원하시는군요. " "이용 방법을 안내해 드릴 테니 잠시만 기다려 주세요."
            ),
            "returning": (
                "오늘도 시설 이용이시군요. " "이용 방법을 안내해 드릴 테니 잠시만 기다려 주세요."
            ),
        },
    },
    "event_participation": {
        "ja": {
            "with_events": "本日のイベント参加ですね。確認できたイベントをご案内します。",
            "without_events": (
                "本日のイベント参加ですね。"
                "受付で確認できるイベント情報がないため、担当案内へおつなぎします。"
            ),
            "fallback": "本日のイベント情報を確認できませんでした。担当案内へおつなぎします。",
        },
        "en": {
            "with_events": (
                "You're here for an event today. " "I'll share the events I found for today."
            ),
            "without_events": (
                "You're here for an event today. "
                "I couldn't find a confirmed event listing, so I'll hand you over for assistance."
            ),
            "fallback": (
                "I couldn't check today's event listing right now, "
                "so I'll hand you over for assistance."
            ),
        },
        "zh": {
            "with_events": "您今天是来参加活动的。我来为您说明今天确认到的活动。",
            "without_events": (
                "您今天是来参加活动的。" "目前没有查到可确认的活动信息，我将为您转接进一步协助。"
            ),
            "fallback": "我暂时无法确认今天的活动信息，我将为您转接进一步协助。",
        },
        "ko": {
            "with_events": (
                "오늘 행사 참여로 방문하셨군요. " "확인된 오늘의 행사를 안내해 드리겠습니다."
            ),
            "without_events": (
                "오늘 행사 참여로 방문하셨군요. "
                "확인된 행사 정보가 없어 추가 안내로 연결하겠습니다."
            ),
            "fallback": "현재 오늘 행사 정보를 확인할 수 없어 추가 안내로 연결하겠습니다.",
        },
    },
    "tour": {
        "ja": {
            "default": "館内ツアーですね。ツアー案内におつなぎします。",
        },
        "en": {
            "default": "You're here for a tour. I'll hand you over to the tour guidance flow.",
        },
        "zh": {
            "default": "您今天是来参加参观导览的。我将为您转接到导览流程。",
        },
        "ko": {
            "default": "투어 방문이시군요. 투어 안내 흐름으로 연결하겠습니다.",
        },
    },
    "consultation": {
        "ja": {
            "notified": "ご相談ですね。スタッフへお知らせしましたので、そのままお待ちください。",
            "fallback": (
                "ご相談ですね。" "スタッフ呼び出しを進めていますので、そのままお待ちください。"
            ),
        },
        "en": {
            "notified": "You'd like a consultation. I've notified the staff, so please wait here.",
            "fallback": (
                "You'd like a consultation. "
                "I'm arranging staff assistance now, so please wait here."
            ),
        },
        "zh": {
            "notified": "您希望进行咨询。我已通知工作人员，请稍候。",
            "fallback": "您希望进行咨询。我正在安排工作人员协助，请稍候。",
        },
        "ko": {
            "notified": "상담을 원하시는군요. 직원을 호출했으니 잠시만 기다려 주세요.",
            "fallback": "상담을 원하시는군요. 직원 연결을 진행하고 있으니 잠시만 기다려 주세요.",
        },
    },
    "other": {
        "ja": {
            "default": "ご用件を確認しました。適切な案内へおつなぎします。",
        },
        "en": {
            "default": "I understood your purpose. I'll hand you over to the appropriate guidance.",
        },
        "zh": {
            "default": "我已确认您的来访目的。我将为您转接到合适的服务。",
        },
        "ko": {
            "default": "방문 목적을 확인했습니다. 적절한 안내로 연결하겠습니다.",
        },
    },
}


@dataclass(frozen=True)
class PurposeFlowResult:
    """Outcome returned by a purpose-specific flow handler."""

    response_text: str
    target_agent: str
    action_type: str
    action_data: Optional[dict[str, Any]]
    requires_staff: bool


class PurposeFlowService:
    """Resolve visit-purpose specific handling before agent handoff."""

    def __init__(
        self,
        domain_service: Optional[ReceptionDomainService] = None,
        supabase_client: Any = None,
        escalation_notifier: Optional[EscalationNotifier] = None,
    ) -> None:
        self._domain_service = domain_service or ReceptionDomainService()
        self._supabase = supabase_client
        self._escalation_notifier = escalation_notifier or send_escalation_notification

    async def resolve(
        self,
        purpose: VisitPurpose,
        language: str,
        session_id: str,
        visitor_identity: VisitorIdentity,
    ) -> PurposeFlowResult:
        """Dispatch to the appropriate purpose handler."""
        handlers = {
            "facility_use": self.handle_facility_use,
            "event_participation": self.handle_event_participation,
            "tour": self.handle_tour,
            "consultation": self.handle_consultation,
            "other": self.handle_other,
        }
        handler = handlers.get(purpose.category, self.handle_other)
        return await handler(language, session_id, visitor_identity)

    async def handle_facility_use(
        self,
        language: str,
        session_id: str,
        visitor_identity: VisitorIdentity,
    ) -> PurposeFlowResult:
        """Handle visitors who want to use the facility."""
        normalized_language = self._normalize_language(language)
        visitor_key = self._visitor_key(visitor_identity)
        target_agent = self._map_target_agent("facility_use")
        response_text = self._text("facility_use", normalized_language, visitor_key)

        return PurposeFlowResult(
            response_text=response_text,
            target_agent=target_agent,
            action_type="guide",
            action_data={
                "purpose_category": "facility_use",
                "visitor_type": visitor_identity.visitor_type.value,
            },
            requires_staff=False,
        )

    async def handle_event_participation(
        self,
        language: str,
        session_id: str,
        visitor_identity: VisitorIdentity,
    ) -> PurposeFlowResult:
        """Handle visitors attending an event, enriching with today's events."""
        normalized_language = self._normalize_language(language)
        target_agent = self._map_target_agent("event_participation")

        try:
            events = await self._fetch_today_events()
        except Exception as exc:
            logger.warning("Failed to fetch today events: %s", exc)
            return PurposeFlowResult(
                response_text=self._text("event_participation", normalized_language, "fallback"),
                target_agent=target_agent,
                action_type="lookup",
                action_data={"events": [], "lookup_failed": True},
                requires_staff=False,
            )

        if events:
            return PurposeFlowResult(
                response_text=self._text("event_participation", normalized_language, "with_events"),
                target_agent=target_agent,
                action_type="lookup",
                action_data={"events": events, "event_count": len(events)},
                requires_staff=False,
            )

        return PurposeFlowResult(
            response_text=self._text("event_participation", normalized_language, "without_events"),
            target_agent=target_agent,
            action_type="lookup",
            action_data={"events": [], "event_count": 0},
            requires_staff=False,
        )

    async def handle_tour(
        self,
        language: str,
        session_id: str,
        visitor_identity: VisitorIdentity,
    ) -> PurposeFlowResult:
        """Handle visitors requesting a tour."""
        normalized_language = self._normalize_language(language)
        return PurposeFlowResult(
            response_text=self._text("tour", normalized_language, "default"),
            target_agent=self._map_target_agent("tour"),
            action_type="handoff",
            action_data={"purpose_category": "tour"},
            requires_staff=False,
        )

    async def handle_consultation(
        self,
        language: str,
        session_id: str,
        visitor_identity: VisitorIdentity,
    ) -> PurposeFlowResult:
        """Handle consultations by escalating to staff and notifying Discord."""
        normalized_language = self._normalize_language(language)
        target_agent = self._map_target_agent("consultation")
        reason = self._consultation_reason(normalized_language)

        notified = False
        try:
            notified = bool(
                await self._escalation_notifier(
                    session_id,
                    reason,
                    visitor_identity.name,
                    normalized_language,
                )
            )
        except Exception as exc:
            logger.warning("Failed to send consultation escalation: %s", exc)

        template_key = "notified" if notified else "fallback"
        return PurposeFlowResult(
            response_text=self._text("consultation", normalized_language, template_key),
            target_agent=target_agent,
            action_type="escalate",
            action_data={
                "reason": reason,
                "notification_sent": notified,
                "session_id": session_id,
            },
            requires_staff=True,
        )

    async def handle_other(
        self,
        language: str,
        session_id: str,
        visitor_identity: VisitorIdentity,
    ) -> PurposeFlowResult:
        """Handle uncategorized purposes with general guidance handoff."""
        normalized_language = self._normalize_language(language)
        return PurposeFlowResult(
            response_text=self._text("other", normalized_language, "default"),
            target_agent=self._map_target_agent("other"),
            action_type="handoff",
            action_data={"purpose_category": "other"},
            requires_staff=False,
        )

    async def _fetch_today_events(self) -> list[dict[str, Any]]:
        """Fetch and normalize today's events from Supabase."""
        client = await self._get_supabase()
        if not client:
            return []

        result = client.table("events").select("*").limit(200).execute()
        rows = result.data or []
        today = datetime.now(_JST).date()

        events = [
            normalized
            for row in rows
            if isinstance(row, dict)
            for normalized in [self._normalize_event(row)]
            if normalized is not None and self._is_today_event(row, today)
        ]
        return sorted(
            events,
            key=lambda event: (
                event["date"],
                event.get("start_at") or "",
                event["title"],
            ),
        )

    async def _get_supabase(self) -> Any:
        """Return the Supabase client, resolving lazily if needed."""
        if self._supabase is not None:
            return self._supabase
        try:
            return get_supabase_client()
        except Exception as exc:
            logger.warning("Supabase client unavailable in PurposeFlowService: %s", exc)
            return None

    def _normalize_language(self, language: str) -> SupportedLanguage:
        return language if language in _SUPPORTED_LANGUAGES else "ja"

    def _visitor_key(self, visitor_identity: VisitorIdentity) -> str:
        return "returning" if visitor_identity.visitor_type.value == "returning" else "new"

    def _map_target_agent(self, category: str) -> str:
        return self._domain_service.map_purpose_to_agent(VisitPurpose(category=category))

    def _text(self, category: str, language: str, key: str) -> str:
        category_templates = _TEXT_TEMPLATES[category]
        language_templates = category_templates.get(language, category_templates["ja"])
        return language_templates[key]

    def _consultation_reason(self, language: str) -> str:
        reasons = {
            "ja": "来訪者が相談対応を希望",
            "en": "Visitor requested consultation support",
            "zh": "来访者希望获得咨询支持",
            "ko": "방문자가 상담 지원을 요청함",
        }
        return reasons.get(language, reasons["ja"])

    def _is_today_event(self, row: Mapping[str, Any], today: date) -> bool:
        event_date = self._extract_event_date(row)
        return event_date == today

    def _extract_event_date(self, row: Mapping[str, Any]) -> Optional[date]:
        for key in _EVENT_DATE_KEYS:
            value = row.get(key)
            parsed = self._parse_date_like(value)
            if parsed is not None:
                return parsed

        for key in _EVENT_DATETIME_KEYS:
            value = row.get(key)
            parsed = self._parse_datetime_like(value)
            if parsed is not None:
                return parsed.date()

        return None

    def _parse_date_like(self, value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.astimezone(_JST).date() if value.tzinfo else value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str) or not value:
            return None

        candidate = value.strip()
        try:
            return date.fromisoformat(candidate[:10])
        except ValueError:
            return None

    def _parse_datetime_like(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value.astimezone(_JST) if value.tzinfo else value.replace(tzinfo=_JST)
        if not isinstance(value, str) or not value:
            return None

        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None

        return parsed.astimezone(_JST) if parsed.tzinfo else parsed.replace(tzinfo=_JST)

    def _normalize_event(self, row: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        title = row.get("title") or row.get("name")
        event_date = self._extract_event_date(row)
        if not title or event_date is None:
            return None

        return {
            "id": row.get("id"),
            "title": title,
            "date": event_date.isoformat(),
            "location": row.get("location") or row.get("venue"),
            "start_at": row.get("start_at") or row.get("starts_at") or row.get("start_time"),
        }
