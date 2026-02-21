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
