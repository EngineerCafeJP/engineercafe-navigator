# Memory Agent

> 会話履歴・記憶に関する質問に回答するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **takegg0311** | メイン実装 |
| **YukitoLyn** | サポート |
| **Natsumi** | サポート |
| **Jun** | サポート |

## 概要

Memory Agentは、ユーザーとの過去の会話履歴に関する質問に回答します。「さっき何を聞いた？」「前に話したことを覚えてる？」といった記憶関連の質問を処理し、SimplifiedMemorySystemと連携して会話の文脈を維持します。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **質問履歴の参照** | 「さっき何を聞いた？」への回答 |
| **回答履歴の参照** | 「前の回答を教えて」への回答 |
| **文脈の維持** | 会話の流れを記憶・参照 |
| **曖昧性解消の補助** | 「もう一つの方は？」への対応 |

### 責任範囲外

- 新しい情報の検索（各専門エージェントの責務）
- 感情分析（EmotionManagerの責務）

## アーキテクチャ上の位置づけ

```
[Router Agent]
       │
       ▼ メモリ関連キーワード検出
┌─────────────────┐
│  Memory Agent   │ ← このエージェント
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ SimplifiedMemorySystem  │
│   (3分間の会話履歴)     │
└─────────────────────────┘
```

## メモリ関連キーワード

### 日本語

```
さっき, 前に, 覚えて, 記憶, 質問, 聞いた, 話した,
どんな, 何を, 言った, 会話, 履歴, 先ほど
```

### 英語

```
remember, recall, earlier, before, previous, asked,
said, mentioned, conversation, history, what did i
```

## 依存関係

### 入力依存

| コンポーネント | 用途 |
|--------------|------|
| `SimplifiedMemorySystem` | 3分間の会話履歴取得 |
| `SessionId` | セッション識別 |

### メモリシステム仕様

```typescript
// SimplifiedMemorySystemの設定
const memory = new SimplifiedMemorySystem('shared');

// 会話履歴の取得
const context = await memory.getContext(query, {
  includeKnowledgeBase: false,  // メモリのみ参照
  language: 'ja'
});
```

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/memory-agent.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `handleMemoryQuery()` | メモリ関連質問の処理 |
| `buildMemoryPrompt()` | メモリコンテキストからプロンプト構築 |
| `isAskingAboutPreviousQuestion()` | 質問履歴への質問か判定 |
| `isAskingAboutPreviousAnswer()` | 回答履歴への質問か判定 |
| `isAskingAboutOtherOption()` | 「もう一つ」系の質問か判定 |
| `handleOtherOptionQuery()` | 曖昧性解消後の補完質問処理 |

### 質問タイプ判定

```typescript
// 質問履歴への質問
const questionKeywords = [
  '何を聞いた', '質問した', 'どんな質問', '聞いたこと',
  'what did i ask', 'what i asked', 'my question'
];

// 回答履歴への質問
const answerKeywords = [
  '答え', '回答', '返事', '応答',
  'answer', 'response', 'replied', 'told me'
];
```

## LangGraph移行後の設計

### ノード定義

```python
def memory_node(state: WorkflowState) -> dict:
    """メモリノード"""
    query = state["query"]
    session_id = state["session_id"]
    language = state["language"]

    # メモリシステムから会話履歴を取得
    memory_context = await simplified_memory.get_context(
        query=query,
        include_knowledge_base=False,
        language=language
    )

    if not memory_context.recent_messages:
        return no_history_response(language)

    # 質問タイプを判定
    query_type = detect_memory_query_type(query)

    # 適切なプロンプトを構築して回答生成
    prompt = build_memory_prompt(query, memory_context, query_type, language)
    answer = await generate_response(prompt)

    return {
        "response": answer,
        "metadata": {"agent": "MemoryAgent", "query_type": query_type}
    }
```

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| 質問履歴 | 「さっき何を聞いた？」→ 前回の質問内容 |
| 回答履歴 | 「前の回答を教えて」→ 前回の回答内容 |
| 履歴なし | 「覚えてる？」→ 履歴がない旨の回答 |
| もう一つ | 「もう一つの方は？」→ 曖昧性解消の補完 |

## 感情タグの使い分け

| 状況 | 感情タグ | 理由 |
|-----|---------|------|
| 履歴あり | `[relaxed]` | 落ち着いて回答 |
| 履歴なし | `[sad]` | 申し訳なさを表現 |
| もう一つ系 | `[happy]` | 補足情報を提供 |
| 文脈不明 | `[surprised]` | 確認を求める |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] SimplifiedMemorySystemの仕組みを把握した
- [ ] 3分間のTTL（有効期限）を理解した
- [ ] 質問タイプ判定ロジックを理解した
- [ ] 「もう一つの方」処理を確認した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - ルーティング元
- [Clarification Agent](../clarification-agent/README.md) - 曖昧性解消
- [SimplifiedMemorySystem](../../systems/memory-system.md) - メモリシステム
