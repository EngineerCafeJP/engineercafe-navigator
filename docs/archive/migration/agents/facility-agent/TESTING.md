# Facility Agent - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

Facility Agentは施設情報の正確性が重要なため、高いテストカバレッジが必要です。

### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | 各メソッド | 個別機能の検証 |
| 統合テスト | Enhanced RAG連携 | エンドツーエンド検証 |
| 回帰テスト | 全リクエストタイプ | 既存機能の維持確認 |

## 単体テストケース

### 1. Wi-Fi情報テスト

```python
# tests/test_facility_agent.py

import pytest
from backend.agents.facility_agent import FacilityAgent

class TestWiFiQueries:
    """Wi-Fi関連クエリのテスト"""

    @pytest.fixture
    def facility_agent(self):
        return FacilityAgent(config={}, llm_client=mock_llm)

    @pytest.mark.parametrize("query,request_type,expected_keywords", [
        # 日本語
        ("Wi-Fiはありますか？", "wifi", ["Wi-Fi", "無料", "利用可能"]),
        ("インターネットは使えますか？", "wifi", ["Wi-Fi", "接続"]),
        ("Wi-Fiのパスワードは？", "wifi", ["Wi-Fi", "パスワード", "受付"]),
        ("ネット環境について", "wifi", ["Wi-Fi", "インターネット"]),

        # 英語
        ("Is there Wi-Fi available?", "wifi", ["Wi-Fi", "available", "free"]),
        ("What's the Wi-Fi password?", "wifi", ["Wi-Fi", "password", "reception"]),
        ("Can I connect to the internet?", "wifi", ["Wi-Fi", "connect", "internet"]),
    ])
    async def test_wifi_queries(self, facility_agent, query, request_type, expected_keywords):
        # 言語判定（日本語文字が含まれているか、または全角/半角の疑問符で判定）
        language = "ja" if any(c in query for c in ["？", "?", "は", "の", "を"]) or \
                      any(ord(c) > 127 for c in query) else "en"
        
        result = await facility_agent.answer_facility_query(
            query, request_type, language
        )
        
        # UnifiedAgentResponseにはsuccessフィールドがないため、textフィールドの存在で判定
        assert "text" in result, f"Response should contain 'text' field: {result}"
        assert result["metadata"]["requestType"] == "wifi"
        response_text = result["text"].lower()
        assert any(kw.lower() in response_text for kw in expected_keywords), \
            f"Expected keywords not found in response: {result['text']}"
```

### 2. 設備情報テスト

```python
class TestFacilityQueries:
    """設備関連クエリのテスト"""

    @pytest.fixture
    def facility_agent(self):
        return FacilityAgent(config={}, llm_client=mock_llm)

    @pytest.mark.parametrize("query,request_type,expected_keywords", [
        # 電源関連
        ("電源は使えますか？", "facility", ["電源", "コンセント", "各席"]),
        ("コンセントはありますか？", "facility", ["電源", "コンセント"]),
        ("Are there power outlets?", "facility", ["power", "outlet", "seat"]),

        # プリンター関連
        ("プリンターは使えますか？", "facility", ["プリンター", "利用"]),
        ("Can I use the printer?", "facility", ["printer", "available"]),

        # その他設備
        ("3Dプリンターはありますか？", "facility", ["3D", "プリンター"]),
        ("プロジェクターは使えますか？", "facility", ["プロジェクター"]),
    ])
    async def test_facility_queries(self, facility_agent, query, request_type, expected_keywords):
        language = "ja" if any(c in query for c in ["？", "?", "は", "の", "を"]) or \
                      any(ord(c) > 127 for c in query) else "en"
        
        result = await facility_agent.answer_facility_query(
            query, request_type, language
        )
        
        assert "text" in result
        assert result["metadata"]["requestType"] == "facility"
        response_text = result["text"].lower()
        assert any(kw.lower() in response_text for kw in expected_keywords), \
            f"Expected keywords not found in response: {result['text']}"
```

### 3. 地下施設テスト

```python
class TestBasementQueries:
    """地下施設関連クエリのテスト"""

    @pytest.fixture
    def facility_agent(self):
        return FacilityAgent(config={}, llm_client=mock_llm)

    @pytest.mark.parametrize("query,request_type,expected_facility,expected_keywords", [
        # MTGスペース
        ("MTGスペースについて", "basement", "MTGスペース", ["MTG", "予約不要", "先着順"]),
        ("地下のミーティングスペース", "basement", "MTGスペース", ["MTG", "打ち合わせ"]),
        ("Tell me about the MTG space", "basement", "MTGスペース", ["MTG", "meeting", "space"]),

        # 集中スペース
        ("集中スペースとは？", "basement", "集中スペース", ["集中", "静か", "作業環境"]),
        ("地下のフォーカススペース", "basement", "集中スペース", ["集中", "focus", "space"]),
        ("What is the focus space?", "basement", "集中スペース", ["focus", "quiet", "work"]),

        # アンダースペース
        ("アンダースペースについて", "basement", "アンダースペース", ["アンダー", "予約", "イベント"]),
        ("地下のアンダースペース", "basement", "アンダースペース", ["アンダー", "under", "space"]),
        ("Tell me about the under space", "basement", "アンダースペース", ["under", "space", "event"]),

        # Makersスペース
        ("Makersスペースについて", "basement", "Makersスペース", ["Makers", "モノづくり", "予約"]),
        ("地下のメーカースペース", "basement", "Makersスペース", ["Makers", "工作"]),
        ("What is the Makers space?", "basement", "Makersスペース", ["makers", "space", "reservation"]),

        # 一般的な地下施設
        ("地下の施設について", "basement", None, ["地下", "B1", "スペース"]),
        ("B1Fの会議室", "basement", None, ["地下", "B1", "会議室"]),
        ("What facilities are in the basement?", "basement", None, ["basement", "B1", "space"]),
    ])
    async def test_basement_queries(
        self, facility_agent, query, request_type, expected_facility, expected_keywords
    ):
        language = "ja" if any(c in query for c in ["？", "?", "は", "の", "を"]) or \
                      any(ord(c) > 127 for c in query) else "en"
        
        result = await facility_agent.answer_facility_query(
            query, request_type, language
        )
        
        assert "text" in result
        assert result["metadata"]["requestType"] == "basement"
        
        response_text = result["text"].lower()
        if expected_facility:
            assert expected_facility.lower() in response_text or \
                   any(kw.lower() in response_text for kw in expected_facility.split()), \
                   f"Expected facility {expected_facility} not found in response: {result['text']}"
        
        assert any(kw.lower() in response_text for kw in expected_keywords), \
            f"Expected keywords not found in response: {result['text']}"
```

### 4. クエリ拡張テスト

```python
class TestQueryEnhancement:
    """クエリ拡張機能のテスト"""

    @pytest.fixture
    def facility_agent(self):
        return FacilityAgent(config={}, llm_client=mock_llm)

    @pytest.mark.parametrize("query,request_type,expected_enhancements", [
        # Wi-Fi拡張
        ("Wi-Fiは？", "wifi", ["無料Wi-Fi", "インターネット", "接続"]),
        
        # 地下施設拡張
        ("地下について", "basement", ["地下", "B1", "MTGスペース", "集中スペース"]),
        ("MTGスペース", "basement", ["地下MTGスペース", "basement", "meeting space"]),
        ("集中スペース", "basement", ["地下集中スペース", "basement", "focus space"]),
        
        # 設備拡張
        ("電源は？", "facility", ["設備", "電源", "コンセント", "プリンター"]),
    ])
    async def test_query_enhancement(self, facility_agent, query, request_type, expected_enhancements):
        enhanced = facility_agent._enhance_query(query, request_type)
        
        enhanced_lower = enhanced.lower()
        for enhancement in expected_enhancements:
            assert enhancement.lower() in enhanced_lower, \
                f"Enhancement '{enhancement}' not found in enhanced query: {enhanced}"
```

## 統合テストケース

### Enhanced RAG連携テスト

```python
# tests/test_facility_integration.py

import pytest
from backend.agents.facility_agent import FacilityAgent
from backend.tools.enhanced_rag_search import EnhancedRAGSearch

class TestFacilityIntegration:
    """FacilityAgentとEnhanced RAGの統合テスト"""

    @pytest.fixture
    def facility_agent(self):
        agent = FacilityAgent(config={}, llm_client=mock_llm)
        agent.add_tool("enhancedRagSearch", EnhancedRAGSearch(supabase_client, openai_client))
        agent.add_tool("contextFilter", ContextFilter())
        return agent

    async def test_wifi_integration(self, facility_agent):
        """Wi-Fi情報の統合テスト"""
        result = await facility_agent.answer_facility_query(
            "Wi-Fiのパスワードは？", "wifi", "ja"
        )
        
        assert "text" in result
        assert result["metadata"]["sources"] == ["enhanced_rag"]
        assert result["metadata"]["processingInfo"]["enhancedRag"] == True
        assert result["metadata"]["processingInfo"]["filtered"] == True

    async def test_basement_integration(self, facility_agent):
        """地下施設情報の統合テスト"""
        result = await facility_agent.answer_facility_query(
            "集中スペースについて教えて", "basement", "ja"
        )
        
        assert "text" in result
        assert "集中" in result["text"] or "focus" in result["text"].lower()
        assert result["metadata"]["requestType"] == "basement"
```

## パフォーマンステスト

### レスポンスタイム計測

```python
import time
import asyncio

class TestFacilityPerformance:
    """パフォーマンステスト"""

    @pytest.fixture
    def facility_agent(self):
        return FacilityAgent(config={}, llm_client=mock_llm)

    async def test_query_performance(self, facility_agent):
        """クエリ処理時間のテスト"""
        queries = [
            ("Wi-Fiはありますか？", "wifi"),
            ("電源は使えますか？", "facility"),
            ("MTGスペースについて", "basement"),
            ("集中スペースとは？", "basement"),
            ("アンダースペースについて", "basement"),
        ]

        times = []
        for query, request_type in queries:
            start = time.perf_counter()
            await facility_agent.answer_facility_query(query, request_type, "ja")
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 目標: 平均2秒以下、最大5秒以下（RAG検索とLLM生成を含む）
        assert avg_time < 2000, f"Average time {avg_time:.2f}ms exceeds 2000ms"
        assert max_time < 5000, f"Max time {max_time:.2f}ms exceeds 5000ms"
```

## 回帰テストマトリクス

### リクエストタイプ別テスト

現在のMastra版の機能を維持しつつ、LangGraph版でも同等以上の精度を目標。

| リクエストタイプ | テストケース数 | 目標精度 | テスト内容 |
|----------------|--------------|---------|-----------|
| `wifi` | 12 | 100% | Wi-Fi有無、パスワード、接続方法 |
| `facility` | 15 | 95% | 電源、プリンター、その他設備 |
| `basement` (一般) | 8 | 95% | 地下施設全般 |
| `basement` (MTG) | 6 | 100% | MTGスペース詳細 |
| `basement` (集中) | 6 | 100% | 集中スペース詳細 |
| `basement` (アンダー) | 6 | 100% | アンダースペース詳細 |
| `basement` (Makers) | 6 | 100% | Makersスペース詳細 |
| **合計** | **59** | **97%以上** | |

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_facility_agent.py -v

# 特定のテストクラスのみ
pytest tests/test_facility_agent.py::TestWiFiQueries -v

# 統合テストのみ
pytest tests/test_facility_integration.py -v

# カバレッジレポート付き
pytest tests/test_facility_agent.py --cov=backend/agents/facility_agent --cov-report=html
```

### CI/CD連携

```yaml
# .github/workflows/test-facility-agent.yml

name: Facility Agent Tests

on:
  push:
    paths:
      - 'backend/agents/facility_agent.py'
      - 'backend/tools/enhanced_rag_search.py'
      - 'backend/tools/context_filter.py'
      - 'tests/test_facility_agent.py'

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
          pytest tests/test_facility_agent.py -v --cov=backend/agents/facility_agent
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 90%以上 |
| リクエストタイプ別精度 | 97%以上 |
| 平均処理時間 | 2秒以下 |
| 最大処理時間 | 5秒以下 |
| 回帰テスト | 全パス |
| Enhanced RAG統合 | 正常動作 |

### リリース前チェックリスト

- [ ] 全単体テストがパス（59件以上）
- [ ] 統合テストがパス
- [ ] パフォーマンステストが基準を満たす
- [ ] 回帰テストマトリクスの精度が97%以上
- [ ] 地下施設4種類（MTG/集中/アンダー/Makers）のテストが全てパス
- [ ] Wi-Fi情報のテストが全てパス
- [ ] 設備情報のテストが全てパス
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了

## 参考リンク

- [Router Agent](../router-agent/TESTING.md) - ルーティングテスト
- [Enhanced RAG](../../tools/enhanced-rag.md) - RAGシステム
- [Facility Agent SPEC](./SPEC.md) - 技術仕様書
- [Facility Agent Migration Guide](./MIGRATION-GUIDE.md) - 移行ガイド
