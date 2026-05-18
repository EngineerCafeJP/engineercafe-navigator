from __future__ import annotations

from typing import Dict, Optional

from backend.utils.language_types import DEFAULT_NOT_FOUND_RESPONSE


class BusinessInfoMatcherMixin:
    @staticmethod
    def _asks_first_visit_registration(query: str, request_type: Optional[str]) -> bool:
        returning_terms = (
            "registered before",
            "already registered",
            "以前登録",
            "再受付",
            "登録済み",
            "이미 등록",
            "전에 등록",
            "已经登记",
        )
        if any(term in query for term in returning_terms):
            return False

        if request_type == "reception" and (
            "受付" in query or "reception" in query or "check in" in query or "check-in" in query
        ):
            first_visit_terms = (
                "first",
                "first-time",
                "first time",
                "初回",
                "初めて",
                "第一次",
                "처음",
            )
            if any(term in query for term in first_visit_terms):
                return True
        keywords = (
            "first visit",
            "first-time visitor",
            "first time visitor",
            "first-time",
            "first time here",
            "register",
            "registration",
            "初回",
            "初めて",
            "利用登録",
            "第一次",
            "登记",
            "처음",
            "등록",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_membership_overview(query: str, request_type: Optional[str]) -> bool:
        if request_type == "community" and BusinessInfoMatcherMixin._asks_engineer_cafe_lab(query):
            return False

        membership_terms = (
            "membership",
            "member",
            "become a member",
            "member benefits",
            "会員制度",
            "会員登録",
            "会員にな",
            "会员制度",
            "加入会员",
            "會員制度",
            "加入會員",
            "멤버십",
            "회원 등록",
            "회원가입",
        )
        if any(term in query for term in membership_terms):
            return True

        return request_type == "reception" and any(
            term in query
            for term in (
                "sign up",
                "registration",
                "利用登録",
                "登録",
                "登记",
                "登記",
                "등록",
            )
        )

    @staticmethod
    def _asks_member_record_phase2_limitation(query: str) -> bool:
        member_terms = (
            "member number",
            "membership number",
            "member card",
            "member record",
            "member records",
            "会員番号",
            "会員証",
            "会員情報",
            "会员编号",
            "会员号码",
            "会员信息",
            "會員編號",
            "會員資訊",
            "회원 번호",
            "회원증",
            "회원 정보",
            "회원정보",
        )
        capability_terms = (
            "seat",
            "seating",
            "recommend",
            "recommendation",
            "personalized",
            "personalised",
            "profile",
            "lookup",
            "database",
            "db",
            "席",
            "座席",
            "個別",
            "提案",
            "案内",
            "履歴",
            "連携",
            "座位",
            "个别",
            "個別",
            "推荐",
            "資料庫",
            "数据库",
            "좌석",
            "자리",
            "개별",
            "추천",
            "안내",
            "이력",
            "연동",
            "데이터베이스",
        )
        return any(term in query for term in member_terms) and any(
            term in query for term in capability_terms
        )

    @staticmethod
    def _asks_opening_hours(query: str, request_type: Optional[str]) -> bool:
        if request_type == "hours":
            return True
        keywords = (
            "opening hours",
            "open hours",
            "business hours",
            "what time",
            "営業時間",
            "開館時間",
            "何時から",
            "何時まで",
            "营业时间",
            "几点",
            "운영 시간",
            "이용 시간",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_closed_days(query: str) -> bool:
        keywords = (
            "休館日",
            "休業日",
            "定休日",
            "休みの日",
            "お休みの日",
            "閉まっている日",
            "閉まってる日",
            "closed day",
            "closed days",
            "holiday",
            "holidays",
            "闭馆",
            "休馆",
            "闭馆日",
            "休馆日",
            "휴관일",
            "쉬는 날",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_community_program(query: str, request_type: Optional[str]) -> bool:
        if request_type != "community":
            return False
        keywords = ("engineer ignition camp", "eic", "devday")
        return any(
            keyword in query for keyword in keywords
        ) or BusinessInfoMatcherMixin._asks_engineer_cafe_lab(query)

    @staticmethod
    def _asks_engineer_friendly_city(query: str) -> bool:
        keywords = (
            "エンジニアフレンドリーシティ",
            "engineer friendly city",
            "efcとは",
            "efc ",
            "efcアワード",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_engineer_cafe_lab(query: str) -> bool:
        keywords = (
            "engineer cafe lab",
            "エンジニアカフェlab",
            "エンジニアカフェラボ",
            "カフェラボ",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_official_social(query: str) -> bool:
        keywords = (
            "公式sns",
            "snsアカウント",
            "twitter",
            "x（旧twitter）",
            "xアカウント",
            "official sns",
            "social media",
            "sns account",
            "official x",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_english_support(query: str) -> bool:
        keywords = (
            "英語対応",
            "英語版",
            "英語で",
            "english support",
            "english website",
            "english version",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_eic_completion_conditions(query: str) -> bool:
        if not any(keyword in query for keyword in ("eic", "engineer ignition camp")):
            return False
        keywords = (
            "修了",
            "認定",
            "条件",
            "completion",
            "complete",
            "certificate",
            "requirements",
            "结业",
            "认定",
            "条件",
            "수료",
            "인정",
            "조건",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_pricing(query: str, request_type: Optional[str]) -> bool:
        if request_type in ("price", "pricing"):
            return True
        keywords = (
            "cost",
            "fee",
            "price",
            "charge",
            "料金",
            "費用",
            "いくら",
            "收费",
            "费用",
            "요금",
            "비용",
            "얼마",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_consultation(query: str, request_type: Optional[str]) -> bool:
        if request_type == "consultation":
            return True
        keywords = (
            "コミュニティマネージャー",
            "相談",
            "キャリア",
            "転職",
            "スキルチェンジ",
            "技術相談",
            "consultation",
            "career advice",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_skill_change(query: str) -> bool:
        return any(keyword in query for keyword in ("スキルチェンジ", "転職", "career change"))

    @staticmethod
    def _asks_corporate_receipt(query: str) -> bool:
        corporate_markers = ("法人", "会社名", "corporate", "company")
        receipt_markers = ("領収書", "請求書", "receipt", "invoice")
        return any(marker in query for marker in corporate_markers) or any(
            marker in query for marker in receipt_markers
        )

    @staticmethod
    def _asks_reservation_requirement(query: str) -> bool:
        excluded_targets = (
            "event",
            "events",
            "event room",
            "workshop",
            "meetup",
            "seminar",
            "meeting room",
            "conference room",
            "room",
            "イベント",
            "イベントスペース",
            "勉強会",
            "セミナー",
            "ミートアップ",
            "会議室",
            "ミーティングルーム",
            "会议室",
            "活动",
            "이벤트",
            "회의실",
        )
        if any(target in query for target in excluded_targets):
            return False

        reservation_markers = (
            "without a reservation",
            "no reservation",
            "need a reservation",
            "reservation needed",
            "reservation required",
            "予約なし",
            "予約無し",
            "予約不要",
            "予約は必要",
            "予約が必要",
            "予約必要",
            "无需预约",
            "需要预约",
            "예약 없이",
            "예약 필요",
        )
        if not any(marker in query for marker in reservation_markers):
            return False

        regular_use_markers = (
            "engineer cafe",
            "coworking",
            "regular",
            "use",
            "visit",
            "利用",
            "使え",
            "コワーキング",
            "普通",
            "通常",
            "使用",
            "共享办公",
            "이용",
            "코워킹",
        )
        return any(marker in query for marker in regular_use_markers)

    @staticmethod
    def _asks_returning_visit(query: str, request_type: Optional[str]) -> bool:
        if request_type != "reception":
            return False
        markers = (
            "また来ました",
            "前にも来た",
            "前にも来たこと",
            "以前来た",
            "以前利用",
            "returning visitor",
            "welcome back",
        )
        return any(marker in query for marker in markers)

    @staticmethod
    def _asks_what_is_engineer_cafe(query: str, language: str) -> bool:
        if language == "en":
            return "what is engineer cafe" in query
        if language == "ko":
            return "엔지니어 카페" in query and any(
                keyword in query for keyword in ("무엇", "뭐", "어떤 곳", "소개")
            )
        keywords = ("エンジニアカフェって", "工程师咖啡是什么", "엔지니어 카페")
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_contact(query: str) -> bool:
        keywords = ("contact", "phone", "電話", "連絡", "問い合わせ", "联系", "전화", "연락")
        return any(keyword in query for keyword in keywords)

    def _get_default_response(self, language: str, request_type: Optional[str]) -> Dict:
        """デフォルト応答を返す

        RAG検索失敗またはLLMエラー時のフォールバック応答を生成します。

        Args:
            language (str): 言語（ja or en）
            request_type (Optional[str]): リクエストタイプ

        Returns:
            Dict: デフォルト応答辞書
                - answer (str): お詫びメッセージ
                - emotion (str): "apologetic"
                - metadata (Dict): 低信頼度（0.3）とフォールバックソース

        Examples:
            >>> agent = BusinessInfoAgent()
            >>> response = agent._get_default_response("ja", "hours")
            >>> print(response["answer"])
            [sad]申し訳ございません。お探しの情報が見つかりませんでした。質問を言い換えていただくか、スタッフにお問い合わせください。

        Notes:
            - confidence は 0.3 に設定（低信頼度）
            - sources は ["fallback"] を記録
        """
        text = DEFAULT_NOT_FOUND_RESPONSE.get(language, DEFAULT_NOT_FOUND_RESPONSE["ja"])

        return {
            "answer": text,
            "emotion": "apologetic",
            "metadata": {
                "agent": "BusinessInfoAgent",
                "confidence": 0.3,
                "request_type": request_type,
                "sources": ["fallback"],
            },
        }
