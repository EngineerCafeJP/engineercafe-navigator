"""
QueryClassifier - クエリ分類専用クラス

TypeScript版から移植:
frontend/src/lib/query-classifier.ts
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.utils.cafe_entity import (
    cafe_entity_metadata,
    has_cafe_or_bar_token,
    is_explicit_engineer_cafe_query,
    is_saino_reference,
    normalize_cafe_query,
    resolve_cafe_entity,
)

logger = logging.getLogger(__name__)


@dataclass
class QueryClassificationResult:
    """クエリ分類結果"""

    category: str
    confidence: float
    debug_info: Dict[str, Any] = field(default_factory=dict)


class QueryClassifier:
    """
    クエリ分類処理を担当するクラス

    ユーザーからの質問を適切なカテゴリに分類します。
    """

    def __init__(self, debug_mode: bool = False):
        """
        Args:
            debug_mode: デバッグモードの有効/無効
        """
        self.debug_mode = debug_mode

    async def classify(self, question: str, conversation_context: Optional[Dict] = None) -> str:
        """
        クエリを分類する（簡易版）

        Args:
            question: ユーザーからの質問
            conversation_context: 会話コンテキスト（オプション）

        Returns:
            str: カテゴリ名
        """
        result = await self.classify_with_details(question, conversation_context)
        return result.category

    async def classify_with_details(
        self, question: str, conversation_context: Optional[Dict] = None
    ) -> QueryClassificationResult:
        """
        詳細情報付きでクエリを分類する

        Args:
            question: ユーザーからの質問
            conversation_context: 会話コンテキスト（オプション）

        Returns:
            QueryClassificationResult: 分類結果
        """
        normalized_question = self._normalize_query(question)

        # 現在時刻のチェック（最優先）
        if self._is_current_time_query(normalized_question):
            return QueryClassificationResult(
                category="current-time",
                confidence=1.0,
                debug_info={"reason": "Current time keywords detected"},
            )

        # カレンダー/イベント（より具体的なカテゴリを先にチェック）
        if self._is_calendar_query(normalized_question):
            return QueryClassificationResult(
                category="calendar",
                confidence=0.9,
                debug_info={"reason": "Calendar/event keywords detected"},
            )

        # Sainoカフェの明示的なクエリ（カフェ曖昧性チェックより前に）
        if self._is_saino_cafe_query(normalized_question):
            return QueryClassificationResult(
                category="saino-cafe",
                confidence=0.9,
                debug_info={
                    "reason": "Saino cafe detected",
                    "cafe_entity_resolution": cafe_entity_metadata(
                        entity="saino_cafe",
                        status="resolved",
                        source="query_classifier",
                    ),
                },
            )

        # エンジニアカフェ特定のクエリ（Saino併設表現の後に評価）
        if self._is_engineer_cafe_specific(normalized_question):
            return QueryClassificationResult(
                category="facility-info",
                confidence=1.0,
                debug_info={
                    "reason": "Engineer Cafe specific",
                    "cafe_entity_resolution": cafe_entity_metadata(
                        entity="engineer_cafe",
                        status="resolved",
                        source="query_classifier",
                    ),
                },
            )

        # カフェの曖昧性チェック（既存ロジックを保持）
        cafe_check = self._check_cafe_ambiguity(normalized_question, conversation_context)
        if cafe_check["needs_clarification"]:
            return QueryClassificationResult(
                category=cafe_check["category"],
                confidence=cafe_check["confidence"],
                debug_info=cafe_check.get("debug_info", {}),
            )
        if cafe_check["category"]:
            return QueryClassificationResult(
                category=cafe_check["category"],
                confidence=cafe_check["confidence"],
                debug_info=cafe_check.get("debug_info", {}),
            )

        # 休館日/休業日
        if self._is_closed_days_query(normalized_question):
            return QueryClassificationResult(
                category="facility-info",
                confidence=0.9,
                debug_info={"reason": "Closed days query"},
            )

        # 歴史関連
        if self._is_history_query(normalized_question):
            return QueryClassificationResult(
                category="facility-info",
                confidence=0.8,
                debug_info={"reason": "History query"},
            )

        # 会議室の曖昧性チェック
        meeting_room_check = self._check_meeting_room_ambiguity(normalized_question)
        if meeting_room_check:
            return meeting_room_check

        # 施設情報
        if self._is_facility_query(normalized_question):
            return QueryClassificationResult(
                category="facility-info",
                confidence=0.8,
                debug_info={"reason": "Facility keywords detected"},
            )

        # その他のカテゴリ判定（料金、設備、アクセス、営業時間）
        specific_category = self._detect_specific_category(normalized_question)
        if specific_category:
            return specific_category

        # デフォルト
        return QueryClassificationResult(
            category="general",
            confidence=0.5,
            debug_info={"reason": "No specific category matched"},
        )

    def _normalize_query(self, query: str) -> str:
        """クエリを正規化する"""
        normalized = normalize_cafe_query(query)

        # 接続詞の除去
        normalized = re.sub(
            r"^(じゃあ|じゃ|では|それでは|えっと|えーと|あの|その)\s*", "", normalized
        )
        normalized = re.sub(r"^(well|then|so|um|uh)\s*", "", normalized, flags=re.I)

        return normalized.strip()

    def _is_current_time_query(self, normalized_question: str) -> bool:
        """現在時刻クエリかどうかをチェック"""
        if self._is_date_only_query(normalized_question):
            return True

        time_keywords = [
            "現在時刻",
            "現在の時刻",
            "今の時間",
            "今何時",
            "currenttime",
            "whattime",
            "timenow",
            "今時刻",
            "時刻を教えて",
            "whattimeisitnow",
        ]

        # 特殊な条件: "時間を教えて" は営業時間などを含まない場合のみ
        if "時間を教えて" in normalized_question:
            exclusions = ["営業時間", "開店", "閉店", "hours", "カフェ", "店"]
            if not any(exc in normalized_question for exc in exclusions):
                if "今" in normalized_question or "現在" in normalized_question:
                    return True

        return any(keyword in normalized_question for keyword in time_keywords)

    @staticmethod
    def _is_date_only_query(normalized_question: str) -> bool:
        """日付だけを確認するクエリかどうかをチェック"""
        compact = re.sub(r"[\s　]+", "", normalized_question.lower())
        compact = compact.strip("!?？。、.,")

        if compact in {
            "今日",
            "本日",
            "明日",
            "昨日",
            "今週",
            "today",
            "tomorrow",
            "yesterday",
            "thisweek",
            "今天",
            "明天",
            "昨天",
            "本周",
            "这周",
            "這周",
            "这个星期",
            "這個星期",
            "오늘",
            "내일",
            "어제",
            "이번주",
            "금주",
        }:
            return True

        live_info_markers = (
            "イベント",
            "event",
            "予定",
            "schedule",
            "ニュース",
            "news",
            "天気",
            "weather",
            "気温",
            "temperature",
            "雨",
            "rain",
            "最新",
            "latest",
            "検索",
            "search",
            "動向",
            "トレンド",
            "trend",
            "updates",
            "活动",
            "活動",
            "日程",
            "新闻",
            "新聞",
            "天气",
            "天氣",
            "气温",
            "氣溫",
            "下雨",
            "搜索",
            "搜尋",
            "趋势",
            "趨勢",
            "更新",
            "이벤트",
            "행사",
            "일정",
            "뉴스",
            "날씨",
            "기온",
            "비",
            "최신",
            "검색",
            "동향",
            "트렌드",
            "업데이트",
        )
        if any(marker in compact for marker in live_info_markers):
            return False

        relative_date_markers = (
            "今日",
            "本日",
            "明日",
            "昨日",
            "今週",
            "today",
            "tomorrow",
            "yesterday",
            "thisweek",
            "今天",
            "明天",
            "昨天",
            "本周",
            "这周",
            "這周",
            "这个星期",
            "這個星期",
            "오늘",
            "내일",
            "어제",
            "이번주",
            "금주",
        )
        date_question_markers = (
            "日付",
            "何月何日",
            "何日",
            "何曜日",
            "曜日",
            "date",
            "dayisit",
            "dayis",
            "whatday",
            "几月几号",
            "幾月幾號",
            "几月几日",
            "幾月幾日",
            "几号",
            "幾號",
            "几日",
            "幾日",
            "星期几",
            "星期幾",
            "周几",
            "週幾",
            "礼拜几",
            "禮拜幾",
            "日期",
            "日子",
            "哪几天",
            "哪幾天",
            "几号到几号",
            "幾號到幾號",
            "몇월며칠",
            "몇월몇일",
            "며칠",
            "몇일",
            "무슨요일",
            "무슨날",
            "요일",
            "날짜",
            "몇일부터몇일까지",
            "며칠부터며칠까지",
        )
        if any(marker in compact for marker in relative_date_markers) and any(
            marker in compact for marker in date_question_markers
        ):
            return True

        return any(
            marker in compact
            for marker in (
                "今日の日付",
                "本日の日付",
                "明日の日付",
                "昨日の日付",
                "whatisthedate",
                "whatsthedate",
                "todaysdate",
                "tomorrowsdate",
                "yesterdaysdate",
                "今天日期",
                "明天日期",
                "昨天日期",
                "今天是几号",
                "今天是幾號",
                "明天是几号",
                "明天是幾號",
                "昨天是几号",
                "昨天是幾號",
                "今天星期几",
                "今天星期幾",
                "今天周几",
                "今天週幾",
                "오늘날짜",
                "내일날짜",
                "어제날짜",
                "오늘며칠",
                "내일며칠",
                "어제며칠",
                "오늘요일",
                "내일요일",
                "어제요일",
            )
        )

    def _check_cafe_ambiguity(
        self, normalized_question: str, conversation_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Resolve cafe references under the Saino-first post-alpha policy."""

        # "カフェ" が含まれているかチェック
        if has_cafe_or_bar_token(normalized_question):
            resolved_entity = resolve_cafe_entity(normalized_question)
            # 既にエンジニアカフェと明示されている場合
            if resolved_entity == "engineer-cafe" or is_explicit_engineer_cafe_query(
                normalized_question
            ):
                if self.debug_mode:
                    logger.debug("Engineer Cafe query/context detected, treating as facility")
                return {
                    "needs_clarification": False,
                    "category": "facility-info",
                    "confidence": 1.0,
                    "debug_info": {
                        "reason": "Engineer Cafe facility-use context detected",
                        "cafe_entity_resolution": cafe_entity_metadata(
                            entity="engineer_cafe",
                            status="resolved",
                            source="query_classifier",
                        ),
                    },
                }

            # Sainoカフェと明示されている場合
            if resolved_entity == "saino" or is_saino_reference(normalized_question):
                if self.debug_mode:
                    logger.debug("Saino Cafe query/context detected, treating as saino-cafe")
                return {
                    "needs_clarification": False,
                    "category": "saino-cafe",
                    "confidence": 0.9,
                    "debug_info": {
                        "reason": "Saino-first cafe policy",
                        "cafe_entity_resolution": cafe_entity_metadata(
                            entity="saino_cafe",
                            status="resolved",
                            source="query_classifier_saino_first",
                        ),
                    },
                }

            # enhanced featuresが有効で、clarificationが不要な場合
            if conversation_context and not conversation_context.get("needs_clarification", True):
                if conversation_context.get("user_profile") in [
                    "first-timer",
                    "engineer",
                ]:
                    return {
                        "needs_clarification": False,
                        "category": "facility-info",
                        "confidence": 0.8,
                    }

            # 作業関連のキーワードがある場合はエンジニアカフェと判断
            work_keywords = ["コワーキング", "作業", "無料", "利用"]
            if any(keyword in normalized_question for keyword in work_keywords):
                return {
                    "needs_clarification": False,
                    "category": "facility-info",
                    "confidence": 0.9,
                }

            # 明示的に「どちらのカフェか」を問う場合のみ確認へ回す。
            if (
                any(marker in normalized_question for marker in ("どっち", "どちら", "which"))
                and "エンジニアカフェ" not in normalized_question
                and "engineercafe" not in normalized_question
            ):
                return {
                    "needs_clarification": True,
                    "category": "cafe-clarification-needed",
                    "confidence": 0.7,
                    "debug_info": {
                        "reason": "Ambiguous cafe query",
                        "cafe_entity_resolution": cafe_entity_metadata(
                            entity="ambiguous",
                            status="needs_clarification",
                            source="query_classifier",
                        ),
                    },
                }

        return {"needs_clarification": False, "category": None, "confidence": 0}

    def _is_calendar_query(self, normalized_question: str) -> bool:
        """カレンダー/イベントクエリかどうかをチェック"""
        if self._is_date_only_query(normalized_question):
            return False

        calendar_keywords = [
            "カレンダー",
            "calendar",
            "イベント",
            "event",
            "予定",
            "schedule",
            "直近",
            "upcoming",
        ]

        return any(keyword in normalized_question for keyword in calendar_keywords)

    def _is_facility_query(self, normalized_question: str) -> bool:
        """施設情報クエリかどうかをチェック"""
        # エンジニアカフェの明示的な言及
        engineer_cafe_keywords = [
            "エンジニアカフェ",
            "エンジニア カフェ",
            "engineer cafe",
            "engineer カフェ",
        ]
        if any(keyword in normalized_question for keyword in engineer_cafe_keywords):
            return True

        # 休館日関連
        closed_keywords = [
            "休業日",
            "定休日",
            "休み",
            "閉まって",
            "closed",
            "holiday",
            "day off",
            "close",
        ]
        if any(keyword in normalized_question for keyword in closed_keywords):
            return True

        # 地下/地階関連
        basement_keywords = [
            "地下",
            "basement",
            "under space",
            "underスペース",
            "under スペース",
            "b1",
        ]
        if any(keyword in normalized_question for keyword in basement_keywords):
            return True

        # その他の施設関連キーワード
        facility_keywords = [
            "施設",
            "facility",
            "福岡市",
            "fukuoka",
            "公式",
            "official",
            "twitter",
            "x.com",
            "会議室",
            "meeting room",
            "受付",
            "reception",
            "フロア",
            "floor",
            "どこ",
            "where",
            "場所",
            "location",
            "階",
            "部屋",
            "room",
        ]

        return any(keyword in normalized_question for keyword in facility_keywords)

    def _detect_specific_category(
        self, normalized_question: str
    ) -> Optional[QueryClassificationResult]:
        """特定のカテゴリを検出"""
        # 料金
        if "料金" in normalized_question or "price" in normalized_question:
            return QueryClassificationResult(
                category="pricing",
                confidence=0.9,
                debug_info={"reason": "Pricing keywords detected"},
            )

        # 設備
        if "設備" in normalized_question or "facility" in normalized_question:
            return QueryClassificationResult(
                category="facilities",
                confidence=0.8,
                debug_info={"reason": "Facilities keywords detected"},
            )

        # アクセス
        if "アクセス" in normalized_question or "access" in normalized_question:
            return QueryClassificationResult(
                category="access",
                confidence=0.9,
                debug_info={"reason": "Access keywords detected"},
            )

        # 営業時間
        time_keywords = ["時間", "営業", "hours", "open"]
        if any(keyword in normalized_question for keyword in time_keywords):
            return QueryClassificationResult(
                category="hours",
                confidence=0.8,
                debug_info={"reason": "Hours keywords detected"},
            )

        return None

    def _is_saino_cafe_query(self, normalized_question: str) -> bool:
        """Sainoカフェクエリかどうかをチェック"""
        return is_saino_reference(normalized_question)

    def _is_closed_days_query(self, normalized_question: str) -> bool:
        """休館日/休業日クエリかどうかをチェック"""
        closed_keywords = [
            "休業日",
            "定休日",
            "休み",
            "閉まって",
            "closed",
            "holiday",
            "day off",
            "close",
            "休館日",
        ]
        return any(keyword in normalized_question for keyword in closed_keywords)

    def _is_engineer_cafe_specific(self, normalized_question: str) -> bool:
        """エンジニアカフェ特定のクエリかどうかをチェック"""
        return is_explicit_engineer_cafe_query(normalized_question)

    def _is_history_query(self, normalized_question: str) -> bool:
        """歴史関連のクエリかどうかをチェック"""
        history_keywords = [
            "history",
            "歴史",
            "background",
            "started",
            "founded",
            "established",
            "開設",
            "設立",
            "始まり",
            "創立",
        ]
        return any(keyword in normalized_question for keyword in history_keywords)

    def _check_meeting_room_ambiguity(
        self, normalized_question: str
    ) -> Optional[QueryClassificationResult]:
        """会議室の曖昧性をチェック"""
        meeting_room_keywords = ["会議室", "meeting room", "ミーティング", "mtg"]
        has_meeting_room = any(keyword in normalized_question for keyword in meeting_room_keywords)

        floor_keywords = [
            "2階",
            "２階",
            "二階",
            "2f",
            "２f",
            "２Ｆ",
            "地下",
            "basement",
            "under",
        ]
        has_specific_floor = any(keyword in normalized_question for keyword in floor_keywords)

        if has_meeting_room and not has_specific_floor:
            return QueryClassificationResult(
                category="meeting-room-clarification-needed",
                confidence=0.7,
                debug_info={"reason": "Ambiguous meeting room query"},
            )

        return None

    def log_classification(self, result: QueryClassificationResult, query: str) -> None:
        """デバッグ情報を含めてログ出力"""
        if self.debug_mode:
            logger.debug(
                "Classification result: query=%s, category=%s, " "confidence=%s, debug_info=%s",
                query,
                result.category,
                result.confidence,
                result.debug_info,
            )
