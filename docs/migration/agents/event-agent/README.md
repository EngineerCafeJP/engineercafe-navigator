# Event Agent

> イベント・カレンダー情報に関する質問に回答するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **テリスケ** | メイン実装 |

## 概要

Event Agentは、エンジニアカフェで開催されるイベント、勉強会、セミナーなどの情報を提供します。Google CalendarおよびConnpass APIと連携し、リアルタイムのイベント情報を取得・回答します。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **今日のイベント** | 本日開催予定のイベント一覧 |
| **今週のイベント** | 今週の予定イベント一覧 |
| **イベント検索** | 特定のキーワードでイベント検索 |
| **イベント詳細** | 個別イベントの詳細情報提供 |

### 責任範囲外

- 施設の予約状況（FacilityAgentの責務）
- 営業時間（BusinessInfoAgentの責務）

## アーキテクチャ上の位置づけ

```
[Router Agent]
       │
       ▼ category: calendar/events
┌─────────────────┐
│   Event Agent   │ ← このエージェント
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌──────────┐
│Calendar│ │Knowledge │
│  API  │ │   Base   │
└───────┘ └──────────┘
```

## 対応するクエリパターン

| パターン | キーワード例 | 期間 |
|---------|-------------|------|
| 今日 | 今日, today, 本日 | 当日のみ |
| 今週 | 今週, this week | 7日間 |
| 来週 | 来週, next week | 翌週7日間 |
| 今月 | 今月, this month | 当月 |

## 依存関係

### 外部サービス

| サービス | 用途 |
|---------|------|
| `Google Calendar API` | カレンダーイベントの取得 |
| `Connpass API` | 技術イベント情報の取得 |
| `Knowledge Base` | イベント関連の静的情報 |

### ツール

```typescript
// Event Agentが使用するツール
const tools = {
  calendarService: CalendarServiceTool,
  ragSearch: RAGSearchTool
};
```

## 現在の実装（Mastra）

### ファイル

```
engineer-cafe-navigator-repo/src/mastra/agents/event-agent.ts
```

### 主要メソッド

| メソッド | 説明 |
|---------|------|
| `answerEventQuery()` | イベント質問への回答 |
| `extractTimeRange()` | クエリから期間を抽出 |
| `buildEventPrompt()` | イベント情報のプロンプト構築 |
| `formatCalendarEvents()` | カレンダーイベントの整形 |
| `getNoEventsResponse()` | イベントなし時の応答 |

### 期間抽出ロジック

```typescript
private extractTimeRange(query: string): 'today' | 'thisWeek' | 'nextWeek' | 'thisMonth' {
  const lowerQuery = query.toLowerCase();

  if (lowerQuery.includes('今日') || lowerQuery.includes('today')) {
    return 'today';
  }
  if (lowerQuery.includes('今週') || lowerQuery.includes('this week')) {
    return 'thisWeek';
  }
  // ... 他のパターン

  return 'thisWeek'; // デフォルト
}
```

## LangGraph移行後の設計

### ノード定義

```python
def event_node(state: WorkflowState) -> dict:
    """イベント情報ノード"""
    query = state["query"]
    language = state["language"]

    # 期間を抽出
    time_range = extract_time_range(query)

    # カレンダーAPIとナレッジベースから取得
    calendar_events = await calendar_service.search_events(time_range)
    knowledge_events = await rag_search(query, category="events")

    # 結果を統合
    combined_events = merge_event_sources(calendar_events, knowledge_events)

    return {
        "response": format_event_response(combined_events, language),
        "metadata": {"agent": "EventAgent", "time_range": time_range}
    }
```

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| 今日のイベント | 「今日のイベントは？」→ 本日の予定一覧 |
| 今週のイベント | 「今週の勉強会は？」→ 今週の予定一覧 |
| イベントなし | 「明日のイベント」→ 予定なしの丁寧な回答 |
| 特定イベント | 「LT会について」→ 該当イベントの詳細 |

## 感情タグの使い分け

| 状況 | 感情タグ | 理由 |
|-----|---------|------|
| イベントあり（複数） | `[happy]` | 盛り上がっている印象 |
| イベントなし | `[sad]` | 残念な気持ちを表現 |
| 一般的な情報 | `[relaxed]` | 落ち着いた説明 |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] Google Calendar API連携を把握した
- [ ] 期間抽出ロジックを理解した
- [ ] イベントなし時の応答を確認した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Router Agent](../router-agent/README.md) - ルーティング元
- [Calendar Service](../../tools/calendar-service.md) - カレンダーAPI
- [Connpass Integration](../../integrations/connpass.md) - Connpass連携
