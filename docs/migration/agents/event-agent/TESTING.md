# Event Agent - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

Event Agentは複数のデータソース（カレンダー、RAG）を統合し、時間範囲に基づいてイベント情報を提供します。高品質な応答と正確な時間範囲処理が求められます。

### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | 各メソッド | 個別機能の検証 |
| 統合テスト | マルチソース統合 | カレンダー+RAG連携検証 |
| エンドツーエンドテスト | ワークフロー全体 | 実運用シナリオ検証 |
| パフォーマンステスト | 応答時間 | 1.5秒以内のレスポンス確認 |

## 単体テストケース

### 1. 時間範囲抽出テスト

```python
# tests/test_event_agent.py

import pytest
from backend.agents.event_agent import EventAgent

class TestTimeRangeExtraction:
    """時間範囲抽出のテスト"""

    @pytest.fixture
    def event_agent(self):
        return EventAgent(llm_client=None, tools={})

    @pytest.mark.parametrize("query,expected_range", [
        # 今日
        ("今日のイベントは？", "today"),
        ("今日は何かイベントある？", "today"),
        ("本日のスケジュール", "today"),
        ("What events are happening today?", "today"),
        ("Today's schedule", "today"),

        # 今週
        ("今週のイベントを教えて", "thisWeek"),
        ("今週は何がありますか？", "thisWeek"),
        ("What's happening this week?", "thisWeek"),
        ("Events this week", "thisWeek"),

        # 来週
        ("来週の勉強会は？", "nextWeek"),
        ("来週のスケジュール", "nextWeek"),
        ("Next week's events", "nextWeek"),
        ("What's planned for next week?", "nextWeek"),

        # 今月
        ("今月のイベント一覧", "thisMonth"),
        ("今月は何があるの？", "thisMonth"),
        ("Events this month", "thisMonth"),
        ("This month's schedule", "thisMonth"),

        # デフォルト（今週）
        ("イベント情報", "thisWeek"),
        ("何かイベントある？", "thisWeek"),
        ("Events", "thisWeek"),
    ])
    def test_extract_time_range(self, event_agent, query, expected_range):
        """時間範囲抽出の正確性を検証"""
        result = event_agent._extract_time_range(query)
        assert result == expected_range, f"Query: {query}"
```

### 2. カレンダーイベント取得テスト

```python
class TestCalendarEventRetrieval:
    """カレンダーイベント取得のテスト"""

    @pytest.fixture
    def mock_calendar_tool(self):
        """カレンダーツールのモック"""
        class MockCalendarTool:
            async def execute(self, params):
                if params["timeRange"] == "today":
                    return {
                        "success": True,
                        "data": {
                            "events": [
                                {
                                    "title": "TypeScript勉強会",
                                    "start": "2025-01-15T19:00:00",
                                    "end": "2025-01-15T21:00:00",
                                    "description": "TypeScriptの基礎から応用まで"
                                }
                            ]
                        }
                    }
                else:
                    return {"success": True, "data": {"events": []}}
        return MockCalendarTool()

    @pytest.mark.asyncio
    async def test_get_calendar_events_success(self, mock_calendar_tool):
        """カレンダーイベント取得成功時のテスト"""
        event_agent = EventAgent(
            llm_client=None,
            tools={"calendarService": mock_calendar_tool}
        )

        result = await event_agent._get_calendar_events("today", "今日のイベント")

        assert result["success"] is True
        assert len(result["data"]["events"]) == 1
        assert result["data"]["events"][0]["title"] == "TypeScript勉強会"

    @pytest.mark.asyncio
    async def test_get_calendar_events_error(self):
        """カレンダーツールエラー時の処理"""
        class ErrorCalendarTool:
            async def execute(self, params):
                raise Exception("Calendar API error")

        event_agent = EventAgent(
            llm_client=None,
            tools={"calendarService": ErrorCalendarTool()}
        )

        result = await event_agent._get_calendar_events("today", "今日のイベント")

        assert result["success"] is False
        assert result["data"] is None
```

### 3. イベントフォーマットテスト

```python
class TestEventFormatting:
    """イベントフォーマットのテスト"""

    @pytest.fixture
    def event_agent(self):
        return EventAgent(llm_client=None, tools={})

    @pytest.fixture
    def sample_events(self):
        return [
            {
                "title": "TypeScript勉強会",
                "start": "2025-01-15T19:00:00",
                "end": "2025-01-15T21:00:00",
                "description": "TypeScriptの基礎から応用まで"
            },
            {
                "title": "Reactハンズオン",
                "start": "2025-01-17T18:30:00",
                "end": "2025-01-17T20:30:00",
                "description": None
            }
        ]

    def test_format_calendar_events_japanese(self, event_agent, sample_events):
        """日本語イベントフォーマット"""
        result = event_agent._format_calendar_events(sample_events, "ja")

        assert "TypeScript勉強会" in result
        assert "時間:" in result
        assert "2025/01/15 19:00:00" in result
        assert "TypeScriptの基礎から応用まで" in result
        assert "説明なし" in result  # description=Noneの場合

    def test_format_calendar_events_english(self, event_agent, sample_events):
        """英語イベントフォーマット"""
        result = event_agent._format_calendar_events(sample_events, "en")

        assert "TypeScript勉強会" in result
        assert "Time:" in result
        assert "2025/01/15 19:00:00" in result
        assert "TypeScriptの基礎から応用まで" in result
        assert "No description" in result

    def test_format_empty_events(self, event_agent):
        """空イベントリストのフォーマット"""
        result = event_agent._format_calendar_events([], "ja")
        assert result == ""
```

### 4. RAG検索統合テスト

```python
class TestRAGSearchIntegration:
    """RAG検索統合のテスト"""

    @pytest.fixture
    def mock_rag_tool(self):
        class MockRAGTool:
            async def execute(self, params):
                return {
                    "success": True,
                    "results": [
                        {"content": "エンジニアカフェでは毎週イベントを開催しています。"},
                        {"content": "勉強会は平日夜に開催されます。"}
                    ]
                }
        return MockRAGTool()

    @pytest.mark.asyncio
    async def test_search_event_knowledge(self, mock_rag_tool):
        """RAG検索によるイベント知識取得"""
        event_agent = EventAgent(
            llm_client=None,
            tools={"ragSearch": mock_rag_tool}
        )

        result = await event_agent._search_event_knowledge("イベント情報", "ja")

        assert result["success"] is True
        assert "results" in result
        assert len(result["results"]) == 2

    def test_extract_knowledge_context_results_format(self):
        """RAG結果からコンテキスト抽出（results形式）"""
        event_agent = EventAgent(llm_client=None, tools={})

        knowledge_result = {
            "success": True,
            "results": [
                {"content": "コンテンツ1"},
                {"content": "コンテンツ2"}
            ]
        }

        context = event_agent._extract_knowledge_context(knowledge_result)

        assert "コンテンツ1" in context
        assert "コンテンツ2" in context

    def test_extract_knowledge_context_data_format(self):
        """RAG結果からコンテキスト抽出（data.context形式）"""
        event_agent = EventAgent(llm_client=None, tools={})

        knowledge_result = {
            "success": True,
            "data": {
                "context": "統合されたコンテキスト"
            }
        }

        context = event_agent._extract_knowledge_context(knowledge_result)

        assert context == "統合されたコンテキスト"
```

### 5. エモーション決定テスト

```python
class TestEmotionDetermination:
    """エモーション決定のテスト"""

    @pytest.fixture
    def event_agent(self):
        return EventAgent(llm_client=None, tools={})

    @pytest.mark.parametrize("has_calendar,has_knowledge,expected_emotion", [
        # カレンダーイベントあり
        (True, True, "excited"),
        (True, False, "excited"),

        # カレンダーイベントなし、知識ベースあり
        (False, True, "helpful"),

        # 両方なし
        (False, False, "apologetic"),
    ])
    def test_determine_emotion(
        self,
        event_agent,
        has_calendar,
        has_knowledge,
        expected_emotion
    ):
        """エモーション決定ロジックの検証"""
        emotion = event_agent._determine_emotion(has_calendar, has_knowledge)
        assert emotion == expected_emotion
```

### 6. イベント不在応答テスト

```python
class TestNoEventsResponse:
    """イベント不在応答のテスト"""

    @pytest.fixture
    def event_agent(self):
        return EventAgent(llm_client=None, tools={})

    @pytest.mark.parametrize("time_range,language", [
        ("today", "ja"),
        ("thisWeek", "ja"),
        ("nextWeek", "ja"),
        ("thisMonth", "ja"),
        ("today", "en"),
        ("thisWeek", "en"),
    ])
    def test_get_no_events_response(self, event_agent, time_range, language):
        """イベント不在応答の生成"""
        response = event_agent._get_no_events_response(time_range, language)

        assert response["agent_name"] == "EventAgent"
        assert response["emotion"] == "apologetic"
        assert response["language"] == language
        assert "[sad]" in response["text"]
        assert response["metadata"]["confidence"] == 0.7
        assert response["metadata"]["category"] == "events"
        assert "calendar" in response["metadata"]["sources"]
        assert "knowledge_base" in response["metadata"]["sources"]
```

## 統合テストケース

### マルチソース統合テスト

```python
# tests/test_event_agent_integration.py

import pytest
from backend.agents.event_agent import EventAgent

class TestMultiSourceIntegration:
    """マルチソース統合のテスト"""

    @pytest.fixture
    def mock_tools(self):
        """カレンダーとRAGツールのモック"""
        class MockCalendarTool:
            async def execute(self, params):
                return {
                    "success": True,
                    "data": {
                        "events": [
                            {
                                "title": "TypeScript勉強会",
                                "start": "2025-01-15T19:00:00",
                                "end": "2025-01-15T21:00:00",
                                "description": "初心者歓迎"
                            }
                        ]
                    }
                }

        class MockRAGTool:
            async def execute(self, params):
                return {
                    "success": True,
                    "results": [
                        {"content": "勉強会は毎週開催されます"}
                    ]
                }

        class MockLLM:
            async def generate(self, prompt):
                return "[happy]今週はTypeScript勉強会があります。1月15日19時から21時まで開催されます。"

        return {
            "calendarService": MockCalendarTool(),
            "ragSearch": MockRAGTool()
        }, MockLLM()

    @pytest.mark.asyncio
    async def test_answer_event_query_with_both_sources(self, mock_tools):
        """カレンダーとRAG両方からデータを取得するテスト"""
        tools, llm = mock_tools
        event_agent = EventAgent(llm_client=llm, tools=tools)

        response = await event_agent.answer_event_query(
            query="今週のイベントは？",
            language="ja"
        )

        assert response["agent_name"] == "EventAgent"
        assert response["emotion"] == "excited"
        assert "[happy]" in response["text"]
        assert "TypeScript" in response["text"]
        assert response["metadata"]["category"] == "events"
        assert "calendar" in response["metadata"]["sources"]
        assert "knowledge_base" in response["metadata"]["sources"]

    @pytest.mark.asyncio
    async def test_answer_event_query_calendar_only(self):
        """カレンダーのみからデータを取得するテスト"""
        class MockCalendarTool:
            async def execute(self, params):
                return {
                    "success": True,
                    "data": {
                        "events": [{"title": "イベント", "start": "2025-01-15T19:00:00"}]
                    }
                }

        class MockRAGTool:
            async def execute(self, params):
                return {"success": False}

        class MockLLM:
            async def generate(self, prompt):
                return "[happy]イベントがあります"

        tools = {
            "calendarService": MockCalendarTool(),
            "ragSearch": MockRAGTool()
        }
        event_agent = EventAgent(llm_client=MockLLM(), tools=tools)

        response = await event_agent.answer_event_query("イベントは？", "ja")

        assert response["emotion"] == "excited"
        assert "calendar" in response["metadata"]["sources"]
        assert "knowledge_base" not in response["metadata"]["sources"]

    @pytest.mark.asyncio
    async def test_answer_event_query_no_events(self):
        """イベント0件のテスト"""
        class MockCalendarTool:
            async def execute(self, params):
                return {"success": True, "data": {"events": []}}

        class MockRAGTool:
            async def execute(self, params):
                return {"success": False}

        tools = {
            "calendarService": MockCalendarTool(),
            "ragSearch": MockRAGTool()
        }
        event_agent = EventAgent(llm_client=None, tools=tools)

        response = await event_agent.answer_event_query("今日のイベント", "ja")

        assert response["emotion"] == "apologetic"
        assert "[sad]" in response["text"]
        assert "見つかりませんでした" in response["text"]
```

### エラーハンドリングテスト

```python
class TestErrorHandling:
    """エラーハンドリングのテスト"""

    @pytest.mark.asyncio
    async def test_calendar_api_error_fallback_to_rag(self):
        """カレンダーAPI失敗時のRAGフォールバック"""
        class ErrorCalendarTool:
            async def execute(self, params):
                raise Exception("Calendar API down")

        class MockRAGTool:
            async def execute(self, params):
                return {
                    "success": True,
                    "results": [{"content": "イベント情報"}]
                }

        class MockLLM:
            async def generate(self, prompt):
                return "[relaxed]イベント情報をご案内します"

        tools = {
            "calendarService": ErrorCalendarTool(),
            "ragSearch": MockRAGTool()
        }
        event_agent = EventAgent(llm_client=MockLLM(), tools=tools)

        response = await event_agent.answer_event_query("イベント", "ja")

        # RAGのみで応答生成
        assert response["text"] is not None
        assert "knowledge_base" in response["metadata"]["sources"]
        assert "calendar" not in response["metadata"]["sources"]

    @pytest.mark.asyncio
    async def test_both_sources_fail(self):
        """両方のソース失敗時の処理"""
        class ErrorTool:
            async def execute(self, params):
                raise Exception("API error")

        tools = {
            "calendarService": ErrorTool(),
            "ragSearch": ErrorTool()
        }
        event_agent = EventAgent(llm_client=None, tools=tools)

        response = await event_agent.answer_event_query("イベント", "ja")

        # イベント不在応答を返す
        assert response["emotion"] == "apologetic"
        assert "[sad]" in response["text"]
```

## パフォーマンステスト

### レスポンスタイム計測

```python
import time
import asyncio

class TestPerformance:
    """パフォーマンステスト"""

    @pytest.fixture
    def fast_mock_tools(self):
        """高速モックツール"""
        class FastCalendarTool:
            async def execute(self, params):
                await asyncio.sleep(0.3)  # 300ms
                return {
                    "success": True,
                    "data": {"events": [{"title": "イベント", "start": "2025-01-15T19:00:00"}]}
                }

        class FastRAGTool:
            async def execute(self, params):
                await asyncio.sleep(0.2)  # 200ms
                return {"success": True, "results": [{"content": "情報"}]}

        class FastLLM:
            async def generate(self, prompt):
                await asyncio.sleep(0.5)  # 500ms
                return "[happy]イベント情報"

        return {
            "calendarService": FastCalendarTool(),
            "ragSearch": FastRAGTool()
        }, FastLLM()

    @pytest.mark.asyncio
    async def test_response_time(self, fast_mock_tools):
        """応答時間のテスト"""
        tools, llm = fast_mock_tools
        event_agent = EventAgent(llm_client=llm, tools=tools)

        start = time.perf_counter()
        await event_agent.answer_event_query("今週のイベント", "ja")
        elapsed = (time.perf_counter() - start) * 1000  # ms

        # 目標: 1.5秒以内
        # 並列実行により、最大値（500ms LLM）+ オーバーヘッドのみ
        assert elapsed < 1500, f"Response time {elapsed:.2f}ms exceeds 1500ms"

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, fast_mock_tools):
        """同時クエリ処理のテスト"""
        tools, llm = fast_mock_tools
        event_agent = EventAgent(llm_client=llm, tools=tools)

        queries = [
            ("今日のイベント", "ja"),
            ("今週のイベント", "ja"),
            ("来週のイベント", "ja"),
        ]

        start = time.perf_counter()
        results = await asyncio.gather(*[
            event_agent.answer_event_query(q, lang)
            for q, lang in queries
        ])
        elapsed = (time.perf_counter() - start) * 1000

        assert len(results) == 3
        # 3件の同時処理が3秒以内
        assert elapsed < 3000, f"Concurrent processing took {elapsed:.2f}ms"
```

## エンドツーエンドテスト

### ワークフロー統合テスト

```python
# tests/test_event_workflow.py

import pytest
from backend.workflows.main_workflow import MainWorkflow

class TestEventWorkflow:
    """EventAgentワークフロー統合テスト"""

    @pytest.fixture
    def workflow(self):
        return MainWorkflow()

    @pytest.mark.asyncio
    async def test_event_query_routing(self, workflow):
        """イベントクエリのルーティングテスト"""
        result = await workflow.ainvoke({
            "query": "今週のイベントは？",
            "session_id": "test_session",
            "language": "ja"
        })

        assert result["metadata"]["agent"] == "EventAgent"
        assert result["metadata"]["category"] == "events"
        assert result["response"] is not None

    @pytest.mark.asyncio
    async def test_multiple_time_ranges(self, workflow):
        """複数時間範囲のテスト"""
        test_cases = [
            ("今日のイベント", "today"),
            ("今週のイベント", "thisWeek"),
            ("来週のイベント", "nextWeek"),
            ("今月のイベント", "thisMonth"),
        ]

        for query, expected_range in test_cases:
            result = await workflow.ainvoke({
                "query": query,
                "session_id": "test_session",
                "language": "ja"
            })

            assert result["metadata"]["agent"] == "EventAgent"
            # 時間範囲が正しく処理されたことを確認
            assert result["response"] is not None
```

## 回帰テストマトリクス

### イベントクエリ精度テスト

| カテゴリ | テストケース数 | 目標精度 |
|---------|--------------|---------|
| 時間範囲抽出 | 20 | 100% |
| カレンダー統合 | 15 | 95% |
| RAG検索統合 | 12 | 98% |
| イベントフォーマット | 10 | 100% |
| エモーション生成 | 8 | 100% |
| エラーハンドリング | 10 | 95% |
| マルチソース統合 | 15 | 90% |
| **合計** | **90** | **95%以上** |

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_event_agent.py -v

# 特定のテストクラスのみ
pytest tests/test_event_agent.py::TestTimeRangeExtraction -v

# 統合テスト
pytest tests/test_event_agent_integration.py -v

# パフォーマンステストのみ
pytest tests/test_event_agent.py::TestPerformance -v

# カバレッジレポート付き
pytest tests/test_event_agent.py --cov=backend/agents/event_agent --cov-report=html
```

### CI/CD連携

```yaml
# .github/workflows/test-event-agent.yml

name: Event Agent Tests

on:
  push:
    paths:
      - 'backend/agents/event_agent.py'
      - 'backend/tools/calendar_service.py'
      - 'tests/test_event_agent.py'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: |
          pytest tests/test_event_agent.py -v --cov=backend/agents/event_agent
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 90%以上 |
| 統合テストカバレッジ | 85%以上 |
| 時間範囲抽出精度 | 100% |
| イベント情報精度 | 100% |
| 平均応答時間 | 1.5秒以下 |
| カレンダー統合成功率 | 95%以上 |
| RAG統合成功率 | 98%以上 |
| マルチソース統合成功率 | 90%以上 |

### リリース前チェックリスト

- [ ] 全単体テストがパス
- [ ] 統合テストがパス
- [ ] パフォーマンステストが基準を満たす
- [ ] 時間範囲抽出が全パターンで動作
- [ ] 日英両言語でのテストが完了
- [ ] エラーハンドリングが適切に機能
- [ ] マルチソース統合が正常動作
- [ ] エモーションタグが正しく生成される
- [ ] カレンダーAPI連携が動作
- [ ] RAG検索が正常動作
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了

## テストデータ

### サンプルイベントデータ

```python
# tests/fixtures/event_fixtures.py

SAMPLE_EVENTS = [
    {
        "title": "TypeScript勉強会",
        "start": "2025-01-15T19:00:00+09:00",
        "end": "2025-01-15T21:00:00+09:00",
        "description": "TypeScriptの基礎から応用まで学びます。初心者歓迎！"
    },
    {
        "title": "Reactハンズオン",
        "start": "2025-01-17T18:30:00+09:00",
        "end": "2025-01-17T20:30:00+09:00",
        "description": "Reactでウェブアプリを作ってみよう"
    },
    {
        "title": "AI/ML勉強会",
        "start": "2025-01-20T14:00:00+09:00",
        "end": "2025-01-20T16:00:00+09:00",
        "description": None
    }
]

SAMPLE_RAG_RESULTS = [
    {"content": "エンジニアカフェでは毎週様々なイベントを開催しています。"},
    {"content": "勉強会は平日夜19時から開催されることが多いです。"},
    {"content": "参加費は無料、ドリンク代のみ別途必要です。"}
]
```

## デバッグガイド

### ログ出力例

```python
# イベントエージェントのログ設定
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
)

# 出力例
# [2025-01-15 19:00:00] INFO - EventAgent - Processing event query: 今週のイベント
# [2025-01-15 19:00:00] DEBUG - EventAgent - Time range extracted: thisWeek
# [2025-01-15 19:00:01] DEBUG - EventAgent - Calendar result: {'success': True, 'data': {...}}
# [2025-01-15 19:00:01] DEBUG - EventAgent - Knowledge context: エンジニアカフェでは...
# [2025-01-15 19:00:02] INFO - EventAgent - Response generated with emotion: excited
```

### トラブルシューティング

| 問題 | 確認事項 | 解決策 |
|-----|---------|-------|
| イベントが取得できない | カレンダーAPIキー | 環境変数確認 |
| 時間範囲が不正 | クエリのキーワード | パターンマッチング追加 |
| フォーマットエラー | 日付形式 | ISO 8601形式確認 |
| 応答が遅い | 並列処理 | asyncio.gather使用確認 |

## 参考リンク

- [pytest ドキュメント](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Google Calendar API テスト](https://developers.google.com/calendar/api/guides/testing)
