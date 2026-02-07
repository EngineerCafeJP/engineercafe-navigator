# テストフィクスチャ・ゴールデンデータセット

評価テスト用のデータセットとローダーを提供します。

## ⚠️ 重要な注意事項

### ダミーデータについて

`golden_datasets/` 内のデータは**評価ロジックのテスト用ダミーデータ**です。

| 項目 | 説明 |
|------|------|
| Wi-Fiパスワード | ダミー値（`engineer2025`など） |
| 営業時間 | ダミー値（実際とは異なる） |
| イベント情報 | 架空のイベント |
| 施設情報 | 簡略化されたダミー情報 |

**これらは実際のエンジニアカフェの情報とは一致しません。**

### 用途

これらのデータセットは以下の目的で使用されます：

1. **評価ロジックの動作確認** - スコアリングが正しく動くか
2. **意味的類似度のテスト** - 類似した文章を正しく判定できるか
3. **ルーティング精度のテスト** - 適切なエージェントにルーティングされるか

### 本番評価を行う場合

実際のエンジニアカフェの回答品質を評価する場合は：

1. 本番用データセットを別途作成（例: `answer_quality_production.json`）
2. 施設情報DBやナレッジベースから正確な情報を取得
3. 実際のユーザークエリログを使用

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

**統計情報:**
- 総テストケース数: 30件
- 対応言語: 日本語(ja), 英語(en), 中国語(zh), 韓国語(ko)
- 対応エージェント: facility, event, business_info, memory_agent, general

### answer_quality.json

LLM Judge評価用のテストケース。

| フィールド | 説明 |
|-----------|------|
| `id` | テストケースID（aq-001, aq-002, ...） |
| `question` | 質問 |
| `expected_answer` | 期待される回答（ダミー） |
| `language` | 言語コード |
| `category` | カテゴリ（facility, event, businessなど） |
| `context` | コンテキスト情報（オプション） |
| `quality_expectations` | 期待される品質スコア閾値 |

**統計情報:**
- 総テストケース数: 10件
- 対応言語: 日本語(ja), 英語(en), 中国語(zh), 韓国語(ko)

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
│   ├── routing_test_cases.json  # ルーティングテストケース
│   └── answer_quality.json      # 回答品質テストケース
└── README.md                  # このファイル
```

## 本番用データセット作成ガイド

本番環境で評価を行う場合の推奨手順：

### 1. データ収集

```python
# 施設情報DBから取得
facility_info = supabase.table("facilities").select("*").execute()

# 実際のユーザークエリログから取得
query_logs = supabase.table("chat_logs").select("query, response").execute()
```

### 2. 本番用データセット作成

```json
// golden_datasets/answer_quality_production.json
{
  "version": "1.0.0",
  "description": "本番環境用回答品質テストデータ",
  "data_source": "engineer-cafe-production-db",
  "last_updated": "2025-02-07",
  "test_cases": [
    {
      "id": "prod-001",
      "question": "Wi-Fiのパスワードを教えてください",
      "expected_answer": "【実際のパスワード情報】",
      "language": "ja",
      "category": "facility"
    }
  ]
}
```

### 3. ローダー拡張

```python
@classmethod
def load_production_cases(cls) -> List[AnswerQualityCase]:
    """本番用テストケースを読み込み"""
    return cls._load_json("answer_quality_production.json")
```

## 関連ドキュメント

- [評価フレームワーク README](../evaluation/README.md)
- [LangSmith統合](../utils/langsmith_integration.py)
