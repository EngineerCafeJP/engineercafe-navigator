from __future__ import annotations

from typing import Dict, Optional


def facility_canonical_part2(
    agent, normalized: str, request_type: Optional[str], language: str
) -> Optional[Dict]:
    if request_type == "access" or agent._asks_location(normalized):
        if agent._asks_fukuoka_airport_route(normalized):
            answers = {
                "ja": (
                    "[relaxed]福岡空港からは地下鉄空港線で天神駅まで約11分、"
                    "運賃は260円です。天神駅16番出口から昭和通りを東へ進み、"
                    "徒歩約5分で福岡市赤煉瓦文化館内のエンジニアカフェに着きます。"
                ),
                "en": (
                    "[relaxed]From Fukuoka Airport, take the Subway Airport Line "
                    "to Tenjin Station; it takes about 11 minutes and costs 260 yen. "
                    "From Tenjin Station Exit 16, walk east along Showa-dori for "
                    "about five minutes to the Fukuoka City Red Brick Culture Hall."
                ),
                "zh": (
                    "[relaxed]从福冈机场乘坐地铁机场线到天神站约11分钟，票价260日元。"
                    "从天神站16号出口沿昭和通步行约5分钟即可到达福冈市赤炼瓦文化馆内的工程师咖啡。"
                ),
                "ko": (
                    "[relaxed]후쿠오카공항에서는 지하철 공항선을 타고 텐진역까지 "
                    "약 11분, 요금은 260엔입니다. 텐진역 16번 출구에서 쇼와도리를 "
                    "동쪽으로 약 5분 걸으면 후쿠오카시 아카렌가 문화관 안의 "
                    "엔지니어 카페입니다."
                ),
            }
            return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

        if agent._asks_hakata_route(normalized):
            answers = {
                "ja": (
                    "[relaxed]博多駅からは地下鉄空港線で天神駅まで約6分、"
                    "運賃は210円です。バスの場合は天神方面行きで「天神」周辺で下車し、"
                    "天神駅16番出口から徒歩約5分で到着します。"
                ),
                "en": (
                    "[relaxed]From Hakata Station, take the Subway Airport Line "
                    "to Tenjin Station; it takes about 6 minutes and costs 210 yen. "
                    "Then walk about five minutes from Tenjin Station Exit 16."
                ),
                "zh": (
                    "[relaxed]从博多站乘坐地铁机场线到天神站约6分钟，票价210日元。"
                    "从天神站16号出口步行约5分钟即可到达。"
                ),
                "ko": (
                    "[relaxed]하카타역에서는 지하철 공항선을 타고 텐진역까지 "
                    "약 6분, 요금은 210엔입니다. 텐진역 16번 출구에서 약 5분 걸으면 도착합니다."
                ),
            }
            return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

        if agent._asks_rain_route(normalized):
            answers = {
                "ja": (
                    "[relaxed]雨の日は、天神駅16番出口から天神地下街とアクロス福岡側の"
                    "通路を経由して、赤煉瓦文化館の近くで地上に出るルートが比較的"
                    "濡れる区間を短くできます。地上に出たら昭和通り沿いに進んでください。"
                ),
                "en": (
                    "[relaxed]On rainy days, use the Tenjin underground mall and "
                    "the ACROS Fukuoka side passage from around Tenjin Station Exit 16, "
                    "then come above ground near the Red Brick Culture Hall to minimize "
                    "the exposed walking section."
                ),
                "zh": (
                    "[relaxed]雨天可从天神站16号出口附近经由天神地下街和ACROS福冈侧通道，"
                    "在赤炼瓦文化馆附近出地面，可减少淋雨路段。"
                ),
                "ko": (
                    "[relaxed]비 오는 날에는 텐진역 16번 출구 주변에서 텐진 지하상가와 "
                    "아크로스 후쿠오카 쪽 통로를 이용한 뒤 아카렌가 문화관 근처에서 "
                    "지상으로 나오면 "
                    "비를 맞는 구간을 줄일 수 있습니다."
                ),
            }
            return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

        answers = {
            "ja": (
                "[relaxed]エンジニアカフェは福岡市中央区天神1丁目15番30号、"
                "福岡市赤煉瓦文化館の中にあります。地下鉄空港線の天神駅から"
                "徒歩約5分で、16番出口から昭和通りを東へ進むと赤煉瓦の建物が目印です。"
                "西鉄バスの場合は「天神4丁目」バス停で降りるとすぐです。"
                "専用駐車場はないため、車の場合は天神地下街など近隣の有料駐車場を"
                "利用してください。"
            ),
            "en": (
                "[relaxed]Engineer Cafe is located in the Fukuoka City Red Brick "
                "Culture Hall in Tenjin, Fukuoka. It is about a five-minute walk "
                "from Tenjin Station."
            ),
            "zh": (
                "[relaxed]工程师咖啡位于福冈市中央区天神1丁目15番30号的"
                "福冈市赤炼瓦文化馆内，在一楼，进门后左手边可以找到接待处。"
                "从天神站步行约5分钟。"
            ),
            "ko": (
                "[relaxed]엔지니어 카페는 텐진 아카렌가 문화관 안에 있습니다. "
                "텐진역에서 걸어서 약 5분 거리이며, 방문 시 직원에게 문의하시면 "
                "안내받을 수 있습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "building" or agent._asks_building_history(normalized):
        if agent._asks_building_architecture(normalized):
            answers = {
                "ja": (
                    "[relaxed]赤煉瓦文化館は辰野式の建築で、赤煉瓦に花崗岩の帯、"
                    "八角塔屋とドーム、大理石の玄関、アールヌーボーの装飾が特徴です。"
                    "煉瓦造2階・地下1階で、延床面積は約282平方メートルです。"
                )
            }
            return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

        answers = {
            "ja": (
                "[relaxed]はい、福岡市赤煉瓦文化館は1969年に国の重要文化財に"
                "指定されました。1909年に日本生命保険株式会社九州支店として"
                "建てられ、1994年に復元リニューアルし、2019年にエンジニアカフェが"
                "開設されました。"
            ),
            "en": (
                "[relaxed]The Fukuoka City Red Brick Culture Hall was built in "
                "1909 and designated a National Important Cultural Property in "
                "1969. It was restored and renewed in 1994, and Engineer Cafe "
                "opened in the building in 2019."
            ),
            "zh": (
                "[relaxed]福冈市赤炼瓦文化馆建于1909年，1969年被指定为国家重要文化财。"
                "1994年修复更新，2019年工程师咖啡在馆内开设。"
            ),
            "ko": (
                "[relaxed]후쿠오카시 아카렌가 문화관은 1909년에 지어졌고 "
                "1969년에 국가 중요문화재로 지정되었습니다. 1994년에 복원 리뉴얼되었으며, "
                "2019년에 이 건물 안에 엔지니어 카페가 문을 열었습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "food_drink" or agent._asks_food_policy(normalized):
        answers = {
            "ja": (
                "[relaxed]メインホール、集中スペース、地下施設では飲食できません。"
                "外部食品の持ち込みは原則禁止で、ふた付きの飲み物は持ち込みできます。"
                "cafe&bar sainoで購入した飲食物は、"
                "saino店内、談話室、テラスなど指定エリアで食べられます。"
            ),
            "en": (
                "[relaxed]You can bring drinks in lidded containers. Outside food "
                "is generally not allowed. Food and drinks bought at cafe&bar saino "
                "can be eaten in designated areas such as saino, the lounge, and "
                "the terrace; eating is not allowed in the main hall, Focus Space, "
                "or basement facilities."
            ),
            "zh": (
                "[relaxed]可以携带有盖饮料。外带食物原则上不允许；"
                "在cafe&bar saino购买的餐饮可以在露台和休息区等指定区域食用。"
            ),
            "ko": (
                "[relaxed]뚜껑이 있는 음료는 반입할 수 있습니다. 외부 음식은 "
                "원칙적으로 허용되지 않으며, cafe&bar saino에서 구매한 음식은 "
                "테라스나 라운지 같은 지정 구역에서 드실 수 있어요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_lounge_room(normalized):
        answers = {
            "ja": (
                "[relaxed]談話室は1階のcafe&bar saino近くにある休憩・交流スペースです。"
                "sainoで購入した飲食物を食べられ、軽い打ち合わせや休憩に向いています。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "floor_layout" or agent._asks_floor_layout(normalized):
        answers = {
            "ja": (
                "[relaxed]フロア構成は、1階がメインホール、cafe&bar saino、"
                "談話室、テラスです。2階は赤煉瓦文化館管理の会議室3室、"
                "地下1階はMAKER'sスペース、集中スペース、MTGスペース、"
                "アンダースペース、防音室です。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "accessibility" or agent._asks_accessibility(normalized):
        answers = {
            "ja": (
                "[relaxed]車椅子ではテラス側からスロープを設置して1階を利用できます。"
                "2階と地下1階は利用できません。来館前に080-6742-7231へ"
                "事前連絡することをおすすめします。多目的トイレはありません。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_charger_loan(normalized):
        answers = {
            "ja": (
                "[relaxed]受付でUSB-CやLightningなどの充電器・ケーブルを貸出できます。"
                "数量限定なので、長時間使う場合は持参がおすすめです。各席には"
                "電源コンセントもあります。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_summer_heat(normalized):
        answers = {
            "ja": (
                "[relaxed]赤煉瓦造りの歴史的建造物で蓄熱しやすく、夏場は暑くなりがちです。"
                "エアコンはありますが、完全に冷えるまで時間がかかる場合があります。"
                "地下1階のUnder SpaceやFocus Spaceは比較的涼しくおすすめです。"
                "飲み物をこまめに取りながらご利用ください。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "nearby" or agent._asks_nearby(normalized):
        nearby = agent._nearby_canonical_response(normalized, language)
        if nearby:
            return agent._canonical_result(nearby, request_type)

    if request_type == "temporary_exit" or agent._asks_temporary_exit_policy(normalized):
        answers = {
            "ja": (
                "[relaxed]15分以内の一時外出は、受付カードを持ったまま自由に"
                "出入りできます。15分以上離席する場合は、受付カードを返却して"
                "一度退館手続きをしてください。"
            ),
            "en": (
                "[relaxed]You may step out freely for up to 15 minutes while "
                "keeping your reception card. If you will be away for 15 minutes "
                "or longer, please return the card and complete checkout once."
            ),
            "zh": (
                "[relaxed]15分钟以内的临时外出可以保留接待卡自由进出。"
                "如果离开15分钟以上，请归还接待卡并先办理退馆手续。"
            ),
            "ko": (
                "[relaxed]15분 이내의 일시 외출은 접수 카드를 가지고 자유롭게 "
                "출입할 수 있습니다. 15분 이상 자리를 비울 때는 접수 카드를 "
                "반납하고 한 번 퇴관 절차를 해 주세요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "pets" or agent._asks_pet_policy(normalized):
        answers = {
            "ja": (
                "[relaxed]盲導犬、聴導犬、介助犬などの補助犬は同伴できます。"
                "それ以外のペットは、テラス席を含めて施設全域で同伴できません。"
            ),
            "en": (
                "[relaxed]Service dogs, such as guide, hearing, or assistance "
                "dogs, are allowed. Other pets are not allowed anywhere in the "
                "facility, including the terrace."
            ),
            "zh": (
                "[relaxed]导盲犬、助听犬、介助犬等辅助犬可以同行。"
                "除此之外的宠物，包括露台座位在内，设施全域都不能带入。"
            ),
            "ko": (
                "[relaxed]안내견, 청각도우미견, 보조견 같은 보조견은 동반할 "
                "수 있습니다. 그 외 반려동물은 테라스를 포함한 시설 전체에 "
                "동반할 수 없습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_printer_or_copier(normalized):
        answers = {
            "ja": (
                "[relaxed]館内に書類用プリンター、コピー機、スキャナーは"
                "設置されていません。印刷やコピーが必要な場合は、徒歩2分ほどの"
                "ファミリーマート天神一丁目店など最寄りコンビニの"
                "ネットプリントサービスをご利用ください。"
            ),
            "en": (
                "[relaxed]No. Engineer Cafe does not provide a standard document "
                "printer, copier, or scanner. The B1F MAKER's Space has 3D printers "
                "and laser cutters, but for paper printing please ask staff or use "
                "a nearby convenience store's net-print service."
            ),
            "zh": (
                "[relaxed]馆内没有提供普通文件打印机、复印机或扫描仪的信息。"
                "地下一层MAKER's Space有3D打印机和激光切割机；如需纸张打印，"
                "请询问工作人员或使用附近便利店。"
            ),
            "ko": (
                "[relaxed]건물 안에 일반 문서용 프린터나 복사기가 제공된다는 "
                "안내는 없습니다. 지하 1층 MAKER's Space에는 3D 프린터와 "
                "레이저 커터가 있으니, 종이 출력은 직원에게 문의하거나 "
                "근처 편의점을 이용해 주세요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_wifi_credential(normalized) and agent._asks_business_hours(normalized):
        answers = {
            "ja": (
                "[relaxed]エンジニアカフェの開館時間は9:00〜22:00です。"
                "Wi-FiのSSIDは engnecf-guest-2.4GHz または engnecf-guest-5GHz、"
                "パスワードは akarenga-112years です。受付カードの裏面にも記載されています。"
            ),
            "en": (
                "[relaxed]Engineer Cafe is open from 9:00 to 22:00. "
                "The Wi-Fi SSIDs are engnecf-guest-2.4GHz and engnecf-guest-5GHz, "
                "and the password is akarenga-112years. It is also printed on the "
                "back of the reception card."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_wifi_credential(normalized):
        answers = {
            "ja": (
                "[relaxed]Wi-FiのSSIDは engnecf-guest-2.4GHz または "
                "engnecf-guest-5GHz です。パスワードは akarenga-112years です。"
                "受付カードの裏面にも記載されています。"
            ),
            "en": (
                "[relaxed]Free Wi-Fi is available at Engineer Cafe. The SSIDs are "
                "engnecf-guest-2.4GHz and engnecf-guest-5GHz, and the password is "
                "akarenga-112years. It is also printed on the back of the reception "
                "card and can be used in the facility, including the terrace."
            ),
            "zh": (
                "[relaxed]工程师咖啡可以使用免费Wi-Fi。SSID为 "
                "engnecf-guest-2.4GHz 或 engnecf-guest-5GHz，密码是 "
                "akarenga-112years。接待卡背面也有记载，设施内包括露台都可以使用。"
            ),
            "ko": (
                "[relaxed]엔지니어 카페의 무료 Wi-Fi SSID는 "
                "engnecf-guest-2.4GHz 또는 engnecf-guest-5GHz이고, "
                "비밀번호는 akarenga-112years입니다. 접수 카드 뒷면에서도 "
                "확인할 수 있으며 테라스를 포함한 시설 내에서 이용할 수 있습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_available_spaces(normalized):
        answers = {
            "ja": (
                "[relaxed]エンジニアカフェのスペースについてご案内します。"
                "メインホール、集中スペース、MAKER'sスペース、MTGスペース、"
                "防音室、アンダースペース、テラス、談話室、2階会議室などがあります。"
                "用途に応じてご選択ください。"
            ),
            "en": (
                "[relaxed]Available spaces include the 1F Main Hall for coworking "
                "and events; B1F Focus Space with six silent booths, Meeting Space, "
                "MAKER's Space with 3D printers and laser cutters, Under Space, and "
                "one Soundproof Room; and three paid meeting rooms on 2F."
            ),
            "zh": (
                "[relaxed]可使用的主要空间包括一楼主厅（共享办公和活动）、"
                "地下一层集中空间6席、会议空间、MAKER's Space、Under Space和防音室，"
                "二楼还有3间收费会议室。"
            ),
            "ko": (
                "[relaxed]주요 이용 공간은 1층 메인 홀(코워킹・이벤트), "
                "지하 1층 집중 스페이스 6석, 미팅 스페이스, MAKER's Space, "
                "언더 스페이스, 방음실이며, 2층에는 유료 회의실 3개가 있습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    return None
