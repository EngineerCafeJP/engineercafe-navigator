# テスト作成ガイド

Engineer Cafe Navigatorプロジェクトでテストを作成するための完全なガイドです。

## 目次

- [はじめに](#はじめに)
- [テスト環境のセットアップ](#テスト環境のセットアップ)
- [pytestの基本](#pytestの基本)
- [フィクスチャの使い方](#フィクスチャの使い方)
- [モックの使い方](#モックの使い方)
- [テストテンプレートの使い方](#テストテンプレートの使い方)
- [LangGraph Evaluateの使い方](#langgraph-evaluateの使い方)
- [ベストプラクティス](#ベストプラクティス)
- [トラブルシューティング](#トラブルシューティング)

---

## はじめに

このプロジェクトでは、以下のテストフレームワークとツールを使用しています:

- **pytest**: Pythonのテストフレームワーク
- **pytest-asyncio**: 非同期テストのサポート
- **unittest.mock**: モックオブジェクトの作成
- **LangGraph Evaluate**: エージェント評価フレームワーク（基本セットアップ済み）

### テストディレクトリ構造

```
backend/tests/
├── conftest.py                    # pytest設定とフィクスチャ
├── __init__.py
├── agents/                        # エージェントテスト
│   ├── test_router_agent.py
│   ├── test_business_info_agent.py
│   ├── test_memory_agent.py
│   └── ...
├── utils/                         # テストユーティリティ
│   ├── test_helpers.py           # テストヘルパー関数
│   ├── mock_helpers.py           # モック作成ヘルパー
│   ├── assertion_helpers.py      # カスタムアサート関数
│   └── langgraph_evaluate_setup.py  # LangGraph Evaluate設定
└── templates/                     # テストテンプレート
    └── test_agent_template.py    # エージェントテストテンプレート
```

---

## テスト環境のセットアップ

### 1. 依存関係のインストール

```bash
cd backend
pip install -r requirements.txt
```

### 2. 環境変数の設定

テスト実行時は自動的にテスト用環境変数が設定されます（`conftest.py`参照）:

```python
SUPABASE_URL=http://localhost:54321
SUPABASE_KEY=test-key
OPENAI_API_KEY=test-openai-key
OPENROUTER_API_KEY=test-openrouter-key
ENVIRONMENT=test
```

### 3. テストの実行

```bash
# すべてのテストを実行
pytest

# 詳細な出力で実行
pytest -v

# 特定のテストファイルを実行
pytest tests/agents/test_router_agent.py

# 特定のテストクラスを実行
pytest tests/agents/test_router_agent.py::TestRouterAgent

# 特定のテストメソッドを実行
pytest tests/agents/test_router_agent.py::TestRouterAgent::test_basic_routing

# カバレッジレポートを生成
pytest --cov=backend --cov-report=html
```

---

## pytestの基本

### テストの書き方

テストは`test_`で始まる関数またはメソッドとして定義します:

```python
import pytest

def test_simple_addition():
    """シンプルなテスト例"""
    result = 1 + 1
    assert result == 2

@pytest.mark.asyncio
async def test_async_function():
    """非同期テスト例"""
    result = await some_async_function()
    assert result is not None
```

### アサート

pytestでは標準のPythonの`assert`文を使用します:

```python
# 等価性チェック
assert result == expected

# 真偽値チェック
assert result is True
assert result is not None

# 例外チェック
with pytest.raises(ValueError):
    function_that_raises()

# メッセージ付きアサート
assert result == expected, f"Expected {expected} but got {result}"
```

### マーカー

テストにマーカーを付けて、特定のテストグループを実行できます:

```python
@pytest.mark.asyncio       # 非同期テスト
@pytest.mark.slow          # 時間がかかるテスト
@pytest.mark.integration   # 統合テスト

def test_something():
    pass
```

実行時:
```bash
# asyncioマーカーのテストのみ実行
pytest -m asyncio

# slowマーカーのテストを除外
pytest -m "not slow"
```

---

## フィクスチャの使い方

フィクスチャは、テストで使用する共通のデータやオブジェクトを提供します。

### 利用可能なフィクスチャ

`conftest.py`で定義されているフィクスチャ:

#### イベントループ

```python
@pytest.fixture(scope="session")
def event_loop():
    """非同期テスト用のイベントループ"""
```

#### OpenRouter Provider

```python
@pytest.fixture
def mock_openrouter_provider():
    """モックOpenRouterProvider"""
```

#### モデル設定

```python
@pytest.fixture
def router_config():
    """RouterAgent用モデル設定"""

@pytest.fixture
def qa_response_config():
    """QA応答用モデル設定"""

@pytest.fixture
def facility_info_config():
    """施設情報用モデル設定"""
```

#### テストデータ

```python
@pytest.fixture
def sample_query():
    """サンプルクエリ: "営業時間を教えてください\""""

@pytest.fixture
def sample_session_id():
    """サンプルセッションID: "test-session-12345\""""

@pytest.fixture
def sample_language():
    """サンプル言語設定: "ja\""""
```

#### エージェントモック

```python
@pytest.fixture
def mock_router_agent():
    """モックRouterAgent"""

@pytest.fixture
def mock_memory_agent():
    """モックMemoryAgent"""
```

### フィクスチャの使用例

```python
def test_with_fixtures(sample_query, sample_session_id, mock_openrouter_provider):
    """フィクスチャを使用したテスト例"""
    agent = MyAgent(provider=mock_openrouter_provider)
    result = await agent.process(
        query=sample_query,
        session_id=sample_session_id
    )
    assert result is not None
```

### カスタムフィクスチャの作成

テストファイル内または`conftest.py`にカスタムフィクスチャを追加できます:

```python
@pytest.fixture
def custom_test_data():
    """カスタムテストデータ"""
    return {
        "key1": "value1",
        "key2": "value2"
    }

def test_with_custom_fixture(custom_test_data):
    assert custom_test_data["key1"] == "value1"
```

---

## モックの使い方

モックは、外部依存関係（API、データベースなど）をテストから分離するために使用します。

### 基本的なモックの作成

```python
from unittest.mock import Mock, AsyncMock

# 同期モック
mock_obj = Mock()
mock_obj.method.return_value = "result"
assert mock_obj.method() == "result"

# 非同期モック
async_mock = AsyncMock()
async_mock.async_method.return_value = "async result"
result = await async_mock.async_method()
assert result == "async result"
```

### テストヘルパーを使ったモック作成

`backend/tests/utils/mock_helpers.py`のヘルパー関数を使用:

```python
from tests.utils.mock_helpers import (
    create_mock_openrouter_provider,
    create_mock_memory_system,
    create_mock_rag_system,
    create_mock_calendar_service
)

# OpenRouterProviderのモック
provider = create_mock_openrouter_provider(
    response_text="テスト回答",
    usage={"prompt_tokens": 10, "completion_tokens": 20}
)

# メモリシステムのモック
memory = create_mock_memory_system(
    context={"recent_messages": []},
    previous_request_type="hours"
)

# RAGシステムのモック
rag = create_mock_rag_system(
    search_results=[
        {"content": "検索結果1", "score": 0.95}
    ]
)
```

### モックの検証

```python
from unittest.mock import Mock

mock = Mock()
mock.method("arg1", keyword="arg2")

# 呼び出しの検証
mock.method.assert_called_once_with("arg1", keyword="arg2")

# 呼び出し回数の検証
assert mock.method.call_count == 1
```

---

## テストテンプレートの使い方

新しいエージェントのテストを作成する際は、テンプレートを使用します。

### 1. テンプレートのコピー

```bash
cp backend/tests/templates/test_agent_template.py \
   backend/tests/agents/test_your_agent.py
```

### 2. テンプレートの編集

```python
# before
class TestAgentTemplate:
    """エージェントテストのテンプレートクラス"""

# after
class TestYourAgent:
    """YourAgentのテストクラス"""
```

### 3. インポートの追加

```python
# テンプレートのTODOコメントを置き換え
from agents.your_agent import YourAgent
```

### 4. テストメソッドの実装

テンプレートには以下のカテゴリのテストが含まれています:

- **初期化テスト** (`test_initialization_*`)
- **基本機能テスト** (`test_basic_*`)
- **エラーハンドリングテスト** (`test_error_*`)
- **エッジケーステスト** (`test_edge_case_*`)
- **統合テスト** (`test_integration_*`)
- **パフォーマンステスト** (`test_performance_*`)

各テストメソッドの`# TODO: 実装`コメント部分を実装してください。

---

## LangGraph Evaluateの使い方

LangGraph Evaluateは、エージェントの出力品質を評価するためのフレームワークです。

### 基本的な使い方

```python
from tests.utils.langgraph_evaluate_setup import create_evaluator

# 評価器の作成（標準メトリクス付き）
evaluator = create_evaluator()

# エージェント出力の評価
agent_output = {
    "answer": "営業時間は10時から20時までです",
    "emotion": "neutral",
    "metadata": {"agent": "business_info"}
}

result = await evaluator.evaluate(agent_output)

# 結果の確認
print(f"Overall passed: {result['overall_passed']}")
for metric_name, metric_result in result['metrics'].items():
    print(f"{metric_name}: {metric_result['score']} (passed: {metric_result['passed']})")
```

### カスタムメトリクスの追加

```python
async def evaluate_custom_metric(
    agent_output: Dict[str, Any],
    expected_output: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None
) -> float:
    """カスタム評価メトリクス"""
    # 評価ロジックを実装
    score = 0.0
    # ... スコア計算 ...
    return score

# 評価器にメトリクスを追加
evaluator.add_metric(
    name="custom_metric",
    evaluator=evaluate_custom_metric,
    description="カスタムメトリクスの説明",
    threshold=0.7
)
```

### 評価スイートの実行

```python
from tests.utils.langgraph_evaluate_setup import run_evaluation_suite

# 複数のエージェント出力を評価
agent_outputs = [
    {"answer": "回答1", "emotion": "neutral", "metadata": {}},
    {"answer": "回答2", "emotion": "happy", "metadata": {}},
]

summary = await run_evaluation_suite(agent_outputs)

print(f"Total evaluations: {summary['total_evaluations']}")
print(f"Passed evaluations: {summary['passed_evaluations']}")
print(f"Pass rate: {summary['pass_rate']:.2%}")
```

---

## ベストプラクティス

### 1. テストの命名規則

```python
# Good: 具体的で説明的な名前
def test_router_routes_business_hours_query_to_business_info_agent():
    pass

# Bad: 曖昧な名前
def test_routing():
    pass
```

### 2. アサートメッセージ

```python
# Good: 失敗時に役立つメッセージ
assert result["agent"] == "business_info", \
    f"Expected 'business_info' but got '{result['agent']}'"

# Bad: メッセージなし
assert result["agent"] == "business_info"
```

### 3. テストの独立性

各テストは独立して実行できるようにします:

```python
# Good: セットアップをテスト内で行う
def test_something():
    agent = MyAgent()  # テスト内でセットアップ
    result = agent.process()
    assert result is not None

# Bad: グローバル状態に依存
global_agent = MyAgent()  # モジュールレベル

def test_something():
    result = global_agent.process()  # グローバル状態に依存
    assert result is not None
```

### 4. テストデータの管理

```python
# Good: フィクスチャまたはヘルパー関数を使用
from tests.utils.test_helpers import create_test_query

def test_with_helper():
    query = create_test_query("hours", "ja")
    result = agent.process(query)
    assert result is not None

# Bad: ハードコーディング
def test_hardcoded():
    query = "営業時間を教えてください"  # 繰り返し
    result = agent.process(query)
    assert result is not None
```

### 5. モックの使用

外部API呼び出しは必ずモック化します:

```python
# Good: モックを使用
def test_with_mock(mock_openrouter_provider):
    agent = MyAgent(provider=mock_openrouter_provider)
    result = await agent.process("query")
    assert result is not None

# Bad: 実際のAPIを呼び出し
def test_with_real_api():
    agent = MyAgent()  # 実際のAPIを呼び出す
    result = await agent.process("query")  # 遅い、不安定
    assert result is not None
```

### 6. テストカバレッジ

重要なコードパスは必ずテストでカバーします:

- 正常系
- エラーハンドリング
- エッジケース
- 統合ポイント

---

## トラブルシューティング

### 問題: ImportError: No module named 'backend'

**解決策**: `conftest.py`で`sys.path`が正しく設定されているか確認

```python
# conftest.py
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
```

### 問題: 非同期テストが実行されない

**解決策**: `@pytest.mark.asyncio`デコレータを追加

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

### 問題: フィクスチャが見つからない

**解決策**: フィクスチャが`conftest.py`で定義されているか確認、またはスコープを確認

```python
# conftest.py
@pytest.fixture  # デフォルトスコープは "function"
def my_fixture():
    return "value"
```

### 問題: テストが遅い

**解決策**:
1. モックを使用して外部API呼び出しを避ける
2. セッションスコープのフィクスチャを使用
3. 並列実行を有効化（`pytest-xdist`）

```bash
pip install pytest-xdist
pytest -n auto  # 自動的にワーカー数を決定
```

### 問題: カバレッジレポートが生成されない

**解決策**: `pytest-cov`がインストールされているか確認

```bash
pip install pytest-cov
pytest --cov=backend --cov-report=html
```

---

## 参考資料

- [pytest公式ドキュメント](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [LangGraph Testing](https://langchain-ai.github.io/langgraph/how-tos/testing/)

---

## ヘルプとサポート

質問や問題がある場合は、以下を確認してください:

1. このガイドのトラブルシューティングセクション
2. 既存のテストファイル（`backend/tests/agents/`）
3. テストテンプレート（`backend/tests/templates/test_agent_template.py`）
4. プロジェクトのIssueページ

Happy Testing! 🎉
