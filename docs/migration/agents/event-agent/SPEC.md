# Event Agent - 技術仕様書

> 入出力仕様・API定義・データ構造

## 入力仕様

### メイン入力: `answerEventQuery()`

```typescript
interface EventQueryInput {
  query: string;              // ユーザーからのイベント関連クエリ
  language: SupportedLanguage; // 'ja' | 'en'
}
```

#### 入力例

```typescript
// 今日のイベント
{
  query: "今日のイベントは？",
  language: "ja"
}

// 今週のスケジュール
{
  query: "What events are scheduled this week?",
  language: "en"
}

// 来週のワークショップ
{
  query: "来週の勉強会を教えて",
  language: "ja"
}

// 今月のイベント
{
  query: "今月のイベントはありますか？",
  language: "ja"
}
```

## 出力仕様

### メイン出力: `UnifiedAgentResponse`

```typescript
interface UnifiedAgentResponse {
  text: string;                    // イベント情報を含む応答テキスト
  emotion: string;                 // 'excited' | 'helpful' | 'apologetic'
  agentName: string;              // 'EventAgent' (固定)
  language: SupportedLanguage;    // 'ja' | 'en'
  metadata: {
    confidence: number;           // 信頼度 (通常 0.7-0.8)
    category: string;             // 'events' (固定)
    sources: string[];            // ['calendar', 'knowledge_base']
    processingInfo: {
      enhancedRag: boolean;       // false (現在未使用)
    };
  };
}
```

#### 出力例

```typescript
// イベントが見つかった場合
{
  text: "[happy]今週は以下のイベントがあります：\n\n- TypeScript勉強会\n  時間: 2025年1月15日 19:00 - 21:00\n  参加者30名募集中です。",
  emotion: "excited",
  agentName: "EventAgent",
  language: "ja",
  metadata: {
    confidence: 0.8,
    category: "events",
    sources: ["calendar", "knowledge_base"],
    processingInfo: {
      enhancedRag: false
    }
  }
}

// イベントが見つからない場合
{
  text: "[sad]今週のエンジニアカフェでの予定されたイベントが見つかりませんでした。最新のイベント情報については、公式ウェブサイトをご確認いただくか、スタッフにお問い合わせください。",
  emotion: "apologetic",
  agentName: "EventAgent",
  language: "ja",
  metadata: {
    confidence: 0.7,
    category: "events",
    sources: ["calendar", "knowledge_base"]
  }
}
```

## 時間範囲抽出

### extractTimeRange()

クエリから時間範囲を自動検出します。

```typescript
type TimeRange = 'today' | 'thisWeek' | 'nextWeek' | 'thisMonth';
```

#### 検出パターン

| TimeRange | 日本語キーワード | 英語キーワード |
|-----------|----------------|---------------|
| `today` | 今日, 本日 | today |
| `thisWeek` | 今週 | this week |
| `nextWeek` | 来週 | next week |
| `thisMonth` | 今月 | this month |

#### デフォルト値

明示的な時間指定がない場合は `thisWeek` を使用。

#### 実装例

```typescript
private extractTimeRange(query: string): TimeRange {
  const lowerQuery = query.toLowerCase();

  if (lowerQuery.includes('今日') || lowerQuery.includes('today') || lowerQuery.includes('本日')) {
    return 'today';
  }
  if (lowerQuery.includes('今週') || lowerQuery.includes('this week')) {
    return 'thisWeek';
  }
  if (lowerQuery.includes('来週') || lowerQuery.includes('next week')) {
    return 'nextWeek';
  }
  if (lowerQuery.includes('今月') || lowerQuery.includes('this month')) {
    return 'thisMonth';
  }

  // Default to this week
  return 'thisWeek';
}
```

## データソース統合

### 1. カレンダーサービス (calendarService)

```typescript
interface CalendarToolInput {
  action: 'searchEvents';
  timeRange: TimeRange;
  query: string;
}

interface CalendarToolResult {
  success: boolean;
  data: {
    events: CalendarEvent[];
  } | null;
}

interface CalendarEvent {
  title: string;
  start: string;        // ISO 8601 timestamp
  end?: string;         // ISO 8601 timestamp (オプション)
  description?: string; // イベント説明 (オプション)
}
```

### 2. RAG検索 (ragSearch)

```typescript
interface RAGSearchInput {
  query: string;
  language: SupportedLanguage;
  limit: number;        // デフォルト: 10
}

interface RAGSearchResult {
  success: boolean;
  results?: Array<{
    content: string;
  }>;
  data?: {
    context: string;
  };
}
```

### マルチソース統合ロジック

```typescript
// カレンダーイベントとRAG結果を組み合わせる
const hasCalendarEvents = calendarResult.success && calendarResult.data?.events?.length > 0;
const hasKnowledgeEvents = knowledgeResult.success && knowledgeContext;

if (!hasCalendarEvents && !hasKnowledgeEvents) {
  return this.getNoEventsResponse(timeRange, language);
}

// ソース情報を記録
const sources = [];
if (hasCalendarEvents) sources.push('calendar');
if (hasKnowledgeEvents) sources.push('knowledge_base');
```

## イベント情報フォーマット

### formatCalendarEvents()

```typescript
private formatCalendarEvents(events: CalendarEvent[], language: SupportedLanguage): string {
  if (!events || events.length === 0) {
    return '';
  }

  return events.map(event => {
    const startTime = new Date(event.start).toLocaleString(
      language === 'ja' ? 'ja-JP' : 'en-US'
    );
    const endTime = event.end
      ? new Date(event.end).toLocaleString(language === 'ja' ? 'ja-JP' : 'en-US')
      : '';

    return language === 'en'
      ? `- ${event.title}\n  Time: ${startTime}${endTime ? ` - ${endTime}` : ''}\n  ${event.description || 'No description'}`
      : `- ${event.title}\n  時間: ${startTime}${endTime ? ` - ${endTime}` : ''}\n  ${event.description || '説明なし'}`;
  }).join('\n\n');
}
```

#### フォーマット例

```
- TypeScript勉強会
  時間: 2025/01/15 19:00:00 - 2025/01/15 21:00:00
  TypeScriptの基礎から応用まで学びます

- Reactハンズオン
  時間: 2025/01/17 18:30:00 - 2025/01/17 20:30:00
  説明なし
```

## エモーションマッピング

### emotion値の選択ロジック

| 条件 | emotion | エモーションタグ |
|------|---------|----------------|
| カレンダーイベント > 0 | excited | [happy] |
| イベント0件 | apologetic | [sad] |
| 通常ケース | helpful | [relaxed] |

### エモーションタグ仕様

応答テキストの先頭に必ず含める：

- `[happy]`: イベントが複数見つかった場合
- `[sad]`: イベントが見つからない場合
- `[relaxed]`: 一般的な情報提供時
- `[surprised]`: 特別なアナウンス時

```typescript
// Determine emotion based on events found
let emotion = 'helpful';
if (hasCalendarEvents && calendarResult.data?.events?.length > 0) {
  emotion = 'excited';
} else if (!hasCalendarEvents && !hasKnowledgeEvents) {
  emotion = 'apologetic';
}
```

## プロンプト構築

### buildEventPrompt()

```typescript
private buildEventPrompt(
  query: string,
  calendarEvents: CalendarEvent[],
  knowledgeContext: string,
  timeRange: TimeRange,
  language: SupportedLanguage
): string
```

#### 日本語プロンプトテンプレート

```
以下のデータに基づいて、エンジニアカフェのイベントについて情報を提供してください。

質問: ${query}
期間: ${this.translateTimeRange(timeRange)}

カレンダーイベント:
${calendarInfo || 'カレンダーにイベントが見つかりません'}

追加のイベント情報:
${knowledgeContext || '追加情報はありません'}

日付、時間、イベントの説明を明確にフォーマットして応答してください。複数のイベントがある場合は、時系列順に一覧表示してください。
```

#### 英語プロンプトテンプレート

```
Provide information about events at Engineer Cafe based on the following data.

Question: ${query}
Time Range: ${timeRange}

Calendar Events:
${calendarInfo || 'No events found in calendar'}

Additional Event Information:
${knowledgeContext || 'No additional information available'}

Format the response with clear dates, times, and event descriptions. If there are multiple events, list them chronologically.
```

## イベント不在時の応答

### getNoEventsResponse()

```typescript
private getNoEventsResponse(timeRange: TimeRange, language: SupportedLanguage): UnifiedAgentResponse {
  const timeRangeText = language === 'ja'
    ? this.translateTimeRange(timeRange)
    : timeRange;

  const text = language === 'en'
    ? `[sad]I couldn't find any scheduled events for ${timeRange} at Engineer Cafe. Please check the official website or contact the staff for the most up-to-date event information.`
    : `[sad]${timeRangeText}のエンジニアカフェでの予定されたイベントが見つかりませんでした。最新のイベント情報については、公式ウェブサイトをご確認いただくか、スタッフにお問い合わせください。`;

  return createUnifiedResponse(
    text,
    'apologetic',
    'EventAgent',
    language,
    {
      confidence: 0.7,
      category: 'events',
      sources: ['calendar', 'knowledge_base']
    }
  );
}
```

## 時間範囲翻訳

### translateTimeRange()

```typescript
private translateTimeRange(timeRange: string): string {
  const translations: Record<string, string> = {
    'today': '今日',
    'thisWeek': '今週',
    'nextWeek': '来週',
    'thisMonth': '今月'
  };

  return translations[timeRange] || timeRange;
}
```

## エラーハンドリング

### ツールエラー処理

```typescript
// Calendar tool error handling
let calendarResult: any = { success: false, data: null };
if (calendarTool) {
  try {
    calendarResult = await calendarTool.execute({
      action: 'searchEvents',
      timeRange,
      query
    });
  } catch (error) {
    console.error('[EventAgent] Calendar tool error:', error);
    // Continue with RAG search even if calendar fails
  }
}

// RAG tool error handling
let knowledgeResult: any = { success: false, data: null };
if (ragTool) {
  try {
    knowledgeResult = await ragTool.execute({
      query,
      language,
      limit: 10
    });
  } catch (error) {
    console.error('[EventAgent] RAG search error:', error);
    // Continue even if RAG search fails
  }
}
```

### フォールバック戦略

| エラーケース | 対応 |
|------------|------|
| カレンダー取得失敗 | RAG検索結果のみ使用 |
| RAG検索失敗 | カレンダー結果のみ使用 |
| 両方失敗 | getNoEventsResponse()を返す |

## LangGraph版の仕様

### Python型定義

```python
from typing import TypedDict, Literal

TimeRange = Literal["today", "thisWeek", "nextWeek", "thisMonth"]
SupportedLanguage = Literal["ja", "en"]

class CalendarEvent(TypedDict):
    title: str
    start: str
    end: str | None
    description: str | None

class EventQueryInput(TypedDict):
    query: str
    language: SupportedLanguage

class UnifiedAgentResponse(TypedDict):
    text: str
    emotion: str
    agent_name: str
    language: SupportedLanguage
    metadata: dict
```

### ノード関数シグネチャ

```python
async def event_agent_node(state: WorkflowState) -> dict:
    """
    イベントエージェントノード: イベント情報の取得と応答生成

    Args:
        state: ワークフロー状態（query, language, session_id等を含む）

    Returns:
        dict: response, emotion, sources を含む辞書
    """
    pass
```

## パフォーマンス指標

### 目標値

| 指標 | 目標 |
|-----|------|
| 平均応答時間 | 1.5秒以下 |
| カレンダー取得成功率 | 95%以上 |
| RAG検索成功率 | 98%以上 |
| マルチソース統合成功率 | 90%以上 |
| イベント情報精度 | 100% |

### 処理時間内訳

```
Total: ~1.5s
├─ カレンダーAPI: 500-800ms
├─ RAG検索: 300-500ms
├─ LLM生成: 400-600ms
└─ その他: 50-100ms
```

## バージョン履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| 1.0 | 2024-01 | 初期実装（Mastra） |
| 1.1 | 2024-07 | マルチソース統合追加 |
| 1.2 | 2024-12 | エモーションタグ強化 |
| 2.0 | 予定 | LangGraph移行 |
