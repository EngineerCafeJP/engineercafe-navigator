# 感情タグ・`emotion` フィールド整理

バックエンドにおける応答の本文 `[...]` タグと、API／ワークフロー状態の `emotion` 文字列の関係を開発者向けにまとめたものです。

## 感情ラベルごとの付与条件

テスト用の `friendly` / `urgent` / `curious` 等は除く。

### `happy` (嬉しい)

- **BusinessInfoAgent / FacilityAgent**: LLM 応答に `[happy]` が含まれる（Business は大小無視、Facility は `.lower()` 比較）。
- **EventAgent**: GoogleカレンダーとConnpassからイベント開催情報を探索し、案内イベントがあるとき。
- **FarewellAgent**: 退館応答の通常成功パス（実装上一貫）。
- **main_workflow**: インライン挨拶（`_handle_greeting`）。
- **reception_templates**: レガシー受付テンプレの戻り。
- **reception_workflow**: サブグラフが応答付きで返すとき `stage` が `greeting`。
- **GeneralKnowledgeAgent（メモリ）**: `_determine_memory_emotion` で `query_type == "other_option"` （「もう一つ」系）。
- **SlideAgent**: スライド `auto` ナレーションに **`welcome` / ようこそ** が含まれるとき（`_extract_emotion_from_slide_content` はこの分岐が先）。

### `sad` (悲しい)

- **BusinessInfoAgent / FacilityAgent**: 応答に `[sad]` が含まれる。
- **EventAgent**: イベントがない、検索タイムアウト、LLM 例外 → `_get_no_events_response` 系。本文は `[sad]` 付き。
- **GeneralKnowledgeAgent（メモリ）**: 直近メッセージなし、または会話履歴なし応答。
- **VoiceAgent**: メインTTS失敗後、フォールバックTTSが成功したときの戻り値。

### `relaxed` (安心する)

- **BusinessInfoAgent / FacilityAgent**: 応答に `[relaxed]` が含まれる。
- **GeneralKnowledgeAgent（一般）**: `_extract_emotion` が `[relaxed]` を検出。
- **GeneralKnowledgeAgent（メモリ）**: `question_history` / `answer_history` かつ履歴あり。

### `surprised` (驚く)

- **clarification_templates**: すべての clarification カテゴリ。本文は `[surprised]`。
- **GeneralKnowledgeAgent（メモリ）**: メモリ処理中の例外応答。
- **GeneralKnowledgeAgent（一般）**: `_extract_emotion` が `[surprised]` を検出。

### `apologetic` (お詫び)

- **BusinessInfoAgent / FacilityAgent**: RAG 失敗・コンテキスト空・LLM 例外の `_get_default_response`（本文は `[sad]` だが `emotion` は `apologetic`）。
- **GeneralKnowledgeAgent**: `_handle_error`（内部エラー）。
- **SlideAgent**: スライド質問のLLM例外時。

### `informative` (有益な情報)

- **BusinessInfoAgent**: `[happy]`/`[sad]`/`[relaxed]` タグがいずれも無く、`request_type` が `hours` (営業時間) または `price` (料金)。
- **FacilityAgent**: 同様にタグなしで `request_type` が `wifi` (Wi-Fi設備情報) または `facility` (設備情報)。

### `guiding` (案内)

- **BusinessInfoAgent**: タグなし、`request_type` が `location` (場所・アクセス)。
- **FacilityAgent**: タグなし、`request_type` が `basement` (地下施設情報)。

### `helpful` (役立つ)

- **BusinessInfoAgent**: タグなし、かつ `request_type` が `hours`/`price`/`location` 以外 （`None` 含む）。
- **FacilityAgent**: タグなし、`request_type` が `wifi`/`facility`/`basement` 以外。
- **SlideAgent**: onDemandキーワード一致、またはLLMでスライド質問に回答できたとき。

### `neutral` (通常)

- **GeneralKnowledgeAgent（一般）**: `_extract_emotion` で `[sad]`…`[apologetic]` まで 何もヒットしない（`[helpful]` は未対応のためここに落ち得る）。
- **GeneralKnowledgeAgent（メモリ）**: 履歴ありで `query_type` が `general_memory` 等（`_determine_memory_emotion` のデフォルト）。
- **main_workflow**: オフトピック（topic guard）。
- **SlideAgent**: 最終／最初スライド案内、無効 `goto`、スライド不在、質問で現在スライド情報なし、ナレーションから該当キーワードなし。
- **reception_workflow**: 応答ありで `stage` が `greeting` 以外。
- **各ノードのフォールバック**: `result.get("emotion", "neutral")`。

### `serious` (切実)

- **emergency_templates**: 緊急カテゴリの固定応答（全サブタイプ）。本文に **`[serious]`** を含むとき。

### `confident` (自信)

- **SlideAgent**: `auto` ナレーションに `service` / サービス` を含むとき（welcome 分岐より後）。

### `grateful` (感謝)

- **SlideAgent**: `auto` ナレーションに `thank` / ありがとう` を含むとき。

### `confused` (困惑)

- **VoiceAgent**: メイン TTS 失敗に加え フォールバックTTSも失敗したとき。

### `None`

- **reception_workflow**: サブグラフが別エージェントへルーティングするとき（`answer=None` の結果）。

## 主要コード参照

| 内容 | パス |
|------|------|
| VRM 表情マップ | `backend/utils/emotion_mapping.py` |
| タグ付与ユーティリティ | `backend/utils/emotion_tagger.py` |
| TTS 側エイリアス・パース | `backend/agents/voice_agent.py`（`VRM_EMOTION_MAP`, `parse_emotion_tags`, `map_to_vrm_emotion`） |
| 営業情報 | `backend/agents/business_info_agent.py` |
| 施設 | `backend/agents/facility_agent.py` |
| イベント | `backend/agents/event_agent.py` |
| 一般知識・メモリ | `backend/agents/general_knowledge_agent.py` |
| スライド | `backend/agents/slide_agent.py` |
| 退館 | `backend/agents/farewell_agent.py` |
| Clarification | `backend/utils/clarification_templates.py` |
| Emergency | `backend/utils/emergency_templates.py` |
| Reception テンプレ | `backend/utils/reception_templates.py` |
| ワークフロー | `backend/workflows/main_workflow.py`, `backend/workflows/reception_workflow.py` |
| 固定エラー／Not Found 文言 | `backend/utils/language_types.py` |

## 改訂履歴

- 2026.04.13 : 作成