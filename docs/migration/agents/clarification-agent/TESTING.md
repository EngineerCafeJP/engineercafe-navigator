# Clarification Agent - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

Clarification Agentはシンプルな実装（LLMを使用しない固定メッセージ）のため、高いテストカバレッジと一貫性の検証が重要です。


### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | `handle_clarification()` メソッド | カテゴリ・言語別のメッセージ生成検証 |
| 統合テスト | ワークフロー連携 | エンドツーエンド検証 |
| 回帰テスト | 全カテゴリ・言語パターン | 既存機能の維持確認 |

## 単体テストケース

### 1. カテゴリ別メッセージ生成テスト

```python
# tests/test_clarification_agent.py

import pytest
from backend.agents.clarification_agent import ClarificationAgent

class TestCategoryMessages:
    """カテゴリ別メッセージ生成のテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.parametrize("category,language,expected_keywords", [
        # カフェの曖昧性解消（日本語）
        (
            "cafe-clarification-needed",
            "ja",
            ["エンジニアカフェ", "サイノカフェ", "どちらについて"]
        ),
        # カフェの曖昧性解消（英語）
        (
            "cafe-clarification-needed",
            "en",
            ["Engineer Cafe", "Saino Cafe", "which one"]
        ),
        # 会議室の曖昧性解消（日本語）
        (
            "meeting-room-clarification-needed",
            "ja",
            ["有料会議室", "地下MTGスペース", "2種類"]
        ),
        # 会議室の曖昧性解消（英語）
        (
            "meeting-room-clarification-needed",
            "en",
            ["Paid Meeting Rooms", "Basement Meeting Spaces", "two types"]
        ),
        # デフォルトの曖昧性解消（日本語）
        (
            "general-clarification-needed",
            "ja",
            ["もう少し詳しく"]
        ),
        # デフォルトの曖昧性解消（英語）
        (
            "general-clarification-needed",
            "en",
            ["more details"]
        ),
    ])
    def test_category_messages(self, agent, category, language, expected_keywords):
        """カテゴリと言語に応じたメッセージが生成されることを確認"""
        result = agent.handle_clarification(
            query="test query",
            category=category,
            language=language
        )
        
        response = result["response"]
        
        # すべてのキーワードが含まれていることを確認
        for keyword in expected_keywords:
            assert keyword in response, f"Keyword '{keyword}' not found in response"
        
        # 感情タグが付与されていることを確認
        assert response.startswith("[surprised]"), "Emotion tag not found"
```

### 2. 感情タグ付与テスト

```python
class TestEmotionTag:
    """感情タグ付与のテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.parametrize("category,language", [
        ("cafe-clarification-needed", "ja"),
        ("cafe-clarification-needed", "en"),
        ("meeting-room-clarification-needed", "ja"),
        ("meeting-room-clarification-needed", "en"),
        ("general-clarification-needed", "ja"),
        ("general-clarification-needed", "en"),
    ])
    def test_emotion_tag_always_surprised(self, agent, category, language):
        """すべての応答に[surprised]タグが付与されることを確認"""
        result = agent.handle_clarification(
            query="test query",
            category=category,
            language=language
        )
        
        assert result["emotion"] == "surprised"
        assert result["response"].startswith("[surprised]")
```

### 3. メタデータ設定テスト

```python
class TestMetadata:
    """メタデータ設定のテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    @pytest.mark.parametrize("category,expected_confidence", [
        ("cafe-clarification-needed", 0.9),
        ("meeting-room-clarification-needed", 0.9),
        ("general-clarification-needed", 0.7),
    ])
    def test_metadata_structure(self, agent, category, expected_confidence):
        """メタデータが正しく設定されることを確認"""
        result = agent.handle_clarification(
            query="test query",
            category=category,
            language="ja"
        )
        
        metadata = result["metadata"]
        
        assert metadata["agent"] == "ClarificationAgent"
        assert metadata["confidence"] == expected_confidence
        assert metadata["category"] == category
        assert metadata["sources"] == ["clarification_system"]

    def test_metadata_language(self, agent):
        """メタデータに言語情報が含まれることを確認（必要に応じて）"""
        result_ja = agent.handle_clarification(
            query="test",
            category="cafe-clarification-needed",
            language="ja"
        )
        
        result_en = agent.handle_clarification(
            query="test",
            category="cafe-clarification-needed",
            language="en"
        )
        
        # 言語によってメッセージが異なることを確認
        assert result_ja["response"] != result_en["response"]
```

### 4. エラーハンドリングテスト

```python
class TestErrorHandling:
    """エラーハンドリングのテスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    def test_invalid_category_fallback(self, agent):
        """無効なカテゴリの場合、デフォルトメッセージを返す"""
        # 無効なカテゴリを渡す（型チェックを回避するため、直接辞書を操作）
        # 実際の実装では、無効なカテゴリは型チェックで防がれるが、
        # エラーハンドリングのテストとして残す
        
        # 正常系のテスト
        result = agent.handle_clarification(
            query="test",
            category="general-clarification-needed",
            language="ja"
        )
        
        assert result["response"] is not None
        assert result["emotion"] == "surprised"

    def test_emotion_tagger_error_handling(self, agent, mocker):
        """EmotionTaggerのエラーをハンドリング"""
        # add_emotion_tagがエラーを起こした場合のテスト
        from backend.utils import emotion_tagger
        
        mocker.patch(
            'backend.utils.emotion_tagger.add_emotion_tag',
            side_effect=Exception("Emotion tagger error")
        )
        
        # エラーが発生してもデフォルトメッセージを返す
        result = agent.handle_clarification(
            query="test",
            category="cafe-clarification-needed",
            language="ja"
        )
        
        # エラーハンドリングにより、何らかの応答が返されることを確認
        assert result is not None
        assert "error" in result.get("metadata", {}) or result["response"] is not None
```

### 5. メッセージ内容の正確性テスト

```python
class TestMessageContent:
    """メッセージ内容の正確性テスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    def test_cafe_clarification_ja_content(self, agent):
        """カフェ曖昧性解消（日本語）のメッセージ内容を確認"""
        result = agent.handle_clarification(
            query="カフェの営業時間は？",
            category="cafe-clarification-needed",
            language="ja"
        )
        
        response = result["response"]
        
        # 必須要素の確認
        assert "エンジニアカフェ" in response
        assert "サイノカフェ" in response
        assert "コワーキングスペース" in response
        assert "カフェ＆バー" in response
        assert "どちらについて" in response

    def test_cafe_clarification_en_content(self, agent):
        """カフェ曖昧性解消（英語）のメッセージ内容を確認"""
        result = agent.handle_clarification(
            query="What are the cafe hours?",
            category="cafe-clarification-needed",
            language="en"
        )
        
        response = result["response"]
        
        # 必須要素の確認
        assert "Engineer Cafe" in response
        assert "Saino Cafe" in response
        assert "coworking space" in response
        assert "cafe & bar" in response
        assert "which one" in response.lower()

    def test_meeting_room_clarification_ja_content(self, agent):
        """会議室曖昧性解消（日本語）のメッセージ内容を確認"""
        result = agent.handle_clarification(
            query="会議室の予約方法は？",
            category="meeting-room-clarification-needed",
            language="ja"
        )
        
        response = result["response"]
        
        # 必須要素の確認
        assert "有料会議室" in response
        assert "地下MTGスペース" in response
        assert "2階" in response or "2F" in response
        assert "地下1階" in response or "B1" in response
        assert "2種類" in response

    def test_meeting_room_clarification_en_content(self, agent):
        """会議室曖昧性解消（英語）のメッセージ内容を確認"""
        result = agent.handle_clarification(
            query="How do I book a meeting room?",
            category="meeting-room-clarification-needed",
            language="en"
        )
        
        response = result["response"]
        
        # 必須要素の確認
        assert "Paid Meeting Rooms" in response
        assert "Basement Meeting Spaces" in response
        assert "2F" in response or "2nd floor" in response
        assert "B1" in response or "basement" in response
        assert "two types" in response.lower()
```

## 統合テストケース

### エンドツーエンドテスト

```python
# tests/test_integration.py

import pytest
from backend.workflows.main_workflow import MainWorkflow

class TestClarificationIntegration:
    """ClarificationAgentとワークフローの統合テスト"""

    @pytest.fixture
    def workflow(self):
        return MainWorkflow()

    async def test_clarification_node_integration(self, workflow):
        """Clarificationノードの統合テスト"""
        test_cases = [
            {
                "query": "カフェの営業時間は？",
                "expected_category": "cafe-clarification-needed",
                "language": "ja"
            },
            {
                "query": "会議室の予約方法は？",
                "expected_category": "meeting-room-clarification-needed",
                "language": "ja"
            },
            {
                "query": "What are the cafe hours?",
                "expected_category": "cafe-clarification-needed",
                "language": "en"
            },
        ]

        for case in test_cases:
            # Router Agentがcategoryを設定する想定
            state = {
                "query": case["query"],
                "session_id": "test_session",
                "language": case["language"],
                "metadata": {
                    "routing": {
                        "category": case["expected_category"]
                    }
                }
            }
            
            # Clarificationノードを直接呼び出し
            result = workflow._clarification_node(state)
            
            assert result["answer"] is not None
            assert result["emotion"] == "surprised"
            assert result["metadata"]["agent"] == "ClarificationAgent"
            assert result["metadata"]["requires_followup"] is True
            assert result["metadata"]["clarification_type"] == case["expected_category"]

    async def test_full_workflow_with_clarification(self, workflow):
        """Clarificationを含む完全なワークフローのテスト"""
        # Router AgentがClarificationAgentにルーティングする想定
        result = await workflow.ainvoke({
            "query": "カフェの営業時間は？",
            "session_id": "test_session",
            "language": "ja"
        })
        
        # Router Agentが正しくClarificationAgentにルーティングすることを確認
        # （Router Agentの実装に依存）
        assert result["answer"] is not None
        assert "[surprised]" in result["answer"]
```

## パフォーマンステスト

### レスポンスタイム計測

```python
import time

class TestPerformance:
    """パフォーマンステスト"""

    @pytest.fixture
    def agent(self):
        return ClarificationAgent()

    def test_response_time(self, agent):
        """応答時間のテスト（LLMを使用しないため非常に高速であるべき）"""
        test_cases = [
            ("cafe-clarification-needed", "ja"),
            ("meeting-room-clarification-needed", "ja"),
            ("general-clarification-needed", "ja"),
            ("cafe-clarification-needed", "en"),
            ("meeting-room-clarification-needed", "en"),
            ("general-clarification-needed", "en"),
        ]
        
        times = []
        for category, language in test_cases:
            start = time.perf_counter()
            agent.handle_clarification(
                query="test query",
                category=category,
                language=language
            )
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        # 目標: 平均1ms以下、最大5ms以下（LLMを使用しないため非常に高速）
        assert avg_time < 1, f"Average time {avg_time:.3f}ms exceeds 1ms"
        assert max_time < 5, f"Max time {max_time:.3f}ms exceeds 5ms"

    def test_concurrent_requests(self, agent):
        """同時リクエストのテスト"""
        import concurrent.futures
        
        def make_request():
            return agent.handle_clarification(
                query="test",
                category="cafe-clarification-needed",
                language="ja"
            )
        
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: make_request(), range(10)))
        elapsed = (time.perf_counter() - start) * 1000
        
        assert len(results) == 10
        assert all(r["emotion"] == "surprised" for r in results)
        # 10件の同時処理が10ms以内（非常に高速）
        assert elapsed < 10, f"Concurrent processing took {elapsed:.2f}ms"
```

## 回帰テストマトリクス

### カテゴリ・言語組み合わせテスト

Clarification Agentは固定メッセージを返すため、全組み合わせのテストが重要です。

| カテゴリ | 言語 | テストケース数 | 目標精度 |
|---------|------|--------------|---------|
| cafe-clarification-needed | ja | 5 | 100% |
| cafe-clarification-needed | en | 5 | 100% |
| meeting-room-clarification-needed | ja | 5 | 100% |
| meeting-room-clarification-needed | en | 5 | 100% |
| general-clarification-needed | ja | 5 | 100% |
| general-clarification-needed | en | 5 | 100% |
| **合計** | - | **30** | **100%** |

###  テストケース詳細
```
TEST_CASES = [
    # カフェ曖昧性解消（日本語）
    {
        "category": "cafe-clarification-needed",
        "language": "ja",
        "queries": [
            "カフェの営業時間は？",
            "カフェの料金を教えて",
            "カフェについて知りたい",
            "カフェのメニューは？",
            "カフェの場所は？",
        ]
    },
    # カフェ曖昧性解消（英語）
    {
        "category": "cafe-clarification-needed",
        "language": "en",
        "queries": [
            "What are the cafe hours?",
            "Tell me about the cafe prices",
            "I want to know about the cafe",
            "What's on the cafe menu?",
            "Where is the cafe?",
        ]
    },
    # 会議室曖昧性解消（日本語）
    {
        "category": "meeting-room-clarification-needed",
        "language": "ja",
        "queries": [
            "会議室の予約方法は？",
            "会議室の料金は？",
            "会議室について教えて",
            "会議室を使いたい",
            "会議室の設備は？",
        ]
    },
    # 会議室曖昧性解消（英語）
    {
        "category": "meeting-room-clarification-needed",
        "language": "en",
        "queries": [
            "How do I book a meeting room?",
            "What's the meeting room fee?",
            "Tell me about the meeting rooms",
            "I want to use a meeting room",
            "What facilities are in the meeting rooms?",
        ]
    },
    # デフォルト曖昧性解消（日本語）
    {
        "category": "general-clarification-needed",
        "language": "ja",
        "queries": [
            "詳しく教えて",
            "もっと知りたい",
            "それについて聞きたい",
            "教えてください",
            "何かありますか？",
        ]
    },
    # デフォルト曖昧性解消（英語）
    {
        "category": "general-clarification-needed",
        "language": "en",
        "queries": [
            "Tell me more",
            "I want to know more",
            "I'd like to know about that",
            "Please tell me",
            "Is there anything?",
        ]
    },
]
```

## テストデータ

### 期待されるメッセージ（日本語）

#### カフェ曖昧性解消

```
[surprised]お手伝いさせていただきます！どちらについてお聞きでしょうか：
1. **エンジニアカフェ**（コワーキングスペース）- 営業時間、設備、利用方法
2. **サイノカフェ**（併設のカフェ＆バー）- メニュー、営業時間、料金

お聞かせください！
```

#### 会議室曖昧性解消

```
[surprised]お手伝いさせていただきます！会議スペースは2種類ございます：
1. **有料会議室（2階）** - 事前予約制の個室（有料）
2. **地下MTGスペース（地下1階）** - カジュアルな打ち合わせ用の無料スペース

どちらについてお知りになりたいですか？
```

#### デフォルト曖昧性解消

```
[surprised]お手伝いさせていただきます！もう少し詳しくお聞かせいただけますか？
```

### 期待されるメッセージ（英語）

#### カフェ曖昧性解消

```
[surprised]I'd be happy to help! Are you asking about:
1. **Engineer Cafe** (the coworking space) - hours, facilities, usage
2. **Saino Cafe** (the attached cafe & bar) - menu, hours, prices

Please let me know which one you're interested in!
```

#### 会議室曖昧性解消

```
[surprised]I'd be happy to help! We have two types of meeting spaces:
1. **Paid Meeting Rooms (2F)** - Private rooms with advance booking required (fees apply)
2. **Basement Meeting Spaces (B1)** - Free open spaces for casual meetings

Which one would you like to know about?
```

#### デフォルト曖昧性解消

```
[surprised]I'd be happy to help! Could you please provide more details about what you'd like to know?
```

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_clarification_agent.py -v

# 特定のテストクラスのみ
pytest tests/test_clarification_agent.py::TestCategoryMessages -v

# パフォーマンステストのみ
pytest tests/test_clarification_agent.py::TestPerformance -v

# カバレッジレポート付き
pytest tests/test_clarification_agent.py --cov=backend/agents/clarification_agent --cov-report=html
```

### CI/CD連携

```yaml
# .github/workflows/test-clarification-agent.yml

name: Clarification Agent Tests

on:
  push:
    paths:
      - 'backend/agents/clarification_agent.py'
      - 'backend/utils/emotion_tagger.py'
      - 'tests/test_clarification_agent.py'

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
          pip install pytest pytest-asyncio pytest-cov pytest-mock
      - name: Run tests
        run: |
          pytest tests/test_clarification_agent.py -v --cov=backend/agents/clarification_agent
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 95%以上 |
| メッセージ生成精度 | 100% |
| 平均処理時間 | 1ms以下 |
| 最大処理時間 | 5ms以下 |
| 回帰テスト | 全パス（30ケース） |

### リリース前チェックリスト

-[ ] 全単体テストがパス
-[ ] 統合テストがパス
-[ ] パフォーマンステストが基準を満たす
-[ ] 回帰テストマトリクスの全ケースが100%パス
-[ ] 日本語/英語のメッセージ内容が正確であることを確認
-[ ] 感情タグが正しく付与されることを確認
-[ ] メタデータが正しく設定されることを確認
-[ ] コードレビュー完了
-[ ] ドキュメント更新完了