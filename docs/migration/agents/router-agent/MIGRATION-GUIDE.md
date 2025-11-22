# RouterAgent 移行ガイド

## 概要

Mastra版のRouterAgentをLangGraph版に移行する手順を説明します。

## 移行の流れ

### Step 1: Mastra版の理解

**確認すべきファイル**:
- `frontend/src/mastra/agents/router-agent.ts`
- `frontend/src/lib/query-classifier.ts`
- `frontend/src/lib/language-processor.ts`

**主要な機能**:
1. 言語検出（`LanguageProcessor.detectLanguage()`）
2. クエリ分類（`QueryClassifier.classifyWithDetails()`）
3. メモリー関連質問の検出（`isMemoryRelatedQuestion()`）
4. エージェント選択（`selectAgent()`）

### Step 2: LangGraph版の実装

#### 2.1 State定義の確認

`backend/workflows/main_workflow.py`の`WorkflowState`を確認:

```python
class WorkflowState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    query: str
    session_id: str
    language: str
    routed_to: str | None  # ルーティング結果
    answer: str | None
    emotion: str | None
    metadata: dict
    context: dict
```

#### 2.2 RouterAgentノードの実装

`backend/agents/router_agent.py`を作成:

```python
from typing import Literal
from langchain_core.messages import HumanMessage
from ..workflows.main_workflow import WorkflowState

def router_node(state: WorkflowState) -> dict:
    """ルーターノード: クエリを適切なエージェントにルーティング"""
    query = state.get("query", "")
    session_id = state.get("session_id", "")
    
    # 1. 言語検出
    language = detect_language(query)
    
    # 2. メモリー関連の質問をチェック
    if is_memory_related_question(query):
        return {
            "routed_to": "memory",
            "language": language,
            "metadata": {
                **state.get("metadata", {}),
                "routing": {
                    "reason": "Memory-related question",
                    "agent": "memory"
                }
            }
        }
    
    # 3. クエリ分類
    classification = classify_query(query)
    
    # 4. エージェント選択
    selected_agent = select_agent(
        classification.category,
        classification.request_type,
        query
    )
    
    return {
        "routed_to": selected_agent,
        "language": language,
        "metadata": {
            **state.get("metadata", {}),
            "routing": {
                "category": classification.category,
                "request_type": classification.request_type,
                "agent": selected_agent,
                "confidence": classification.confidence
            }
        }
    }
```

#### 2.3 言語検出の実装

`backend/utils/language_processor.py`を作成:

```python
from typing import Literal
import re

SupportedLanguage = Literal["ja", "en"]

def detect_language(query: str) -> SupportedLanguage:
    """クエリの言語を検出"""
    # 日本語の文字（ひらがな、カタカナ、漢字）が含まれているか
    japanese_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')
    
    if japanese_pattern.search(query):
        return "ja"
    else:
        return "en"
```

#### 2.4 クエリ分類の実装

`backend/utils/query_classifier.py`を作成:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class QueryClassification:
    category: str
    request_type: Optional[str]
    confidence: float

def classify_query(query: str) -> QueryClassification:
    """クエリを分類"""
    query_lower = query.lower()
    
    # カテゴリの判定
    if any(keyword in query_lower for keyword in ["営業", "時間", "料金", "場所", "hours", "price", "location"]):
        category = "business"
        request_type = extract_request_type(query)
    elif any(keyword in query_lower for keyword in ["設備", "施設", "wifi", "wi-fi", "facility"]):
        category = "facility"
        request_type = None
    elif any(keyword in query_lower for keyword in ["イベント", "カレンダー", "予約", "event", "calendar"]):
        category = "event"
        request_type = None
    elif any(keyword in query_lower for keyword in ["?", "？", "どちら", "どっち", "which"]):
        category = "clarification"
        request_type = None
    else:
        category = "general"
        request_type = None
    
    return QueryClassification(
        category=category,
        request_type=request_type,
        confidence=0.8  # TODO: より正確な信頼度計算
    )
```

#### 2.5 エージェント選択の実装

```python
def select_agent(
    category: str,
    request_type: Optional[str],
    query: str
) -> str:
    """エージェントを選択"""
    if category == "business":
        return "business_info"
    elif category == "facility":
        return "facility"
    elif category == "event":
        return "event"
    elif category == "clarification":
        return "clarification"
    else:
        return "general_knowledge"
```

### Step 3: ワークフローへの統合

`backend/workflows/main_workflow.py`を更新:

```python
from ..agents.router_agent import router_node

class MainWorkflow:
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)
        
        # ノードの追加
        workflow.add_node("memory", self._memory_node)
        workflow.add_node("router", router_node)  # RouterAgentノード
        
        # エッジの定義
        workflow.add_edge(START, "memory")
        workflow.add_edge("memory", "router")
        
        # 条件付きルーティング
        workflow.add_conditional_edges(
            "router",
            self._route_decision,
            {
                "business_info": "business_info",
                "facility": "facility",
                "event": "event",
                "clarification": "clarification",
                "general_knowledge": "general_knowledge",
                "memory": "memory",
            }
        )
        
        # ...
```

### Step 4: テストの作成

`backend/tests/agents/test_router_agent.py`を作成:

```python
import pytest
from backend.agents.router_agent import router_node
from backend.workflows.main_workflow import WorkflowState

def test_router_node_business_query():
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

## チェックリスト

### 実装前

- [ ] Mastra版のコードを理解
- [ ] 参考実装（coworking-space-system）を確認
- [ ] 実装計画を立てる

### 実装中

- [ ] RouterAgentノードの実装
- [ ] 言語検出の実装
- [ ] クエリ分類の実装
- [ ] エージェント選択の実装
- [ ] ワークフローへの統合

### 実装後

- [ ] 単体テストの作成
- [ ] 統合テストの作成
- [ ] ドキュメントの更新
- [ ] コードレビュー

## 注意事項

1. **文脈継承**: Mastra版の文脈継承機能を実装する必要がある
2. **メモリー統合**: チェックポインターとの統合が必要
3. **エラーハンドリング**: ルーティング失敗時の処理を実装

## 参考

- [README.md](./README.md): RouterAgentの概要
- [COWORKING-SYSTEM-ANALYSIS.md](../../COWORKING-SYSTEM-ANALYSIS.md): 参考実装の分析
- [MASTRA-AGENT-ANALYSIS.md](../../MASTRA-AGENT-ANALYSIS.md): Mastra版の分析

