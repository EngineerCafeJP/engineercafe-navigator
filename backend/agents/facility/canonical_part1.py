from __future__ import annotations

from typing import Dict, Optional


def facility_canonical_part1(
    agent, normalized: str, request_type: Optional[str], language: str
) -> Optional[Dict]:
    from backend.agents.business_info_agent import BusinessInfoAgent

    if BusinessInfoAgent._asks_saino_cafe(normalized):
        answer = BusinessInfoAgent._saino_cafe_answer(normalized, language)
        if answer:
            return agent._canonical_result(answer, request_type)

    if agent._asks_cafe_drink_request(normalized):
        answers = {
            "ja": (
                "[relaxed]コーヒーでしたら、1階のcafe&bar sainoで注文できます。"
                "ブレンドコーヒー380円、カフェラテ570円、カフェモカ700円があります。"
                "購入した飲み物は、saino店内、談話室、テラスなど指定エリアでお楽しみください。"
            ),
            "en": (
                "[relaxed]For coffee, please order at cafe&bar saino on the 1st floor. "
                "Blend coffee is 380 yen, cafe latte is 570 yen, and cafe mocha is "
                "700 yen. Drinks bought at saino can be enjoyed in designated areas "
                "such as saino, the lounge, and the terrace."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_break_request(normalized):
        answers = {
            "ja": (
                "[relaxed]少し休憩するなら、1階のcafe&bar saino、談話室、"
                "テラスが使いやすいです。sainoで購入した飲み物や軽食は、"
                "saino店内、談話室、テラスなど指定エリアで楽しめます。"
            ),
            "en": (
                "[relaxed]For a short break, cafe&bar saino, the lounge, and the "
                "terrace on the 1st floor are good options. Food and drinks bought "
                "at saino can be enjoyed in designated areas such as saino, the "
                "lounge, and the terrace."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_main_hall(normalized):
        answers = {
            "ja": (
                "[relaxed]1階メインホールはイベント優先のコワーキングスペースです。"
                "通常は約30席あり、Wi-Fiと電源を利用できます。4Kモニター貸出や"
                "VRゴーグルなどの最新機材もあり、イベントや発表にも使われます。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_maker_space_equipment(normalized):
        answers = {
            "ja": (
                "[relaxed]MAKER'sスペースは地下1階にあり、レーザー加工機、"
                "3Dプリンター（Bambu Lab P1S）、はんだごて、ボール盤、"
                "オシロスコープなどを利用できます。機材使用料は無料ですが、"
                "3Dプリンターのフィラメント代は有料です。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "exclusive_rental" or agent._asks_exclusive_rental(normalized):
        answers = {
            "ja": (
                "[relaxed]メインホールは30〜50名規模のイベントに対応できます。"
                "エンジニア関連イベントは条件付きで無料になる場合があります。"
                "貸切やイベント利用は事前予約とコミュニティマネージャー面談が"
                "必要な場合があるため、早めに相談してください。"
            )
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_3d_printer_filament_price(normalized):
        answers = {
            "ja": (
                "[relaxed]MAKER'sスペースの3Dプリンター用フィラメントは"
                "使用分を買い取り方式で精算します。Bambu Lab P1S用の"
                "PLA白・黒とABS白・黒は2円/gで、使用量に単価をかけて"
                "10円未満は切り捨てです。福岡市在住の学生は無料です。"
            ),
            "en": (
                "[relaxed]3D printer filament in MAKER's Space is charged by "
                "the amount used. Standard PLA and ABS for the Bambu Lab P1S are "
                "2 yen per gram, with amounts under 10 yen rounded down. Students "
                "living in Fukuoka City can use filament for free."
            ),
            "zh": (
                "[relaxed]MAKER's Space的3D打印机耗材按实际使用量结算。"
                "Bambu Lab P1S用的PLA白色、黑色和ABS白色、黑色都是2日元/g，"
                "不足10日元会舍去。福冈市在住学生免费。"
            ),
            "ko": (
                "[relaxed]MAKER's Space의 3D 프린터 필라멘트는 사용량만큼 "
                "정산합니다. Bambu Lab P1S용 PLA 흰색・검정색과 ABS 흰색・검정색은 "
                "2엔/g이며, 10엔 미만은 절사됩니다. 후쿠오카시 거주 학생은 무료입니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_3d_printer_use(normalized):
        answers = {
            "ja": (
                "[relaxed]3Dプリンターを館内で使う手順は、まず地下1階の"
                "MAKER'sスペースで約1時間の無料講習を受け、操作方法と"
                "安全ルールを確認します。講習後はWeb予約優先制で利用でき、"
                "予約は前日まで受け付けています。"
            ),
            "en": (
                "[relaxed]To use a 3D printer here, first take the free one-hour "
                "training in MAKER's Space on B1F to learn the operation steps and "
                "safety rules. After training, use is prioritized by web reservation, "
                "accepted until the day before."
            ),
            "zh": (
                "[relaxed]3D打印机可在地下一层MAKER's Space使用。"
                "首次使用需要参加约1小时的免费讲习；讲习后采用网页预约优先制，"
                "预约受理到前一天为止。"
            ),
            "ko": (
                "[relaxed]3D 프린터는 지하 1층 MAKER's Space에서 이용할 수 있습니다. "
                "처음 이용할 때는 약 1시간의 무료 강습이 필요하며, 이후에는 "
                "웹 예약 우선제로 전날까지 예약할 수 있습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "toilet" or agent._asks_toilet(normalized):
        if agent._asks_multipurpose_toilet(normalized):
            answers = {
                "ja": (
                    "[relaxed]館内に多目的トイレはありません。"
                    "通常のトイレは1階テラス奥にあります。"
                    "車椅子利用など事前確認が必要な場合は、来館前に"
                    "080-6742-7231へお問い合わせください。"
                ),
                "en": (
                    "[relaxed]There is no multipurpose accessible restroom in "
                    "the building. The regular restroom is at the back of the 1F "
                    "terrace. If you need accessibility confirmation before your "
                    "visit, please call 080-6742-7231."
                ),
                "zh": (
                    "[relaxed]馆内没有多功能洗手间。普通洗手间在一楼露台深处。"
                    "如需无障碍确认，请来馆前拨打080-6742-7231咨询。"
                ),
                "ko": (
                    "[relaxed]건물 안에는 다목적 화장실이 없습니다. 일반 화장실은 "
                    "1층 테라스 안쪽에 있습니다. 접근성 확인이 필요하면 방문 전에 "
                    "080-6742-7231로 문의해 주세요."
                ),
            }
            return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

        answers = {
            "ja": (
                "[relaxed]トイレは1階テラスの奥にあります。館内から直接は"
                "行けないため、受付奥の通路からテラスに出て、テラス奥へ"
                "進んでください。"
            ),
            "en": (
                "[relaxed]The restroom is at the back of the 1F terrace. "
                "You cannot access it directly from inside the building, so go "
                "through the passage behind reception to the terrace, then continue "
                "to the back."
            ),
            "zh": (
                "[relaxed]洗手间在一楼露台深处。馆内不能直接过去，"
                "请从前台后方通道到露台，再往露台里面走。"
            ),
            "ko": (
                "[relaxed]화장실은 1층 테라스 안쪽에 있습니다. 건물 안에서는 "
                "바로 갈 수 없으니, 접수대 안쪽 통로로 테라스에 나간 뒤 "
                "안쪽으로 이동해 주세요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_online_meeting_place(normalized):
        if agent._asks_soundproof_room(normalized):
            answers = {
                "ja": (
                    "[relaxed]防音室は地下1階に1室あります。1回1時間まで、"
                    "先着順で利用でき、予約はできません。オンラインミーティングや"
                    "電話に向いています。"
                )
            }
            return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

        answers = {
            "ja": (
                "[relaxed]通話OKは1階メインホール、談話室、テラス、"
                "cafe&bar sainoです。通話NGは地下1階の集中スペースです。"
                "オンラインミーティングには地下1階の防音室が最適で、"
                "1回1時間まで先着順で使えます。"
            ),
            "en": (
                "[relaxed]For calls or online meetings, you can use the 1F main "
                "hall, lounge, terrace, or cafe&bar saino. There is also one "
                "soundproof room on B1F for up to one hour at a time. The B1F "
                "Focus Space does not allow talking or phone calls."
            ),
            "zh": (
                "[relaxed]电话或线上会议可以在一楼主厅、谈话室、露台或"
                "cafe&bar saino进行。地下一层有一间防音室，每次最多可用1小时，"
                "适合线上会议和电话。集中空间禁止交谈和通话。"
            ),
            "ko": (
                "[relaxed]전화나 온라인 미팅은 1층 메인 홀, 담화실, 테라스, "
                "cafe&bar saino에서 가능합니다. 지하 1층에는 1회 1시간까지 "
                "쓸 수 있는 방음실이 1개 있으며, 집중 스페이스에서는 대화와 전화가 금지됩니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_focus_space(normalized):
        answers = {
            "ja": (
                "[relaxed]集中スペースは地下1階にある静かなブース型スペースです。"
                "6席あり、座席指定制・先着順で予約はできません。会話や電話は"
                "できないので、静かに作業したい方向けです。"
            ),
            "en": (
                "[relaxed]The Focus Space is a quiet booth-style work area on B1F. "
                "It has six seats, is first-come first-served with assigned seating, "
                "and cannot be reserved. Talking and phone calls are not allowed."
            ),
            "zh": (
                "[relaxed]集中空间位于地下一层，是安静的隔间式工作区。"
                "共有6个座位，指定座位、先到先用，不能预约。这里禁止交谈和通话。"
            ),
            "ko": (
                "[relaxed]집중 스페이스는 지하 1층의 조용한 부스형 작업 공간입니다. "
                "6석이 있으며 좌석 지정제와 선착순으로 운영되고 예약은 불가합니다. "
                "대화와 전화는 할 수 없습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "children_noise" or agent._asks_children_policy(normalized):
        if agent._asks_solicitation_or_nap_policy(normalized):
            answers = {
                "ja": (
                    "[relaxed]営利目的の勧誘、強引な名刺交換、セールス行為は"
                    "禁止されています。公的施設のルールとして、館内での仮眠や"
                    "昼寝もできません。"
                ),
                "en": (
                    "[relaxed]Commercial solicitation, aggressive business-card "
                    "exchange, and sales activity are not allowed. Sleeping or "
                    "napping in the facility is also not permitted."
                ),
                "zh": (
                    "[relaxed]馆内禁止营利性推销、强行交换名片和销售行为。"
                    "作为公共设施规则，也不能在馆内睡觉或午睡。"
                ),
                "ko": (
                    "[relaxed]영리 목적의 권유, 강요하는 명함 교환, 판매 행위는 "
                    "금지되어 있습니다. 공공 시설 규칙상 관내에서 수면이나 낮잠도 불가합니다."
                ),
            }
            return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

        answers = {
            "ja": (
                "[relaxed]お子様連れでも、保護者同伴であれば利用できます。"
                "特別な年齢制限はありませんが、安全管理のため走り回りや大声は避け、"
                "お子様から目を離さないでください。専用備品、授乳室、おむつ交換台はありません。"
            ),
            "en": (
                "[relaxed]Children may visit with a parent or guardian, and there "
                "is no special age limit. Please keep them supervised, avoid running "
                "or loud noise, and note that dedicated childcare equipment, nursing "
                "rooms, and diaper-changing tables are not available."
            ),
            "zh": (
                "[relaxed]儿童可在监护人陪同下使用，没有特别年龄限制。"
                "为安全起见，请避免奔跑或大声喧哗，并不要让儿童离开视线。"
                "馆内没有儿童专用备品、哺乳室或尿布更换台。"
            ),
            "ko": (
                "[relaxed]어린이는 보호자 동반 시 이용할 수 있으며 특별한 나이 제한은 "
                "없습니다. 안전을 위해 뛰어다니거나 큰 소리를 내지 않도록 하고, "
                "전용 비품, 수유실, 기저귀 교환대는 없습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "lost_found" or agent._asks_lost_found(normalized):
        answers = {
            "ja": (
                "[relaxed]コワーキングスペースやカフェエリアでの忘れ物は、"
                "1階のエンジニアカフェ受付で保管しています。2階会議室やトイレなど"
                "共用部の忘れ物は赤煉瓦文化館受付の場合もあります。"
                "電話（080-6742-7231）でお問い合わせください。"
            ),
            "en": (
                "[relaxed]For lost items, please ask the 1F Engineer Cafe reception "
                "first. Items found in shared areas such as the 2F meeting rooms or "
                "restrooms may be kept at the Red Brick Culture Hall reception. "
                "You can also call 080-6742-7231."
            ),
            "zh": (
                "[relaxed]遗失物请先询问一楼工程师咖啡前台。"
                "二楼会议室或洗手间等公共区域的遗失物，也可能由赤炼瓦文化馆前台保管。"
                "电话是080-6742-7231。"
            ),
            "ko": (
                "[relaxed]분실물은 먼저 1층 엔지니어 카페 접수에 문의해 주세요. "
                "2층 회의실이나 화장실 같은 공용부의 분실물은 아카렌가 문화관 접수에서 "
                "보관하는 경우도 있습니다. 전화번호는 080-6742-7231입니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_laser_cutter_materials(normalized):
        answers = {
            "ja": (
                "[relaxed]レーザー加工機では、アクリル、MDF、木材、紙、革、"
                "フェルトなどが使えます。素材は持ち込み制です。PVC（塩ビ）は"
                "有毒ガスが出るため禁止で、ポリカーボネート、ガラス、金属、"
                "発泡スチロールも使えません。"
            ),
            "en": (
                "[relaxed]The laser cutter can be used with acrylic, MDF, wood, "
                "paper, leather, and felt brought by the user. PVC is prohibited "
                "because it releases toxic gas, and polycarbonate, glass, metal, "
                "and styrofoam cannot be used."
            ),
            "zh": (
                "[relaxed]激光切割机可使用自带的亚克力、MDF、木材、纸、皮革、"
                "毛毡等材料。PVC会产生有毒气体，禁止使用；聚碳酸酯、玻璃、金属、"
                "泡沫塑料也不能使用。"
            ),
            "ko": (
                "[relaxed]레이저 가공기는 지참한 아크릴, MDF, 목재, 종이, 가죽, "
                "펠트 등을 사용할 수 있습니다. PVC는 유독 가스가 발생해 금지되며, "
                "폴리카보네이트, 유리, 금속, 스티로폼도 사용할 수 없습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_laser_cutter_use(normalized):
        answers = {
            "ja": (
                "[relaxed]レーザー加工機は地下1階のMAKER'sスペースで利用できます。"
                "初回は約30分の講習が必要で、利用はWeb予約優先制です。"
                "大きな加工や素材確認は事前にスタッフへ相談してください。"
            ),
            "en": (
                "[relaxed]The laser cutter is available in MAKER's Space on B1F. "
                "First-time users need about 30 minutes of training, and use is "
                "prioritized by web reservation. Please check materials with staff "
                "in advance."
            ),
            "zh": (
                "[relaxed]激光切割机可在地下一层MAKER's Space使用。首次使用需要约30分钟讲习，"
                "使用采用网页预约优先制，材料请事前向工作人员确认。"
            ),
            "ko": (
                "[relaxed]레이저 가공기는 지하 1층 MAKER's Space에서 이용할 수 있습니다. "
                "첫 이용 시 약 30분 강습이 필요하며, 웹 예약 우선제로 운영됩니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_projector_or_av_loan(normalized):
        answers = {
            "ja": (
                "[relaxed]イベントや発表用に、プロジェクター、スクリーン、マイク、"
                "HDMIケーブル、4Kモニターなどを貸出できます。LT会やハッカソン発表に"
                "利用でき、大規模利用はコミュニティマネージャーへ相談してください。"
            ),
            "en": (
                "[relaxed]For events and presentations, equipment such as a "
                "projector, screen, microphone, HDMI cable, and 4K monitor can be "
                "borrowed. For larger use, please consult a community manager."
            ),
            "zh": (
                "[relaxed]活动或发表可借用投影仪、幕布、麦克风、HDMI线、4K显示器等。"
                "大规模使用请咨询社区经理。"
            ),
            "ko": (
                "[relaxed]이벤트나 발표용으로 프로젝터, 스크린, 마이크, HDMI 케이블, "
                "4K 모니터 등을 대여할 수 있습니다. 대규모 이용은 커뮤니티 "
                "매니저에게 상담해 주세요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_water_server(normalized):
        answers = {
            "ja": (
                "[relaxed]館内にウォーターサーバーや自動販売機はありません。"
                "ペットボトルや水筒など、ふた付き容器の飲料は持ち込みできます。"
                "飲み物はcafe&bar sainoや近隣コンビニでも購入できます。"
            ),
            "en": (
                "[relaxed]There is no water server or vending machine in the "
                "building. Drinks in lidded containers, such as plastic bottles or "
                "personal bottles, may be brought in. You can also buy drinks at "
                "cafe&bar saino or nearby convenience stores."
            ),
            "zh": (
                "[relaxed]馆内没有饮水机或自动售货机。可携带带盖饮料，如瓶装水或水壶。"
                "也可在cafe&bar saino或附近便利店购买饮料。"
            ),
            "ko": (
                "[relaxed]관내에는 워터 서버나 자동판매기가 없습니다. 페트병이나 텀블러처럼 "
                "뚜껑이 있는 음료는 반입할 수 있으며, cafe&bar saino나 근처 편의점에서도 "
                "음료를 구매할 수 있습니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if agent._asks_power_outlet(normalized):
        answers = {
            "ja": (
                "[relaxed]エンジニアカフェでは作業席の周辺で電源コンセントを"
                "利用できます。見つからない場合や席の移動が必要な場合は、"
                "受付スタッフに確認してください。"
            ),
            "en": (
                "[relaxed]Power outlets are available around the coworking and "
                "work areas at Engineer Cafe. If you cannot find one nearby, "
                "please ask the reception staff."
            ),
            "zh": (
                "[relaxed]工程师咖啡的共享办公和工作区域附近可以使用电源插座。"
                "如果找不到，请向前台工作人员确认。"
            ),
            "ko": (
                "[relaxed]엔지니어 카페의 코워킹 및 작업 공간 주변에서 전원 "
                "콘센트를 이용할 수 있습니다. 찾기 어려우면 접수 직원에게 문의해 주세요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "photography" or agent._asks_photography_policy(normalized):
        answers = {
            "ja": (
                "[relaxed]一般利用時の写真撮影やスナップ撮影は可能です。"
                "他の利用者の顔や作業内容が写り込む場合はプライバシーに配慮し、"
                "商業撮影、三脚・フラッシュ、大規模な撮影は事前にスタッフへ確認してください。"
            ),
            "en": (
                "[relaxed]Casual photos and snapshots are allowed. Please respect "
                "other visitors' privacy if faces or work screens may be visible. "
                "Commercial shoots, tripods, flash, or large-scale filming should "
                "be confirmed with staff in advance."
            ),
            "zh": (
                "[relaxed]一般参观时可以拍照和进行简单记录。若拍到其他使用者的脸或"
                "工作内容，请注意隐私。商业拍摄、三脚架、闪光灯或大规模拍摄请事先向工作人员确认。"
            ),
            "ko": (
                "[relaxed]일반 이용 중 사진 촬영이나 스냅 촬영은 가능합니다. "
                "다른 이용자의 얼굴이나 작업 내용이 찍힐 수 있으면 개인정보에 유의해 주세요. "
                "상업 촬영, 삼각대, 플래시, 대규모 촬영은 사전에 직원에게 확인해 주세요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "bicycle" or agent._asks_bicycle_parking(normalized):
        answers = {
            "ja": (
                "[relaxed]エンジニアカフェ専用の駐輪場はありません。"
                "自転車で来館する場合は、近隣の公共駐輪場を利用してください。"
            ),
            "en": (
                "[relaxed]There is no dedicated bicycle parking at Engineer Cafe. "
                "Please use nearby public bicycle parking areas."
            ),
            "zh": (
                "[relaxed]工程师咖啡没有专用自行车停车场。骑自行车来访时，"
                "请使用附近的公共自行车停车场。"
            ),
            "ko": (
                "[relaxed]엔지니어 카페 전용 자전거 주차장은 없습니다. 자전거로 방문할 때는 "
                "근처 공공 자전거 주차장을 이용해 주세요."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)

    if request_type == "meeting_room" or agent._asks_meeting_room_pricing(normalized):
        answers = {
            "ja": (
                "[relaxed]2階会議室は赤煉瓦文化館管理の有料施設です。"
                "9時〜12時の料金例は、会議室1（12名）が800円〜、"
                "会議室2（8名）が500円〜、会議室3（30名）が1,700円〜です。"
                "時間帯により料金が変わるため、詳しくは赤煉瓦文化館側へ確認してください。"
            ),
            "en": (
                "[relaxed]The 2F meeting rooms are paid facilities managed by the "
                "Red Brick Culture Hall. Example 9:00-12:00 fees are 800 yen for "
                "Meeting Room 1 (12 people), 500 yen for Meeting Room 2 (8 people), "
                "and 1,700 yen for Meeting Room 3 (30 people)."
            ),
            "zh": (
                "[relaxed]二楼会议室是赤炼瓦文化馆管理的收费设施。"
                "9:00-12:00的费用例：会议室1（12人）800日元，会议室2（8人）500日元，"
                "会议室3（30人）1,700日元。"
            ),
            "ko": (
                "[relaxed]2층 회의실은 아카렌가 문화관이 관리하는 유료 시설입니다. "
                "9시-12시 요금 예시는 회의실1(12명) 800엔, 회의실2(8명) 500엔, "
                "회의실3(30명) 1,700엔입니다."
            ),
        }
        return agent._canonical_result(answers.get(language, answers["ja"]), request_type)
