# RouterAgent（統合エージェント）

## 概要

RouterAgentは、ユーザーのクエリを分析し、適切な専門エージェントにルーティングする統合エージェントです。Primary Assistantパターンで実装され、全体のワークフローを制御します。

## 担当者

- **寺田@terisuke**（優先度1）- 責任者
- **YukitoLyn**（優先度1）

## 役割と責任範囲

### やること

1. **クエリの言語検出**
   - 日本語/英語の自動検出
   - 応答言語の決定

2. **クエリの分類**
   - カテゴリの判定（business, facility, event, general, clarification）
   - 特定リクエストタイプの抽出（hours, pricing, location等）

3. **メモリー関連の質問の検出**
   - 「以前何を聞いたか」等のメモリー関連質問を優先的に検出
   - MemoryAgentへの直接ルーティング

4. **文脈依存クエリの処理**
   - 短いクエリ（「営業時間は？」等）の文脈継承
   - 前回のrequestTypeとエンティティの継承

5. **適切なエージェントへのルーティング**
   - クエリの内容に基づいて最適なエージェントを選択
   - ルーティング結果の返却

### やらないこと

- クエリへの直接回答（専門エージェントに委譲）
- データベースへの直接アクセス
- RAG検索の実行（専門エージェントに委譲）

## 依存関係

### 依存するコンポーネント

- **LanguageProcessor**: 言語検出
- **QueryClassifier**: クエリ分類
- **SimplifiedMemorySystem**: メモリーアクセス（文脈継承用）

### 依存されるコンポーネント

- **すべての専門エージェント**: RouterAgentのルーティング結果に基づいて処理

## 主要機能

### 1. 言語検出

```python
def detect_language(query: str) -> SupportedLanguage:
    """クエリの言語を検出"""
    # LanguageProcessorを使用
    # 日本語/英語の判定
    # 応答言語の決定
```

### 2. クエリ分類

```python
def classify_query(query: str) -> QueryClassification:
    """クエリを分類"""
    # QueryClassifierを使用
    # category, requestType, confidenceを返却
```

### 3. ルーティング決定

```python
def route_query(query: str, session_id: str) -> RouteResult:
    """クエリを適切なエージェントにルーティング"""
    # メモリー関連の質問をチェック
    # クエリを分類
    # エージェントを選択
    # RouteResultを返却
```

## Mastra版からの移行

### 対応関係

| Mastra版 | LangGraph版 |
|----------|-------------|
| `RouterAgent.routeQuery()` | `router_node()` |
| `QueryClassifier` | `query_classifier` ツール |
| `LanguageProcessor` | `language_processor` ツール |
| `RouteResult` | `WorkflowState.routed_to` |

### 実装のポイント

1. **Primary Assistantパターン**
   - coworking-space-systemの`primary_assistant`を参考
   - ツールベースのルーティング（`ToBusinessInfoAgent`, `ToFacilityAgent`等）

2. **状態管理**
   - `WorkflowState.routed_to`にルーティング結果を保存
   - 条件付きエッジで各エージェントに分岐

3. **メモリー統合**
   - チェックポインターとの統合
   - 文脈継承の実装

## 実装例

### LangGraphノード実装

```python
def router_node(state: WorkflowState) -> dict:
    """ルーターノード: クエリを適切なエージェントにルーティング"""
    query = state.get("query", "")
    session_id = state.get("session_id", "")
    
    # 言語検出
    language = detect_language(query)
    
    # メモリー関連の質問をチェック
    if is_memory_related_question(query):
        return {
            "routed_to": "memory",
            "language": language,
            "metadata": {"reason": "Memory-related question"}
        }
    
    # クエリ分類
    classification = classify_query(query)
    
    # エージェント選択
    selected_agent = select_agent(
        classification.category,
        classification.request_type,
        query
    )
    
    return {
        "routed_to": selected_agent,
        "language": language,
        "metadata": {
            "category": classification.category,
            "request_type": classification.request_type,
            "confidence": classification.confidence
        }
    }
```

## テスト戦略

### 単体テスト

- 言語検出のテスト
- クエリ分類のテスト
- ルーティング決定のテスト
- メモリー関連質問の検出テスト

### 統合テスト

- 各エージェントへのルーティングテスト
- ワークフロー全体のテスト

## 次のステップ

1. [MIGRATION-GUIDE.md](./MIGRATION-GUIDE.md) を読んで移行手順を確認
2. [CI-CD.md](./CI-CD.md) を読んでCI/CD設定を確認
3. [TESTING.md](./TESTING.md) を読んでテスト戦略を確認
4. featureブランチを作成して実装を開始

## 参考資料

- [MASTRA-AGENT-ANALYSIS.md](../../MASTRA-AGENT-ANALYSIS.md): Mastra版の分析
- [COWORKING-SYSTEM-ANALYSIS.md](../../COWORKING-SYSTEM-ANALYSIS.md): 参考実装の分析
- [INTEGRATION-GUIDE.md](../../INTEGRATION-GUIDE.md): 統合ガイド

