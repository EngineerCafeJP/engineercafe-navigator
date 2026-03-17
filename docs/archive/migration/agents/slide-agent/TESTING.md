# Slide Agent (SlideNarrator) - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

SlideNarrator は音声ナレーション、キャラクター制御、スライドナビゲーションを統合した複雑なエージェントです。各機能を個別にテストし、統合テストで全体の動作を検証します。

### テストレベル

| レベル | 対象 | 目的 |
|-------|------|------|
| 単体テスト | 各メソッド | 個別機能の検証 |
| 統合テスト | ワークフロー連携 | エンドツーエンド検証 |
| パフォーマンステスト | 音声生成・スライド遷移 | レスポンス時間計測 |
| 回帰テスト | 全ナビゲーションパターン | 既存機能の維持確認 |

## 単体テストケース

### 1. ナレーション読み込みテスト

```python
# tests/test_slide_narrator.py

import pytest
from backend.agents.slide_narrator import SlideNarrator
from backend.tools.narration_loader import NarrationLoader
from backend.memory.simple_memory import SimpleMemory

class TestNarrationLoading:
    """ナレーション読み込みのテスト"""

    @pytest.fixture
    def narrator(self):
        return SlideNarrator(
            model=None,  # モックモデル
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("slide_file,language,expected_slides", [
        ("engineer-cafe", "ja", 10),
        ("engineer-cafe", "en", 10),
    ])
    async def test_load_narration_success(
        self,
        narrator,
        slide_file,
        language,
        expected_slides
    ):
        """正常にナレーションを読み込めることを確認"""
        await narrator.load_narration(slide_file, language)

        assert narrator.narration_data is not None
        assert narrator.total_slides == expected_slides
        assert narrator.current_slide == 1
        assert len(narrator.narration_data['slides']) == expected_slides

    @pytest.mark.asyncio
    async def test_load_narration_invalid_file(self, narrator):
        """存在しないファイルでエラーが発生することを確認"""
        with pytest.raises(FileNotFoundError):
            await narrator.load_narration("nonexistent", "ja")

    @pytest.mark.asyncio
    async def test_load_narration_invalid_language(self, narrator):
        """サポートされていない言語でエラーが発生することを確認"""
        with pytest.raises(FileNotFoundError):
            await narrator.load_narration("engineer-cafe", "fr")

    @pytest.mark.asyncio
    async def test_narration_data_structure(self, narrator):
        """ナレーションデータの構造を検証"""
        await narrator.load_narration("engineer-cafe", "ja")

        # メタデータの検証
        assert 'metadata' in narrator.narration_data
        assert narrator.narration_data['metadata']['language'] == 'ja'
        assert 'title' in narrator.narration_data['metadata']

        # スライドデータの検証
        for slide in narrator.narration_data['slides']:
            assert 'slideNumber' in slide
            assert 'narration' in slide
            assert 'auto' in slide['narration']
            assert 'transitions' in slide
```

### 2. スライドナレーションテスト

```python
class TestSlideNarration:
    """スライドナレーションのテスト"""

    @pytest.fixture
    async def loaded_narrator(self):
        """ナレーション読み込み済みのナレーター"""
        narrator = SlideNarrator(
            model=None,
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )
        await narrator.load_narration("engineer-cafe", "ja")
        return narrator

    @pytest.mark.asyncio
    async def test_narrate_current_slide(self, loaded_narrator):
        """現在のスライドをナレーション"""
        result = await loaded_narrator.narrate_slide()

        assert result.slide_number == 1
        assert result.narration is not None
        assert len(result.narration) > 0
        assert result.character_action in [
            'greeting', 'presenting', 'explaining', 'bowing', 'neutral'
        ]
        assert result.emotion in [
            'happy', 'explaining', 'confident', 'grateful', 'curious', 'neutral'
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("slide_number,expected_action", [
        (1, "greeting"),      # "ようこそ" を含む
        (3, "neutral"),       # 一般的な説明
        (10, "neutral"),      # 最終スライド
    ])
    async def test_narrate_specific_slide(
        self,
        loaded_narrator,
        slide_number,
        expected_action
    ):
        """特定のスライドをナレーション"""
        result = await loaded_narrator.narrate_slide(slide_number)

        assert result.slide_number == slide_number
        assert result.character_action == expected_action

    @pytest.mark.asyncio
    async def test_narrate_invalid_slide_number(self, loaded_narrator):
        """無効なスライド番号でエラー"""
        with pytest.raises(ValueError, match="Invalid slide number"):
            await loaded_narrator.narrate_slide(0)

        with pytest.raises(ValueError, match="Invalid slide number"):
            await loaded_narrator.narrate_slide(999)

    @pytest.mark.asyncio
    async def test_narrate_without_loading(self):
        """ナレーション未読み込みでエラー"""
        narrator = SlideNarrator(
            model=None,
            memory=SimpleMemory()
        )

        with pytest.raises(ValueError, match="No narration data loaded"):
            await narrator.narrate_slide()
```

### 3. スライドナビゲーションテスト

```python
class TestSlideNavigation:
    """スライドナビゲーションのテスト"""

    @pytest.fixture
    async def loaded_narrator(self):
        narrator = SlideNarrator(
            model=None,
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )
        await narrator.load_narration("engineer-cafe", "ja")
        return narrator

    @pytest.mark.asyncio
    async def test_next_slide_success(self, loaded_narrator):
        """次のスライドへ正常に移動"""
        result = await loaded_narrator.next_slide()

        assert result.success is True
        assert result.slide_number == 2
        assert result.narration is not None
        assert result.transition_message is not None

    @pytest.mark.asyncio
    async def test_next_slide_at_last_slide(self, loaded_narrator):
        """最後のスライドで次へ移動を試みる"""
        # 最後のスライドへ移動
        loaded_narrator.current_slide = loaded_narrator.total_slides

        result = await loaded_narrator.next_slide()

        assert result.success is False
        assert "最後のスライド" in result.transition_message

    @pytest.mark.asyncio
    async def test_previous_slide_success(self, loaded_narrator):
        """前のスライドへ正常に移動"""
        # スライド2へ移動
        loaded_narrator.current_slide = 2

        result = await loaded_narrator.previous_slide()

        assert result.success is True
        assert result.slide_number == 1
        assert result.narration is not None

    @pytest.mark.asyncio
    async def test_previous_slide_at_first_slide(self, loaded_narrator):
        """最初のスライドで前へ移動を試みる"""
        result = await loaded_narrator.previous_slide()

        assert result.success is False
        assert "最初のスライド" in result.transition_message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("target_slide", [1, 5, 10])
    async def test_goto_slide_success(self, loaded_narrator, target_slide):
        """指定スライドへ正常に移動"""
        result = await loaded_narrator.goto_slide(target_slide)

        assert result.success is True
        assert result.slide_number == target_slide

    @pytest.mark.asyncio
    @pytest.mark.parametrize("invalid_slide", [0, -1, 999])
    async def test_goto_slide_invalid(self, loaded_narrator, invalid_slide):
        """無効なスライド番号での移動は失敗"""
        result = await loaded_narrator.goto_slide(invalid_slide)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_navigation_sequence(self, loaded_narrator):
        """スライドナビゲーションのシーケンステスト"""
        # 1 → 2 → 3 → 2 → 5
        await loaded_narrator.next_slide()  # 2
        assert loaded_narrator.current_slide == 2

        await loaded_narrator.next_slide()  # 3
        assert loaded_narrator.current_slide == 3

        await loaded_narrator.previous_slide()  # 2
        assert loaded_narrator.current_slide == 2

        await loaded_narrator.goto_slide(5)  # 5
        assert loaded_narrator.current_slide == 5
```

### 4. 質問応答テスト

```python
class TestSlideQuestionAnswering:
    """スライド質問応答のテスト"""

    @pytest.fixture
    async def loaded_narrator(self):
        narrator = SlideNarrator(
            model=MockLLM(),  # モックLLM
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )
        await narrator.load_narration("engineer-cafe", "ja")
        return narrator

    @pytest.mark.asyncio
    @pytest.mark.parametrize("question,expected_keyword", [
        ("詳しく教えて", "2019年8月"),           # onDemand応答
        ("無料ですか？", "完全無料"),             # onDemand応答
        ("場所はどこ？", "赤煉瓦文化館"),         # onDemand応答
    ])
    async def test_on_demand_answers(
        self,
        loaded_narrator,
        question,
        expected_keyword
    ):
        """onDemand応答のテスト"""
        answer = await loaded_narrator.answer_slide_question(question)

        assert answer is not None
        assert expected_keyword in answer

    @pytest.mark.asyncio
    async def test_dynamic_answer_generation(self, loaded_narrator):
        """LLMによる動的応答生成のテスト"""
        # onDemandに定義されていない質問
        question = "このスライドのポイントは何ですか？"

        answer = await loaded_narrator.answer_slide_question(question)

        assert answer is not None
        assert len(answer) > 0

    @pytest.mark.asyncio
    async def test_question_without_narration_data(self):
        """ナレーション未読み込み時の質問でエラー"""
        narrator = SlideNarrator(model=MockLLM(), memory=SimpleMemory())

        with pytest.raises(ValueError, match="No narration data loaded"):
            await narrator.answer_slide_question("質問")

    @pytest.mark.asyncio
    async def test_slide_4_facility_questions(self, loaded_narrator):
        """スライド4（地下施設）の質問応答"""
        # スライド4へ移動
        await loaded_narrator.goto_slide(4)

        test_cases = [
            ("ミーティングスペースについて", "2名以上"),
            ("集中スペースについて", "6ブース"),
            ("Makersスペースについて", "3Dプリンタ"),
        ]

        for question, expected_keyword in test_cases:
            answer = await loaded_narrator.answer_slide_question(question)
            assert expected_keyword in answer
```

### 5. キャラクターアクション決定テスト

```python
class TestCharacterActionDetermination:
    """キャラクターアクション決定のテスト"""

    @pytest.fixture
    def narrator(self):
        return SlideNarrator(model=None, memory=SimpleMemory())

    @pytest.mark.parametrize("narration_text,expected_action", [
        ("皆さん、エンジニアカフェへようこそ", "greeting"),
        ("サービスについてご説明します", "presenting"),
        ("料金は以下の通りです", "explaining"),
        ("ご利用ありがとうございました", "bowing"),
        ("通常のナレーション", "neutral"),
        ("Welcome to Engineer Cafe", "greeting"),
        ("Our service includes", "presenting"),
        ("The price is", "explaining"),
        ("Thank you for visiting", "bowing"),
    ])
    def test_determine_character_action(
        self,
        narrator,
        narration_text,
        expected_action
    ):
        """ナレーション内容からキャラクターアクションを決定"""
        slide_data = {
            'narration': {'auto': narration_text}
        }

        action = narrator._determine_character_action(slide_data)
        assert action == expected_action
```

### 6. 感情抽出テスト

```python
class TestEmotionExtraction:
    """感情抽出のテスト"""

    @pytest.fixture
    def narrator(self):
        return SlideNarrator(model=None, memory=SimpleMemory())

    @pytest.mark.parametrize("narration_text,expected_emotion", [
        ("ようこそ、エンジニアカフェへ", "happy"),
        ("料金についてご説明します", "explaining"),
        ("サービスの特徴をお伝えします", "confident"),
        ("ご質問はございますか？", "curious"),
        ("ありがとうございました", "grateful"),
        ("通常のナレーション", "neutral"),
        ("Welcome to the cafe", "happy"),
        ("The cost is 100 yen", "explaining"),
        ("Our service features", "confident"),
        ("Do you have any questions?", "curious"),
        ("Thank you very much", "grateful"),
    ])
    def test_extract_emotion(
        self,
        narrator,
        narration_text,
        expected_emotion
    ):
        """ナレーション内容から感情を抽出"""
        slide_data = {
            'narration': {'auto': narration_text}
        }

        emotion = narrator._extract_emotion_from_slide_content(slide_data)
        assert emotion == expected_emotion
```

### 7. 自動再生テスト

```python
class TestAutoPlay:
    """自動再生のテスト"""

    @pytest.fixture
    async def loaded_narrator(self):
        narrator = SlideNarrator(
            model=None,
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )
        await narrator.load_narration("engineer-cafe", "ja")
        return narrator

    @pytest.mark.asyncio
    async def test_set_auto_play_enabled(self, loaded_narrator):
        """自動再生を有効化"""
        await loaded_narrator.set_auto_play(True, 5000)

        assert loaded_narrator.auto_play is True
        assert await loaded_narrator.memory.get('autoPlay') is True
        assert await loaded_narrator.memory.get('autoPlayInterval') == 5000

    @pytest.mark.asyncio
    async def test_set_auto_play_disabled(self, loaded_narrator):
        """自動再生を無効化"""
        await loaded_narrator.set_auto_play(False)

        assert loaded_narrator.auto_play is False
        assert await loaded_narrator.memory.get('autoPlay') is False

    @pytest.mark.asyncio
    async def test_stop_auto_play(self, loaded_narrator):
        """自動再生を停止"""
        await loaded_narrator.set_auto_play(True)
        await loaded_narrator.stop_auto_play()

        assert loaded_narrator.auto_play is False
```

## 統合テストケース

### エンドツーエンドテスト

```python
# tests/test_presentation_workflow.py

import pytest
from backend.workflows.presentation_workflow import PresentationWorkflow
from backend.agents.slide_narrator import SlideNarrator

class TestPresentationWorkflow:
    """プレゼンテーションワークフローの統合テスト"""

    @pytest.fixture
    def workflow(self):
        narrator = SlideNarrator(
            model=MockLLM(),
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )
        return PresentationWorkflow(narrator)

    @pytest.mark.asyncio
    async def test_full_presentation_flow(self, workflow):
        """完全なプレゼンテーションフローのテスト"""
        # ナレーション読み込み
        result = await workflow.graph.ainvoke({
            "slide_file": "engineer-cafe",
            "language": "ja",
            "action": "load",
            "slide_number": None,
            "question": None
        })
        assert result['error'] is None

        # 次スライドへ移動
        result = await workflow.graph.ainvoke({
            "slide_file": "engineer-cafe",
            "language": "ja",
            "action": "next",
            "slide_number": None,
            "question": None
        })
        assert result['result']['success'] is True
        assert result['result']['slide_number'] == 2

        # 特定スライドへ移動
        result = await workflow.graph.ainvoke({
            "slide_file": "engineer-cafe",
            "language": "ja",
            "action": "goto",
            "slide_number": 5,
            "question": None
        })
        assert result['result']['success'] is True
        assert result['result']['slide_number'] == 5

        # 質問応答
        result = await workflow.graph.ainvoke({
            "slide_file": "engineer-cafe",
            "language": "ja",
            "action": "question",
            "slide_number": None,
            "question": "このスライドについて教えて"
        })
        assert result['result']['answer'] is not None

    @pytest.mark.asyncio
    async def test_complete_navigation_sequence(self, workflow):
        """完全なナビゲーションシーケンステスト"""
        # ナレーション読み込み
        await workflow.graph.ainvoke({
            "slide_file": "engineer-cafe",
            "language": "ja",
            "action": "load",
            "slide_number": None,
            "question": None
        })

        # スライド1→10まで全て移動
        for i in range(1, 11):
            if i > 1:
                result = await workflow.graph.ainvoke({
                    "slide_file": "engineer-cafe",
                    "language": "ja",
                    "action": "next",
                    "slide_number": None,
                    "question": None
                })
                assert result['result']['slide_number'] == i

        # 最終スライドで次へ移動を試みる
        result = await workflow.graph.ainvoke({
            "slide_file": "engineer-cafe",
            "language": "ja",
            "action": "next",
            "slide_number": None,
            "question": None
        })
        assert result['result']['success'] is False
```

## パフォーマンステスト

### レスポンスタイム計測

```python
import time

class TestPerformance:
    """パフォーマンステスト"""

    @pytest.fixture
    async def loaded_narrator(self):
        narrator = SlideNarrator(
            model=MockLLM(),
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )
        await narrator.load_narration("engineer-cafe", "ja")
        return narrator

    @pytest.mark.asyncio
    async def test_narration_loading_time(self):
        """ナレーション読み込み時間のテスト"""
        narrator = SlideNarrator(
            model=None,
            memory=SimpleMemory(),
            narration_loader=NarrationLoader()
        )

        start = time.perf_counter()
        await narrator.load_narration("engineer-cafe", "ja")
        elapsed = (time.perf_counter() - start) * 1000  # ms

        # 目標: 100ms以下
        assert elapsed < 100, f"Loading took {elapsed:.2f}ms, expected < 100ms"

    @pytest.mark.asyncio
    async def test_slide_navigation_time(self, loaded_narrator):
        """スライドナビゲーション時間のテスト"""
        times = []

        for _ in range(5):
            start = time.perf_counter()
            await loaded_narrator.next_slide()
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        # 目標: 平均50ms以下（音声生成を除く）
        assert avg_time < 50, f"Average navigation time {avg_time:.2f}ms, expected < 50ms"

    @pytest.mark.asyncio
    async def test_question_answering_time(self, loaded_narrator):
        """質問応答時間のテスト"""
        questions = [
            "詳しく教えて",
            "無料ですか？",
            "場所はどこ？"
        ]

        times = []
        for question in questions:
            start = time.perf_counter()
            await loaded_narrator.answer_slide_question(question)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 目標: 平均200ms以下、最大500ms以下
        assert avg_time < 200, f"Average time {avg_time:.2f}ms, expected < 200ms"
        assert max_time < 500, f"Max time {max_time:.2f}ms, expected < 500ms"
```

## 回帰テストマトリクス

### 機能カバレッジテスト

| カテゴリ | テストケース数 | 目標成功率 |
|---------|--------------|----------|
| ナレーション読み込み | 5 | 100% |
| スライドナレーション | 8 | 100% |
| スライドナビゲーション | 12 | 100% |
| 質問応答（onDemand） | 10 | 100% |
| 質問応答（動的） | 5 | 90% |
| キャラクターアクション | 9 | 100% |
| 感情抽出 | 11 | 100% |
| 自動再生 | 4 | 100% |
| エラーハンドリング | 6 | 100% |
| **合計** | **70** | **98%以上** |

## テスト実行方法

### ローカル実行

```bash
# 全テスト実行
pytest tests/test_slide_narrator.py -v

# 特定のテストクラスのみ
pytest tests/test_slide_narrator.py::TestSlideNavigation -v

# パフォーマンステストのみ
pytest tests/test_slide_narrator.py::TestPerformance -v

# カバレッジレポート付き
pytest tests/test_slide_narrator.py --cov=backend/agents/slide_narrator --cov-report=html

# 非同期テストのみ
pytest tests/test_slide_narrator.py -m asyncio
```

### CI/CD連携

```yaml
# .github/workflows/test-slide-agent.yml

name: Slide Agent Tests

on:
  push:
    paths:
      - 'backend/agents/slide_narrator.py'
      - 'backend/tools/narration_loader.py'
      - 'backend/workflows/presentation_workflow.py'
      - 'tests/test_slide_narrator.py'
      - 'backend/data/narrations/*.json'

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
          pytest tests/test_slide_narrator.py -v --cov=backend/agents/slide_narrator
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## モックオブジェクト

### MockLLM

```python
# tests/mocks/mock_llm.py

class MockLLM:
    """LLMのモック"""

    async def ainvoke(self, messages):
        """モック応答を返す"""
        class MockResponse:
            content = "これはモックの応答です。スライドの内容について説明しています。"

        return MockResponse()
```

### MockTTSService

```python
# tests/mocks/mock_tts.py

import base64

class MockTTSService:
    """TTSサービスのモック"""

    async def text_to_speech(self, text: str, language: str) -> dict:
        """モック音声データを返す"""
        # ダミーの音声データ
        dummy_audio = b"mock_audio_data"
        audio_base64 = base64.b64encode(dummy_audio).decode('utf-8')

        return {
            'success': True,
            'audioBase64': audio_base64
        }
```

## 品質基準

### 合格基準

| 項目 | 基準 |
|-----|------|
| 単体テストカバレッジ | 95%以上 |
| 機能テスト成功率 | 98%以上 |
| ナレーション読み込み時間 | 100ms以下 |
| スライドナビゲーション時間 | 50ms以下（音声生成除く） |
| 質問応答時間（onDemand） | 平均200ms以下 |
| 質問応答時間（動的） | 平均2000ms以下 |
| 回帰テスト | 全パス |

### リリース前チェックリスト

- [ ] 全単体テストがパス
- [ ] 統合テストがパス
- [ ] パフォーマンステストが基準を満たす
- [ ] 全ナレーションファイルが正しく読み込める
- [ ] 全スライドへの移動が正常に動作する
- [ ] onDemand応答が全て正しく機能する
- [ ] キャラクターアクション決定が正確
- [ ] 感情抽出が正確
- [ ] エラーハンドリングが適切
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了

## デバッグツール

### ナレーションデータビューア

```python
# tools/debug/narration_viewer.py

import json
from pathlib import Path

def view_narration_data(slide_file: str, language: str):
    """ナレーションデータを読みやすく表示"""
    file_path = Path(f"backend/data/narrations/{slide_file}-{language}.json")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"=== {data['metadata']['title']} ===")
    print(f"Language: {data['metadata']['language']}")
    print(f"Total Slides: {len(data['slides'])}\n")

    for slide in data['slides']:
        print(f"--- Slide {slide['slideNumber']} ---")
        print(f"Auto: {slide['narration']['auto']}")
        if 'onDemand' in slide['narration']:
            print(f"On-Demand Keywords: {list(slide['narration']['onDemand'].keys())}")
        print()

# 使用例
view_narration_data("engineer-cafe", "ja")
```

### スライドナビゲーションシミュレーター

```python
# tools/debug/navigation_simulator.py

import asyncio
from backend.agents.slide_narrator import SlideNarrator

async def simulate_navigation():
    """スライドナビゲーションをシミュレート"""
    narrator = SlideNarrator(
        model=None,
        memory=SimpleMemory(),
        narration_loader=NarrationLoader()
    )

    await narrator.load_narration("engineer-cafe", "ja")

    print(f"Total Slides: {narrator.total_slides}")

    # 全スライドを移動
    for i in range(1, narrator.total_slides + 1):
        result = await narrator.goto_slide(i)
        print(f"Slide {i}: {result.character_action} - {result.emotion}")
        print(f"  Narration: {result.narration[:50]}...")

# 実行
asyncio.run(simulate_navigation())
```

## 参考リンク

- [pytest ドキュメント](https://docs.pytest.org/)
- [pytest-asyncio ドキュメント](https://pytest-asyncio.readthedocs.io/)
- [元実装: slide-narrator.ts](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/mastra/agents/slide-narrator.ts)
- [ナレーションデータ例](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/slides/narration/engineer-cafe-ja.json)
