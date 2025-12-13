# Slide Agent (SlideNarrator) - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
engineer-cafe-navigator2025/frontend/src/
├── mastra/agents/slide-narrator.ts    # 446行
├── mastra/tools/narration-loader.ts   # ナレーション読み込みツール
└── slides/narration/
    ├── engineer-cafe-ja.json          # 日本語ナレーション
    └── engineer-cafe-en.json          # 英語ナレーション
```

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   └── slide_narrator.py              # 新規作成
├── tools/
│   ├── narration_loader.py            # 新規作成
│   └── text_to_speech.py              # 既存（修正）
├── data/
│   └── narrations/
│       ├── engineer-cafe-ja.json      # コピー
│       └── engineer-cafe-en.json      # コピー
└── workflows/
    └── presentation_workflow.py       # 新規作成
```

## 移行ステップ

### Step 1: ナレーションデータの移行

#### 1.1 JSONファイルのコピー

```bash
# ナレーションデータディレクトリを作成
mkdir -p backend/data/narrations

# ナレーションファイルをコピー
cp frontend/src/slides/narration/*.json backend/data/narrations/
```

#### 1.2 データ構造の検証

```python
# backend/utils/narration_validator.py

import json
from typing import Dict, List, Any
from pathlib import Path

class NarrationValidator:
    """ナレーションデータの検証"""

    @staticmethod
    def validate_narration_file(file_path: Path) -> bool:
        """ナレーションファイルの構造を検証"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # メタデータチェック
            assert 'metadata' in data
            assert 'title' in data['metadata']
            assert 'language' in data['metadata']
            assert 'speaker' in data['metadata']

            # スライドチェック
            assert 'slides' in data
            assert isinstance(data['slides'], list)

            for slide in data['slides']:
                assert 'slideNumber' in slide
                assert 'narration' in slide
                assert 'auto' in slide['narration']
                assert 'transitions' in slide

            return True
        except (AssertionError, json.JSONDecodeError, KeyError) as e:
            print(f"Validation error: {e}")
            return False
```

### Step 2: NarrationLoader ツールの移行

**元ファイル**: `frontend/src/mastra/tools/narration-loader.ts`

```python
# backend/tools/narration_loader.py

import json
from pathlib import Path
from typing import Dict, Any, Literal

SupportedLanguage = Literal["ja", "en"]

class NarrationLoader:
    """ナレーションJSONファイルを読み込むツール"""

    def __init__(self, narrations_dir: str = "backend/data/narrations"):
        self.narrations_dir = Path(narrations_dir)

    async def load(
        self,
        slide_file: str,
        language: SupportedLanguage
    ) -> Dict[str, Any]:
        """
        ナレーションJSONファイルを読み込む

        Args:
            slide_file: スライドファイル名（拡張子なし）
            language: 言語コード ('ja' または 'en')

        Returns:
            ナレーションデータ（辞書形式）

        Raises:
            FileNotFoundError: ファイルが存在しない場合
            json.JSONDecodeError: JSON解析に失敗した場合
        """
        file_path = self.narrations_dir / f"{slide_file}-{language}.json"

        if not file_path.exists():
            raise FileNotFoundError(
                f"Narration file not found: {file_path}"
            )

        with open(file_path, 'r', encoding='utf-8') as f:
            narration_data = json.load(f)

        # データ構造の検証
        self._validate_structure(narration_data)

        return narration_data

    def _validate_structure(self, data: Dict[str, Any]) -> None:
        """ナレーションデータの構造を検証"""
        required_keys = ['metadata', 'slides']
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required key: {key}")

        if not isinstance(data['slides'], list):
            raise ValueError("'slides' must be a list")

        for slide in data['slides']:
            if 'slideNumber' not in slide or 'narration' not in slide:
                raise ValueError("Invalid slide structure")
```

### Step 3: SlideNarrator エージェントの移行

**元ファイル**: `frontend/src/mastra/agents/slide-narrator.ts`

```python
# backend/agents/slide_narrator.py

from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass
import re

from langchain_core.messages import HumanMessage
from backend.tools.narration_loader import NarrationLoader
from backend.tools.text_to_speech import TextToSpeechService
from backend.memory.simple_memory import SimpleMemory

SupportedLanguage = Literal["ja", "en"]

@dataclass
class NarrationResult:
    """ナレーション実行結果"""
    narration: str
    slide_number: int
    audio_buffer: bytes
    character_action: str
    character_control_data: Optional[Dict] = None
    emotion: Optional[str] = None

@dataclass
class NavigationResult:
    """スライドナビゲーション結果"""
    success: bool
    narration: Optional[str] = None
    slide_number: Optional[int] = None
    audio_buffer: Optional[bytes] = None
    character_action: Optional[str] = None
    character_control_data: Optional[Dict] = None
    emotion: Optional[str] = None
    transition_message: Optional[str] = None

class SlideNarrator:
    """スライドナレーションエージェント"""

    def __init__(
        self,
        model: Any,
        memory: Optional[SimpleMemory] = None,
        narration_loader: Optional[NarrationLoader] = None,
        tts_service: Optional[TextToSpeechService] = None
    ):
        self.model = model
        self.memory = memory or SimpleMemory()
        self.narration_loader = narration_loader or NarrationLoader()
        self.tts_service = tts_service or TextToSpeechService()

        # 状態管理
        self.current_slide: int = 1
        self.total_slides: int = 0
        self.auto_play: bool = False
        self.narration_data: Optional[Dict] = None

        # 外部エージェント（オプション）
        self.voice_output_agent: Optional[Any] = None
        self.character_control_agent: Optional[Any] = None

        # エージェント指示
        self.instructions = """You are a slide narration agent for Engineer Cafe presentations.
Your role is to:
1. Provide scripted narration for each slide
2. Handle slide navigation commands
3. Answer questions about slide content
4. Maintain presentation flow and timing
5. Coordinate with slide display and character animation

Deliver narrations in a clear, engaging manner.
Respond to navigation commands promptly.
Provide informative answers to content questions.

IMPORTANT: When answering questions about slides, always start your response with an emotion tag.
Available emotions: [happy], [sad], [angry], [relaxed], [surprised]

Use [relaxed] for informational answers about slide content
Use [happy] when explaining exciting features or benefits
Use [surprised] when the user asks unexpected questions
Use [sad] when unable to find information in the current slide"""

    async def load_narration(
        self,
        slide_file: str,
        language: SupportedLanguage
    ) -> None:
        """
        ナレーションJSONを読み込む

        Args:
            slide_file: スライドファイル名
            language: 言語 ('ja' または 'en')
        """
        self.narration_data = await self.narration_loader.load(
            slide_file, language
        )
        self.total_slides = len(self.narration_data['slides'])
        self.current_slide = 1

        # メモリに保存
        await self.memory.store('currentSlide', self.current_slide)
        await self.memory.store('totalSlides', self.total_slides)
        await self.memory.store('narrationData', self.narration_data)

    async def narrate_slide(
        self,
        slide_number: Optional[int] = None
    ) -> NarrationResult:
        """
        スライドをナレーションする

        Args:
            slide_number: スライド番号（省略時は現在のスライド）

        Returns:
            NarrationResult: ナレーション結果
        """
        target_slide = slide_number or self.current_slide

        if not self.narration_data:
            raise ValueError("No narration data loaded")

        if target_slide < 1 or target_slide > self.total_slides:
            raise ValueError(f"Invalid slide number: {target_slide}")

        # スライドデータを取得
        slide_data = next(
            (s for s in self.narration_data['slides']
             if s['slideNumber'] == target_slide),
            None
        )

        if not slide_data:
            raise ValueError(f"No narration data for slide {target_slide}")

        narration = slide_data['narration']['auto']

        # 言語取得
        language: SupportedLanguage = await self.memory.get('language') or 'ja'

        # キャラクター制御決定
        character_action = self._determine_character_action(slide_data)
        emotion = self._extract_emotion_from_slide_content(slide_data)

        # 音声生成
        audio_buffer: bytes
        character_control_data: Optional[Dict] = None

        if self.voice_output_agent and self.character_control_agent:
            # 統合エージェントを使用
            import asyncio

            voice_result, character_result = await asyncio.gather(
                self.voice_output_agent.convert_text_to_speech(
                    text=narration,
                    language=language,
                    emotion=emotion,
                    agent_name='SlideNarrator'
                ),
                self.character_control_agent.process_character_control(
                    emotion=emotion,
                    text=narration,
                    agent_name='SlideNarrator'
                )
            )

            if not voice_result['success']:
                raise RuntimeError(f"Voice output failed: {voice_result.get('error')}")

            audio_buffer = voice_result['audioData']
            character_control_data = character_result if character_result['success'] else None

            # リップシンク処理
            if character_control_data and audio_buffer:
                lip_sync_result = await self.character_control_agent.process_character_control(
                    audio_data=audio_buffer,
                    agent_name='SlideNarrator'
                )
                if lip_sync_result['success'] and lip_sync_result.get('lipSyncData'):
                    character_control_data['lipSyncData'] = lip_sync_result['lipSyncData']

        else:
            # フォールバック: 直接TTSサービスを使用
            tts_result = await self.tts_service.text_to_speech(
                text=narration,
                language=language
            )

            if not tts_result['success']:
                raise RuntimeError(f"Text-to-Speech failed: {tts_result.get('error')}")

            # Base64からバイトに変換
            import base64
            audio_buffer = base64.b64decode(tts_result['audioBase64'])

        # 現在のスライドを更新
        self.current_slide = target_slide
        await self.memory.store('currentSlide', self.current_slide)

        return NarrationResult(
            narration=narration,
            slide_number=target_slide,
            audio_buffer=audio_buffer,
            character_action=character_action,
            character_control_data=character_control_data,
            emotion=emotion
        )

    async def next_slide(self) -> NavigationResult:
        """次のスライドへ移動"""
        if self.current_slide >= self.total_slides:
            # 言語取得
            language = await self.memory.get('language') or 'ja'
            message = (
                "This is the last slide. Would you like to go back to the beginning or ask any questions?"
                if language == 'en' else
                "最後のスライドです。最初に戻りますか、それとも何かご質問はございますか？"
            )
            return NavigationResult(success=False, transition_message=message)

        # トランジションメッセージ取得
        slide_data = next(
            (s for s in self.narration_data['slides']
             if s['slideNumber'] == self.current_slide),
            None
        )
        transition_message = slide_data.get('transitions', {}).get('next') if slide_data else None

        # 次スライドへ移動
        self.current_slide += 1
        result = await self.narrate_slide(self.current_slide)

        return NavigationResult(
            success=True,
            narration=result.narration,
            slide_number=result.slide_number,
            audio_buffer=result.audio_buffer,
            character_action=result.character_action,
            character_control_data=result.character_control_data,
            emotion=result.emotion,
            transition_message=transition_message
        )

    async def previous_slide(self) -> NavigationResult:
        """前のスライドへ移動"""
        if self.current_slide <= 1:
            # 言語取得
            language = await self.memory.get('language') or 'ja'
            message = (
                "This is the first slide. Would you like to continue forward?"
                if language == 'en' else
                "最初のスライドです。先に進みますか？"
            )
            return NavigationResult(success=False, transition_message=message)

        # トランジションメッセージ取得
        slide_data = next(
            (s for s in self.narration_data['slides']
             if s['slideNumber'] == self.current_slide),
            None
        )
        transition_message = slide_data.get('transitions', {}).get('previous') if slide_data else None

        # 前スライドへ移動
        self.current_slide -= 1
        result = await self.narrate_slide(self.current_slide)

        return NavigationResult(
            success=True,
            narration=result.narration,
            slide_number=result.slide_number,
            audio_buffer=result.audio_buffer,
            character_action=result.character_action,
            character_control_data=result.character_control_data,
            emotion=result.emotion,
            transition_message=transition_message
        )

    async def goto_slide(self, slide_number: int) -> NavigationResult:
        """指定スライドへ移動"""
        if slide_number < 1 or slide_number > self.total_slides:
            return NavigationResult(success=False)

        result = await self.narrate_slide(slide_number)

        return NavigationResult(
            success=True,
            narration=result.narration,
            slide_number=result.slide_number,
            audio_buffer=result.audio_buffer,
            character_action=result.character_action,
            character_control_data=result.character_control_data,
            emotion=result.emotion
        )

    async def answer_slide_question(self, question: str) -> str:
        """
        スライド内容に関する質問に回答

        Args:
            question: 質問文

        Returns:
            回答テキスト
        """
        if not self.narration_data:
            raise ValueError("No narration data loaded")

        # 現在のスライドデータ取得
        current_slide_data = next(
            (s for s in self.narration_data['slides']
             if s['slideNumber'] == self.current_slide),
            None
        )

        # 言語取得
        language = await self.memory.get('language') or 'ja'

        # onDemand応答チェック
        if current_slide_data and 'onDemand' in current_slide_data.get('narration', {}):
            on_demand = current_slide_data['narration']['onDemand']

            # キーワードマッチング
            for keyword, response in on_demand.items():
                if keyword.lower() in question.lower():
                    return response

        # 動的応答生成
        slide_context = str(current_slide_data) if current_slide_data else ''

        prompt = (
            f"Answer this question about slide {self.current_slide}: {question}\nSlide context: {slide_context}"
            if language == 'en' else
            f"スライド{self.current_slide}について以下の質問に答えてください: {question}\nスライドの内容: {slide_context}"
        )

        # LLMで応答生成
        messages = [HumanMessage(content=prompt)]
        response = await self.model.ainvoke(messages)

        return response.content

    def _determine_character_action(self, slide_data: Dict) -> str:
        """スライド内容からキャラクターアクションを決定"""
        narration = slide_data['narration']['auto'].lower()

        if 'welcome' in narration or 'ようこそ' in narration:
            return 'greeting'
        elif 'service' in narration or 'サービス' in narration:
            return 'presenting'
        elif 'price' in narration or '料金' in narration:
            return 'explaining'
        elif 'thank' in narration or 'ありがとう' in narration:
            return 'bowing'
        else:
            return 'neutral'

    def _extract_emotion_from_slide_content(self, slide_data: Dict) -> str:
        """スライド内容から感情を抽出"""
        narration = slide_data['narration']['auto'].lower()

        if any(kw in narration for kw in ['welcome', 'ようこそ', 'hello']):
            return 'happy'
        elif any(kw in narration for kw in ['price', '料金', 'cost']):
            return 'explaining'
        elif any(kw in narration for kw in ['service', 'サービス', 'feature']):
            return 'confident'
        elif any(kw in narration for kw in ['thank', 'ありがとう', 'appreciate']):
            return 'grateful'
        elif any(kw in narration for kw in ['question', '質問', 'help']):
            return 'curious'
        else:
            return 'neutral'

    async def get_current_slide_info(self) -> Dict:
        """現在のスライド情報を取得"""
        slide_data = next(
            (s for s in self.narration_data['slides']
             if s['slideNumber'] == self.current_slide),
            None
        ) if self.narration_data else None

        return {
            'currentSlide': self.current_slide,
            'totalSlides': self.total_slides,
            'slideData': slide_data
        }

    async def set_auto_play(self, enabled: bool, interval: Optional[int] = None) -> None:
        """自動再生設定"""
        self.auto_play = enabled
        await self.memory.store('autoPlay', enabled)

        if enabled and interval:
            await self.memory.store('autoPlayInterval', interval)

    async def start_auto_play(self) -> None:
        """自動再生開始"""
        if not self.auto_play:
            return

        # TODO: 自動進行ロジックの実装
        # 指定間隔でnext_slide()を呼び出す
        pass

    async def stop_auto_play(self) -> None:
        """自動再生停止"""
        self.auto_play = False
        await self.memory.store('autoPlay', False)
```

### Step 4: ワークフローへの統合

```python
# backend/workflows/presentation_workflow.py

from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal

from backend.agents.slide_narrator import SlideNarrator

class PresentationState(TypedDict):
    """プレゼンテーションワークフローの状態"""
    slide_file: str
    language: str
    action: Literal["load", "next", "previous", "goto", "question"]
    slide_number: int | None
    question: str | None
    result: dict | None
    error: str | None

class PresentationWorkflow:
    """スライドプレゼンテーションワークフロー"""

    def __init__(self, slide_narrator: SlideNarrator):
        self.slide_narrator = slide_narrator
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """ワークフローグラフを構築"""
        workflow = StateGraph(PresentationState)

        # ノード追加
        workflow.add_node("load_narration", self._load_narration_node)
        workflow.add_node("next_slide", self._next_slide_node)
        workflow.add_node("previous_slide", self._previous_slide_node)
        workflow.add_node("goto_slide", self._goto_slide_node)
        workflow.add_node("answer_question", self._answer_question_node)

        # エントリーポイント
        workflow.set_entry_point("load_narration")

        # 条件付きエッジ
        workflow.add_conditional_edges(
            "load_narration",
            self._action_router,
            {
                "next": "next_slide",
                "previous": "previous_slide",
                "goto": "goto_slide",
                "question": "answer_question",
                "end": END
            }
        )

        # 各ノードから終了へ
        workflow.add_edge("next_slide", END)
        workflow.add_edge("previous_slide", END)
        workflow.add_edge("goto_slide", END)
        workflow.add_edge("answer_question", END)

        return workflow.compile()

    async def _load_narration_node(self, state: PresentationState) -> dict:
        """ナレーション読み込みノード"""
        try:
            await self.slide_narrator.load_narration(
                state['slide_file'],
                state['language']
            )
            return {"error": None}
        except Exception as e:
            return {"error": str(e)}

    async def _next_slide_node(self, state: PresentationState) -> dict:
        """次スライドノード"""
        try:
            result = await self.slide_narrator.next_slide()
            return {"result": result.__dict__, "error": None}
        except Exception as e:
            return {"error": str(e)}

    async def _previous_slide_node(self, state: PresentationState) -> dict:
        """前スライドノード"""
        try:
            result = await self.slide_narrator.previous_slide()
            return {"result": result.__dict__, "error": None}
        except Exception as e:
            return {"error": str(e)}

    async def _goto_slide_node(self, state: PresentationState) -> dict:
        """指定スライドへ移動ノード"""
        try:
            slide_number = state.get('slide_number')
            if slide_number is None:
                raise ValueError("slide_number is required for goto action")

            result = await self.slide_narrator.goto_slide(slide_number)
            return {"result": result.__dict__, "error": None}
        except Exception as e:
            return {"error": str(e)}

    async def _answer_question_node(self, state: PresentationState) -> dict:
        """質問応答ノード"""
        try:
            question = state.get('question')
            if not question:
                raise ValueError("question is required for question action")

            answer = await self.slide_narrator.answer_slide_question(question)
            return {"result": {"answer": answer}, "error": None}
        except Exception as e:
            return {"error": str(e)}

    def _action_router(self, state: PresentationState) -> str:
        """アクションに基づいてルーティング"""
        if state.get('error'):
            return "end"

        action = state.get('action', 'end')

        action_map = {
            'next': 'next',
            'previous': 'previous',
            'goto': 'goto',
            'question': 'question'
        }

        return action_map.get(action, 'end')
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] Pythonの依存パッケージを確認した（langchain, langgraph等）
- [ ] テスト環境を準備した
- [ ] ナレーションJSONファイルを確認した

### Phase 2: データ移行

- [ ] `backend/data/narrations/` ディレクトリを作成した
- [ ] ナレーションJSONファイルをコピーした
- [ ] データ構造の検証スクリプトを作成した
- [ ] 全ナレーションファイルが正しく読み込めることを確認した

### Phase 3: ツール移行

- [ ] `narration_loader.py` を作成した
- [ ] ファイル読み込み機能をテストした
- [ ] エラーハンドリングを実装した
- [ ] 単体テストを作成・通過した

### Phase 4: SlideNarrator本体

- [ ] `slide_narrator.py` を作成した
- [ ] 全メソッドを移行した（loadNarration, narrateSlide, etc.）
- [ ] キャラクターアクション決定ロジックを移行した
- [ ] 感情抽出ロジックを移行した
- [ ] 単体テストを作成・通過した

### Phase 5: 音声統合

- [ ] TextToSpeechServiceとの統合を実装した
- [ ] VoiceOutputAgentとの統合を実装した（オプション）
- [ ] CharacterControlAgentとの統合を実装した（オプション）
- [ ] リップシンク処理を実装した

### Phase 6: ワークフロー統合

- [ ] `presentation_workflow.py` を作成した
- [ ] 全アクション（load, next, previous, goto, question）を実装した
- [ ] 条件付きエッジを正しく設定した
- [ ] エンドツーエンドテストを通過した

### Phase 7: 検証

- [ ] 全ナビゲーションパターンをテストした
- [ ] 質問応答機能をテストした
- [ ] onDemand応答をテストした
- [ ] トランジションメッセージをテストした
- [ ] パフォーマンスを計測した
- [ ] ログ出力を確認した

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| JSONファイルが読み込めない | ファイルパスの不整合 | 絶対パスを使用し、`Path`オブジェクトで管理 |
| 日本語が正しく表示されない | エンコーディングの問題 | `open(..., encoding='utf-8')` を使用 |
| スライド番号がずれる | 0始まりと1始まりの混同 | スライド番号は1始まりに統一 |
| 音声生成が失敗する | TTSサービスの設定不備 | API キーとサービス設定を確認 |
| async/await エラー | 非同期処理の不整合 | 全ての呼び出し元を確認 |

### デバッグのヒント

```python
# ナレーションデータのダンプ
import json
print(json.dumps(slide_narrator.narration_data, indent=2, ensure_ascii=False))

# 現在のスライド情報を確認
slide_info = await slide_narrator.get_current_slide_info()
print(f"Current: {slide_info['currentSlide']}/{slide_info['totalSlides']}")

# キャラクターアクション決定のテスト
slide_data = narration_data['slides'][0]
action = slide_narrator._determine_character_action(slide_data)
print(f"Character action: {action}")
```

## パフォーマンス最適化

### ナレーションデータのキャッシュ

```python
from functools import lru_cache

class NarrationLoader:
    @lru_cache(maxsize=10)
    async def load(self, slide_file: str, language: str) -> Dict:
        """キャッシュ付きナレーション読み込み"""
        # ... 実装 ...
```

### 音声生成の並列化

```python
# 複数スライドの音声を事前生成
import asyncio

async def preload_audio(slide_numbers: list[int]):
    """複数スライドの音声を並列で事前生成"""
    tasks = [
        slide_narrator.narrate_slide(num)
        for num in slide_numbers
    ]
    results = await asyncio.gather(*tasks)
    return results
```

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Mastra ドキュメント](https://mastra.dev)
- [元実装: slide-narrator.ts](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/mastra/agents/slide-narrator.ts)
- [ナレーションデータ例](/Users/teradakousuke/Developer/engineer-cafe-navigator2025/frontend/src/slides/narration/engineer-cafe-ja.json)
