> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Reception Quality Issues - 2026-05-16

## Scope

- 対象期間: 2026-05-15T12:42:58Z から 2026-05-16T04:42Z までの直近24時間
- 追加調査: 2026-05-01 から 2026-05-16 までの直近半月の構造化ログ、および 2026-05-09 から 2026-05-16 までの直近1週間の会話本文ログ
- 対象サービス: Cloud Run `engineer-cafe-backend` / revision `engineer-cafe-backend-00206-r2q`
- 確認元:
  - `backend/tests/reports/cloud-logging-check-20260516_last24h_codex.md`
  - Cloud Logging `chat_response`, `stt_winner`, request-scoped application logs
  - Supabase `agent_memory` session messages
  - `/tmp/engineer_cafe_cloud_events_last7d.json`
  - `/tmp/engineer_cafe_cloud_events_last15d.json`
  - `/tmp/engineer_cafe_cloud_chat_response_20260501_20260516.json`
  - `/tmp/engineer_cafe_cloud_stt_winner_20260501_20260516.json`
  - `/tmp/engineer_cafe_agent_memory_last7d.json`
  - `/tmp/engineer_cafe_agent_memory_20260501_20260516.json`
  - 添付スクリーンショット `Engineer Cafe Navigator.jpeg`

## Log Summary

直近24時間の構造化ログでは、STT trace は5件、`chat_response` は5件だった。
STT構造化イベント生成、`chat_response` 必須フィールド、API 5xx、LTM保存失敗、UUID hygiene、reception persistence はすべて PASS。

可用性・永続化のエラーは確認されていない。一方で、会話品質上の問題が実ログで再現している。

直近1週間の追加調査では、Cloud Logging 上の `chat_response` は349件、`stt_winner` は48件だった。
Supabase `agent_memory` では696行、うち user message は348件、331セッションを確認した。
ルート分布は `BusinessInfoAgent` 139件、`facility-info` 109件、`EventAgent` 31件、`general` 28件、`reception` 8件などで、テスト・品質ゲート由来の発話が多い。

直近半月の追加調査では、Cloud Logging の `chat_response` 4264件、`stt_winner` 670件を確認した。
`stt_winner` の内訳は `qwen` 596件、`vosk` 70件、`none` 4件。
Supabase `agent_memory` では8386メッセージ、うち user 4196件、assistant 4190件、3768セッションを確認した。
評価用・テスト用の発話を除いた production-like user utterance は2660件だった。

半月ログの会話分類では、挨拶・雑談 69件、飲食・休憩 124件、施設 1018件、会員・受付 245件、STT断片 44件、BusinessInfo系 966件、イベント 314件を確認した。
production-like に絞ると、飲食・休憩 116件、施設 817件、BusinessInfo系 856件が多く、受付AIとして「目的確認」だけではなく、軽い要望から施設案内へ自動遷移する必要性が高い。
Cloud Logging の `chat_response` は本文を含まないため、発話本文の評価は Supabase `agent_memory` を主に使った。

会話らしい呼びかけに絞ると、主な実例は以下だった。

- 概要質問: `tell me about Engineer Cafe`, `ここではどんなことやってますか`
- 挨拶・雑談: `おはようございます。`, `こんにちは、お元気ですか。`, `こんにちは。`
- 言語確認: `英語を話せます。`, `英語対応はしていますか？`
- 飲食要望: `コーヒーを飲みたいんですけれども。`, `コーヒーを飲みたい。`
- STT断片・ノイズ: `007430`, `え、休コンビとかないの。`, 崩れた英語発話

結論として、受付AIは明示的な施設質問には概ね答えられているが、曖昧な雑談・要望表現を受付の目的確認テンプレートに戻しやすい。
受付である以上、雑談専用ルーティングと、雑談中に検出した施設・飲食・イベントなどの intent へ自然に移行するオーケストレーションが必要。

## Observed Conversations

| Time (UTC) | Session | User utterance | Route | Stored assistant response | Evaluation |
| --- | --- | --- | --- | --- | --- |
| 2026-05-16T04:06:01Z | `603a7ccb-ddd8-4120-9cc5-22fa112829f0` | `コーヒーを飲みたいんですけれども。` | `reception` | `ご用件をお聞かせください。例えば... コワーキングスペースの利用 / イベント参加 / 施設見学 / 技術相談...` | NG。受付としては `cafe&bar saino` の案内、注文場所、営業時間、価格、館内飲食可能エリアなどへつなぐべき。 |
| 2026-05-16T04:06:37Z | same | `大きい` | `reception` | 同じ用件確認テンプレート | 要確認。STT断片または操作誤入力の可能性が高いが、前ターン文脈を使えていない。 |
| 2026-05-16T04:06:57Z | same | `コーヒーを飲みたい。` | `reception` | 同じ用件確認テンプレート | NG。同じ失敗が再現。 |
| 2026-05-15T19:54:51Z | `3e674121-c73e-4616-9521-adcddaae973c` | `tell me about Engineer Cafe` | `general` | Engineer Cafe の概要を回答 | OK。ただし tRAG の `en->ja` ログが文字化け風の低品質翻訳になっている。 |
| 2026-05-16T04:20:42Z | `d708840d-c005-46c4-a715-603668a86787` | `i want to be the main hope i want to work the holiday should we stay this` | `reception` | 英語の用件確認テンプレート | 要確認。STT結果が崩れており、`hours` が抽出されているのに受付テンプレートへ戻っている。 |

## Issue 1: Ambiguous Coffee / Drink Intent Falls Back To Reception Prompt

### Current Behavior

「コーヒーを飲みたい」のような曖昧だが受付で自然に扱うべき発話が、`cafe&bar saino` や館内飲食案内ではなく、受付の用件確認テンプレートに戻る。

### Expected Behavior

受付AIとして、雑談・目的表明・軽い要望を施設案内へ接続する。

例:

- 「コーヒーを飲みたい」→ `cafe&bar saino` の場所、注文可能性、代表価格、営業時間へ案内
- 「ちょっと休憩したい」→ サイノ、談話室、テラス、コワーキング利用を案内
- 「お腹すいた」→ サイノのフード、周辺ランチ、持ち込みルールを必要に応じて案内

### Root Cause

受付フローがアクティブな状態では、通常QAへ抜けるために `_looks_like_information_query()` を通る必要がある。
この判定は `教えて`, `知りたい`, `どこ`, `いくら`, `ありますか`, `tell me` などの明示的な質問マーカーに偏っており、`飲みたい`, `食べたい`, `休憩したい`, `注文したい` のような要望表現を情報要求として扱っていない。

通常ルーティング側には `coffee` / `カフェ` を `saino` に寄せる仕組みがあるが、アクティブ受付フロー内でそこまで到達していない。

関連箇所:

- `backend/workflows/main_workflow.py` `_looks_like_information_query()`
- `backend/workflows/reception_workflow.py` `_INFORMATION_QUERY_MARKERS`
- `backend/utils/purpose_classifier.py` `_PURPOSE_KEYWORDS`
- `backend/config/routing_constants.py` `FOOD_DRINK_VERBS`, `FOOD_DRINK_KEYWORDS`
- `backend/utils/cafe_entity.py` `resolve_cafe_entity()`

### Next Phase Fix Target

- 受付中バイパス判定に、要望表現を追加する。今回実装済み。
  - `飲みたい`, `食べたい`, `注文したい`, `休憩したい`, `座りたい`, `使いたい`, `見たい`
  - English: `want to drink`, `want coffee`, `want to eat`, `take a break`, `grab a coffee`
- `コーヒー`, `カフェラテ`, `ドリンク`, `ランチ`, `メニュー`, `サイノ`, `saino`, `coffee` を受付中でも `facility` または `business_info` の `food_drink` / `saino-cafe` へ通す。今回実装済み。
- 目的分類にも `コーヒー`, `飲みたい`, `食べたい`, `休憩` を追加し、`other` に落とさない。今回実装済み。
- 回答テンプレートは「受付用件を聞き返す」ではなく、「案内 + 必要なら確認」にする。今回、コーヒー・休憩要望に対して実装済み。

## Issue 2: Active Reception State Hijacks Normal Conversation

### Current Behavior

同一セッションで、曖昧発話やSTT断片が繰り返し `reception` に吸収され、同じ用件確認テンプレートが返る。

### Root Cause

`reception_status.stage` が `greeting`, `purpose_hearing`, `routing` の間、通常QAへの離脱条件が限定的。結果として、受付フローの「目的を聞く」状態が強く、会話ログの前後文脈やサイノ関連語より優先される。

### Next Phase Fix Target

- アクティブ受付中でも `classify_fast_intent()` と `QueryClassifier` の結果を先に評価する対象を広げる。今回、`daily_conversation` と飲食・休憩要望は受付中でも通常ルーティングへ渡すように実装済み。
- `こんにちは、お元気ですか` のような挨拶・軽い社交発話は、雑談へ離脱させず、短く応答して受付の用件確認を継続するよう実装済み。
- 半月ログ由来の `受付手続きはこれで完了ですか`, `受け付けで何を伝えれば入館できますか` は、受付フロー内でも `business_info/reception` の通常QAへ渡すよう実装済み。
- `Please remember that I prefer English answers.` の `member` 部分一致で reception に誤爆しないよう、英語会員キーワードを語句ベースへ寄せた。
- 同じ `purpose_hearing` テンプレートを2回以上返す場合は、`repeated_reception_clarification` の品質シグナルを reception session metadata に残す。今回実装済み。
- `reception_action=clarify_purpose` が連続したセッションを会話品質アラートとしてログ化する。今回実装済み。

## Issue 3: STT / tRAG Quality Signals Are Not Surfaced In Response Decisions

### Current Behavior

英語発話で `i want to be the main hope...` のような崩れたSTT結果が残っている。また tRAG の `en->ja` ログで、翻訳結果が `ル ル...` や `このこの...` のように壊れている。

### Root Cause

STT信頼度や翻訳異常が、その後の受付応答方針に十分反映されていない。`request_type=hours` のような抽出結果がありながら、最終的には受付テンプレートに戻っている。

### Next Phase Fix Target

- tRAG翻訳結果に反復文字・低情報量検知を追加し、異常時は翻訳を使わない。今回実装済み。
- STTの低品質推定時は「聞き取れた範囲では...」と確認しつつ、抽出できた intent を案内に使う。
- `stt_winner` ログに transcript と信頼度または品質シグナルを安全に分析できる形で残す。

### Fix Applied In This Patch

- `ル ル ル ル`, `このこのこのこの` のような低情報量・反復型の tRAG 翻訳を拒否するフィルタを追加した。
- EN->JA の CTranslate2 翻訳でも、低情報量翻訳は RAG クエリに採用せず元クエリへフォールバックする。
- STT側は既存の疑わしい短文・低信頼判定を維持し、本パッチでは受付ルーティング側で「抽出できた intent を優先する」範囲を拡張した。

## Issue 4: iPad Safari Pinch Zoom Causes Kiosk Stage Misalignment

### Current Behavior

添付画像では、画面を指で拡大縮小した後、アバター・背景・ボタン群が左側に寄り、右側と下側に濃紺の余白が出ている。キオスク画面全体がビューポートに追従できていない。

### Root Cause

`useKioskViewportLock()` が `window.visualViewport.width/height` を CSS 変数 `--kiosk-viewport-width`, `--kiosk-viewport-height` に反映し、その値で `body` と `.kiosk-viewport-root` を固定している。
ピンチズーム時、iOS Safari の `visualViewport` は縮小された表示領域サイズとスクロールオフセットを返すため、アプリの固定ルート幅・高さもズーム後の小さい値に更新される。

さらに:

- `maximumScale: 1` / `userScalable: false` は iOS Safari で完全にはピンチ抑止にならない場合がある。
- `touch-action: none` / `manipulation` は Safari のブラウザピンチを完全には止められない。
- `visualViewport.offsetLeft/offsetTop` を考慮していないため、ズーム後の表示領域に対して固定要素が左上基準でずれる。

関連箇所:

- `frontend/src/app/hooks/useKioskViewportLock.ts`
- `frontend/src/app/layout.tsx`
- `frontend/src/app/globals.css`
- `frontend/src/app/components/CharacterAvatar.tsx`

### Next Phase Fix Target

- キオスクモードではピンチジェスチャーを `gesturestart`, `gesturechange`, `touchmove` で抑止する実装を追加する。
- `visualViewport.scale !== 1` の間は CSS viewport 変数を更新しない、または layout viewport (`window.innerWidth/innerHeight`) を基準に固定する。
- 必要なら `visualViewport.offsetLeft/offsetTop` を反映して固定ルートを補正する。
- Playwrightで iPad相当 viewport の resize / visualViewport mock / touch gesture 後に `.kiosk-viewport-root` が全画面を維持する回帰テストを追加する。

### Fix Applied In This Patch

- `visualViewport.scale !== 1` または offset ありの場合は、CSS viewport 変数を `innerWidth/innerHeight` の layout viewport 基準で維持する。
- Safari の visualViewport jitter で小さい値が返っても、キオスクルートを layout viewport 未満へ縮めない。
- `gesturestart`, `gesturechange`, `gestureend` と複数指 `touchmove` を non-passive listener で抑止する。
- kiosk lock 中の `html/body` は `touch-action: none` にし、viewport meta に `minimumScale: 1` を追加した。

## Issue 5: Member Number Recognition Implies Personalized Seat Guidance

### Current Behavior

会員証OCRで会員番号を読み取った後、受付開始APIへ `visitor_identity` が渡される経路があり、利用者からは「会員登録情報に基づいて席のチョイスまでできるはず」と解釈されやすい。
2026-05-16 の現地利用でも、会員番号認識後に「なぜ会員登録に基づいた席のチョイスができないのか」という指摘があった。

### Expected Behavior

フェーズ1では、会員番号は読み取り確認に留める。
会員DBに基づく個別案内、過去利用履歴に基づく席提案、来館者属性に基づく応答はフェーズ2以降であることを明示する。

### Root Cause

フロントの会員証OCR成功フローが、OCR結果から `visitor_identity` を作って `startReception()` に渡しうる。
バックエンド側は `visitor_identity.user_id` がある場合に returning visitor として個別挨拶を生成するため、フェーズ1の機能範囲より広く見える。

関連箇所:

- `frontend/src/app/page.tsx` `startMemberCardReceptionFromOcr()`
- `frontend/src/lib/reception-identity.ts`
- `backend/api/ocr.py`
- `backend/api/reception.py` `start_reception()`

### Fix Applied In This Patch

- キオスク本線の会員証OCR成功時は `visitor_identity` を受付開始APIへ渡さない。
- 読み取り後の音声をテンプレート化し、「会員番号の確認まで」「会員情報に基づく座席提案や個別案内はフェーズ2以降」と明示する。
- テンプレートは `frontend/src/lib/member-card-reception.ts` に分離し、Nodeテストで固定した。
- BusinessInfoAgent でも会員番号・会員情報ベースの席提案や個別案内を聞かれた場合は、会員番号確認までに留め、DB連携や個別案内はフェーズ2以降である旨へ固定した。

## Issue 6: Log-Derived Routing Gaps In Multilingual And Facility Queries

### Current Behavior

半月ログでは、以下のような発話が deterministic routing の隙間になっていた。

- `エンジニアカフェって何ですか？` が周辺カフェ・nearby 系に寄るリスク
- `MAKER'sスペースではどんな機材が使えますか？` が機材案内に直行しにくい
- `와이파이 비밀번호가 뭐예요?`, `工程师咖啡的营业时间是什么？` など多言語の基本質問でキーワード不足

### Fix Applied In This Patch

- `カフェ` 単体を nearby キーワードから外し、エンジニアカフェ自体の概要質問は `business_info/general` へ明示ルーティングする。
- Maker'sスペース + 機材/設備/利用系の発話は `facility/facility` に寄せる。
- Wi-Fi、営業時間、料金、イベント、アクセス、受付、飲食の中国語・韓国語キーワードを追加した。
- `エンジニアカフェで飲みは可能ですか？`, `受付手続きはこれで完了ですか。`, `受け付けで何を伝えれば入館できますか？` を回帰テスト化した。

## Priority

1. P0: `コーヒーを飲みたい` など受付現場で自然な要望を `saino-cafe` / `food_drink` 案内へ接続する。
2. P0: ピンチズーム後のキオスク画面ズレを防ぐ。
3. P0: 会員番号認識後にフェーズ1の機能範囲を明示し、個別席案内が可能であるように見せない。
4. P0: 半月ログ由来の多言語・受付完了・Maker'sスペース・概要質問の誤ルーティングを deterministic route で塞ぐ。
5. P1: 受付テンプレート連続返答を品質アラート化する。
6. P1: STT低品質シグナルをさらに応答文言へ反映する。
