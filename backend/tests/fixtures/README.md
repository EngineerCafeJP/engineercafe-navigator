# テストフィクスチャ・ゴールデンデータセット

評価テスト用のデータセットとローダーを提供します。

## データソース

`golden_datasets/` 内のデータは **実際のエンジニアカフェの公開情報** に基づいています。

| ソース | パス |
|--------|------|
| リファレンス資料 | `docs/reference/engineer-cafe-reference.md` |
| 公式サイト | https://engineercafe.jp/ |
| connpass | https://engineercafe.connpass.com/ |

### 含まれる情報

| 項目 | 内容 | ソース |
|------|------|--------|
| 営業時間 | 9:00〜22:00、相談受付13:00〜21:00 | リファレンス |
| 休館日 | 毎月最終月曜日、12/29〜1/3 | リファレンス |
| アクセス | 天神駅徒歩5分 | リファレンス |
| MAKER'sスペース | レーザー加工機、3Dプリンター | リファレンス |
| cafe&bar saino | 営業時間、定休日 | リファレンス |
| 2階会議室 | 福岡市管理、コミネット予約 | リファレンス |
| 建物情報 | 1909年建築、国の重要文化財 | リファレンス |

### 用途

これらのデータセットは以下の目的で使用されます：

1. **評価ロジックの動作確認** - スコアリングが正しく動くか
2. **意味的類似度のテスト** - 類似した文章を正しく判定できるか
3. **ルーティング精度のテスト** - 適切なエージェントにルーティングされるか
4. **回答品質の評価** - 実際の情報に基づく回答精度の確認

## データセット一覧

### routing_test_cases.json

ルーティング精度評価用のテストケース。

| フィールド | 説明 |
|-----------|------|
| `id` | テストケースID（rt-001, rt-002, ...） |
| `query` | ユーザークエリ |
| `expected_agent` | 期待されるルーティング先エージェント |
| `expected_category` | 期待されるカテゴリ |
| `language` | 言語コード（ja, en, zh, ko） |
| `tags` | 分類タグ（fast-path, memory, facilityなど） |
| `note` | 補足情報（実際の施設情報） |

**統計情報:**
- 総テストケース数: 32件
- 対応言語: 日本語(ja), 英語(en), 中国語(zh), 韓国語(ko)
- 対応エージェント: facility, event, business_info, memory_agent

### answer_quality.json

LLM Judge評価用のテストケース。

| フィールド | 説明 |
|-----------|------|
| `id` | テストケースID（aq-001, aq-002, ...） |
| `question` | 質問 |
| `expected_answer` | 期待される回答（実際の施設情報に基づく） |
| `language` | 言語コード |
| `category` | カテゴリ（facility, event, business_infoなど） |
| `context` | コンテキスト情報（オプション） |
| `quality_expectations` | 期待される品質スコア閾値 |

**統計情報:**
- 総テストケース数: 12件
- 対応言語: 日本語(ja), 英語(en), 韓国語(ko)

## モックファクトリ（新規追加）

### mock_agents.py

テスト用のエージェントモックを生成します。

```python
from tests.fixtures import (
    create_mock_orchestrator,
    create_mock_business_info_agent,
    create_mock_vision_agent,
)

# オーケストレーターモック
mock_orch = create_mock_orchestrator(
    next_agent="facility",
    category="wifi",
    confidence=0.95
)
decision = await mock_orch.decide_next_agent("Wi-Fiは？")
# decision.next_agent == "facility"

# ビジネス情報エージェントモック
mock_agent = create_mock_business_info_agent(
    answer="営業時間は10:00-22:00です",
    emotion="informative"
)
result = await mock_agent.answer_business_query("営業時間は？")
# result["answer"] == "営業時間は10:00-22:00です"
```

**利用可能なモック:**
- `create_mock_orchestrator()` - ルーティング決定
- `create_mock_business_info_agent()` - 営業情報エージェント
- `create_mock_facility_agent()` - 施設情報エージェント
- `create_mock_event_agent()` - イベント情報エージェント
- `create_mock_vision_agent()` - OCR/顔認識
- `create_mock_stt_agent()` - 音声認識
- `create_mock_voice_agent()` - 音声合成

### mock_llm.py

LLMプロバイダーとレスポンスのモックを生成します。

```python
from tests.fixtures import create_mock_llm, create_mock_rag_search

# LLMモック（予測可能なレスポンス）
mock_llm = create_mock_llm(content="テストレスポンス")
response = await mock_llm.ainvoke([HumanMessage(content="test")])
# response.content == "テストレスポンス"

# RAG検索モック
mock_rag = create_mock_rag_search(
    results=[{"content": "営業時間は10:00-22:00です", "score": 0.95}]
)
results = await mock_rag.search("営業時間")
```

### sample_states.py

ワークフロー状態のサンプルデータを生成します。

```python
from tests.fixtures import create_text_query_state, create_routing_decision

# テキストクエリ状態
state = create_text_query_state(
    query="営業時間は？",
    language="ja",
    session_id="test-123"
)

# ルーティング決定
routing = create_routing_decision(
    agent="facility",
    category="facility",
    request_type="wifi"
)
```

### sample_images.py

テスト用の合成画像を生成します。

```python
from tests.fixtures import create_blank_image, create_wide_image

# 空白画像（100x100x3）
img = create_blank_image(width=100, height=100)

# 大きな画像（リサイズテスト用）
img = create_wide_image(1920, 1080)  # 1920x1080

# QRコード風パターン
img = create_qr_like_image()
```

## DatasetLoader使用例

```python
from tests.fixtures.dataset_loader import DatasetLoader

# 全ルーティングテストケース取得
all_cases = DatasetLoader.load_routing_test_cases()

# 日本語のみ
ja_cases = DatasetLoader.load_routing_test_cases(language="ja")

# 特定タグでフィルタ
fast_path_cases = DatasetLoader.load_routing_test_cases(tags=["fast-path"])
memory_cases = DatasetLoader.load_memory_cases()

# 回答品質テストケース
quality_cases = DatasetLoader.load_answer_quality_cases(language="ja")

# 多言語テストケース（言語別にグループ化）
multilingual = DatasetLoader.load_multilingual_cases(languages=["ja", "en"])

# データセット情報取得
info = DatasetLoader.get_dataset_info()
print(f"ルーティングテスト数: {info['routing_test_cases']['total']}")
print(f"対応言語: {info['languages']}")
print(f"対応エージェント: {info['agents']}")
```

## ファイル構成

```
tests/fixtures/
├── __init__.py
├── dataset_loader.py          # DatasetLoaderクラス
├── mock_agents.py             # エージェントモックファクトリ
├── mock_llm.py                # LLMモックファクトリ
├── sample_states.py           # ワークフロー状態ファクトリ
├── sample_images.py           # テスト画像ジェネレーター
├── test_fixtures_validation.py # フィクスチャ検証テスト
├── golden_datasets/
│   ├── routing_test_cases.json  # ルーティングテストケース（実データ）
│   └── answer_quality.json      # 回答品質テストケース（実データ）
└── README.md                  # このファイル
```

## リファレンス資料の更新

エンジニアカフェの情報が更新された場合：

1. `docs/reference/engineer-cafe-reference.md` を更新
2. `golden_datasets/*.json` を同期更新
3. バージョン番号を更新（`version` フィールド）

## 関連ドキュメント

- [評価フレームワーク README](../evaluation/README.md)
- [LangSmith統合](../utils/langsmith_integration.py)
- [エンジニアカフェリファレンス](../../../docs/reference/engineer-cafe-reference.md)
