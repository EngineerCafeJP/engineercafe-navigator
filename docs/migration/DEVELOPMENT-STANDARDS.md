# 開発標準 - LangGraph移行プロジェクト

## 概要

このドキュメントは、LangGraph移行プロジェクトにおける開発標準を定義します。すべての開発者はこの標準に従って開発を進めてください。

## ディレクトリ構造

```
backend/
├── agents/              # エージェント実装
│   ├── __init__.py
│   ├── router_agent.py
│   ├── business_info_agent.py
│   └── ...
├── workflows/           # LangGraphワークフロー
│   ├── __init__.py
│   └── main_workflow.py
├── tools/               # エージェントツール
│   ├── __init__.py
│   ├── rag_tools.py
│   ├── ocr_tools.py
│   └── ...
├── models/              # データモデル・型定義
│   ├── __init__.py
│   ├── types.py
│   └── agent_response.py
├── utils/               # 共通ユーティリティ
│   ├── __init__.py
│   ├── logger.py
│   ├── error_handler.py
│   └── language_processor.py
├── config/              # 設定管理
│   ├── __init__.py
│   └── settings.py
├── tests/               # テスト
│   ├── __init__.py
│   ├── conftest.py
│   ├── agents/
│   ├── workflows/
│   └── integration/
├── main.py              # FastAPIアプリケーション
├── requirements.txt     # 依存関係
├── pyproject.toml       # Poetry設定
└── pytest.ini          # pytest設定
```

## コーディング規約

### Pythonスタイル

- **フォーマッター**: Black（line-length: 100）
- **リンター**: Ruff
- **型チェック**: mypy

```bash
# フォーマット
black backend/

# リンター
ruff check backend/

# 型チェック
mypy backend/
```

### 命名規則

- **ファイル名**: `snake_case.py`
- **クラス名**: `PascalCase`
- **関数・変数名**: `snake_case`
- **定数**: `UPPER_SNAKE_CASE`

### 型ヒント

すべての関数に型ヒントを付与：

```python
from typing import Optional, Dict, Any
from models.types import WorkflowState, UnifiedAgentResponse

def process_query(
    query: str,
    session_id: str,
    language: str = "ja"
) -> UnifiedAgentResponse:
    """クエリを処理"""
    pass
```

## エラーハンドリング

### 標準的なエラーハンドリング

```python
from utils.error_handler import handle_error, AgentError

try:
    result = some_operation()
except Exception as e:
    error_response = handle_error(e, agent_name="MyAgent")
    return error_response
```

### カスタムエラー

```python
from utils.error_handler import AgentError

raise AgentError(
    message="処理に失敗しました",
    agent_name="MyAgent",
    error_code="PROCESSING_ERROR",
    details={"query": query}
)
```

## ロギング

### ロガーの使用

```python
from utils.logger import get_logger

logger = get_logger(__name__)

logger.info("処理を開始しました")
logger.error("エラーが発生しました", exc_info=True)
```

### ログレベル

- **DEBUG**: デバッグ情報
- **INFO**: 一般的な情報
- **WARNING**: 警告
- **ERROR**: エラー
- **CRITICAL**: 重大なエラー

## テスト標準

### テストファイルの配置

- 単体テスト: `tests/agents/test_router_agent.py`
- 統合テスト: `tests/integration/test_workflow_integration.py`
- エンドツーエンドテスト: `tests/e2e/test_full_workflow.py`

### テストの書き方

```python
import pytest
from backend.agents.router_agent import router_node
from backend.models.types import WorkflowState

@pytest.mark.unit
def test_router_node_business_query(sample_workflow_state):
    """営業情報クエリのルーティングテスト"""
    state: WorkflowState = sample_workflow_state
    state["query"] = "営業時間は何時ですか？"
    
    result = router_node(state)
    
    assert result["routed_to"] == "business_info"
    assert result["language"] == "ja"
```

### テストマーカー

- `@pytest.mark.unit`: 単体テスト
- `@pytest.mark.integration`: 統合テスト
- `@pytest.mark.e2e`: エンドツーエンドテスト
- `@pytest.mark.slow`: 実行に時間がかかるテスト

### テスト実行

```bash
# すべてのテスト
pytest tests/

# 単体テストのみ
pytest tests/ -m unit

# カバレッジ付き
pytest tests/ --cov=backend --cov-report=html
```

## 環境変数管理

### 環境変数の設定

`.env.example`をコピーして`.env`を作成：

```bash
cp backend/.env.example backend/.env
# .envを編集
```

### 環境変数の読み込み

```python
from config.settings import get_settings

settings = get_settings()
api_key = settings.openai_api_key
```

## コードレビュー

### PR作成時のチェックリスト

- [ ] コードがBlackでフォーマットされている
- [ ] Ruffのリンターエラーがない
- [ ] mypyの型チェックが通過している
- [ ] テストが追加されている（カバレッジ80%以上）
- [ ] ドキュメントが更新されている
- [ ] エラーハンドリングが適切
- [ ] ロギングが適切

### レビュアー

- 統合エージェント担当者（寺田@terisuke, YukitoLyn）
- 担当エージェントの他の担当者

## CI/CD

### GitHub Actions

`.github/workflows/backend-ci.yml`で自動実行：

1. リンター（Ruff, Black）
2. 型チェック（mypy）
3. テスト実行
4. カバレッジレポート

### ローカルでの実行

```bash
# すべてのチェックを実行
cd backend
ruff check .
black --check .
mypy .
pytest tests/
```

## ドキュメント

### ドキュメント文字列

すべての関数・クラスにdocstringを記述：

```python
def process_query(query: str, session_id: str) -> UnifiedAgentResponse:
    """
    クエリを処理してエージェント応答を返す
    
    Args:
        query: ユーザーのクエリ
        session_id: セッションID
        
    Returns:
        エージェント応答
        
    Raises:
        AgentError: 処理に失敗した場合
    """
    pass
```

### エージェントドキュメント

各エージェントのドキュメントは`docs/migration/agents/{agent-name}/`に配置。

## 参考

- [Python PEP 8](https://pep8.org/)
- [Black Documentation](https://black.readthedocs.io/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [pytest Documentation](https://docs.pytest.org/)

