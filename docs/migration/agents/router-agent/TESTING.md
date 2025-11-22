# RouterAgent テスト戦略

## 概要

RouterAgentのテスト戦略とテストケースを説明します。

## テストの種類

### 1. 単体テスト

**目的**: RouterAgentの各機能を個別にテスト

**対象**:
- 言語検出
- クエリ分類
- メモリー関連質問の検出
- エージェント選択

### 2. 統合テスト

**目的**: ワークフロー全体でのルーティングをテスト

**対象**:
- ワークフロー全体でのルーティング
- 各エージェントへの正しいルーティング
- エラーハンドリング

### 3. パフォーマンステスト

**目的**: レスポンスタイムとスループットをテスト

**対象**:
- ルーティング決定のレスポンスタイム
- 同時リクエストの処理

## テストケース

### 言語検出のテスト

```python
def test_detect_language_japanese():
    """日本語クエリの検出テスト"""
    query = "営業時間は何時ですか？"
    language = detect_language(query)
    assert language == "ja"

def test_detect_language_english():
    """英語クエリの検出テスト"""
    query = "What are your business hours?"
    language = detect_language(query)
    assert language == "en"
```

### クエリ分類のテスト

```python
def test_classify_business_query():
    """営業情報クエリの分類テスト"""
    query = "営業時間は何時ですか？"
    classification = classify_query(query)
    assert classification.category == "business"
    assert classification.request_type == "hours"

def test_classify_facility_query():
    """施設情報クエリの分類テスト"""
    query = "Wi-Fiは使えますか？"
    classification = classify_query(query)
    assert classification.category == "facility"
```

### メモリー関連質問の検出テスト

```python
def test_is_memory_related_question():
    """メモリー関連質問の検出テスト"""
    query = "以前何を聞きましたか？"
    assert is_memory_related_question(query) == True

def test_is_not_memory_related_question():
    """メモリー関連でない質問のテスト"""
    query = "営業時間は何時ですか？"
    assert is_memory_related_question(query) == False
```

### ルーティング決定のテスト

```python
def test_route_business_query():
    """営業情報クエリのルーティングテスト"""
    state: WorkflowState = {
        "messages": [],
        "query": "営業時間は何時ですか？",
        "session_id": "test-session",
        "language": "ja",
        "routed_to": None,
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": {}
    }
    
    result = router_node(state)
    
    assert result["routed_to"] == "business_info"
    assert result["language"] == "ja"
    assert result["metadata"]["routing"]["category"] == "business"
```

### エラーハンドリングのテスト

```python
def test_router_node_empty_query():
    """空のクエリのエラーハンドリングテスト"""
    state: WorkflowState = {
        "messages": [],
        "query": "",
        "session_id": "test-session",
        "language": "ja",
        "routed_to": None,
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": {}
    }
    
    result = router_node(state)
    
    # デフォルトでgeneral_knowledgeにルーティング
    assert result["routed_to"] == "general_knowledge"
```

## テスト実行

### ローカルでの実行

```bash
# 単体テストの実行
cd backend
pytest tests/agents/test_router_agent.py -v

# カバレッジ付きで実行
pytest tests/agents/test_router_agent.py -v --cov=backend/agents/router_agent --cov-report=html

# 統合テストの実行
pytest tests/integration/test_router_integration.py -v
```

### CI/CDでの実行

GitHub Actionsで自動実行されます（[CI-CD.md](./CI-CD.md)を参照）。

## カバレッジ目標

- **単体テスト**: 80%以上
- **統合テスト**: 主要なシナリオをカバー

## モックとフィクスチャ

### モック

```python
from unittest.mock import Mock, patch

@patch('backend.agents.router_agent.detect_language')
def test_router_node_with_mock(mock_detect_language):
    """モックを使用したテスト"""
    mock_detect_language.return_value = "ja"
    
    state: WorkflowState = {
        # ...
    }
    
    result = router_node(state)
    
    mock_detect_language.assert_called_once()
    assert result["language"] == "ja"
```

### フィクスチャ

```python
import pytest

@pytest.fixture
def sample_state():
    """サンプルの状態を返すフィクスチャ"""
    return {
        "messages": [],
        "query": "営業時間は何時ですか？",
        "session_id": "test-session",
        "language": "ja",
        "routed_to": None,
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": {}
    }

def test_router_node_with_fixture(sample_state):
    """フィクスチャを使用したテスト"""
    result = router_node(sample_state)
    assert result["routed_to"] == "business_info"
```

## 参考

- [CI-CD.md](./CI-CD.md): CI/CD設定
- [README.md](./README.md): RouterAgentの概要

