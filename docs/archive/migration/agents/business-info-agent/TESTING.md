# Business Info Agent - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

Business Info Agentは営業情報の正確性が重要なため、高いテストカバレッジが必要です。

### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | 各メソッド | 個別機能の検証 |
| 統合テスト | RAG・メモリ連携 | エンドツーエンド検証 |
| 回帰テスト | 全情報カテゴリ | 既存機能の維持確認 |

## 単体テストケース

### 1. 営業時間クエリテスト

```python
# tests/test_business_info_agent.py

import pytest
from backend.agents.business_info_agent import BusinessInfoAgent

class TestBusinessHoursQueries:
    """営業時間クエリのテスト"""

    @pytest.fixture
    def agent(self, mock_llm, mock_supabase, mock_openai):
        return BusinessInfoAgent(mock_llm, mock_supabase, mock_openai)

    @pytest.mark.parametrize("query,expected_type", [
        # 日本語
        ("エンジニアカフェの営業時間は？", "hours"),
        ("何時まで開いてますか？", "hours"),
        ("何時から利用できますか？", "hours"),
        ("開館時間を教えて", "hours"),

        # 英語
        ("What are the opening hours?", "hours"),
        ("When does it close?", "hours"),
        ("What time does it open?", "hours"),
    ])
    async def test_hours_query_detection(self, agent, query, expected_type):
        # requestTypeがhoursとして処理されることを確認
        result = await agent.answer_business_query(
            query=query,
            category="facility-info",
            request_type="hours",
            language="ja" if any(c > '\u3000' for c in query) else "en"
        )
        assert result["metadata"]["request_type"] == expected_type

    @pytest.mark.parametrize("query,lang,expected_keywords", [
        ("エンジニアカフェの営業時間は？", "ja", ["9:00", "22:00"]),
        ("What are the opening hours?", "en", ["9:00", "22:00"]),
    ])
    async def test_hours_response_content(self, agent, query, lang, expected_keywords):
        result = await agent.answer_business_query(
            query=query,
            category="facility-info",
            request_type="hours",
            language=lang
        )
        for keyword in expected_keywords:
            assert keyword in result["text"]
```

### 2. 料金クエリテスト

```python
class TestPricingQueries:
    """料金クエリのテスト"""

    @pytest.fixture
    def agent(self, mock_llm, mock_supabase, mock_openai):
        return BusinessInfoAgent(mock_llm, mock_supabase, mock_openai)

    @pytest.mark.parametrize("query,expected_type", [
        # 日本語
        ("利用料金はいくらですか？", "price"),
        ("料金を教えてください", "price"),
        ("いくらかかりますか？", "price"),

        # 英語
        ("How much does it cost?", "price"),
        ("What are the fees?", "price"),
        ("Is it free?", "price"),
    ])
    async def test_price_query_detection(self, agent, query, expected_type):
        result = await agent.answer_business_query(
            query=query,
            category="facility-info",
            request_type="price",
            language="ja" if any(c > '\u3000' for c in query) else "en"
        )
        assert result["metadata"]["request_type"] == expected_type

    async def test_engineer_cafe_free_response(self, agent):
        """エンジニアカフェ基本エリアが無料であることを確認"""
        result = await agent.answer_business_query(
            query="エンジニアカフェの利用料金は？",
            category="facility-info",
            request_type="price",
            language="ja"
        )
        assert "無料" in result["text"] or "free" in result["text"].lower()
```

### 3. 場所クエリテスト

```python
class TestLocationQueries:
    """場所・アクセスクエリのテスト"""

    @pytest.fixture
    def agent(self, mock_llm, mock_supabase, mock_openai):
        return BusinessInfoAgent(mock_llm, mock_supabase, mock_openai)

    @pytest.mark.parametrize("query,expected_type", [
        # 日本語
        ("場所はどこですか？", "location"),
        ("アクセス方法を教えて", "location"),
        ("住所を教えてください", "location"),

        # 英語
        ("Where is it located?", "location"),
        ("How do I get there?", "location"),
        ("What is the address?", "location"),
    ])
    async def test_location_query_detection(self, agent, query, expected_type):
        result = await agent.answer_business_query(
            query=query,
            category="facility-info",
            request_type="location",
            language="ja" if any(c > '\u3000' for c in query) else "en"
        )
        assert result["metadata"]["request_type"] == expected_type
```

### 4. Sainoカフェクエリテスト

```python
class TestSainoCafeQueries:
    """Sainoカフェ関連クエリのテスト"""

    @pytest.fixture
    def agent(self, mock_llm, mock_supabase, mock_openai):
        return BusinessInfoAgent(mock_llm, mock_supabase, mock_openai)

    @pytest.mark.parametrize("query,expected_entity", [
        ("Sainoカフェの営業時間は？", "saino"),
        ("サイノカフェの料金は？", "saino"),
        ("sainoの方は何時まで？", "saino"),
    ])
    async def test_saino_entity_detection(self, agent, query, expected_entity):
        result = await agent.answer_business_query(
            query=query,
            category="saino-cafe",
            request_type="hours",
            language="ja"
        )
        # Sainoカフェの情報が含まれることを確認
        assert "saino" in result["text"].lower() or "サイノ" in result["text"]

    async def test_saino_hours_different_from_engineer_cafe(self, agent):
        """SainoカフェとEngineer Cafeの営業時間が異なることを確認"""
        saino_result = await agent.answer_business_query(
            query="Sainoカフェの営業時間は？",
            category="saino-cafe",
            request_type="hours",
            language="ja"
        )
        # Sainoカフェは11:00-20:30（エンジニアカフェと異なる）
        assert "11:00" in saino_result["text"] or "20:30" in saino_result["text"]
```

### 5. 文脈継承テスト

```python
class TestContextInheritance:
    """文脈継承機能のテスト"""

    @pytest.fixture
    def agent(self, mock_llm, mock_supabase, mock_openai):
        return BusinessInfoAgent(mock_llm, mock_supabase, mock_openai)

    @pytest.mark.parametrize("query,expected_inherited", [
        ("土曜日は？", True),
        ("日曜日も同じ？", True),
        ("平日はどう？", True),
        ("sainoの方は？", True),
        ("そっちは？", True),
        ("エンジニアカフェの営業時間は？", False),  # 明示的なクエリ
    ])
    async def test_context_dependent_detection(self, agent, query, expected_inherited):
        is_context_dependent = agent._is_short_context_query(query)
        assert is_context_dependent == expected_inherited

    async def test_request_type_inheritance(self, agent, mock_memory_with_hours_context):
        """前回のhoursクエリからrequestTypeを継承"""
        # メモリに前回の「営業時間」クエリを設定
        agent.memory = mock_memory_with_hours_context

        result = await agent.answer_business_query(
            query="土曜日は？",
            category="facility-info",
            request_type=None,  # 明示的には指定しない
            language="ja",
            session_id="test_session"
        )

        # hoursが継承されていることを確認
        assert result["metadata"]["processing_info"]["context_inherited"] == True
        assert result["metadata"]["request_type"] == "hours"

    async def test_entity_inheritance_from_context(self, agent, mock_memory_with_saino_context):
        """前回のSainoカフェクエリからエンティティを継承"""
        agent.memory = mock_memory_with_saino_context

        result = await agent.answer_business_query(
            query="土曜日は？",
            category="facility-info",
            request_type=None,
            language="ja",
            session_id="test_session"
        )

        # Sainoカフェの情報が返されることを確認
        assert "saino" in result["text"].lower() or "サイノ" in result["text"]
```

### 6. クエリ拡張テスト

```python
class TestQueryEnhancement:
    """クエリ拡張機能のテスト"""

    @pytest.fixture
    def agent(self, mock_llm, mock_supabase, mock_openai):
        return BusinessInfoAgent(mock_llm, mock_supabase, mock_openai)

    @pytest.mark.parametrize("query,request_type,context_entity,expected_contains", [
        # エンティティ優先
        ("土曜日は？", "hours", "saino", "sainoカフェ"),
        ("いくら？", "price", "saino", "sainoカフェ"),

        # 曜日関連
        ("土曜日は？", "hours", None, "営業時間"),
        ("日曜は？", "hours", None, "営業時間"),

        # requestTypeベース
        ("エンジニアカフェ", "hours", None, "営業時間"),
        ("エンジニアカフェ", "price", None, "料金"),
    ])
    def test_query_enhancement(self, agent, query, request_type, context_entity, expected_contains):
        enhanced = agent._enhance_context_query(query, request_type, "ja", context_entity)
        assert expected_contains in enhanced
```

## 統合テストケース

### Enhanced RAG統合テスト

```python
class TestEnhancedRAGIntegration:
    """Enhanced RAGとの統合テスト"""

    @pytest.fixture
    def agent_with_real_rag(self, llm, supabase_client, openai_client):
        return BusinessInfoAgent(llm, supabase_client, openai_client)

    async def test_rag_search_for_hours(self, agent_with_real_rag):
        """営業時間のRAG検索が正しく動作することを確認"""
        result = await agent_with_real_rag.answer_business_query(
            query="エンジニアカフェの営業時間は？",
            category="facility-info",
            request_type="hours",
            language="ja"
        )

        assert result["metadata"]["sources"] == ["enhanced_rag"]
        assert result["metadata"]["processing_info"]["enhanced_rag"] == True
        assert "9:00" in result["text"] or "22:00" in result["text"]

    async def test_entity_aware_scoring(self, agent_with_real_rag):
        """エンティティ認識がスコアリングに影響することを確認"""
        # Sainoカフェのクエリ
        saino_result = await agent_with_real_rag.answer_business_query(
            query="Sainoカフェの営業時間は？",
            category="saino-cafe",
            request_type="hours",
            language="ja"
        )

        # エンジニアカフェのクエリ
        ec_result = await agent_with_real_rag.answer_business_query(
            query="エンジニアカフェの営業時間は？",
            category="facility-info",
            request_type="hours",
            language="ja"
        )

        # それぞれ異なる営業時間が返されることを確認
        assert saino_result["text"] != ec_result["text"]
```

### メモリシステム統合テスト

```python
class TestMemoryIntegration:
    """メモリシステムとの統合テスト"""

    async def test_conversation_continuity(self, agent_with_real_memory):
        """会話の連続性が維持されることを確認"""
        session_id = "test_session_123"

        # 1. 最初の質問
        first_result = await agent_with_real_memory.answer_business_query(
            query="エンジニアカフェの営業時間は？",
            category="facility-info",
            request_type="hours",
            language="ja",
            session_id=session_id
        )

        # 2. フォローアップ質問
        followup_result = await agent_with_real_memory.answer_business_query(
            query="土曜日は？",
            category="facility-info",
            request_type=None,  # 継承させる
            language="ja",
            session_id=session_id
        )

        # 文脈が継承されていることを確認
        assert followup_result["metadata"]["processing_info"]["context_inherited"] == True
```

## パフォーマンステスト

### レスポンスタイム計測

```python
import time
import asyncio

class TestPerformance:
    """パフォーマンステスト"""

    async def test_response_time(self, agent):
        """レスポンス時間のテスト"""
        queries = [
            ("エンジニアカフェの営業時間は？", "hours"),
            ("料金はいくらですか？", "price"),
            ("場所はどこですか？", "location"),
            ("Sainoカフェの営業時間は？", "hours"),
        ]

        times = []
        for query, request_type in queries:
            start = time.perf_counter()
            await agent.answer_business_query(
                query=query,
                category="facility-info",
                request_type=request_type,
                language="ja"
            )
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 目標: 平均3秒以下、最大5秒以下
        assert avg_time < 3000, f"Average time {avg_time:.2f}ms exceeds 3000ms"
        assert max_time < 5000, f"Max time {max_time:.2f}ms exceeds 5000ms"

    async def test_concurrent_queries(self, agent):
        """同時クエリのテスト"""
        queries = [("エンジニアカフェの営業時間は？", "hours")] * 5

        start = time.perf_counter()
        results = await asyncio.gather(*[
            agent.answer_business_query(
                query=q,
                category="facility-info",
                request_type=rt,
                language="ja"
            )
            for q, rt in queries
        ])
        elapsed = (time.perf_counter() - start) * 1000

        assert len(results) == 5
        assert all(r["metadata"]["confidence"] > 0.5 for r in results)
        # 5件の同時処理が10秒以内
        assert elapsed < 10000
```

## 回帰テストマトリクス

### 情報正確性テスト

| カテゴリ | テストケース数 | 目標精度 |
|---------|--------------|---------|
| 営業時間 | 10 | 100% |
| 料金 | 8 | 100% |
| 場所 | 8 | 100% |
| Sainoカフェ | 8 | 95% |
| 文脈継承 | 10 | 90% |
| **合計** | **44** | **95%以上** |

### 期待値テストケース

```python
class TestExpectedResponses:
    """期待される回答のテスト"""

    @pytest.mark.parametrize("query,expected_response_contains", [
        # 営業時間
        ("エンジニアカフェの営業時間は？", ["9:00", "22:00"]),
        ("Sainoカフェの営業時間は？", ["11:00", "20:30"]),

        # 料金
        ("エンジニアカフェの利用料金は？", ["無料"]),

        # 場所
        ("エンジニアカフェの場所は？", ["福岡", "天神"]),
    ])
    async def test_expected_response_content(self, agent, query, expected_response_contains):
        result = await agent.answer_business_query(
            query=query,
            category="facility-info",
            request_type=None,
            language="ja"
        )

        for expected in expected_response_contains:
            assert expected in result["text"], f"Expected '{expected}' in response"
```

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_business_info_agent.py -v

# 特定のテストクラスのみ
pytest tests/test_business_info_agent.py::TestBusinessHoursQueries -v

# パフォーマンステストのみ
pytest tests/test_business_info_agent.py::TestPerformance -v

# カバレッジレポート付き
pytest tests/test_business_info_agent.py --cov=backend/agents/business_info_agent --cov-report=html
```

### CI/CD連携

```yaml
# .github/workflows/test-business-info-agent.yml

name: Business Info Agent Tests

on:
  push:
    paths:
      - 'backend/agents/business_info_agent.py'
      - 'backend/tools/enhanced_rag_search.py'
      - 'backend/tools/context_filter.py'
      - 'tests/test_business_info_agent.py'

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
          pytest tests/test_business_info_agent.py -v --cov=backend/agents/business_info_agent
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 85%以上 |
| 情報正確性 | 95%以上 |
| 平均レスポンス時間 | 3秒以下 |
| 文脈継承成功率 | 90%以上 |
| 回帰テスト | 全パス |

### リリース前チェックリスト

- [ ] 全単体テストがパス
- [ ] 統合テストがパス
- [ ] パフォーマンステストが基準を満たす
- [ ] 営業時間の情報が正確
- [ ] 料金の情報が正確
- [ ] Sainoカフェの情報が正確
- [ ] 文脈継承が正しく動作
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了
