# Event Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
frontend/src/mastra/agents/
└── event-agent.ts                   # 250行
```

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   └── event_agent.py              # 新規作成
├── tools/
│   ├── calendar_service.py         # 既存（修正）
│   └── rag_search.py               # 既存（利用）
└── workflows/
    └── main_workflow.py            # 既存（修正）
```

## 移行ステップ

### Step 1: Event Agent 本体の移行

**元ファイル**: `frontend/src/mastra/agents/event-agent.ts`

```python
# backend/agents/event_agent.py

from typing import TypedDict, Literal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

TimeRange = Literal["today", "thisWeek", "nextWeek", "thisMonth"]
SupportedLanguage = Literal["ja", "en"]

class CalendarEvent(TypedDict):
    title: str
    start: str
    end: str | None
    description: str | None

class UnifiedAgentResponse(TypedDict):
    text: str
    emotion: str
    agent_name: str
    language: SupportedLanguage
    metadata: dict

class EventAgent:
    def __init__(self, llm_client, tools: dict):
        """
        イベントエージェントの初期化

        Args:
            llm_client: LLMクライアント（Gemini等）
            tools: ツール辞書 {'calendarService': ..., 'ragSearch': ...}
        """
        self.llm = llm_client
        self.tools = tools
        self.name = "EventAgent"

    async def answer_event_query(
        self,
        query: str,
        language: SupportedLanguage
    ) -> UnifiedAgentResponse:
        """
        イベントクエリへの応答生成

        Args:
            query: ユーザーからのイベント関連クエリ
            language: 応答言語 ('ja' | 'en')

        Returns:
            UnifiedAgentResponse: エージェント応答
        """
        logger.info(f"[EventAgent] Processing event query: {query}")

        # 時間範囲抽出
        time_range = self._extract_time_range(query)

        # カレンダーイベント取得
        calendar_result = await self._get_calendar_events(time_range, query)

        # RAG検索でイベント情報を取得
        knowledge_result = await self._search_event_knowledge(query, language)

        # 結果を統合
        has_calendar_events = (
            calendar_result.get("success", False) and
            calendar_result.get("data", {}).get("events", [])
        )
        has_knowledge_events = knowledge_result.get("success", False)

        if not has_calendar_events and not has_knowledge_events:
            return self._get_no_events_response(time_range, language)

        # プロンプト構築
        prompt = self._build_event_prompt(
            query=query,
            calendar_events=calendar_result.get("data", {}).get("events", []),
            knowledge_context=self._extract_knowledge_context(knowledge_result),
            time_range=time_range,
            language=language
        )

        # LLM生成
        response_text = await self.llm.generate(prompt)

        # ソース情報を記録
        sources = []
        if has_calendar_events:
            sources.append("calendar")
        if has_knowledge_events:
            sources.append("knowledge_base")

        # エモーション決定
        emotion = self._determine_emotion(has_calendar_events, has_knowledge_events)

        return self._create_unified_response(
            text=response_text,
            emotion=emotion,
            language=language,
            sources=sources
        )

    def _extract_time_range(self, query: str) -> TimeRange:
        """
        クエリから時間範囲を抽出

        Args:
            query: ユーザークエリ

        Returns:
            TimeRange: 'today' | 'thisWeek' | 'nextWeek' | 'thisMonth'
        """
        lower_query = query.lower()

        # 今日
        if any(kw in lower_query for kw in ['今日', 'today', '本日']):
            return 'today'

        # 今週
        if any(kw in lower_query for kw in ['今週', 'this week']):
            return 'thisWeek'

        # 来週
        if any(kw in lower_query for kw in ['来週', 'next week']):
            return 'nextWeek'

        # 今月
        if any(kw in lower_query for kw in ['今月', 'this month']):
            return 'thisMonth'

        # デフォルト: 今週
        return 'thisWeek'

    async def _get_calendar_events(
        self,
        time_range: TimeRange,
        query: str
    ) -> dict:
        """
        カレンダーからイベントを取得

        Args:
            time_range: 時間範囲
            query: 元のクエリ

        Returns:
            dict: {'success': bool, 'data': {'events': [...]}}
        """
        calendar_tool = self.tools.get("calendarService")
        if not calendar_tool:
            logger.warning("[EventAgent] Calendar tool not available")
            return {"success": False, "data": None}

        try:
            result = await calendar_tool.execute({
                "action": "searchEvents",
                "timeRange": time_range,
                "query": query
            })
            return result
        except Exception as e:
            logger.error(f"[EventAgent] Calendar tool error: {e}")
            return {"success": False, "data": None}

    async def _search_event_knowledge(
        self,
        query: str,
        language: SupportedLanguage
    ) -> dict:
        """
        RAG検索でイベント関連知識を取得

        Args:
            query: 検索クエリ
            language: 言語

        Returns:
            dict: RAG検索結果
        """
        rag_tool = self.tools.get("ragSearch")
        if not rag_tool:
            logger.warning("[EventAgent] RAG search tool not available")
            return {"success": False, "data": None}

        try:
            result = await rag_tool.execute({
                "query": query,
                "language": language,
                "limit": 10
            })
            return result
        except Exception as e:
            logger.error(f"[EventAgent] RAG search error: {e}")
            return {"success": False, "data": None}

    def _extract_knowledge_context(self, knowledge_result: dict) -> str:
        """
        RAG検索結果からコンテキストを抽出

        Args:
            knowledge_result: RAG検索結果

        Returns:
            str: コンテキスト文字列
        """
        if not knowledge_result.get("success"):
            return ""

        # results形式
        if "results" in knowledge_result and isinstance(knowledge_result["results"], list):
            return "\n\n".join(r.get("content", "") for r in knowledge_result["results"])

        # data.context形式
        if "data" in knowledge_result and "context" in knowledge_result["data"]:
            return knowledge_result["data"]["context"]

        return ""

    def _build_event_prompt(
        self,
        query: str,
        calendar_events: list[CalendarEvent],
        knowledge_context: str,
        time_range: TimeRange,
        language: SupportedLanguage
    ) -> str:
        """
        イベント情報応答のプロンプトを構築

        Args:
            query: ユーザークエリ
            calendar_events: カレンダーイベントリスト
            knowledge_context: RAG検索結果のコンテキスト
            time_range: 時間範囲
            language: 応答言語

        Returns:
            str: LLM用プロンプト
        """
        calendar_info = self._format_calendar_events(calendar_events, language)

        if language == "en":
            return f"""Provide information about events at Engineer Cafe based on the following data.

Question: {query}
Time Range: {time_range}

Calendar Events:
{calendar_info or 'No events found in calendar'}

Additional Event Information:
{knowledge_context or 'No additional information available'}

Format the response with clear dates, times, and event descriptions. If there are multiple events, list them chronologically."""

        else:  # ja
            time_range_ja = self._translate_time_range(time_range)
            return f"""以下のデータに基づいて、エンジニアカフェのイベントについて情報を提供してください。

質問: {query}
期間: {time_range_ja}

カレンダーイベント:
{calendar_info or 'カレンダーにイベントが見つかりません'}

追加のイベント情報:
{knowledge_context or '追加情報はありません'}

日付、時間、イベントの説明を明確にフォーマットして応答してください。複数のイベントがある場合は、時系列順に一覧表示してください。"""

    def _format_calendar_events(
        self,
        events: list[CalendarEvent],
        language: SupportedLanguage
    ) -> str:
        """
        カレンダーイベントをフォーマット

        Args:
            events: イベントリスト
            language: 言語

        Returns:
            str: フォーマット済みイベント情報
        """
        if not events:
            return ""

        formatted_events = []
        locale = "ja_JP" if language == "ja" else "en_US"

        for event in events:
            try:
                start_time = datetime.fromisoformat(event["start"]).strftime("%Y/%m/%d %H:%M:%S")
                end_time = ""
                if event.get("end"):
                    end_time = datetime.fromisoformat(event["end"]).strftime("%Y/%m/%d %H:%M:%S")

                if language == "en":
                    formatted = f"- {event['title']}\n  Time: {start_time}"
                    if end_time:
                        formatted += f" - {end_time}"
                    formatted += f"\n  {event.get('description', 'No description')}"
                else:
                    formatted = f"- {event['title']}\n  時間: {start_time}"
                    if end_time:
                        formatted += f" - {end_time}"
                    formatted += f"\n  {event.get('description', '説明なし')}"

                formatted_events.append(formatted)
            except Exception as e:
                logger.error(f"[EventAgent] Error formatting event: {e}")
                continue

        return "\n\n".join(formatted_events)

    def _translate_time_range(self, time_range: TimeRange) -> str:
        """
        時間範囲を日本語に翻訳

        Args:
            time_range: 時間範囲

        Returns:
            str: 日本語訳
        """
        translations = {
            "today": "今日",
            "thisWeek": "今週",
            "nextWeek": "来週",
            "thisMonth": "今月"
        }
        return translations.get(time_range, time_range)

    def _determine_emotion(
        self,
        has_calendar_events: bool,
        has_knowledge_events: bool
    ) -> str:
        """
        エモーションを決定

        Args:
            has_calendar_events: カレンダーイベントの有無
            has_knowledge_events: 知識ベースイベントの有無

        Returns:
            str: emotion値
        """
        if has_calendar_events:
            return "excited"
        elif not has_calendar_events and not has_knowledge_events:
            return "apologetic"
        else:
            return "helpful"

    def _get_no_events_response(
        self,
        time_range: TimeRange,
        language: SupportedLanguage
    ) -> UnifiedAgentResponse:
        """
        イベント不在時の応答を生成

        Args:
            time_range: 時間範囲
            language: 言語

        Returns:
            UnifiedAgentResponse: イベント不在応答
        """
        time_range_text = (
            self._translate_time_range(time_range) if language == "ja"
            else time_range
        )

        if language == "en":
            text = f"[sad]I couldn't find any scheduled events for {time_range} at Engineer Cafe. Please check the official website or contact the staff for the most up-to-date event information."
        else:
            text = f"[sad]{time_range_text}のエンジニアカフェでの予定されたイベントが見つかりませんでした。最新のイベント情報については、公式ウェブサイトをご確認いただくか、スタッフにお問い合わせください。"

        return self._create_unified_response(
            text=text,
            emotion="apologetic",
            language=language,
            sources=["calendar", "knowledge_base"],
            confidence=0.7
        )

    def _create_unified_response(
        self,
        text: str,
        emotion: str,
        language: SupportedLanguage,
        sources: list[str],
        confidence: float = 0.8
    ) -> UnifiedAgentResponse:
        """
        統一応答オブジェクトを生成

        Args:
            text: 応答テキスト
            emotion: エモーション
            language: 言語
            sources: データソースリスト
            confidence: 信頼度

        Returns:
            UnifiedAgentResponse: 統一応答
        """
        return {
            "text": text,
            "emotion": emotion,
            "agent_name": self.name,
            "language": language,
            "metadata": {
                "confidence": confidence,
                "category": "events",
                "sources": sources,
                "processing_info": {
                    "enhanced_rag": False
                }
            }
        }
```

### Step 2: ワークフローへの統合

**修正ファイル**: `backend/workflows/main_workflow.py`

```python
# backend/workflows/main_workflow.py

from backend.agents.event_agent import EventAgent

class MainWorkflow:
    def __init__(self):
        # エージェント初期化
        self.event_agent = EventAgent(
            llm_client=self.llm,
            tools={
                "calendarService": self.calendar_tool,
                "ragSearch": self.rag_tool
            }
        )
        self.graph = self._build_graph()

    async def _event_agent_node(self, state: WorkflowState) -> dict:
        """
        イベントエージェントノード

        Args:
            state: ワークフロー状態

        Returns:
            dict: 更新状態
        """
        query = state.get("query", "")
        language = state.get("language", "ja")

        # EventAgentを使用
        response = await self.event_agent.answer_event_query(query, language)

        return {
            "response": response["text"],
            "emotion": response["emotion"],
            "metadata": {
                **state.get("metadata", {}),
                "agent": "EventAgent",
                "sources": response["metadata"]["sources"],
                "confidence": response["metadata"]["confidence"]
            }
        }

    def _build_graph(self):
        """ワークフローグラフの構築"""
        from langgraph.graph import StateGraph

        graph = StateGraph(WorkflowState)

        # ノード追加
        graph.add_node("router", self._router_node)
        graph.add_node("event", self._event_agent_node)  # イベントノード追加
        # ... 他のノード

        # エッジ追加
        graph.add_conditional_edges(
            "router",
            self._route_decision,
            {
                "event": "event",  # EventAgentへのルーティング
                # ... 他のルーティング
            }
        )

        return graph.compile()
```

### Step 3: ツールインターフェースの調整

#### Calendar Service Tool

```python
# backend/tools/calendar_service.py

from typing import TypedDict, Literal
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

TimeRange = Literal["today", "thisWeek", "nextWeek", "thisMonth"]

class CalendarServiceTool:
    def __init__(self, google_calendar_client):
        self.calendar_client = google_calendar_client

    async def execute(self, params: dict) -> dict:
        """
        カレンダーツール実行

        Args:
            params: {
                'action': 'searchEvents',
                'timeRange': TimeRange,
                'query': str
            }

        Returns:
            dict: {'success': bool, 'data': {'events': [...]}}
        """
        action = params.get("action")
        if action != "searchEvents":
            return {"success": False, "error": "Unknown action"}

        time_range = params.get("timeRange", "thisWeek")
        query = params.get("query", "")

        try:
            # 時間範囲を日付範囲に変換
            start_date, end_date = self._get_date_range(time_range)

            # Google Calendar APIで検索
            events = await self.calendar_client.search_events(
                start_date=start_date,
                end_date=end_date,
                query=query
            )

            return {
                "success": True,
                "data": {
                    "events": events
                }
            }
        except Exception as e:
            logger.error(f"[CalendarServiceTool] Error: {e}")
            return {"success": False, "error": str(e)}

    def _get_date_range(self, time_range: TimeRange) -> tuple[datetime, datetime]:
        """
        時間範囲を日付範囲に変換

        Args:
            time_range: 時間範囲

        Returns:
            tuple: (start_date, end_date)
        """
        now = datetime.now()

        if time_range == "today":
            start = now.replace(hour=0, minute=0, second=0)
            end = now.replace(hour=23, minute=59, second=59)
        elif time_range == "thisWeek":
            start = now - timedelta(days=now.weekday())
            end = start + timedelta(days=6)
        elif time_range == "nextWeek":
            start = now + timedelta(days=(7 - now.weekday()))
            end = start + timedelta(days=6)
        elif time_range == "thisMonth":
            start = now.replace(day=1, hour=0, minute=0, second=0)
            next_month = start.replace(month=start.month + 1) if start.month < 12 else start.replace(year=start.year + 1, month=1)
            end = next_month - timedelta(seconds=1)
        else:
            start = now
            end = now + timedelta(days=7)

        return start, end
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] Python依存パッケージを確認した（langchain, google-calendar等）
- [ ] テスト環境を準備した

### Phase 2: EventAgent本体

- [ ] `event_agent.py` を作成した
- [ ] `answer_event_query()` メソッドを実装した
- [ ] `_extract_time_range()` を実装した
- [ ] `_format_calendar_events()` を実装した
- [ ] 単体テストを作成・通過した

### Phase 3: ツール統合

- [ ] `calendar_service.py` を修正/作成した
- [ ] `rag_search.py` との統合を確認した
- [ ] ツールエラーハンドリングを実装した

### Phase 4: ワークフロー統合

- [ ] `main_workflow.py` にEventAgentノードを追加した
- [ ] ルーティング条件を設定した
- [ ] エンドツーエンドテストを通過した

### Phase 5: 検証

- [ ] 全時間範囲パターンをテストした（today, thisWeek, nextWeek, thisMonth）
- [ ] マルチソース統合を検証した（calendar + RAG）
- [ ] エモーション生成を確認した
- [ ] 日英両言語での動作確認を完了した

## データ型変換ガイド

### TypeScript → Python

| TypeScript | Python | 備考 |
|-----------|--------|------|
| `string` | `str` | |
| `number` | `int` / `float` | |
| `boolean` | `bool` | |
| `any` | `Any` | typing.Anyをimport |
| `Array<T>` | `list[T]` | Python 3.9+ |
| `Record<K, V>` | `dict[K, V]` | |
| `T \| null` | `T \| None` | |
| `interface` | `TypedDict` | typing.TypedDict |
| `type` | `TypeAlias` | typing.TypeAlias |

### 非同期処理

```typescript
// TypeScript
async answerEventQuery(query: string): Promise<Response> {
  const result = await this.tool.execute(params);
  return result;
}
```

```python
# Python
async def answer_event_query(self, query: str) -> dict:
    result = await self.tool.execute(params)
    return result
```

### 日付処理

```typescript
// TypeScript
const startTime = new Date(event.start).toLocaleString('ja-JP');
```

```python
# Python
from datetime import datetime
start_time = datetime.fromisoformat(event["start"]).strftime("%Y/%m/%d %H:%M:%S")
```

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| タイムゾーンのずれ | 日付処理でUTC/JSTの混在 | datetimeにtzinfo設定 |
| カレンダーAPI認証エラー | Google Calendar認証設定不足 | OAuth2設定確認 |
| イベント0件で例外発生 | Noneチェック不足 | `events or []` でデフォルト設定 |
| 日本語フォーマット崩れ | ロケール設定ミス | strftimeで明示的にフォーマット指定 |

### デバッグ方法

```python
# ログレベル設定
import logging
logging.basicConfig(level=logging.DEBUG)

# デバッグログ追加
logger.debug(f"[EventAgent] Calendar result: {calendar_result}")
logger.debug(f"[EventAgent] Knowledge context: {knowledge_context}")
logger.debug(f"[EventAgent] Time range: {time_range}")
```

## パフォーマンス最適化

### 並列処理

```python
# カレンダーとRAG検索を並列実行
import asyncio

calendar_task = self._get_calendar_events(time_range, query)
knowledge_task = self._search_event_knowledge(query, language)

calendar_result, knowledge_result = await asyncio.gather(
    calendar_task,
    knowledge_task,
    return_exceptions=True
)
```

### キャッシング

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def _translate_time_range(self, time_range: TimeRange) -> str:
    """時間範囲翻訳（キャッシュ付き）"""
    translations = {
        "today": "今日",
        "thisWeek": "今週",
        "nextWeek": "来週",
        "thisMonth": "今月"
    }
    return translations.get(time_range, time_range)
```

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Google Calendar API](https://developers.google.com/calendar)
- [元実装: event-agent.ts](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/mastra/agents/event-agent.ts)
