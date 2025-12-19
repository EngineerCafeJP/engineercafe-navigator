# Voice Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

音声入出力（STT/TTS）と、リアルタイム会話時の前後処理（品質チェック・聞き直し・感情タグ処理・TTS前処理・キャラクター制御連携）を司るコンポーネントです。</br>
Mastra/TypeScript 版では `realtime-agent.ts` が音声パイプライン全体を統括し、TTS 部分を `voice-output-agent.ts` に委譲する構成でした。</br>
LangGraph/Python 版ではこれらを **ワークフローのノード** に分割し、依存ユーティリティを Python モジュールへ移管します。</br>
テンプレートは Router Agent の移行ガイドを参照。

## 移行概要

### 現在の実装（Mastra/TypeScript）

```bash
engineer-cafe-navigator-repo/src/
├── mastra/agents/
│   ├── realtime-agent.ts        # リアルタイム音声処理かつVoice Agentメイン部分　1674行
│   └── voice-output-agent.ts    # TTS処理（前処理・長文制限・フェイルセーフ）　228行
├── lib/
│   ├── stt-correction.ts        # STT誤認識補正（正則化＋置換）　281行
│   └── emotion-tag-parser.ts    # 感情タグ解析・付与（タグ抽出・クリーン化）　203行
└── utils/
    ├── emotion-manager.ts       # 感情推定・VRM表情マッピング　399行
    ├── performance-monitor.ts   # 処理時間計測ユーティリティ　44行
    └── tts-preprocess.ts        # TTS前処理（略語「MTG」→「ミーティング/meeting」など）、4行
```

- `realtime-agent.ts`：STT→補正→品質チェック→聞き取り直し→QA/RAG→LLM→感情解析→メモリ保存→TTS→キャラクター制御までの一貫処理を持つリアルタイム音声エージェント。ストリーミングTTSやリップシンクも実装。
- `voice-output-agent.ts`：感情タグ解析とMarkdown除去、略語展開（TTS前処理）、文字数上限のトランケート、TTS呼び出し、失敗時のフェイルセーフ（謝罪文のTTS）を提供。
- `emotion-tag-parser.ts`：`[emotion[:intensity]]` タグの抽出・正規化・主要感情決定、VRM表情マッピング補助。
- `stt-corrections.ts`：日本語/英語の誤認補正ルール群と適用ユーティリティ、品質指標・統計。
- `tts-preprocess.ts`：略語 MTG → ミーティング/meeting などの軽量前処理。

### 移行先（LangGraph/Python）

以下のバックエンド構成に合わせます（必要に応じて追加モジュールやファイルは後で補填します）。

```bash
backend/
├── main.py                 # FastAPIアプリケーション
├── agents/                 # LangGraphエージェント
│   ├── __init__.py
│   ├── router_agent.py
│   ├── business_info_agent.py
│   └── ...
├── workflows/              # LangGraphワークフロー
│   ├── __init__.py
│   └── main_workflow.py
├── tools/                  # エージェントツール
│   ├── __init__.py
│   └── ...
├── models/                 # データモデル
│   ├── __init__.py
│   └── ...
├── utils/                  # ユーティリティ
│   ├── __init__.py
│   └── ...
└── tests/                  # テスト
    └── ...
```

> **方針**</br>
`realtime-agent.ts` に内包されていた処理を、LangGraph の **ノード** と **ツール/ユーティリティ** に分割して移管します。</br>
Router Agent の移行ガイドの構成・粒度を基準にします。

ファイル構成の予定

```bash
backend/
├── agents/
│   ├── voice_output_agent.py        # 新規　VoiceOutputAgent相当（TTS前処理・長文制約・フェイルセーフ）
│   └── voice_orchestrator.py        # 新規　司令塔（必要なら作成、もしくはworkflowsへ直実装）
├── tools/
│   ├── stt_port.py                  # 新規　STTサービスポート（speech_to_text）
│   ├── tts_port.py                  # 新規　TTSサービスポート（text_to_speech）
│   ├── qa_service.py                # 新規　QA/RAG呼び出しアダプタ
│   ├── memory_facade.py             # 新規　Shared/Simplified/Supabaseの統合
│   └── character_control.py         # 新規　キャラクター制御アダプタ
├── utils/
│   ├── stt_correction.py            # 移管　STT補正
│   ├── emotion_tag_parser.py        # 移管　感情タグ解析
│   ├── emotion_manager.py           # 移管　感情推定／VRMマッピング
│   ├── tts_preprocess.py            # 移管　TTS前処理
│   └── perf.py                      # 移管　計測ユーティリティ
└── workflows/
    └── main_workflow.py             # 移管、一部修正　LangGraphワークフロー（ノード追加・統合）
```

## 移行ステップ

### Step 1: 依存ユーティリティの Python への移管

- **STT 補正**：`src/lib/stt-corrections.ts` → `backend/utils/stt_correction.py`
  - 誤認補正ルール群の移植（文脈条件付き置換/正規表現）と補助指標（誤認疑い検知・自信度微調整・統計）。
- **Emotion Tag Parser**：`src/lib/emotion-tag-parser.ts` → `backend/utils/emotion_tag_parser.py`
  - タグ抽出・強度・主要感情・VRM対応の表情マッピング補助の移植。
- **TTS 前処理**：`src/utils/tts-preprocess.ts` → `backend/utils/tts_preprocess.py`
  - 略語 MTG の展開などの軽量前処理。
- **Performance Monitor**：`src/lib/performance-monitor.ts`（または同等の計測）→ `backend/utils/perf.py`
  - 処理開始/終了と要約ログ。**TODO**: 既存計測API/仕様に合わせて関数名・出力形式を確定。

> *注意*：Voice Agent README の記載に基づき、モバイルブラウザでの音声再生制約（自動再生/ユーザー操作）に関わる補助モジュールは `utils/` または `tools/` 配下に後日移管。

#### 1.1 STT Correction の移行

**元**： `src/lib/stt-correction.ts` → **先**： `backend/utils/stt_correction.py`

- 正規表現パターン／前後処理（空白正規化・句読点補正）を Python に移植。

```python
# backend/utils/stt_correction.py（骨子）
import re

def correct(text: str) -> str:
    if not text: return text
    corrected = text
    # 代表例：エンジニアカフェ／サイノカフェ／Wi-Fi
    corrected = re.sub(r"engineer\s*(cafe|coffee|wall)", "エンジニアカフェ", corrected, flags=re.I)
    corrected = re.sub(r"(wife\s*i|why\s*fi|y\s*fi)", "Wi-Fi", corrected, flags=re.I)
    # ...（全文はTSのパターン群を移植）
       corrected = re.sub(r"\s+", " ", corrected).strip()
```

#### 1.2 Emotion Tag Parser の移行

**元**： `src/lib/emotion-tag-parser.ts` → **先**： `backend/utils/emotion_tag_parser.py`

- タグ抽出・クリーン化・主感情決定のロジックを Python 化。

#### 1.3 TTS Preprocess の移行

**元**： `src/utils/tts-preprocess.ts` → **先**： `backend/utils/tts_preprocess.py`

- MTG→ミーティング等の前処理を Python に移植。

#### 1.4 Performance Monitor の移行

**元**： `src/utils/performance-monitor.ts` → **先**： `backend/utils/perf.py`

- 計測開始/終了/要約のインターフェースを Python で提供。

#### 1.5 Emotion Manager の移行

**元**： `src/utils/emotion-manager.ts` → **先**： `backend/utils/emotion_manager.py`

- キーワードスコアリングでの推定、VRM表情マッピング、遷移イージングの基本方針を Python へ。

### Step 2: VoiceOutputAgent 本体の移行

**元ファイル**: `src/mastra/agents/voice-output-agent.ts`
**先ファイル**: `backend/agents/voice_output_agent.py`

- **責務**：
  1) 感情タグ解析（`emotion_tag_parser.parse`）
  2) Markdown等の体裁除去（TTS向けクリーニング）
  3) 略語展開などの TTS 前処理（`tts_preprocess.clean` 等）
  4) 文字数（byte）上限でトランケート（ハード: 5000 / ソフト: 4500 を推奨）
  5) TTS ポート呼び出し（`tools/text_to_speech`）
  6) 失敗時のフェイルセーフ（謝罪文の TTS）

```python
# backend/agents/voice_output_agent.py（骨子）
from backend.utils.emotion_tag_parser import parse
from backend.utils.tts_preprocess import clean, truncate_bytes
from backend.tools.tts_port import text_to_speech  # TODO: 実際の配置名に合わせる

async def convert_text_to_speech(text: str, language: str, emotion_hint: str | None = None) -> dict:
    parsed = parse(text)  # clean_text, emotions[], primary_emotion
    tts_text = clean(parsed["clean_text"], language)
    tts_text = truncate_bytes(tts_text, max_bytes=5000, soft_limit=4500)
    emotion = emotion_hint or (parsed.get("primary_emotion") or "neutral")
    res = await text_to_speech(tts_text, language, emotion)
    if not res.get("success"):
        # フェイルセーフ：謝罪メッセージのTTS
        fb_text = "申し訳ございません。音声の生成に失敗しました。" if language == "ja" else "I apologize, but I failed to generate the audio response."
        fb = await text_to_speech(fb_text, language, "sad")
        return {"success": fb.get("success", False), "audio_bytes": fb.get("audio_bytes", b""), "emotion": "sad", "clean_text": parsed.get("clean_text", "")}
    return {"success": True, "audio_bytes": res["audio_bytes"], "emotion": emotion, "clean_text": parsed.get("clean_text", "")}
```

- **根拠**：既存 TS の `VoiceOutputAgent` の設計（タグ解析→前処理→長文対策→TTS→フェイルセーフ）を踏襲。

### Step 3: RealtimeAgent 音声パイプラインの分割移行

**元ファイル**: `src/mastra/agents/realtime-agent.ts`

現状の `realtime-agent.ts` は 1 クラスが音声パイプラインのすべてを担っています。</br>
LangGraph では下記の **ノード分割**を行い、`workflows/main_workflow.py` に統合します。

- **stt_node**：ArrayBuffer/Base64 → STT → `stt_correction.correct` → 品質チェック（自信度・ノイズ） → 言語候補検出。
- **clarify_or_route_node**：品質 NG の場合、聞き取り直し応答（感情タグ `[surprised]` 等）を生成して TTS。品質 OK の場合 Router/QA へ進む。
- **qa_node**：RAG/QA を優先して回答取得（空なら LLM フォールバック）。**TODO**: 既存 QA 呼び出しの Python 版 I/F を確定。
- **llm_fallback_node**：LLM 応答生成＋`emotion_tag_parser` によるタグ付与。
- **emotion_and_memory_node**：`emotion_manager` による感情推定、Shared/Simplified/Supabase への保存、言語自動切替（信頼度 0.98 以上）。**TODO**: メモリファサードの I/F を確定。
- **tts_node**：`convert_text_to_speech` を呼び出して音声生成（フェイルセーフあり）。
- **character_node**：音声・感情に基づく表情/リップシンク生成（VRM 連携）。**TODO**: 連携仕様を Python 側で定義。

### Step 4: ワークフローへの統合

Router Agent の移行ガイドと同様に、ノード群を `main_workflow.py` に追加し、</br>
条件分岐で Clarify→TTS / QA→LLM→Emotion/Mem→TTS→Character→Format の順に接続します。

```python
# workflows/main_workflow.py（例）
# TODO: 既存 main_workflow の構造に合わせて補正
from langgraph.graph import StateGraph, START, END  # 実際のAPIに合わせて修正

g = StateGraph(WorkflowState)
g.add_node("stt", stt_node)
g.add_node("clarify_or_route", clarify_or_route_node)
g.add_node("qa", qa_node)
g.add_node("llm_fallback", llm_fallback_node)
g.add_node("emotion_and_memory", emotion_and_memory_node)
g.add_node("tts", tts_node)
g.add_node("character", character_node)

g.add_edge(START, "stt")
g.add_edge("stt", "clarify_or_route")
g.add_conditional_edges(
    "clarify_or_route",
    lambda s: "tts" if s["stt_quality"] and not s["stt_quality"]["is_valid"] else "qa",
    {"tts": "tts", "qa": "qa"}
)
g.add_edge("qa", "llm_fallback")
g.add_edge("llm_fallback", "emotion_and_memory")
g.add_edge("emotion_and_memory", "tts")
g.add_edge("tts", "character")
g.add_edge("character", END)
```

## 移行チェックリスト

- [ ] ユーティリティ移管（`stt_correction.py` / `emotion_tag_parser.py` / `tts_preprocess.py` / `perf.py`）
- [ ] VoiceOutputAgent 移管（`agents/voice_output_agent.py`）
- [ ] `realtime-agent.ts` のノード分割設計・実装
- [ ] `workflows/main_workflow.py` への統合（条件分岐の正当性）
- [ ] TTS 長文対策（5000 bytes ハード / 4500 ソフト）
- [ ] モバイル音声制約への対応（ユーザー操作待ち処理など）
- [ ] ログと計測（STT ≤ 500ms / TTS ≤ 1.0s / タグ解析・補正 ≤ 10ms / 総合 ≤ 2.0s の目安）

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|---|---|---|
| STTの文字化け/空文字 | Base64 変換や STT ポート I/Fの不整合 | `audio_base64` のエンコード/デコードを見直し、</br>STTポートの仕様（`speech_to_text`）に合わせる。</br>**TODO**: Python側のI/F確定。 |
| 品質NGが過剰に発生 | しきい値/正規化不十分 | `stt_correction` 適用順序を早め、</br>`checkSpeechQuality` 相当の閾値（confidence等）を調整。 |
| TTSが5000 bytes超過で失敗 | 長文対策未適用 | `truncate_bytes` を必ず適用し、末尾に省略文言を追加。 |
| 感情タグが反映されない | タグ正規化の差異 | `emotion_tag_parser` のパターンを TS と同等に移植し、未タグ時は適切な既定感情を付与。 |
| キャラクターが音声と同期しない | リップシンク生成漏れ | `character_node` に `audio_bytes` を確実に渡し、VRMマッピングの重み計算を調整。**TODO**: Python側で仕様定義。 |
| 計測ログが散在 | 計測責務が曖昧 | 各ノードから `perf.py` を呼び、処理時間・合計の要約を出力。</br>**TODO**: 計測出力のフォーマット確定。

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Mastra ドキュメント](https://mastra.dev)
- Router Agent の移行ガイド（構成・粒度の参照）
- Voice Agent README（責務境界・性能目標・モバイル対策）
- 現行 TS 実装：`realtime-agent.ts` / `voice-output-agent.ts` / `emotion-tag-parser.ts` / `stt-corrections.ts` / `tts-preprocess.ts`（移管元）
