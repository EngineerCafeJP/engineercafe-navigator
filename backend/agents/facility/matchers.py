from __future__ import annotations

from typing import Dict, Optional

from backend.config.routing_constants import match_pet_policy_keywords


class FacilityMatcherMixin:
    @staticmethod
    def _canonical_result(answer: str, request_type: Optional[str]) -> Dict:
        return {
            "answer": answer,
            "emotion": "relaxed",
            "metadata": {
                "agent": "FacilityAgent",
                "confidence": 0.95,
                "category": "facility-info",
                "request_type": request_type,
                "route": "facility-info",
                "sources": ["enhanced_rag"],
            },
        }

    @staticmethod
    def _asks_location(query: str) -> bool:
        keywords = (
            "where",
            "located",
            "access",
            "アクセス",
            "どこ",
            "在哪里",
            "위치",
            "어디",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_fukuoka_airport_route(query: str) -> bool:
        return any(keyword in query for keyword in ("福岡空港", "fukuoka airport", "机场", "공항"))

    @staticmethod
    def _asks_hakata_route(query: str) -> bool:
        return any(keyword in query for keyword in ("博多駅", "hakata station", "하카타역"))

    @staticmethod
    def _asks_rain_route(query: str) -> bool:
        return any(keyword in query for keyword in ("雨の日", "rainy", "rain", "下雨", "비 오는"))

    @staticmethod
    def _asks_nearby(query: str) -> bool:
        keywords = (
            "周辺",
            "近く",
            "近隣",
            "ランチ",
            "病院",
            "ホテル",
            "コンビニ",
            "nearby",
            "lunch",
            "clinic",
            "hospital",
            "hotel",
            "convenience store",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _nearby_canonical_response(query: str, language: str) -> Optional[str]:
        if any(keyword in query for keyword in ("ランチ", "lunch", "restaurant", "レストラン")):
            answers = {
                "ja": (
                    "[relaxed]周辺でランチを探すなら、天神地下街に徒歩3〜5分で多数の飲食店があります。"
                    "西中洲エリアも徒歩約5分で、アクロス福岡内にも飲食店があります。"
                    "軽食なら近隣コンビニも利用できます。"
                ),
                "en": (
                    "[relaxed]For lunch nearby, Tenjin Underground Mall has many "
                    "restaurants about a 3 to 5 minute walk away. Nishinakasu is about "
                    "five minutes away, and ACROS Fukuoka also has restaurants. "
                    "Nearby convenience stores are useful for light meals."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("病院", "clinic", "hospital", "医療")):
            answers = {
                "ja": (
                    "[relaxed]近くの医療機関として、アクロス福岡4階の麻生クリニック、"
                    "あやすぎビルクリニック、黒田クリニックが徒歩1〜3分圏内にあります。"
                    "総合病院が必要な場合は博多方面も候補です。緊急時は119番に通報してください。"
                ),
                "en": (
                    "[relaxed]Nearby clinics include Aso Clinic on the 4F of ACROS "
                    "Fukuoka, Ayasugi Building Clinic, and Kuroda Clinic, about a "
                    "1 to 3 minute walk away. For emergencies, call 119."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("ホテル", "hotel", "accommodation", "宿泊")):
            answers = {
                "ja": (
                    "[relaxed]近くのホテルなら、高級ホテルでは西鉄グランドホテルが徒歩約5分、"
                    "ソラリア西鉄ホテルが徒歩約7分です。ビジネス利用ならプラザホテル天神が"
                    "徒歩約3分です。ゲストハウスならWeBase博多なども候補になります。"
                ),
                "en": (
                    "[relaxed]Nearby hotel options include Nishitetsu Grand Hotel "
                    "about five minutes away, Solaria Nishitetsu Hotel about seven "
                    "minutes away, and Plaza Hotel Tenjin about three minutes away."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("コンビニ", "convenience store")):
            answers = {
                "ja": (
                    "[relaxed]近くのコンビニは、ファミリーマート天神一丁目店、"
                    "ファミリーマート天神四丁目店、ローソンS天神ブリック店が徒歩1〜3分圏内です。"
                    "ATMや軽食の利用にも便利です。"
                ),
                "en": (
                    "[relaxed]Nearby convenience stores include FamilyMart Tenjin "
                    "1-chome, FamilyMart Tenjin 4-chome, and Lawson S Tenjin Brick, "
                    "about a 1 to 3 minute walk away."
                ),
            }
            return answers.get(language, answers["ja"])

        return None

    @staticmethod
    def _asks_power_outlet(query: str) -> bool:
        keywords = (
            "power",
            "outlet",
            "outlets",
            "socket",
            "sockets",
            "plug",
            "電源",
            "コンセント",
            "插座",
            "电源",
            "전원",
            "콘센트",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_meeting_room_pricing(query: str) -> bool:
        return any(keyword in query for keyword in ("会議室", "meeting room")) and any(
            keyword in query for keyword in ("料金", "いくら", "fee", "cost", "price")
        )

    @staticmethod
    def _asks_main_hall(query: str) -> bool:
        if not any(keyword in query for keyword in ("メインホール", "main hall")):
            return False
        excluded_markers = ("貸切", "飲食", "食べ", "food", "eat", "exclusive", "rental")
        if any(marker in query for marker in excluded_markers):
            return False
        main_hall_info_markers = (
            "どこ",
            "場所",
            "ありますか",
            "ある",
            "どんなスペース",
            "どんな場所",
            "どの階",
            "何階",
            "where",
            "located",
            "location",
            "what kind",
        )
        return any(marker in query for marker in main_hall_info_markers)

    @staticmethod
    def _asks_maker_space_equipment(query: str) -> bool:
        maker_markers = ("maker'sスペース", "maker's space", "makersスペース", "メイカースペース")
        equipment_markers = ("機材", "設備", "使え", "利用", "equipment", "facilities")
        return any(marker in query for marker in maker_markers) and any(
            marker in query for marker in equipment_markers
        )

    @staticmethod
    def _asks_exclusive_rental(query: str) -> bool:
        rental_markers = ("貸切", "貸し切り", "イベント利用", "exclusive", "rental")
        return any(marker in query for marker in rental_markers)

    @staticmethod
    def _asks_building_architecture(query: str) -> bool:
        architecture_markers = (
            "建築的特徴",
            "建築の特徴",
            "辰野式",
            "花崗岩",
            "八角塔屋",
            "ドーム",
            "アールヌーボー",
            "architectural",
            "architecture",
        )
        return any(marker in query for marker in architecture_markers)

    @staticmethod
    def _asks_building_history(query: str) -> bool:
        return any(
            keyword in query for keyword in ("重要文化財", "赤煉瓦", "red brick", "historic")
        )

    @staticmethod
    def _asks_food_policy(query: str) -> bool:
        keywords = (
            "food",
            "drink",
            "eat",
            "outside food",
            "食べ物",
            "飲み物",
            "飲食",
            "食物",
            "自带食物",
            "带食物",
            "带吃的",
            "外带食物",
            "饮料",
            "餐饮",
            "음식",
            "음료",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_cafe_drink_request(query: str) -> bool:
        drink_markers = (
            "コーヒー",
            "珈琲",
            "カフェラテ",
            "カフェモカ",
            "エスプレッソ",
            "ドリンク",
            "coffee",
            "latte",
            "espresso",
            "beverage",
        )
        desire_markers = (
            "飲みたい",
            "注文",
            "オーダー",
            "買いたい",
            "ください",
            "want",
            "order",
            "buy",
            "grab",
        )
        return any(marker in query for marker in drink_markers) and (
            any(marker in query for marker in desire_markers)
            or any(marker in query for marker in ("コーヒー", "珈琲", "coffee"))
        )

    @staticmethod
    def _asks_break_request(query: str) -> bool:
        return any(
            marker in query
            for marker in (
                "休憩",
                "休みたい",
                "一息",
                "ゆっくり",
                "ちょっと休",
                "take a break",
                "rest",
                "relax",
            )
        )

    @staticmethod
    def _asks_temporary_exit_policy(query: str) -> bool:
        keywords = (
            "一時外出",
            "途中外出",
            "外出のルール",
            "出入り",
            "再入館",
            "再入場",
            "離席",
            "15分以内",
            "15分以上",
            "temporary exit",
            "step out",
            "leave temporarily",
            "re-enter",
            "reentry",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_pet_policy(query: str) -> bool:
        return match_pet_policy_keywords(query)

    @staticmethod
    def _asks_3d_printer_filament_price(query: str) -> bool:
        printer_markers = ("3dプリンター", "3d printer", "3d打印", "3d 프린터")
        material_markers = ("フィラメント", "filament", "材料", "素材", "耗材")
        price_markers = (
            "料金",
            "価格",
            "費用",
            "値段",
            "いくら",
            "price",
            "fee",
            "cost",
            "收费",
            "费用",
        )
        has_printer_or_material = any(marker in query for marker in printer_markers) or any(
            marker in query for marker in material_markers
        )
        return has_printer_or_material and any(marker in query for marker in price_markers)

    @staticmethod
    def _asks_3d_printer_use(query: str) -> bool:
        printer_markers = ("3dプリンター", "3d printer", "3d打印", "3d 프린터")
        use_markers = (
            "使い方",
            "使いたい",
            "使えますか",
            "利用",
            "予約",
            "講習",
            "use",
            "reservation",
            "reserve",
            "training",
            "使用",
            "预约",
            "사용",
            "예약",
        )
        return any(marker in query for marker in printer_markers) and any(
            marker in query for marker in use_markers
        )

    @staticmethod
    def _asks_toilet(query: str) -> bool:
        keywords = (
            "トイレ",
            "お手洗い",
            "おてあらい",
            "化粧室",
            "toilet",
            "restroom",
            "bathroom",
            "洗手间",
            "厕所",
            "화장실",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_multipurpose_toilet(query: str) -> bool:
        return any(
            keyword in query
            for keyword in (
                "多目的トイレ",
                "多目的",
                "accessible restroom",
                "accessible toilet",
                "multipurpose",
            )
        )

    @staticmethod
    def _asks_online_meeting_place(query: str) -> bool:
        keywords = (
            "オンライン会議",
            "オンラインミーティング",
            "web会議",
            "通話",
            "電話できる場所",
            "電話したい",
            "防音室",
            "phone booth",
            "online meeting",
            "video call",
            "take a call",
            "线上会议",
            "在线会议",
            "通话",
            "화상 회의",
            "온라인 미팅",
            "통화",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_soundproof_room(query: str) -> bool:
        return any(keyword in query for keyword in ("防音室", "soundproof room", "phone booth"))

    @staticmethod
    def _asks_lounge_room(query: str) -> bool:
        return any(keyword in query for keyword in ("談話室", "ラウンジ", "lounge"))

    @staticmethod
    def _asks_floor_layout(query: str) -> bool:
        keywords = (
            "フロア構成",
            "フロアマップ",
            "フロアガイド",
            "floor layout",
            "floor map",
            "floor guide",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_accessibility(query: str) -> bool:
        keywords = (
            "車椅子",
            "バリアフリー",
            "スロープ",
            "エレベーター",
            "wheelchair",
            "accessibility",
            "accessible",
            "barrier-free",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_photography_policy(query: str) -> bool:
        keywords = (
            "撮影",
            "写真",
            "カメラ",
            "スナップ",
            "photo",
            "photography",
            "filming",
            "camera",
            "拍照",
            "摄影",
            "촬영",
            "사진",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_charger_loan(query: str) -> bool:
        charger_markers = ("充電器", "充電ケーブル", "usb-c", "lightning", "charger", "cable")
        loan_markers = ("借り", "貸出", "貸し出し", "ありますか", "borrow", "loan")
        return any(marker in query for marker in charger_markers) and any(
            marker in query for marker in loan_markers
        )

    @staticmethod
    def _asks_summer_heat(query: str) -> bool:
        return any(keyword in query for keyword in ("夏場", "暑い", "暑く", "heat", "hot"))

    @staticmethod
    def _asks_focus_space(query: str) -> bool:
        keywords = (
            "集中スペース",
            "focus space",
            "静かに作業",
            "静かな作業",
            "集中できる",
            "集中空间",
            "집중 스페이스",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_children_policy(query: str) -> bool:
        keywords = (
            "子連れ",
            "子供",
            "子ども",
            "お子様",
            "ベビーカー",
            "children",
            "kids",
            "stroller",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_solicitation_or_nap_policy(query: str) -> bool:
        keywords = (
            "勧誘",
            "名刺交換",
            "セールス",
            "営業行為",
            "営利目的",
            "仮眠",
            "昼寝",
            "solicitation",
            "sales",
            "nap",
            "sleep",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_lost_found(query: str) -> bool:
        keywords = (
            "忘れ物",
            "落とし物",
            "なくした",
            "失くした",
            "置き忘れ",
            "紛失",
            "lost",
            "missing",
            "left behind",
            "left my",
            "forgot",
            "遗失",
            "丢失",
            "분실",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_laser_cutter_materials(query: str) -> bool:
        laser_markers = (
            "レーザー加工機",
            "レーザーカッター",
            "laser cutter",
            "激光",
            "레이저",
        )
        material_markers = (
            "素材",
            "材料",
            "使える",
            "使えますか",
            "material",
            "materials",
            "acrylic",
            "pvc",
            "材质",
            "材料",
            "소재",
            "재료",
        )
        return any(marker in query for marker in laser_markers) and any(
            marker in query for marker in material_markers
        )

    @staticmethod
    def _asks_laser_cutter_use(query: str) -> bool:
        laser_markers = (
            "レーザー加工機",
            "レーザーカッター",
            "laser cutter",
            "激光",
            "레이저",
        )
        use_markers = (
            "使いたい",
            "使えますか",
            "利用",
            "予約",
            "講習",
            "use",
            "reservation",
            "training",
            "使用",
            "预约",
            "사용",
        )
        return any(marker in query for marker in laser_markers) and any(
            marker in query for marker in use_markers
        )

    @staticmethod
    def _asks_projector_or_av_loan(query: str) -> bool:
        equipment_markers = (
            "プロジェクター",
            "スクリーン",
            "マイク",
            "4kモニター",
            "hdmi",
            "projector",
            "screen",
            "microphone",
            "4k monitor",
        )
        loan_markers = (
            "借り",
            "貸出",
            "貸し出し",
            "使えますか",
            "利用",
            "borrow",
            "loan",
            "lend",
            "available",
            "rent",
        )
        return any(marker in query for marker in equipment_markers) and any(
            marker in query for marker in loan_markers
        )

    @staticmethod
    def _asks_water_server(query: str) -> bool:
        keywords = (
            "ウォーターサーバー",
            "給水",
            "自動販売機",
            "water server",
            "water dispenser",
            "vending machine",
            "饮水机",
            "自动售货机",
            "워터 서버",
            "자판기",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_bicycle_parking(query: str) -> bool:
        keywords = (
            "駐輪場",
            "駐輪",
            "自転車",
            "bicycle parking",
            "bike parking",
            "cycle parking",
            "자전거 주차",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_printer_or_copier(query: str) -> bool:
        keywords = (
            "printer",
            "copier",
            "print",
            "copy",
            "プリンター",
            "コピー",
            "打印",
            "复印",
            "프린터",
            "복사",
        )
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_available_spaces(query: str) -> bool:
        space_markers = (
            "スペースを使いたい",
            "利用可能スペース",
            "どんなスペース",
            "available spaces",
            "what spaces",
            "spaces are available",
        )
        return any(marker in query for marker in space_markers)

    @staticmethod
    def _asks_wifi_credential(query: str) -> bool:
        keywords = ("ssid", "password", "パスワード", "密码", "비밀번호")
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _asks_business_hours(query: str) -> bool:
        business_hours_markers = (
            "営業時間",
            "開館時間",
            "何時",
            "いつまで",
            "opening hours",
            "business hours",
            "open hours",
        )
        return any(marker in query for marker in business_hours_markers)
