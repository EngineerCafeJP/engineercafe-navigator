# {AgentName}

> {エージェントの一言説明}

## 担当者

| 担当者 | 役割 |
|-------|------|
| **{名前}** | メイン実装 |
| **{名前}** | レビュー・サポート |

## 概要

{エージェントの目的と責任範囲を2-3文で説明}

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **{責務1}** | {説明} |
| **{責務2}** | {説明} |
| **{責務3}** | {説明} |

### 責任範囲外

- {他エージェントの責務1}
- {他エージェントの責務2}

## アーキテクチャ上の位置づけ

```
[入力]
   │
   ▼
┌─────────────────┐
│  {AgentName}    │ ← このエージェント
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│ 処理1 │ │ 処理2 │
└───────┘ └───────┘
         │
         ▼
    [出力先]
```

## 入出力仕様

### 入力 (Input)

```typescript
interface {AgentName}Input {
  query: string;              // ユーザーのクエリ
  language: 'ja' | 'en';      // 言語
  sessionId: string;          // セッションID
  // エージェント固有のフィールド
}
```

### 出力 (Output)

```typescript
interface {AgentName}Output {
  success: boolean;
  response?: string;          // 応答テキスト
  emotion?: string;           // 感情タグ
  metadata: {
    agent: string;
    // その他のメタデータ
  };
  error?: string;
}
```

## ルーティング条件

RouterAgentがこのエージェントを選択する条件：

### キーワードパターン

**日本語:**
- {キーワード1}
- {キーワード2}

**英語:**
- {keyword1}
- {keyword2}

### コンテキスト条件

- {条件1}
- {条件2}

## 実装詳細

### LangGraphノード定義

```python
from langgraph.graph import StateGraph
from typing import TypedDict

class {AgentName}State(TypedDict):
    query: str
    language: str
    session_id: str
    # エージェント固有のフィールド

async def {agent_name}_node(state: {AgentName}State) -> dict:
    """
    {エージェントの処理を説明}
    """
    query = state["query"]
    language = state["language"]

    # 1. {処理ステップ1}
    # 2. {処理ステップ2}
    # 3. {処理ステップ3}

    return {
        "response": result,
        "emotion": "neutral",
        "metadata": {"agent": "{AgentName}"}
    }
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `{method1}()` | {説明} |
| `{method2}()` | {説明} |
| `{method3}()` | {説明} |

## RAG/ツール連携

### 使用するツール

| ツール | 用途 |
|-------|------|
| Enhanced RAG Search | {用途} |
| Memory System | {用途} |
| {その他} | {用途} |

### RAG検索カテゴリ

```python
rag_categories = [
    "{category1}",
    "{category2}",
]
```

## エラーハンドリング

| エラー種別 | 対処方法 | フォールバック |
|-----------|---------|---------------|
| RAG検索失敗 | {対処} | {フォールバック} |
| LLM タイムアウト | {対処} | {フォールバック} |
| {その他} | {対処} | {フォールバック} |

## パフォーマンス目標

| 指標 | 目標値 |
|-----|-------|
| P50 レイテンシ | < {X}ms |
| P95 レイテンシ | < {X}ms |
| 成功率 | > {X}% |
| トークン使用量 | < {X} tokens/request |

## テストケース

### 単体テスト

```python
@pytest.mark.asyncio
async def test_{agent_name}_basic():
    """基本的なクエリのテスト"""
    state = {
        "query": "{テストクエリ}",
        "language": "ja",
        "session_id": "test-123"
    }

    result = await {agent_name}_node(state)

    assert result["success"] == True
    assert "{期待キーワード}" in result["response"]
```

### テストケース一覧

| カテゴリ | テストケース | 期待結果 |
|---------|-------------|---------|
| 正常系 | {ケース1} | {期待結果} |
| 正常系 | {ケース2} | {期待結果} |
| エッジケース | {ケース3} | {期待結果} |
| エラー系 | {ケース4} | {期待結果} |

## 既知の制限事項

1. **{制限1}**: {説明と回避策}
2. **{制限2}**: {説明と回避策}

## マイグレーションチェックリスト

### 準備フェーズ

- [ ] Mastra版の実装を理解した
- [ ] 入出力仕様を確認した
- [ ] 依存するツール/APIを確認した
- [ ] テストデータセットを準備した

### 実装フェーズ

- [ ] StateGraph定義を作成した
- [ ] ノード関数を実装した
- [ ] エラーハンドリングを追加した
- [ ] ログ/トレースを実装した

### テストフェーズ

- [ ] 単体テストを作成した（20件以上）
- [ ] 統合テストを作成した
- [ ] 評価データセットで検証した（85%以上のパス率）
- [ ] パフォーマンステストを実行した

### デプロイフェーズ

- [ ] ドキュメントを更新した
- [ ] コードレビューを完了した
- [ ] ステージング環境でテストした
- [ ] 本番デプロイを完了した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - ルーティング
- [{関連Agent1}](../{agent1}/README.md) - {関連内容}
- [{関連Agent2}](../{agent2}/README.md) - {関連内容}
- [LangGraph開発ガイド](../../LANGGRAPH-DEVELOPMENT-GUIDE.md)

## 変更履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| v1.0.0 | YYYY-MM-DD | 初回実装 |
