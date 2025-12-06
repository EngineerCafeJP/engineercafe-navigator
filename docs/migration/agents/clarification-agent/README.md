# Clarification Agent

> 曖昧な質問の明確化を担当するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **Chie** | メイン実装 |
| **Jun** | レビュー・サポート |

## 概要

Clarification Agentは、ユーザーからの曖昧な質問（「カフェの営業時間は？」「会議室の予約方法は？」など）に対して、どの施設について聞いているのか確認を行います。エンジニアカフェとSainoカフェ、または有料会議室と地下MTGスペースの区別が必要な場合に呼び出されます。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **カフェの曖昧性解消** | エンジニアカフェ or Sainoカフェの特定 |
| **会議室の曖昧性解消** | 有料会議室(2F) or 地下MTGスペースの特定 |
| **選択肢の提示** | ユーザーに分かりやすい選択肢を提示 |

### 責任範囲外

- 実際の情報提供（確認後、適切なエージェントへ再ルーティング）
- 曖昧でない質問への対応

## アーキテクチャ上の位置づけ

```
[Router Agent]
       │
       ▼ category: cafe-clarification-needed
       │         / meeting-room-clarification-needed
┌──────────────────────┐
│ Clarification Agent  │ ← このエージェント
└──────────┬───────────┘
           │
           ▼ ユーザーの回答
┌──────────────────────┐
│    Router Agent      │ ← 再ルーティング
└──────────────────────┘
```

## 曖昧性解消のパターン

### カフェの曖昧性

**トリガー**: 「カフェ」という単語が含まれるが、どちらか特定できない場合

```
ユーザー: カフェの営業時間は？
Clarification Agent:
  お手伝いさせていただきます！どちらについてお聞きでしょうか：
  1. エンジニアカフェ（コワーキングスペース）- 営業時間、設備、利用方法
  2. サイノカフェ（併設のカフェ＆バー）- メニュー、営業時間、料金
  お聞かせください！
```

### 会議室の曖昧性

**トリガー**: 「会議室」という単語が含まれるが、どちらか特定できない場合

```
ユーザー: 会議室の予約方法は？
Clarification Agent:
  お手伝いさせていただきます！会議スペースは2種類ございます：
  1. 有料会議室（2階）- 事前予約制の個室（有料）
  2. 地下MTGスペース（地下1階）- カジュアルな打ち合わせ用の無料スペース
  どちらについてお知りになりたいですか？
```

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/clarification-agent.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `handleClarification()` | 曖昧性解消の処理 |

### カテゴリ別処理

```typescript
async handleClarification(
  query: string,
  category: string,  // 'cafe-clarification-needed' | 'meeting-room-clarification-needed'
  language: SupportedLanguage
): Promise<UnifiedAgentResponse>
```

## LangGraph移行後の設計

### ノード定義

```python
def clarification_node(state: WorkflowState) -> dict:
    """曖昧性解消ノード"""
    category = state["metadata"]["routing"]["category"]
    language = state["language"]

    if category == "cafe-clarification-needed":
        message = get_cafe_clarification_message(language)
    elif category == "meeting-room-clarification-needed":
        message = get_meeting_room_clarification_message(language)
    else:
        message = get_default_clarification_message(language)

    return {
        "response": message,
        "metadata": {
            "agent": "ClarificationAgent",
            "requires_followup": True,
            "clarification_type": category
        }
    }
```

### 状態管理

```python
class ClarificationState(TypedDict):
    clarification_type: str  # 'cafe' | 'meeting-room'
    options: list[str]       # 提示した選択肢
    awaiting_response: bool  # ユーザー回答待ち
```

## 感情タグの使い分け

| 状況 | 感情タグ | 理由 |
|-----|---------|------|
| 選択肢提示 | `[surprised]` | 「えっ、どちらですか？」的なニュアンス |
| 一般的な確認 | `[surprised]` | 質問をしている印象 |

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| カフェ曖昧 | 「カフェの営業時間は？」→ 選択肢提示 |
| 会議室曖昧 | 「会議室の予約方法は？」→ 選択肢提示 |
| 明確な質問 | 「エンジニアカフェの営業時間」→ ルーティングされない |

## ユーザー回答後の処理

ユーザーが選択肢に回答した後の処理は、Router Agentが担当します：

1. ユーザーが「エンジニアカフェ」と回答
2. Router Agentが再度ルーティング
3. BusinessInfoAgentへ転送
4. 具体的な回答を提供

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] カフェ曖昧性解消のメッセージを確認した
- [ ] 会議室曖昧性解消のメッセージを確認した
- [ ] 日本語/英語の両方のメッセージを確認した
- [ ] Memory Agentとの連携（「もう一つの方」）を理解した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - ルーティング元
- [Memory Agent](../memory-agent/README.md) - 「もう一つの方」処理
- [Language Classifier](../language-classifier/README.md) - 言語処理
