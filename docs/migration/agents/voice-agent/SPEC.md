# Voice Agent - 技術仕様書

> 入出力仕様・API定義・データ構造・性能要件

## 1. コンポーネント境界

- **VoiceOutputAgent**（`backend/agents/voice_output_agent.py`）：テキスト応答を TTS 用に整形し、音声を生成する責務。フェイルセーフ込み。
- **STT/TTS ツールポート**（`backend/tools/`）：`speech_to_text(audio_base64, language)`・`text_to_speech(text, language, emotion)` を提供。**TODO**: 実 I/F を確定。
- **ユーティリティ**（`backend/utils/`）：`stt_correction.py` / `emotion_tag_parser.py` / `tts_preprocess.py` / `perf.py`。
- **ワークフローノード**（`backend/workflows/main_workflow.py`）：`stt_node` / `clarify_or_route_node` / `qa_node` / `llm_fallback_node` / `emotion_and_memory_node` / `tts_node` / `character_node`。

## 2. 型・データ構造

```python
from typing import TypedDict, Literal, Optional
SupportedLanguage = Literal["ja", "en"]
SupportedEmotion = Literal["neutral", "happy", "sad", "angry", "relaxed", "surprised"]

class SpeechToTextResult(TypedDict):
    success: bool
    transcript: Optional[str]
    confidence: Optional[float]
    error: Optional[str]

class TextToSpeechResult(TypedDict):
    success: bool
    audio_bytes: Optional[bytes]
    error: Optional[str]

class VoiceOutputRequest(TypedDict):
    text: str                 # 応答テキスト（感情タグ含む可）
    language: SupportedLanguage
    emotion: Optional[str]    # ヒント（省略可）
    session_id: Optional[str]
    agent_name: Optional[str]

class VoiceOutputResponse(TypedDict):
    success: bool
    audio_bytes: Optional[bytes]
    clean_text: Optional[str]
    emotion: Optional[str]
    error: Optional[str]
```

## 3. API 仕様（入出力仕様）

### 3.1 STT ツールポート

```python
aSYNC def speech_to_text(audio_base64: str, language: SupportedLanguage) -> SpeechToTextResult
```

- **入力**：`audio_base64`（PCM/Opus などを Base64 化した文字列）、`language`。
- **出力**：`transcript`（補正前の生文字列）、`confidence`（0.0〜1.0）。
- **仕様**：`stt_correction.correct()` をワークフローノード（`stt_node`）側で適用。品質NG（`confidence < 0.6`、ノイズなど）の場合は Clarify に分岐。

### 3.2 TTS ツールポート

```python
aSYNC def text_to_speech(text: str, language: SupportedLanguage, emotion: Optional[str]) -> TextToSpeechResult
```

- **入力**：`text`（TTS向けに整形済）、`language`、`emotion`。
- **出力**：`audio_bytes`（バイト列）。失敗時は `success=False` と `error`。

### 3.3 VoiceOutputAgent

```python
aSYNC def convert_text_to_speech(req: VoiceOutputRequest) -> VoiceOutputResponse
```

- **前処理**：
  - 感情タグ解析（`emotion_tag_parser.parse`）→ `clean_text` 抽出・主要感情決定。
  - Markdown除去・略語展開（`tts_preprocess.clean`）→ 5000 bytes ハード / 4500 bytes ソフトでトランケート。
- **音声生成**：`tools.text_to_speech(clean_text, language, emotion)` 呼び出し。失敗時は謝罪文でフェイルセーフ。
- **出力**：`audio_bytes`、`clean_text`、`emotion`。

### 3.4 ストリーミング TTS（オプション）

- 文単位に分割し、各チャンクを逐次 `text_to_speech` へ。LipSync 用に `audio_bytes` を `character_node` へ伝搬。**TODO**: 実チャンク分割ロジックを Python で定義。

## 4. 前処理仕様

- **Markdown 除去**：見出し/太字/斜体/コード/リンク/リスト記号を安全に削除（過剰除去・不足除去を避ける）。
- **略語展開**：`MTG` → `ミーティング`（ja）/`meeting`（en）。単語境界で検出。
- **バイト上限**：ハード 5000 / ソフト 4500。日本語は句点（。）、英語は終止記号（.!?）で優先的に切る。

## 5. 品質・分岐仕様

- **品質チェック**（STT）：`confidence < 0.6` やノイズ・空文字・フィラー等のパターンは Clarify 分岐。聞き取り直し応答には `[surprised]` を付与。
- **言語自動切替**：検出信頼度 0.98 以上で `setLanguage`（セッション）を更新。**TODO**: Python版のしきい値設定。
- **感情語彙**：`neutral/happy/sad/angry/relaxed/surprised` を基本集合に統一。**TODO**: VRM 対応の別名マッピング。

## 6. 性能要件

- **目安**：STT ≤ 500ms、TTS ≤ 1.0s、タグ解析/補正 ≤ 10ms、総合 ≤ 2.0s。
- **計測**：各ノードで `perf.py` に開始/終了/要約を送出。**TODO**: 計測フォーマット。

## 7. ログ/エラー

- **正常系ログ**：処理経路と分岐、適用ルール/タグ、バイト長。
- **異常系ログ**：TTS/STT 失敗・品質NG理由。フェイルセーフの有無。

## 8. 参考

- Voice Agent README（責務/性能/モバイル対策）
- Router Agent の SPEC/移行ガイド（構成参照）
- TS 実装（realtime/voice-output/emotion-tag/STT-corrections/tts-preprocess）
