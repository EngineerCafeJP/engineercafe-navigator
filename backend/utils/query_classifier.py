"""
QueryClassifier - クエリ分類専用クラス

TypeScript版から移植:
frontend/src/lib/query-classifier.ts
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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

        # エンジニアカフェ特定のクエリ（カフェ曖昧性チェックより前に移動）
        if self._is_engineer_cafe_specific(normalized_question):
            return QueryClassificationResult(
                category="facility-info",
                confidence=1.0,
                debug_info={"reason": "Engineer Cafe specific"},
            )

        # Sainoカフェの明示的なクエリ（カフェ曖昧性チェックより前に）
        if self._is_saino_cafe_query(normalized_question):
            return QueryClassificationResult(
                category="saino-cafe",
                confidence=0.9,
                debug_info={"reason": "Saino cafe detected"},
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
        normalized = query.lower()

        # Saino関連の正規化
        normalized = re.sub(r"coffee say no", "saino cafe", normalized)
        normalized = re.sub(r"才能", "saino", normalized)
        normalized = re.sub(r"say no", "saino", normalized)
        normalized = re.sub(r"才能カフェ", "saino cafe", normalized)
        normalized = re.sub(r"才能 カフェ", "saino cafe", normalized)
        normalized = re.sub(r"セイノ", "saino", normalized)
        normalized = re.sub(r"サイノ", "saino", normalized)

        # 接続詞の除去
        normalized = re.sub(
            r"^(じゃあ|じゃ|では|それでは|えっと|えーと|あの|その)\s*", "", normalized
        )
        normalized = re.sub(r"^(well|then|so|um|uh)\s*", "", normalized, flags=re.I)

        return normalized.strip()

    def _is_current_time_query(self, normalized_question: str) -> bool:
        """現在時刻クエリかどうかをチェック"""
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

    def _check_cafe_ambiguity(
        self, normalized_question: str, conversation_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """カフェの曖昧性をチェック"""

        # "カフェ" が含まれているかチェック
        if "カフェ" in normalized_question or "cafe" in normalized_question:
            # 既にエンジニアカフェと明示されている場合
            if "エンジニアカフェ" in normalized_question or "engineercafe" in normalized_question:
                if self.debug_mode:
                    print("[QueryClassifier] Explicit Engineer Cafe query, treating as facility")
                return {
                    "needs_clarification": False,
                    "category": "facility-info",
                    "confidence": 1.0,
                }

            # Sainoカフェと明示されている場合
            if "saino" in normalized_question or "サイノ" in normalized_question:
                if self.debug_mode:
                    print("[QueryClassifier] Explicit Saino Cafe query, treating as saino-cafe")
                return {
                    "needs_clarification": False,
                    "category": "saino-cafe",
                    "confidence": 1.0,
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

            # 曖昧な場合は確認が必要
            if (
                "エンジニアカフェ" not in normalized_question
                and "engineercafe" not in normalized_question
            ):
                return {
                    "needs_clarification": True,
                    "category": "cafe-clarification-needed",
                    "confidence": 0.7,
                    "debug_info": {"reason": "Ambiguous cafe query"},
                }

        return {"needs_clarification": False, "category": "", "confidence": 0}

    def _is_calendar_query(self, normalized_question: str) -> bool:
        """カレンダー/イベントクエリかどうかをチェック"""
        calendar_keywords = [
            "カレンダー",
            "calendar",
            "イベント",
            "event",
            "予定",
            "schedule",
            "今日",
            "today",
            "明日",
            "tomorrow",
            "今週",
            "this week",
            "直近",
            "upcoming",
            "何月",
            "何日",
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

        # 会議室の曖昧性
        meeting_room_keywords = ["会議室", "meeting room", "ミーティング", "mtg"]
        has_meeting_room = any(keyword in normalized_question for keyword in meeting_room_keywords)

        floor_keywords = ["2階", "2f", "地下", "basement", "under"]
        has_specific_floor = any(keyword in normalized_question for keyword in floor_keywords)

        if has_meeting_room and not has_specific_floor:
            return QueryClassificationResult(
                category="meeting-room-clarification-needed",
                confidence=0.7,
                debug_info={"reason": "Ambiguous meeting room query"},
            )

        return None

    def _is_saino_cafe_query(self, normalized_question: str) -> bool:
        """Sainoカフェクエリかどうかをチェック"""
        saino_keywords = ["サイノ", "saino"]
        has_saino = any(keyword in normalized_question for keyword in saino_keywords)

        併設_keywords = ["併設", "併設されてる"]
        cafe_keywords = ["カフェ", "cafe", "bar"]

        has_併設_cafe = any(併設 in normalized_question for 併設 in 併設_keywords) and any(
            cafe in normalized_question for cafe in cafe_keywords
        )

        return has_saino or has_併設_cafe

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
        keywords = [
            "エンジニアカフェ",
            "エンジニア カフェ",
            "engineer cafe",
            "engineer カフェ",
            "engineercafe",
        ]
        return any(keyword in normalized_question for keyword in keywords)

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

        floor_keywords = ["2階", "2f", "地下", "basement", "under"]
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
            print("[QueryClassifier] Classification result:")
            print(f"  Query: {query}")
            print(f"  Category: {result.category}")
            print(f"  Confidence: {result.confidence}")
            if result.debug_info:
                print(f"  Debug Info: {result.debug_info}")
