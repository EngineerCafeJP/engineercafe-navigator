# General Knowledge Agent - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

General Knowledge Agentは情報源の組み合わせとウェブ検索判定が重要なため、多様なシナリオのテストが必要です。

### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | 各メソッド | 個別機能の検証 |
| 統合テスト | ツール連携 | RAG + Web検索の連携検証 |
| エンドツーエンドテスト | ワークフロー全体 | 実際のユースケース検証 |

## 単体テストケース

### 1. ウェブ検索判定テスト

```python
# tests/test_general_knowledge_agent.py

import pytest
from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

class TestWebSearchDetection:
    """ウェブ検索判定のテスト"""

    @pytest.fixture
    def agent(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        return GeneralKnowledgeAgent(llm)

    @pytest.mark.parametrize("query,should_search", [
        # ウェブ検索が必要
        ("最新のAI技術について教えて", True),
        ("現在の福岡のスタートアップシーンは？", True),
        ("今のトレンドについて知りたい", True),
        ("最新ニュースを教えて", True),
        ("What are the latest AI trends?", True),
        ("Tell me about current technology news", True),

        # ウェブ検索が不要
        ("エンジニアカフェの営業時間は？", False),
        ("料金を教えてください", False),
        ("場所はどこですか？", False),
        ("Wi-Fiはありますか？", False),
        ("What is Engineer Cafe?", False),
        ("Tell me about the facilities", False),
    ])
    def test_should_use_web_search(self, agent, query, should_search):
        result = agent._should_use_web_search(query)
        assert result == should_search, f"Query: {query}"
```

### 2. 信頼度計算テスト

```python
class TestConfidenceCalculation:
    """信頼度計算のテスト"""

    @pytest.fixture
    def agent(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        return GeneralKnowledgeAgent(llm)

    @pytest.mark.parametrize("sources,expected_confidence", [
        # 両方のソース
        (["knowledge base", "web search"], 0.9),
        (["knowledge_base", "web_search"], 0.9),

        # ナレッジベースのみ
        (["knowledge base"], 0.8),
        (["knowledge_base"], 0.8),

        # ウェブ検索のみ
        (["web search"], 0.6),
        (["web_search"], 0.6),

        # フォールバック
        ([], 0.3),
        (["fallback"], 0.3),
    ])
    def test_calculate_confidence(self, agent, sources, expected_confidence):
        confidence = agent._calculate_confidence(sources)
        assert confidence == expected_confidence, f"Sources: {sources}"
```

### 3. プロンプト構築テスト

```python
class TestPromptBuilding:
    """プロンプト構築のテスト"""

    @pytest.fixture
    def agent(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        return GeneralKnowledgeAgent(llm)

    def test_build_general_prompt_japanese(self, agent):
        query = "エンジニアカフェについて教えて"
        context = "エンジニアカフェは福岡のコワーキングスペースです。"
        sources = ["knowledge base"]
        language = "ja"

        prompt = agent._build_general_prompt(query, context, sources, language)

        assert "knowledge base" in prompt
        assert query in prompt
        assert context in prompt
        assert "質問:" in prompt
        assert "情報:" in prompt

    def test_build_general_prompt_english(self, agent):
        query = "Tell me about Engineer Cafe"
        context = "Engineer Cafe is a coworking space in Fukuoka."
        sources = ["knowledge base", "web search"]
        language = "en"

        prompt = agent._build_general_prompt(query, context, sources, language)

        assert "knowledge base and web search" in prompt
        assert query in prompt
        assert context in prompt
        assert "Question:" in prompt
        assert "Information:" in prompt
```

### 4. デフォルトレスポンステスト

```python
class TestDefaultResponse:
    """デフォルトレスポンスのテスト"""

    @pytest.fixture
    def agent(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        return GeneralKnowledgeAgent(llm)

    def test_default_response_japanese(self, agent):
        response = agent._get_default_general_response("ja")

        assert response["text"].startswith("[sad]")
        assert response["emotion"] == "apologetic"
        assert response["agent_name"] == "GeneralKnowledgeAgent"
        assert response["language"] == "ja"
        assert response["metadata"]["confidence"] == 0.3
        assert response["metadata"]["sources"] == ["fallback"]

    def test_default_response_english(self, agent):
        response = agent._get_default_general_response("en")

        assert response["text"].startswith("[sad]")
        assert response["emotion"] == "apologetic"
        assert response["agent_name"] == "GeneralKnowledgeAgent"
        assert response["language"] == "en"
        assert response["metadata"]["confidence"] == 0.3
```

## 統合テストケース

### 5. マルチソースレスポンステスト

```python
# tests/test_general_knowledge_integration.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

class TestMultiSourceResponse:
    """マルチソースレスポンスのテスト"""

    @pytest.fixture
    def agent(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="[relaxed]テスト回答"))
        return GeneralKnowledgeAgent(llm)

    @pytest.fixture
    def rag_search_tool(self):
        tool = AsyncMock()
        tool.ainvoke = AsyncMock(return_value={
            "success": True,
            "results": [
                {"content": "ナレッジベースの情報"}
            ]
        })
        return tool

    @pytest.fixture
    def web_search_tool(self):
        tool = AsyncMock()
        tool.ainvoke = AsyncMock(return_value={
            "success": True,
            "text": "ウェブ検索の情報"
        })
        return tool

    @pytest.mark.asyncio
    async def test_both_sources_success(self, agent, rag_search_tool, web_search_tool):
        """両方のソースから情報を取得"""
        response = await agent.answer_general_query(
            query="最新のAI技術について教えて",
            language="ja",
            rag_search_tool=rag_search_tool,
            web_search_tool=web_search_tool
        )

        assert response["metadata"]["confidence"] == 0.9
        assert "knowledge base" in response["metadata"]["sources"]
        assert "web search" in response["metadata"]["sources"]
        assert response["emotion"] == "helpful"

    @pytest.mark.asyncio
    async def test_knowledge_base_only(self, agent, rag_search_tool, web_search_tool):
        """ナレッジベースのみから情報を取得"""
        # ウェブ検索を無効化
        agent._should_use_web_search = lambda q: False

        response = await agent.answer_general_query(
            query="エンジニアカフェについて教えて",
            language="ja",
            rag_search_tool=rag_search_tool,
            web_search_tool=web_search_tool
        )

        assert response["metadata"]["confidence"] == 0.8
        assert response["metadata"]["sources"] == ["knowledge base"]

    @pytest.mark.asyncio
    async def test_web_search_only(self, agent, rag_search_tool, web_search_tool):
        """ウェブ検索のみから情報を取得"""
        # ナレッジベースを失敗させる
        rag_search_tool.ainvoke = AsyncMock(return_value={"success": False})

        response = await agent.answer_general_query(
            query="最新のニュースを教えて",
            language="ja",
            rag_search_tool=rag_search_tool,
            web_search_tool=web_search_tool
        )

        assert response["metadata"]["confidence"] == 0.6
        assert response["metadata"]["sources"] == ["web search"]
```

### 6. フォールバック処理テスト

```python
class TestFallbackHandling:
    """フォールバック処理のテスト"""

    @pytest.fixture
    def agent(self):
        llm = MagicMock()
        return GeneralKnowledgeAgent(llm)

    @pytest.fixture
    def failed_rag_search_tool(self):
        tool = AsyncMock()
        tool.ainvoke = AsyncMock(return_value={"success": False})
        return tool

    @pytest.fixture
    def failed_web_search_tool(self):
        tool = AsyncMock()
        tool.ainvoke = AsyncMock(return_value={"success": False})
        return tool

    @pytest.mark.asyncio
    async def test_all_sources_fail(self, agent, failed_rag_search_tool, failed_web_search_tool):
        """全てのソースが失敗した場合"""
        response = await agent.answer_general_query(
            query="テストクエリ",
            language="ja",
            rag_search_tool=failed_rag_search_tool,
            web_search_tool=failed_web_search_tool
        )

        assert response["text"].startswith("[sad]")
        assert response["emotion"] == "apologetic"
        assert response["metadata"]["confidence"] == 0.3
        assert response["metadata"]["sources"] == ["fallback"]

    @pytest.mark.asyncio
    async def test_rag_exception_handling(self, agent, failed_web_search_tool):
        """RAG検索で例外が発生した場合"""
        rag_tool = AsyncMock()
        rag_tool.ainvoke = AsyncMock(side_effect=Exception("RAG error"))

        response = await agent.answer_general_query(
            query="テストクエリ",
            language="ja",
            rag_search_tool=rag_tool,
            web_search_tool=failed_web_search_tool
        )

        # エラーハンドリングにより、デフォルトレスポンスが返される
        assert response["metadata"]["confidence"] == 0.3
```

## エンドツーエンドテスト

### 7. ワークフロー統合テスト

```python
# tests/test_general_knowledge_e2e.py

import pytest
from backend.workflows.main_workflow import MainWorkflow

class TestGeneralKnowledgeWorkflow:
    """ワークフロー統合テスト"""

    @pytest.fixture
    def workflow(self):
        return MainWorkflow()

    @pytest.mark.asyncio
    async def test_general_knowledge_routing(self, workflow):
        """General Knowledgeへのルーティング"""
        result = await workflow.graph.ainvoke({
            "query": "福岡のスタートアップについて教えて",
            "session_id": "test_session",
            "language": "ja"
        })

        assert result["metadata"]["agent"] == "GeneralKnowledgeAgent"
        assert result["metadata"]["confidence"] > 0.5
        assert len(result["metadata"]["sources"]) > 0

    @pytest.mark.asyncio
    async def test_web_search_trigger(self, workflow):
        """ウェブ検索が適切にトリガーされる"""
        result = await workflow.graph.ainvoke({
            "query": "最新のAIトレンドは？",
            "session_id": "test_session",
            "language": "ja"
        })

        # ウェブ検索がトリガーされるべき
        assert "web search" in result["metadata"].get("sources", []) or \
               "web_search" in result["metadata"].get("sources", [])
```

## パフォーマンステスト

### 8. レスポンスタイム計測

```python
import time
import asyncio

class TestPerformance:
    """パフォーマンステスト"""

    @pytest.fixture
    def agent(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp")
        return GeneralKnowledgeAgent(llm)

    @pytest.mark.asyncio
    async def test_response_time(self, agent, rag_search_tool, web_search_tool):
        """レスポンスタイム計測"""
        queries = [
            "エンジニアカフェについて教えて",
            "最新のAI技術について教えて",
            "福岡のスタートアップシーンは？",
        ]

        times = []
        for query in queries:
            start = time.perf_counter()
            await agent.answer_general_query(
                query=query,
                language="ja",
                rag_search_tool=rag_search_tool,
                web_search_tool=web_search_tool
            )
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 目標: 平均4000ms以下、最大6000ms以下
        assert avg_time < 4000, f"Average time {avg_time:.2f}ms exceeds 4000ms"
        assert max_time < 6000, f"Max time {max_time:.2f}ms exceeds 6000ms"
```

## テストカバレッジ目標

### カバレッジマトリクス

| テストカテゴリ | テストケース数 | カバレッジ目標 |
|--------------|--------------|--------------|
| ウェブ検索判定 | 12 | 100% |
| 信頼度計算 | 7 | 100% |
| プロンプト構築 | 6 | 100% |
| マルチソース処理 | 10 | 95% |
| エラーハンドリング | 8 | 90% |
| E2Eシナリオ | 15 | 85% |
| **合計** | **58** | **95%以上** |

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_general_knowledge_agent.py -v

# 統合テストのみ
pytest tests/test_general_knowledge_integration.py -v

# E2Eテストのみ
pytest tests/test_general_knowledge_e2e.py -v

# カバレッジレポート付き
pytest tests/test_general_knowledge_agent.py --cov=backend/agents/general_knowledge_agent --cov-report=html

# パフォーマンステストのみ
pytest tests/test_general_knowledge_agent.py::TestPerformance -v
```

### CI/CD連携

```yaml
# .github/workflows/test-general-knowledge-agent.yml

name: General Knowledge Agent Tests

on:
  push:
    paths:
      - 'backend/agents/general_knowledge_agent.py'
      - 'backend/tools/web_search.py'
      - 'tests/test_general_knowledge_*.py'

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
        env:
          GOOGLE_CUSTOM_SEARCH_API_KEY: ${{ secrets.GOOGLE_CUSTOM_SEARCH_API_KEY }}
          GOOGLE_CUSTOM_SEARCH_CX: ${{ secrets.GOOGLE_CUSTOM_SEARCH_CX }}
        run: |
          pytest tests/test_general_knowledge_agent.py -v --cov=backend/agents/general_knowledge_agent
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 95%以上 |
| 統合テストカバレッジ | 90%以上 |
| ウェブ検索判定精度 | 95%以上 |
| 平均レスポンスタイム | 4000ms以下 |
| 最大レスポンスタイム | 6000ms以下 |
| 信頼度計算精度 | 100% |

### リリース前チェックリスト

- [ ] 全単体テストがパス
- [ ] 全統合テストがパス
- [ ] E2Eテストがパス
- [ ] パフォーマンステストが基準を満たす
- [ ] ウェブ検索判定が正しく動作
- [ ] マルチソース処理が正常に動作
- [ ] エラーハンドリングが適切に機能
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了

## テストデータ準備

### モックデータ

```python
# tests/fixtures/general_knowledge_fixtures.py

import pytest

@pytest.fixture
def mock_kb_results():
    """ナレッジベース検索のモックデータ"""
    return {
        "success": True,
        "results": [
            {
                "content": "エンジニアカフェは福岡市中央区にあるコワーキングスペースです。",
                "similarity": 0.9
            },
            {
                "content": "24時間365日利用可能で、様々な設備が整っています。",
                "similarity": 0.85
            }
        ]
    }

@pytest.fixture
def mock_web_results():
    """ウェブ検索のモックデータ"""
    return {
        "success": True,
        "text": "最新のAI技術について、2025年現在は生成AIとマルチモーダルモデルが主流です。"
    }

@pytest.fixture
def test_queries():
    """テストクエリのセット"""
    return {
        "general": [
            "エンジニアカフェについて教えて",
            "Tell me about Engineer Cafe"
        ],
        "web_search": [
            "最新のAI技術について教えて",
            "What are the latest technology trends?"
        ],
        "fallback": [
            "明日の天気は？",
            "What's the weather tomorrow?"
        ]
    }
```

## デバッグ・トラブルシューティング

### よくある問題

| 問題 | チェック項目 | 解決策 |
|-----|------------|-------|
| テストが失敗する | APIキー設定 | 環境変数を確認 |
| タイムアウト | ネットワーク接続 | タイムアウト設定を調整 |
| 信頼度が低い | ソース検出ロジック | ソース名の正規化を確認 |
| 感情タグなし | LLM出力形式 | プロンプトのinstructionsを確認 |

### デバッグログ設定

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('general_knowledge_agent')
logger.setLevel(logging.DEBUG)
```

## 参考リンク

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [元実装: general-knowledge-agent.ts](../../engineer-cafe-navigator-repo/frontend/src/mastra/agents/general-knowledge-agent.ts)
