from __future__ import annotations

from typing import Dict, Optional

from backend.utils.cafe_entity import is_saino_reference


class BusinessInfoCafeMixin:
    @staticmethod
    def _asks_saino_cafe(query: str) -> bool:
        return is_saino_reference(query)

    @staticmethod
    def _saino_cafe_answer(
        query: str, language: str, request_type: Optional[str] = None
    ) -> Optional[str]:
        if request_type == "hours" or any(
            keyword in query
            for keyword in (
                "営業時間",
                "営業",
                "定休日",
                "休業日",
                "休み",
                "business hours",
                "opening hours",
                "hours",
                "closed",
                "holiday",
            )
        ):
            answers = {
                "ja": (
                    "[relaxed]cafe&bar sainoの営業時間は、平日はDay Time "
                    "12:00〜17:00、Night Time 18:00〜20:00、土日祝は"
                    "11:00〜20:00です。定休日は月曜と水曜です。"
                ),
                "en": (
                    "[relaxed]cafe&bar saino is open on weekdays from 12:00 to "
                    "17:00 for Day Time and 18:00 to 20:00 for Night Time, and "
                    "on weekends and holidays from 11:00 to 20:00. It is closed "
                    "on Mondays and Wednesdays."
                ),
                "zh": (
                    "[relaxed]cafe&bar saino平日Day Time为12:00到17:00，"
                    "Night Time为18:00到20:00；周末和节假日为11:00到20:00。"
                    "周一和周三定休。"
                ),
                "ko": (
                    "[relaxed]cafe&bar saino의 영업시간은 평일 Day Time "
                    "12:00-17:00, Night Time 18:00-20:00이며, 주말과 공휴일은 "
                    "11:00-20:00입니다. 정기 휴일은 월요일과 수요일입니다."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("フード", "food", "menu", "メニュー", "ランチ")):
            answers = {
                "ja": (
                    "[relaxed]サイノカフェでランチ向けに食べるなら、サンドや"
                    "ワッフルなどのフードメニューがあります。てりたまハンバーグサンド"
                    "700円、ツナチーズメルトサンド700円、あんバター白玉サンド"
                    "650円、ワッフル420円、アイスクリーム420円などで、"
                    "ドリンクセットは50円引きです。"
                ),
                "en": (
                    "[relaxed]For lunch at cafe&bar saino, choose from food items "
                    "such as teritama hamburger sandwiches for 700 yen, tuna cheese "
                    "melt sandwiches for 700 yen, "
                    "an-butter shiratama sandwiches for 650 yen, waffles for 420 yen, "
                    "and ice cream for 420 yen. Drink sets are 50 yen off."
                ),
                "zh": (
                    "[relaxed]saino咖啡有照烧鸡蛋汉堡三明治700日元、金枪鱼芝士"
                    "热三明治700日元、红豆黄油白玉三明治650日元、华夫饼420日元、"
                    "冰淇淋420日元等。饮料套餐可减50日元。"
                ),
                "ko": (
                    "[relaxed]saino 카페의 푸드 메뉴에는 데리타마 햄버그 샌드 "
                    "700엔, 참치 치즈 멜트 샌드 700엔, 앙버터 시라타마 샌드 "
                    "650엔, 와플 420엔, 아이스크림 420엔 등이 있습니다. "
                    "드링크 세트는 50엔 할인됩니다."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(
            keyword in query for keyword in ("コーヒー", "coffee", "カフェラテ", "値段", "price")
        ):
            answers = {
                "ja": (
                    "[relaxed]サイノカフェのコーヒーは、ブレンドコーヒー380円、"
                    "シングルオリジン460円から、エスプレッソ400円、カフェラテ"
                    "570円、カフェモカ700円です。"
                ),
                "en": (
                    "[relaxed]At cafe&bar saino, blended coffee is 380 yen, single "
                    "origin coffee starts at 460 yen, espresso is 400 yen, cafe latte "
                    "is 570 yen, and cafe mocha is 700 yen."
                ),
                "zh": (
                    "[relaxed]saino咖啡的拼配咖啡是380日元，单品咖啡460日元起，"
                    "浓缩咖啡400日元，拿铁570日元，摩卡700日元。"
                ),
                "ko": (
                    "[relaxed]saino 카페의 커피는 블렌드 커피 380엔, 싱글 오리진 "
                    "460엔부터, 에스프레소 400엔, 카페라테 570엔, 카페모카 700엔입니다."
                ),
            }
            return answers.get(language, answers["ja"])

        if any(keyword in query for keyword in ("アルコール", "お酒", "alcohol", "beer", "bar")):
            answers = {
                "ja": (
                    "[relaxed]はい、cafe&bar sainoはNight Timeの18:00〜20:00に"
                    "バー営業をしています。ハイネケン500円、ハイボール450円から、"
                    "カクテル各700円などがあります。"
                ),
                "en": (
                    "[relaxed]Yes. cafe&bar saino operates as a bar during Night "
                    "Time from 18:00 to 20:00. Heineken is 500 yen, highballs start "
                    "at 450 yen, and cocktails are 700 yen each."
                ),
                "zh": (
                    "[relaxed]可以。cafe&bar saino在Night Time 18:00到20:00作为酒吧营业。"
                    "喜力啤酒500日元，Highball 450日元起，鸡尾酒每杯700日元等。"
                ),
                "ko": (
                    "[relaxed]네, cafe&bar saino는 Night Time인 18:00-20:00에 "
                    "바로도 운영합니다. 하이네켄은 500엔, 하이볼은 450엔부터, "
                    "칵테일은 각 700엔입니다."
                ),
            }
            return answers.get(language, answers["ja"])

        answers = {
            "ja": (
                "[relaxed]隣のカフェは1階のcafe&bar sainoです。営業時間は、"
                "平日はDay Time 12:00〜17:00、Night Time 18:00〜20:00、"
                "土日祝は11:00〜20:00です。月曜と水曜が定休日で、"
                "コーヒーやランチ向けのサンド、Night Timeのバー利用も案内できます。"
            ),
            "en": (
                "[relaxed]The adjacent cafe is cafe&bar saino on the 1st floor. "
                "It is open on weekdays from 12:00 to 17:00 for Day Time and "
                "18:00 to 20:00 for Night Time, and on weekends and holidays "
                "from 11:00 to 20:00. It is closed on Mondays and Wednesdays."
            ),
            "zh": (
                "[relaxed]旁边的咖啡店是1楼的cafe&bar saino。平日Day Time为"
                "12:00到17:00，Night Time为18:00到20:00；周末和节假日为"
                "11:00到20:00。周一和周三定休。"
            ),
            "ko": (
                "[relaxed]옆 카페는 1층의 cafe&bar saino입니다. 평일 Day Time은 "
                "12:00-17:00, Night Time은 18:00-20:00이며, 주말과 공휴일은 "
                "11:00-20:00입니다. 정기 휴일은 월요일과 수요일입니다."
            ),
        }
        return answers.get(language, answers["ja"])

    @staticmethod
    def _ambiguous_cafe_hours_answer(language: str) -> str:
        answers = {
            "ja": (
                "[relaxed]カフェの営業時間は、エンジニアカフェなら9:00〜22:00、"
                "併設のcafe&bar sainoなら平日12:00〜17:00と18:00〜20:00、"
                "土日祝11:00〜20:00です。どちらのカフェについてか指定すると、"
                "より正確に案内できます。"
            ),
            "en": (
                "[relaxed]For cafe hours, Engineer Cafe is open from 9:00 to 22:00. "
                "The attached cafe&bar saino is open weekdays 12:00-17:00 and "
                "18:00-20:00, and weekends/holidays 11:00-20:00."
            ),
            "zh": (
                "[relaxed]如果问“咖啡”的营业时间，工程师咖啡是9:00到22:00。"
                "馆内cafe&bar saino平日为12:00到17:00和18:00到20:00，"
                "周末和节假日为11:00到20:00。"
            ),
            "ko": (
                "[relaxed]카페 영업시간이라면 엔지니어 카페는 9:00-22:00입니다. "
                "함께 있는 cafe&bar saino는 평일 12:00-17:00 및 18:00-20:00, "
                "주말과 공휴일은 11:00-20:00입니다."
            ),
        }
        return answers.get(language, answers["ja"])

    @staticmethod
    def _canonical_result(
        answer: str,
        request_type: Optional[str],
        *,
        category: Optional[str] = None,
        cafe_entity_resolution: Optional[dict] = None,
    ) -> Dict:
        metadata = {
            "agent": "BusinessInfoAgent",
            "confidence": 0.95,
            "request_type": request_type,
            "route": category or request_type or "business_info",
            "sources": ["enhanced_rag"],
        }
        if category:
            metadata["category"] = category
        if cafe_entity_resolution:
            metadata["cafe_entity_resolution"] = cafe_entity_resolution
        return {
            "answer": answer,
            "emotion": "relaxed",
            "metadata": metadata,
        }
