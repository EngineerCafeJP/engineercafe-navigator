# Router Agent - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

Router Agentは全てのクエリの入り口となるため、高いテストカバレッジが必要です。

### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | 各メソッド | 個別機能の検証 |
| 統合テスト | ワークフロー連携 | エンドツーエンド検証 |
| 回帰テスト | 全ルーティングパターン | 既存機能の維持確認 |

## 単体テストケース

### 1. 言語検出テスト

```python
# tests/test_router_agent.py

import pytest
from backend.agents.router_agent import RouterAgent

class TestLanguageDetection:
    """言語検出のテスト"""

    @pytest.fixture
    def router(self):
        return RouterAgent()

    @pytest.mark.parametrize("query,expected_lang", [
        # 日本語
        ("エンジニアカフェの営業時間を教えてください", "ja"),
        ("地下の会議室について教えて", "ja"),
        ("Wi-Fiはありますか？", "ja"),

        # 英語
        ("What are the opening hours?", "en"),
        ("Tell me about the basement meeting rooms", "en"),
        ("Is there Wi-Fi available?", "en"),

        # 混合（日本語優先）
        ("Engineer Cafeの営業時間は？", "ja"),
        ("Wi-Fi passwordは何ですか？", "ja"),
    ])
    async def test_language_detection(self, router, query, expected_lang):
        result = await router.route_query(query, "test_session")
        assert result["language"] == expected_lang
```

### 2. エージェント選択テスト

```python
class TestAgentSelection:
    """エージェント選択のテスト"""

    @pytest.fixture
    def router(self):
        return RouterAgent()

    @pytest.mark.parametrize("query,expected_agent", [
        # BusinessInfoAgent
        ("エンジニアカフェの営業時間は？", "BusinessInfoAgent"),
        ("料金を教えてください", "BusinessInfoAgent"),
        ("場所はどこですか？", "BusinessInfoAgent"),
        ("Sainoカフェの営業時間は？", "BusinessInfoAgent"),

        # FacilityAgent
        ("Wi-Fiはありますか？", "FacilityAgent"),
        ("地下の施設について教えて", "FacilityAgent"),
        ("電源は使えますか？", "FacilityAgent"),
        ("MTGスペースについて", "FacilityAgent"),

        # EventAgent
        ("今日のイベントは？", "EventAgent"),
        ("来週の勉強会を教えて", "EventAgent"),
        ("カレンダーを見せて", "EventAgent"),

        # MemoryAgent
        ("さっき何を聞いた？", "MemoryAgent"),
        ("覚えてる？", "MemoryAgent"),
        ("前に話したこと", "MemoryAgent"),

        # ClarificationAgent
        ("カフェの営業時間は？", "ClarificationAgent"),  # どのカフェか不明
        ("会議室の予約方法は？", "ClarificationAgent"),  # どの会議室か不明

        # GeneralKnowledgeAgent
        ("天気を教えて", "GeneralKnowledgeAgent"),
        ("福岡のおすすめスポットは？", "GeneralKnowledgeAgent"),
    ])
    async def test_agent_selection(self, router, query, expected_agent):
        result = await router.route_query(query, "test_session")
        assert result["agent"] == expected_agent, f"Query: {query}"
```

### 3. リクエストタイプ抽出テスト

```python
class TestRequestTypeExtraction:
    """リクエストタイプ抽出のテスト"""

    @pytest.fixture
    def router(self):
        return RouterAgent()

    @pytest.mark.parametrize("query,expected_type", [
        # hours
        ("営業時間を教えて", "hours"),
        ("何時まで開いてますか？", "hours"),
        ("What are the opening hours?", "hours"),

        # price
        ("料金はいくらですか？", "price"),
        ("利用料金を教えて", "price"),
        ("How much does it cost?", "price"),

        # location
        ("場所はどこですか？", "location"),
        ("アクセス方法を教えて", "location"),
        ("Where is it located?", "location"),

        # wifi
        ("Wi-Fiはありますか？", "wifi"),
        ("ネット環境について", "wifi"),
        ("Is there Wi-Fi?", "wifi"),

        # basement
        ("地下の施設について", "basement"),
        ("B1Fの会議室", "basement"),
        ("MTGスペースについて", "basement"),

        # event
        ("イベント情報", "event"),
        ("勉強会はありますか？", "event"),
        ("Any upcoming events?", "event"),

        # None
        ("こんにちは", None),
        ("ありがとう", None),
    ])
    async def test_request_type_extraction(self, router, query, expected_type):
        result = await router.route_query(query, "test_session")
        assert result["request_type"] == expected_type, f"Query: {query}"
```

### 4. メモリ関連判定テスト

```python
class TestMemoryRelatedDetection:
    """メモリ関連質問の判定テスト"""

    @pytest.fixture
    def router(self):
        return RouterAgent()

    @pytest.mark.parametrize("query,is_memory_related", [
        # メモリ関連
        ("さっき何を聞いたっけ？", True),
        ("前に話したことを覚えてる？", True),
        ("どんな質問をした？", True),
        ("Do you remember what I asked?", True),

        # メモリ関連ではない（ビジネス情報）
        ("どんなメニューがありますか？", False),  # 「どんな」含むがメニュー質問
        ("どんな設備がありますか？", False),
        ("Sainoカフェについて", False),

        # 施設関連（メモリではない）
        ("地下にどんなスペースがある？", False),
        ("どんな会議室がありますか？", False),
    ])
    async def test_memory_related_detection(self, router, query, is_memory_related):
        result = await router.route_query(query, "test_session")
        if is_memory_related:
            assert result["agent"] == "MemoryAgent", f"Query: {query}"
        else:
            assert result["agent"] != "MemoryAgent", f"Query: {query}"
```

### 5. 文脈依存クエリテスト

```python
class TestContextDependentQueries:
    """文脈依存クエリのテスト"""

    @pytest.fixture
    def router(self):
        return RouterAgent()

    @pytest.mark.parametrize("query,expected_agent", [
        # 時間関連の文脈依存
        ("土曜日も同じ時間？", "BusinessInfoAgent"),
        ("日曜日は？", "BusinessInfoAgent"),
        ("平日も開いてる？", "BusinessInfoAgent"),

        # エンティティ関連の文脈依存
        ("Sainoの方は？", "BusinessInfoAgent"),
        ("そっちはどう？", "BusinessInfoAgent"),  # 文脈によって変わる可能性
    ])
    async def test_context_dependent_queries(self, router, query, expected_agent):
        result = await router.route_query(query, "test_session")
        assert result["agent"] == expected_agent, f"Query: {query}"
```

## 統合テストケース

### エンドツーエンドテスト

```python
# tests/test_integration.py

import pytest
from backend.workflows.main_workflow import MainWorkflow

class TestRouterIntegration:
    """RouterAgentとワークフローの統合テスト"""

    @pytest.fixture
    def workflow(self):
        return MainWorkflow()

    async def test_full_routing_flow(self, workflow):
        """完全なルーティングフローのテスト"""
        test_cases = [
            {
                "query": "エンジニアカフェの営業時間は？",
                "expected_node": "business_info"
            },
            {
                "query": "Wi-Fiのパスワードは？",
                "expected_node": "facility"
            },
            {
                "query": "今週のイベントは？",
                "expected_node": "event"
            },
        ]

        for case in test_cases:
            result = await workflow.ainvoke({
                "query": case["query"],
                "session_id": "test_session"
            })

            assert result["metadata"]["routing"]["agent"] is not None
            # ノード名のアサーション（実装に応じて調整）
```

## パフォーマンステスト

### レスポンスタイム計測

```python
import time
import asyncio

class TestPerformance:
    """パフォーマンステスト"""

    @pytest.fixture
    def router(self):
        return RouterAgent()

    async def test_routing_performance(self, router):
        """ルーティング処理時間のテスト"""
        queries = [
            "エンジニアカフェの営業時間は？",
            "Wi-Fiはありますか？",
            "今日のイベントは？",
            "さっき何を聞いた？",
            "カフェの料金は？",
        ]

        times = []
        for query in queries:
            start = time.perf_counter()
            await router.route_query(query, "test_session")
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 目標: 平均100ms以下、最大200ms以下
        assert avg_time < 100, f"Average time {avg_time:.2f}ms exceeds 100ms"
        assert max_time < 200, f"Max time {max_time:.2f}ms exceeds 200ms"

    async def test_concurrent_routing(self, router):
        """同時リクエストのテスト"""
        queries = ["エンジニアカフェの営業時間は？"] * 10

        start = time.perf_counter()
        results = await asyncio.gather(*[
            router.route_query(q, f"session_{i}")
            for i, q in enumerate(queries)
        ])
        elapsed = (time.perf_counter() - start) * 1000

        assert len(results) == 10
        assert all(r["agent"] == "BusinessInfoAgent" for r in results)
        # 10件の同時処理が500ms以内
        assert elapsed < 500, f"Concurrent processing took {elapsed:.2f}ms"
```

## 回帰テストマトリクス

### ルーティング精度テスト

現在のMastra版で94.1%のルーティング精度を達成。LangGraph版でも同等以上を目標。

| カテゴリ | テストケース数 | 目標精度 |
|---------|--------------|---------|
| 営業時間 | 10 | 100% |
| 料金 | 8 | 100% |
| 場所 | 8 | 100% |
| 設備 | 12 | 95% |
| 地下施設 | 10 | 95% |
| イベント | 8 | 100% |
| メモリ | 10 | 95% |
| 曖昧性解消 | 8 | 90% |
| 文脈依存 | 10 | 90% |
| **合計** | **84** | **94%以上** |

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_router_agent.py -v

# 特定のテストクラスのみ
pytest tests/test_router_agent.py::TestAgentSelection -v

# パフォーマンステストのみ
pytest tests/test_router_agent.py::TestPerformance -v

# カバレッジレポート付き
pytest tests/test_router_agent.py --cov=backend/agents/router_agent --cov-report=html
```

### CI/CD連携

```yaml
# .github/workflows/test-router-agent.yml

name: Router Agent Tests

on:
  push:
    paths:
      - 'backend/agents/router_agent.py'
      - 'backend/utils/query_classifier.py'
      - 'backend/utils/language_processor.py'
      - 'tests/test_router_agent.py'

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
          pytest tests/test_router_agent.py -v --cov=backend/agents/router_agent
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 90%以上 |
| ルーティング精度 | 94%以上 |
| 平均処理時間 | 100ms以下 |
| 最大処理時間 | 200ms以下 |
| 回帰テスト | 全パス |

### リリース前チェックリスト

- [ ] 全単体テストがパス
- [ ] 統合テストがパス
- [ ] パフォーマンステストが基準を満たす
- [ ] 回帰テストマトリクスの精度が94%以上
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了
