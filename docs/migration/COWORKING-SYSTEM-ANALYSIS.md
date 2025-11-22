# Coworking Space System 分析

## 概要

このドキュメントは、参考リポジトリ `langgraph-reference/coworking-space-system` の実装を分析し、Engineer Cafe Navigatorへの適用方法を説明します。

## 参考リポジトリの取得

`langgraph-reference`はgit submoduleとして管理されています。以下のコマンドで取得できます：

```bash
# 初回クローン時
git clone --recurse-submodules <repository-url>

# 既存リポジトリの場合
git submodule update --init --recursive
```

参考リポジトリのパス: `langgraph-reference/coworking-space-system/`

## リポジトリ構造

```
langgraph-reference/coworking-space-system/
├── src/
│   ├── agents/              # 専門アシスタント（エージェント）
│   │   ├── reception_assistant.py
│   │   ├── space_booking_assistant.py
│   │   ├── event_management_assistant.py
│   │   └── membership_assistant.py
│   ├── tools/               # ツール（データベース操作等）
│   │   ├── visitor_tools.py
│   │   ├── space_tools.py
│   │   ├── event_tools.py
│   │   ├── member_tools.py
│   │   └── payment_tools.py
│   ├── graph.py             # メインのLangGraphワークフロー
│   ├── types.py            # 型定義（State, ルーティングツール等）
│   ├── database.py         # データベース接続管理
│   └── config.py           # 設定管理
├── database/               # データベーススキーマとデモデータ
├── app.py                  # Streamlit Webアプリ
└── test_*.py              # 各種テストファイル
```

## アーキテクチャパターン

### 1. Primary Assistant + Specialized Assistants パターン

**構造**:
- **Primary Assistant**: 総合受付・ルーティング担当
- **Specialized Assistants**: 各専門領域のアシスタント

**実装例** (`src/graph.py`):
```python
# Primary Assistant
primary_assistant_runnable = primary_assistant_prompt | llm.bind_tools([
    ToReceptionAssistant,
    ToSpaceBookingAssistant,
    ToEventManagementAssistant, 
    ToMembershipAssistant,
])

# ルーティング
workflow.add_conditional_edges(
    "primary_assistant",
    tools_condition,
    {
        "tools": "primary_assistant_tools",
        "continue": "route_primary_assistant",
    }
)
```

**Engineer Cafe Navigatorへの適用**:
- `RouterAgent` が Primary Assistant の役割
- `BusinessInfoAgent`, `FacilityAgent`, `EventAgent` 等が Specialized Assistants

### 2. State管理パターン

**State定義** (`src/types.py`):
```python
class State(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    member_info: str
    dialog_state: Annotated[
        List[DialogState],
        update_dialog_stack,
    ]
```

**特徴**:
- `messages`: 会話履歴（LangGraphの標準パターン）
- `member_info`: 会員情報（JSON文字列）
- `dialog_state`: 現在アクティブなアシスタントのスタック

**Engineer Cafe Navigatorへの適用**:
```python
class WorkflowState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    query: str
    session_id: str
    language: str
    routed_to: str | None
    answer: str | None
    emotion: str | None
    metadata: dict
    context: dict
```

### 3. ツールベースの実装パターン

**ツール定義例** (`src/tools/space_tools.py`):
```python
@tool
def get_available_spaces(
    space_type: str = None,
    start_datetime: str = None,
    end_datetime: str = None
) -> str:
    """利用可能なスペースを取得"""
    # データベースクエリ実行
    # 結果をJSON文字列で返す
    return json.dumps(results)
```

**特徴**:
- LangChainの`@tool`デコレータを使用
- データベース操作をツールとして実装
- エラーハンドリングとバリデーションを含む

**Engineer Cafe Navigatorへの適用**:
- RAG検索ツール
- カレンダー取得ツール
- メモリ操作ツール
- OCR処理ツール（新規）

### 4. ルーティングパターン

**ルーティング関数** (`src/graph.py`):
```python
def route_primary_assistant(state: State) -> Literal[
    "reception_assistant",
    "space_booking_assistant",
    "event_management_assistant",
    "membership_assistant",
    "continue"
]:
    """Primary Assistantからのルーティング決定"""
    last_message = state["messages"][-1]
    
    if last_message.tool_calls:
        tool_name = last_message.tool_calls[0]["name"]
        # ツール名に基づいてルーティング
        if tool_name == "ToReceptionAssistant":
            return "reception_assistant"
        # ...
    
    return "continue"
```

**Engineer Cafe Navigatorへの適用**:
- `RouterAgent`の`routeQuery`メソッドをPython版に移植
- クエリ分類とエージェント選択ロジックを実装

### 5. チェックポインター（永続化）パターン

**実装** (`src/database.py`):
```python
from langgraph.checkpoint.postgres import PostgresSaver

def get_postgres_checkpointer():
    """PostgreSQLベースのチェックポインターを取得"""
    return PostgresSaver(
        connection_string=settings.postgres_connection_string
    )

# グラフに適用
workflow = workflow.compile(checkpointer=get_postgres_checkpointer())
```

**特徴**:
- 会話状態の永続化
- セッション管理
- ヒューマンインザループ対応

**Engineer Cafe Navigatorへの適用**:
- Supabase（PostgreSQL）を使用
- セッション管理と会話履歴の永続化

## 主要コンポーネントの実装例

### 1. エージェントノードの実装

**例: Reception Assistant** (`src/agents/reception_assistant.py`):
```python
def reception_assistant_node(state: State) -> dict:
    """受付アシスタントノード"""
    # 会員情報を取得
    member_info = get_member_info_string()
    
    # プロンプトを作成
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"あなたは受付アシスタントです。{member_info}"),
        ("placeholder", "{messages}"),
    ])
    
    # LLMを呼び出し
    runnable = prompt | llm.bind_tools([...])
    result = runnable.invoke(state)
    
    return {"messages": [result]}
```

**Engineer Cafe Navigatorへの適用**:
- 各エージェント（BusinessInfoAgent, FacilityAgent等）を同様のパターンで実装
- Mastra版のロジックをPython版に移植

### 2. ツールノードの実装

**例** (`src/graph.py`):
```python
def reception_tools_node(state: State) -> dict:
    """受付アシスタントのツール実行ノード"""
    last_message = state["messages"][-1]
    
    # ツールを実行
    tool_results = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        # ツールを実行
        result = execute_tool(tool_name, tool_args)
        tool_results.append(
            ToolMessage(content=result, tool_call_id=tool_call["id"])
        )
    
    return {"messages": tool_results}
```

**Engineer Cafe Navigatorへの適用**:
- RAG検索ツール
- カレンダー取得ツール
- メモリ操作ツール
- OCR処理ツール

### 3. エラーハンドリング

**例** (`src/utils/error_handler.py`):
```python
def handle_tool_error(tool_name: str, error: Exception) -> str:
    """ツールエラーを処理"""
    error_message = f"ツール '{tool_name}' の実行中にエラーが発生しました: {str(error)}"
    logger.error(error_message)
    return json.dumps({"error": error_message, "tool": tool_name})
```

**Engineer Cafe Navigatorへの適用**:
- 各エージェントとツールにエラーハンドリングを実装
- ユーザーフレンドリーなエラーメッセージ

## Engineer Cafe Navigatorへの適用ポイント

### 1. アーキテクチャの対応関係

| Coworking Space System | Engineer Cafe Navigator |
|------------------------|------------------------|
| Primary Assistant | RouterAgent |
| Reception Assistant | BusinessInfoAgent, FacilityAgent |
| Space Booking Assistant | EventAgent（カレンダー統合） |
| Event Management Assistant | EventAgent |
| Membership Assistant | MemoryAgent（会話履歴管理） |

### 2. 実装の優先順位

1. **State定義**: `WorkflowState`の拡張
2. **RouterAgent**: Primary Assistantパターンの実装
3. **各Specialized Agent**: ツールベースの実装
4. **チェックポインター**: Supabase統合
5. **エラーハンドリング**: 包括的なエラー処理

### 3. 新規実装が必要な部分

- **OCRAgent**: coworking-space-systemにはないため、新規実装
- **VoiceAgent**: 音声入出力の統合
- **CharacterControlAgent**: 3Dキャラクター制御

## 参考実装ファイル

### 必須確認ファイル

1. **`src/graph.py`**: メインのワークフロー実装
2. **`src/types.py`**: Stateと型定義
3. **`src/agents/reception_assistant.py`**: エージェント実装例
4. **`src/tools/space_tools.py`**: ツール実装例
5. **`src/database.py`**: データベース接続とチェックポインター

### テストファイル

1. **`test_basic.py`**: 基本的な動作確認
2. **`test_assistants.py`**: エージェントの統合テスト
3. **`test_checkpointer.py`**: チェックポインターのテスト

## 次のステップ

1. `backend/workflows/main_workflow.py`を参考実装に基づいて拡張
2. 各エージェントを`backend/agents/`に実装
3. ツールを`backend/tools/`に実装
4. テストを`backend/tests/`に作成

## 注意事項

- coworking-space-systemはAnthropic Claudeを使用しているが、Engineer Cafe NavigatorはGemini/OpenAIを使用
- データベーススキーマは異なるため、適切にマッピングが必要
- 音声入出力と3Dキャラクター制御は新規実装が必要

